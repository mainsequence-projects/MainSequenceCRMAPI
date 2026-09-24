from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from ...contracts import validate_payload
from ...models.queries import QueryScope
from ..errors import ResourceConflict
from ..resources.catalog import ORDER_COLUMNS
from .base import TransferBase, _counts, _json_value, _summary

TERMINAL_STATES = {"succeeded", "cancelled", "expired"}
RETRYABLE_STATES = {"partial", "failed"}


class TransferJobs(TransferBase):
    def transfers(self, actor_uid: uuid.UUID, scope: QueryScope) -> dict[str, Any]:
        table = self._table("transfer_job")
        clauses: list[str] = []
        parameters: dict[str, Any] = {}
        if scope.filters.get("mine", True):
            clauses.append("initiator_uid=%(actor_uid)s::uuid")
            parameters["actor_uid"] = str(actor_uid)
        for key in ("direction", "status"):
            if key in scope.filters:
                clauses.append(f"{key}=%({key})s")
                parameters[key] = scope.filters[key]
        if scope.search:
            clauses.append("lower(coalesce(input_manifest->>'display_name','')) LIKE %(search)s")
            parameters["search"] = f"%{scope.search.casefold()}%"
        direction = "DESC" if (scope.ordering or "-created_at").startswith("-") else "ASC"
        try:
            order = ORDER_COLUMNS["transfers"][(scope.ordering or "-created_at").removeprefix("-")]
        except KeyError as exc:
            raise ValueError("Unsupported transfer ordering") from exc
        parameters.update(
            {"page_size": scope.page_size, "page_offset": scope.page_index * scope.page_size}
        )
        result = self._operation(
            operation="select",
            sql=(
                f'WITH q AS (SELECT * FROM "{table}" WHERE {" AND ".join(clauses) if clauses else "TRUE"}), '
                f"paged AS (SELECT *, row_number() OVER () AS __row FROM q ORDER BY {order} {direction}, q.uid {direction} "
                "LIMIT %(page_size)s::integer OFFSET %(page_offset)s::integer) "
                "SELECT COALESCE((SELECT jsonb_agg(jsonb_build_object("
                "'uid',uid,'direction',direction,'status',status,'mapping_revision',mapping_revision,"
                "'plan_hash',plan_hash,'counts',COALESCE(validation_report->'counts','{}'::jsonb),"
                "'cancel_requested',cancel_requested,'created_at',created_at,'updated_at',updated_at) "
                "ORDER BY __row) FROM paged), '[]'::jsonb) AS items, (SELECT count(*) FROM q) AS total_items"
            ),
            parameters=parameters,
            parameter_types={key: "string" for key in parameters},
            tables={"transfer_job": "read"},
            max_rows=1,
        )
        row = result["rows"][0]
        items = [_summary(item) for item in _json_value(row.get("items"), list, "transfers")]
        total = int(row.get("total_items", 0))
        return {
            "items": items,
            "pageInfo": {
                "pageIndex": scope.page_index,
                "pageSize": scope.page_size,
                "totalItems": total,
                "hasNextPage": (scope.page_index + 1) * scope.page_size < total,
                "hasPreviousPage": scope.page_index > 0,
            },
        }

    def transfer_detail(self, job_uid: uuid.UUID, actor_uid: uuid.UUID) -> dict[str, Any]:
        return _summary(self._job_row(job_uid, actor_uid))

    def create_import(
        self,
        actor_uid: uuid.UUID,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        data = validate_payload("CreateImport", payload)
        job = self._table("transfer_job")
        connection = self._table("source_connection")
        uid = uuid.uuid4()
        manifest = {"display_name": data["display_name"], "entity_type": data["entity_type"]}
        result = self._operation(
            operation="insert",
            sql=(
                f'INSERT INTO "{job}" (uid, created_at, updated_at, created_by_uid, updated_by_uid, '
                "version, direction, adapter_id, source_connection_uid, initiator_uid, status, input_manifest, mapping, "
                "mapping_revision, plan_hash, validation_report, cancel_requested, lease_epoch) "
                f"SELECT %(uid)s::uuid, NOW(), NOW(), %(actor_uid)s::uuid, %(actor_uid)s::uuid, "
                "1, 'import', %(adapter_id)s, %(source_connection_uid)s::uuid, %(actor_uid)s::uuid, 'uploading', "
                "%(manifest)s::jsonb, '{}'::jsonb, 1, NULL, %(report)s::jsonb, false, 0 "
                f'FROM "{connection}" c WHERE c.uid=%(source_connection_uid)s::uuid '
                "AND c.adapter_id=%(adapter_id)s "
                "RETURNING *"
            ),
            parameters={
                "actor_uid": str(actor_uid),
                "uid": str(uid),
                "adapter_id": data["adapter_id"],
                "source_connection_uid": data["source_connection_uid"],
                "manifest": json.dumps(manifest),
                "report": json.dumps({"counts": _counts({})}),
            },
            parameter_types={
                "uid": "uuid",
                "adapter_id": "string",
                "source_connection_uid": "uuid",
                "manifest": "jsonb",
                "report": "jsonb",
            },
            tables={
                "transfer_job": "write",
                "source_connection": "read",
            },
            max_rows=1,
        )
        return _summary(self._changed_row(result))

    def stage_upload(
        self,
        actor_uid: uuid.UUID,
        job_uid: uuid.UUID,
        filename: str,
        content_type: str,
        digest: str,
        rows: list[dict[str, Any]],
        entity_type: str,
    ) -> dict[str, Any]:
        job_row = self._job_row(job_uid, actor_uid)
        if job_row["direction"] != "import" or job_row["status"] not in {
            "uploading",
            "staged",
            "needs_mapping",
            "validated",
        }:
            raise ResourceConflict("Transfer does not accept an upload in its current state")
        job = self._table("transfer_job")
        transfer_row = self._table("transfer_row")
        staged = []
        for ordinal, payload in enumerate(rows):
            row_type = str(payload.get("__entity_type", entity_type))
            canonical = json.dumps(
                payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            )
            external_id = (
                payload.get("source_id", payload.get("id")) if isinstance(payload, dict) else None
            )
            staged.append(
                {
                    "uid": str(uuid.uuid5(job_uid, f"{row_type}:{ordinal}")),
                    "entity_type": row_type,
                    "ordinal": ordinal,
                    "external_id": None if external_id is None else str(external_id),
                    "raw_payload": payload,
                    "raw_hash": hashlib.sha256(canonical.encode()).hexdigest(),
                }
            )
        manifest = _json_value(job_row.get("input_manifest") or {}, dict, "input manifest")
        manifest.update(
            {
                "filename": filename[:255],
                "content_type": content_type[:255],
                "sha256": digest,
                "rows": len(staged),
            }
        )
        result = self._operation(
            operation="update",
            sql=(
                f'WITH gate AS (SELECT j.uid FROM "{job}" AS j WHERE '
                "j.uid=%(job_uid)s::uuid AND j.initiator_uid=%(actor_uid)s::uuid "
                "AND j.version=%(expected_version)s::bigint "
                "AND j.status IN ('uploading','staged','needs_mapping','validated') FOR UPDATE), "
                f'cleared AS (DELETE FROM "{transfer_row}" AS r USING gate WHERE '
                "r.job_uid=gate.uid RETURNING r.uid), staged AS ("
                f'INSERT INTO "{transfer_row}" AS r (uid, job_uid, entity_type, ordinal, external_id, raw_payload, '
                "raw_hash, state, errors, warnings, attempts, created_at, updated_at) "
                "SELECT x.uid::uuid, gate.uid, x.entity_type, x.ordinal, x.external_id, "
                "x.raw_payload, x.raw_hash, 'staged', '[]'::jsonb, '[]'::jsonb, 0, NOW(), NOW() "
                "FROM gate CROSS JOIN (SELECT count(*) FROM cleared) prior "
                "CROSS JOIN jsonb_to_recordset(%(rows)s::jsonb) AS x(uid text, entity_type text, ordinal bigint, external_id text, raw_payload jsonb, raw_hash text) RETURNING r.uid) "
                f"UPDATE \"{job}\" AS j SET status='staged', "
                "input_manifest=%(manifest)s::jsonb, mapping='{}'::jsonb, "
                "mapping_revision=mapping_revision+1, plan_hash=NULL, "
                "validation_report=%(report)s::jsonb, updated_at=NOW(), "
                "updated_by_uid=%(actor_uid)s::uuid, version=version+1 "
                "FROM gate CROSS JOIN (SELECT count(*) FROM staged) staged_count "
                "WHERE j.uid=gate.uid AND j.version=%(expected_version)s::bigint RETURNING j.*"
            ),
            parameters={
                "actor_uid": str(actor_uid),
                "job_uid": str(job_uid),
                "expected_version": int(job_row["version"]),
                "rows": json.dumps(staged),
                "manifest": json.dumps(manifest),
                "report": json.dumps({"counts": {**_counts({}), "total": len(staged)}}),
            },
            parameter_types={
                "job_uid": "uuid",
                "rows": "jsonb",
                "manifest": "jsonb",
                "report": "jsonb",
            },
            tables={
                "transfer_job": "write",
                "transfer_row": "write",
            },
            max_rows=1,
        )
        return _summary(self._changed_row(result))

    def save_mapping(
        self,
        actor_uid: uuid.UUID,
        job_uid: uuid.UUID,
        mapping: dict[str, Any],
    ) -> dict[str, Any]:
        job = self._table("transfer_job")
        result = self._operation(
            operation="update",
            sql=(
                f'UPDATE "{job}" AS j SET mapping=%(mapping)s::jsonb, mapping_revision=mapping_revision+1, '
                "status='needs_mapping', plan_hash=NULL, validation_report=jsonb_build_object('counts', "
                "COALESCE(validation_report->'counts','{}'::jsonb)), updated_at=NOW(), updated_by_uid=%(actor_uid)s::uuid, "
                "version=version+1 WHERE j.uid=%(job_uid)s::uuid "
                "AND j.initiator_uid=%(actor_uid)s::uuid AND j.direction='import' AND j.status IN ('staged','needs_mapping','validated') RETURNING j.*"
            ),
            parameters={
                "actor_uid": str(actor_uid),
                "mapping": json.dumps(mapping),
                "job_uid": str(job_uid),
            },
            parameter_types={"mapping": "jsonb", "job_uid": "uuid"},
            tables={"transfer_job": "write"},
            max_rows=1,
        )
        return _summary(self._changed_row(result))

    def commit_import(
        self,
        actor_uid: uuid.UUID,
        job_uid: uuid.UUID,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        command = validate_payload("ImportCommitRequest", payload)
        row = self._job_row(job_uid, actor_uid)
        if (
            row.get("plan_hash") != command["plan_hash"]
            or int(row["mapping_revision"]) != command["mapping_revision"]
        ):
            raise ResourceConflict("The sealed import plan is stale")
        counts = _counts(
            _json_value(row.get("validation_report") or {}, dict, "validation report").get("counts")
        )
        if command["mode"] == "strict" and counts["blocked"]:
            raise ResourceConflict("Strict import cannot start while rows are blocked")
        return self._transition(
            actor_uid,
            job_uid,
            {"validated", "needs_mapping"},
            "queued",
            cancel=False,
        )

    def cancel(
        self,
        actor_uid: uuid.UUID,
        job_uid: uuid.UUID,
    ) -> dict[str, Any]:
        row = self._job_row(job_uid, actor_uid)
        if row["status"] in TERMINAL_STATES:
            return _summary(row)
        if row["status"] in {"queued", "uploading", "staged", "needs_mapping", "validated"}:
            return self._transition(
                actor_uid,
                job_uid,
                {row["status"]},
                "cancelled",
                cancel=True,
            )
        return self._transition(
            actor_uid,
            job_uid,
            {"running", "partial", "failed"},
            row["status"],
            cancel=True,
        )

    def retry(
        self,
        actor_uid: uuid.UUID,
        job_uid: uuid.UUID,
    ) -> dict[str, Any]:
        return self._transition(
            actor_uid,
            job_uid,
            RETRYABLE_STATES,
            "queued",
            cancel=False,
        )

    def _transition(
        self,
        actor_uid: uuid.UUID,
        job_uid: uuid.UUID,
        allowed: set[str],
        status: str,
        *,
        cancel: bool,
    ) -> dict[str, Any]:
        job = self._table("transfer_job")
        result = self._operation(
            operation="update",
            sql=(
                f'UPDATE "{job}" AS j SET status=%(status)s, cancel_requested=%(cancel)s::boolean, '
                "lease_holder=NULL, lease_expires_at=NULL, updated_at=NOW(), updated_by_uid=%(actor_uid)s::uuid, "
                "version=version+1 WHERE j.uid=%(job_uid)s::uuid "
                "AND j.initiator_uid=%(actor_uid)s::uuid AND j.status = ANY(SELECT jsonb_array_elements_text(%(allowed)s::jsonb)) RETURNING j.*"
            ),
            parameters={
                "actor_uid": str(actor_uid),
                "status": status,
                "cancel": cancel,
                "job_uid": str(job_uid),
                "allowed": json.dumps(sorted(allowed)),
            },
            parameter_types={
                "status": "string",
                "cancel": "boolean",
                "job_uid": "uuid",
                "allowed": "jsonb",
            },
            tables={"transfer_job": "write"},
            max_rows=1,
        )
        return _summary(self._changed_row(result))
