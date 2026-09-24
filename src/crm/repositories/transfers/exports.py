from __future__ import annotations

import json
import uuid
from typing import Any

from ...contracts import validate_payload
from ...metatables import MODELS
from ...portability.exporting import export_entity_names, export_record_key, package_export
from .base import TransferBase, _json_value, _summary


class TransferExports(TransferBase):
    def create_export(
        self,
        actor_uid: uuid.UUID,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        data = validate_payload("CreateExport", payload)
        job_uid = uuid.uuid4()
        entity_names = export_entity_names(data["entity_type"])
        records: dict[str, list] = {}
        for name in entity_names:
            table = self._table(name)
            archived = (
                ""
                if data["include_archived"] or "archived_at" not in MODELS[name].__table__.columns
                else " AND archived_at IS NULL"
            )
            result = self._operation(
                operation="select",
                sql=f'SELECT to_jsonb(t) AS item FROM "{table}" t WHERE TRUE{archived} ORDER BY uid',
                parameters={},
                parameter_types={},
                tables={name: "read"},
                max_rows=20000,
            )
            records[export_record_key(name)] = [
                _json_value(row["item"], dict, "export row") for row in result.get("rows") or []
            ]
        if "contact" in entity_names:
            affiliation = "contact_company_affiliation"
            table = self._table(affiliation)
            archived = "" if data["include_archived"] else " AND a.archived_at IS NULL"
            result = self._operation(
                operation="select",
                sql=(
                    f'SELECT to_jsonb(a) AS item FROM "{table}" a '
                    f"WHERE TRUE{archived} ORDER BY a.uid"
                ),
                parameters={},
                parameter_types={},
                tables={affiliation: "read"},
                max_rows=20000,
            )
            exported_contacts = {str(row["uid"]) for row in records["contacts"]}
            affiliations = [
                _json_value(row["item"], dict, "affiliation export row")
                for row in result.get("rows") or []
            ]
            affiliations = [
                row for row in affiliations if str(row["contact_uid"]) in exported_contacts
            ]
            if data["format"] == "portable-json":
                records["contact_company_affiliations"] = affiliations
            else:
                by_contact: dict[str, list[dict[str, Any]]] = {}
                for row in affiliations:
                    by_contact.setdefault(str(row["contact_uid"]), []).append(row)
                for contact_row in records["contacts"]:
                    contact_row["affiliations"] = by_contact.get(str(contact_row["uid"]), [])
        manifest, counts = package_export(data, records)
        job = self._table("transfer_job")
        result = self._operation(
            operation="insert",
            sql=(
                f"INSERT INTO \"{job}\" (uid, created_at, updated_at, created_by_uid, updated_by_uid, version, direction, adapter_id, source_connection_uid, initiator_uid, status, input_manifest, mapping, mapping_revision, plan_hash, validation_report, cancel_requested, lease_epoch, output_manifest) VALUES (%(uid)s::uuid,NOW(),NOW(),%(actor_uid)s::uuid,%(actor_uid)s::uuid,1,'export','mainsequence-portable-v1',NULL,%(actor_uid)s::uuid,'succeeded',%(input)s::jsonb,'{{}}'::jsonb,1,NULL,%(report)s::jsonb,false,0,%(output)s::jsonb) RETURNING *"
            ),
            parameters={
                "uid": str(job_uid),
                "actor_uid": str(actor_uid),
                "input": json.dumps(data),
                "report": json.dumps({"counts": counts}),
                "output": json.dumps(manifest, default=str),
            },
            parameter_types={
                "uid": "uuid",
                "actor_uid": "uuid",
                "input": "jsonb",
                "report": "jsonb",
                "output": "jsonb",
            },
            tables={"transfer_job": "write"},
            max_rows=1,
        )
        return _summary(result["rows"][0])
