from __future__ import annotations

import json
import uuid
from typing import Any

from ...contracts import validate_payload
from ...portability.planning import assess_staged_rows, sealed_plan_hash
from ..errors import ResourceConflict
from .base import TransferBase, _counts, _json_value


class ImportPlanning(TransferBase):
    def validate_import(self, actor_uid: uuid.UUID, job_uid: uuid.UUID) -> dict[str, Any]:
        job_row = self._job_row(job_uid, actor_uid)
        mapping = _json_value(job_row.get("mapping") or {}, dict, "mapping")
        if not mapping:
            raise ResourceConflict("Save an import mapping before validation")
        row_table = self._table("transfer_row")
        result = self._operation(
            operation="select",
            sql=(
                f'SELECT uid, entity_type, ordinal, raw_hash, raw_payload FROM "{row_table}" WHERE job_uid=%(job_uid)s::uuid ORDER BY ordinal, uid'
            ),
            parameters={"job_uid": str(job_uid)},
            parameter_types={"job_uid": "uuid"},
            tables={"transfer_row": "read"},
            max_rows=20000,
        )
        rows = [
            {**row, "raw_payload": _json_value(row.get("raw_payload"), dict, "staged row")}
            for row in result.get("rows") or []
        ]
        issues, decisions = assess_staged_rows(rows)
        input_sha256 = _json_value(job_row.get("input_manifest") or {}, dict, "input manifest").get(
            "sha256"
        )
        plan_hash = sealed_plan_hash(input_sha256, mapping, int(job_row["mapping_revision"]), rows)
        counts = _counts(
            {
                "total": len(rows),
                "valid": sum(item["state"] == "valid" for item in decisions),
                "blocked": sum(item["state"] == "blocked" for item in decisions),
            }
        )
        report = {"counts": counts, "issues": issues[:200], "has_more_issues": len(issues) > 200}
        job = self._table("transfer_job")
        updated = self._operation(
            operation="update",
            sql=(
                f'WITH gate AS (SELECT j.uid FROM "{job}" AS j WHERE '
                "j.uid=%(job_uid)s::uuid AND j.initiator_uid=%(actor_uid)s::uuid "
                "AND j.version=%(expected_version)s::bigint FOR UPDATE), "
                f'changed_rows AS (UPDATE "{row_table}" r SET state=x.state, errors=x.errors, '
                "warnings=x.warnings, updated_at=NOW() FROM gate CROSS JOIN "
                "jsonb_to_recordset(%(decisions)s::jsonb) AS x(uid text, state text, errors jsonb, warnings jsonb) "
                "WHERE r.job_uid=gate.uid AND r.uid=x.uid::uuid RETURNING r.uid) "
                f'UPDATE "{job}" AS j SET status=%(status)s, '
                "plan_hash=%(plan_hash)s, validation_report=%(report)s::jsonb, "
                "updated_at=NOW(), updated_by_uid=%(actor_uid)s::uuid, version=version+1 "
                "FROM gate CROSS JOIN (SELECT count(*) FROM changed_rows) changed_count "
                "WHERE j.uid=gate.uid AND j.version=%(expected_version)s::bigint RETURNING j.*"
            ),
            parameters={
                "actor_uid": str(actor_uid),
                "expected_version": int(job_row["version"]),
                "decisions": json.dumps(decisions),
                "job_uid": str(job_uid),
                "status": "validated" if counts["blocked"] == 0 else "needs_mapping",
                "plan_hash": plan_hash,
                "report": json.dumps(report),
            },
            parameter_types={
                "decisions": "jsonb",
                "job_uid": "uuid",
                "status": "string",
                "plan_hash": "string",
                "report": "jsonb",
            },
            tables={
                "transfer_row": "write",
                "transfer_job": "write",
            },
            max_rows=1,
        )
        self._changed_row(updated)
        return self.plan(actor_uid, job_uid)

    def plan(self, actor_uid: uuid.UUID, job_uid: uuid.UUID) -> dict[str, Any]:
        row = self._job_row(job_uid, actor_uid)
        if row["direction"] != "import" or not row.get("plan_hash"):
            raise ResourceConflict("Import has no sealed validation plan")
        report = _json_value(row.get("validation_report") or {}, dict, "validation report")
        payload = {
            "job_uid": str(row["uid"]),
            "plan_hash": row["plan_hash"],
            "mapping_revision": int(row["mapping_revision"]),
            "can_commit": _counts(report.get("counts"))["valid"] > 0
            and _counts(report.get("counts"))["blocked"] == 0,
            "counts": _counts(report.get("counts")),
            "issues": report.get("issues", [])[:200],
            "has_more_issues": bool(report.get("has_more_issues", False)),
        }
        return validate_payload("TransferPlan", payload)
