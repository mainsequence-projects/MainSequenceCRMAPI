from __future__ import annotations

import uuid
from typing import Any

from ...contracts import validate_payload
from ...portability.exporting import render_error_csv, render_export
from ..errors import ResourceConflict
from .base import TransferBase, _json_value


class TransferReports(TransferBase):
    def issues(
        self,
        actor_uid: uuid.UUID,
        job_uid: uuid.UUID,
        page_index: int,
        page_size: int,
    ) -> dict[str, Any]:
        self._job_row(job_uid, actor_uid)
        table = self._table("transfer_row")
        result = self._operation(
            operation="select",
            sql=(
                f"WITH issues AS (SELECT uid, entity_type, ordinal, jsonb_array_elements(errors || warnings) AS issue FROM \"{table}\" WHERE job_uid=%(job_uid)s::uuid), q AS (SELECT jsonb_build_object('row_uid',uid,'entity_type',entity_type,'ordinal',ordinal,'field',issue->'field','code',issue->>'code','message',issue->>'message','severity',issue->>'severity') AS item FROM issues), paged AS (SELECT item, row_number() OVER () AS n FROM q LIMIT %(page_size)s::integer OFFSET %(page_offset)s::integer) SELECT COALESCE(jsonb_agg(item ORDER BY n),'[]'::jsonb) AS items, (SELECT count(*) FROM q) AS total_items FROM paged"
            ),
            parameters={
                "job_uid": str(job_uid),
                "page_size": page_size,
                "page_offset": page_index * page_size,
            },
            parameter_types={
                "job_uid": "uuid",
                "page_size": "integer",
                "page_offset": "integer",
            },
            tables={"transfer_row": "read"},
            max_rows=1,
        )
        row = result["rows"][0]
        items = [
            validate_payload("ValidationIssue", item)
            for item in _json_value(row.get("items"), list, "issues")
        ]
        total = int(row.get("total_items", 0))
        return {
            "items": items,
            "pageInfo": {
                "pageIndex": page_index,
                "pageSize": page_size,
                "totalItems": total,
                "hasNextPage": (page_index + 1) * page_size < total,
                "hasPreviousPage": page_index > 0,
            },
        }

    def errors_csv(self, actor_uid: uuid.UUID, job_uid: uuid.UUID) -> str:
        self._job_row(job_uid, actor_uid)
        table = self._table("transfer_row")
        result = self._operation(
            operation="select",
            sql=(
                f"SELECT uid, entity_type, ordinal, external_id, errors, warnings FROM \"{table}\" WHERE job_uid=%(job_uid)s::uuid AND (errors<>'[]'::jsonb OR warnings<>'[]'::jsonb) ORDER BY ordinal, uid"
            ),
            parameters={"job_uid": str(job_uid)},
            parameter_types={"job_uid": "uuid"},
            tables={"transfer_row": "read"},
            max_rows=20000,
        )
        return render_error_csv(result.get("rows") or [])

    def download_export(self, actor_uid: uuid.UUID, job_uid: uuid.UUID) -> tuple[str, str, str]:
        row = self._job_row(job_uid, actor_uid)
        if row["direction"] != "export" or row["status"] != "succeeded":
            raise ResourceConflict("Export output is not ready")
        manifest = _json_value(row.get("output_manifest"), dict, "output manifest")
        return render_export(manifest)
