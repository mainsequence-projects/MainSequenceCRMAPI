from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from ...contracts import validate_payload
from ...metatables import MODELS
from ..errors import ResourceConflict, ResourceNotFound
from ..gateway import GovernedGateway

COUNT_KEYS = ("total", "valid", "blocked", "committed", "skipped", "failed")


def _json_value(value: Any, expected: type, label: str) -> Any:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"CRM {label} contains invalid JSON") from exc
    if not isinstance(value, expected):
        raise RuntimeError(f"CRM {label} has an invalid shape")
    return value


def _counts(value: Any) -> dict[str, int]:
    raw = _json_value(value or {}, dict, "transfer counts")
    return {key: int(raw.get(key, 0)) for key in COUNT_KEYS}


def _summary(row: dict[str, Any]) -> dict[str, Any]:
    report = _json_value(row.get("validation_report") or {}, dict, "validation report")
    payload = {
        "uid": str(row["uid"]),
        "direction": row["direction"],
        "status": row["status"],
        "mapping_revision": int(row["mapping_revision"]),
        "plan_hash": row.get("plan_hash"),
        "counts": _counts(report.get("counts", {})),
        "cancel_requested": bool(row.get("cancel_requested", False)),
        "created_at": row["created_at"].isoformat()
        if isinstance(row["created_at"], datetime)
        else row["created_at"],
        "updated_at": row["updated_at"].isoformat()
        if isinstance(row["updated_at"], datetime)
        else row["updated_at"],
    }
    return validate_payload("TransferSummary", payload)


class TransferBase(GovernedGateway):
    @staticmethod
    def _table(name: str) -> str:
        return MODELS[name].__tablename__

    @staticmethod
    def _changed_row(result: dict[str, Any]) -> dict[str, Any]:
        rows = result.get("rows")
        if not isinstance(rows, list) or len(rows) != 1:
            raise ResourceConflict("Transfer command precondition failed")
        return rows[0]

    def _job_row(self, job_uid: uuid.UUID, actor_uid: uuid.UUID) -> dict[str, Any]:
        job = self._table("transfer_job")
        result = self._operation(
            operation="select",
            sql=(
                f'SELECT * FROM "{job}" WHERE uid=%(job_uid)s::uuid '
                "AND initiator_uid=%(actor_uid)s::uuid LIMIT 1"
            ),
            parameters={
                "job_uid": str(job_uid),
                "actor_uid": str(actor_uid),
            },
            parameter_types={"job_uid": "uuid", "actor_uid": "uuid"},
            tables={"transfer_job": "read"},
            max_rows=1,
        )
        rows = result.get("rows")
        if not isinstance(rows, list) or not rows:
            raise ResourceNotFound("Transfer not found")
        return rows[0]
