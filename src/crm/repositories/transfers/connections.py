from __future__ import annotations

import uuid
from typing import Any

from ...contracts import validate_payload
from .base import TransferBase, _json_value


class SourceConnections(TransferBase):
    def source_connections(self, page_index: int, page_size: int) -> dict[str, Any]:
        table = self._table("source_connection")
        result = self._operation(
            operation="select",
            sql=(
                f'WITH q AS (SELECT uid, name, adapter_id, source_account_key, version FROM "{table}" '
                "WHERE adapter_id <> 'google-workspace-v1' ORDER BY name, uid), "
                "paged AS (SELECT *, row_number() OVER () AS __row FROM q "
                "LIMIT %(page_size)s::integer OFFSET %(page_offset)s::integer) "
                "SELECT COALESCE((SELECT jsonb_agg(to_jsonb(paged)-'__row' ORDER BY __row) FROM paged), "
                "'[]'::jsonb) AS items, (SELECT count(*) FROM q) AS total_items"
            ),
            parameters={
                "page_size": page_size,
                "page_offset": page_index * page_size,
            },
            parameter_types={
                "page_size": "integer",
                "page_offset": "integer",
            },
            tables={"source_connection": "read"},
            max_rows=1,
        )
        rows = result.get("rows")
        if not isinstance(rows, list) or len(rows) != 1:
            raise RuntimeError("CRM source connection query returned no envelope")
        items = _json_value(rows[0].get("items"), list, "source connections")
        items = [validate_payload("SourceConnection", item) for item in items]
        total = int(rows[0].get("total_items", 0))
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

    def create_source_connection(
        self,
        actor_uid: uuid.UUID,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        data = validate_payload("SourceConnectionCreate", payload)
        table = self._table("source_connection")
        uid = uuid.uuid4()
        result = self._operation(
            operation="insert",
            sql=(
                f'INSERT INTO "{table}" (uid, created_at, updated_at, created_by_uid, '
                "updated_by_uid, version, name, adapter_id, source_account_key, configuration) "
                "VALUES (%(uid)s::uuid, NOW(), NOW(), %(actor_uid)s::uuid, "
                "%(actor_uid)s::uuid, 1, %(name)s, %(adapter_id)s, %(source_account_key)s, '{}'::jsonb "
                ") RETURNING *"
            ),
            parameters={"actor_uid": str(actor_uid), "uid": str(uid), **data},
            parameter_types={
                "uid": "uuid",
                "name": "string",
                "adapter_id": "string",
                "source_account_key": "string",
            },
            tables={"source_connection": "write"},
            max_rows=1,
        )
        row = self._changed_row(result)
        return validate_payload(
            "SourceConnection",
            {
                key: row[key]
                for key in ("uid", "name", "adapter_id", "source_account_key", "version")
            },
        )
