"""Shared, provider-bound Main Sequence MetaTable operation gateway."""

from __future__ import annotations

import json
from typing import Any

from mainsequence.client import MetaTable

from ..platform.catalog import CatalogBinding, CatalogRegistry, configured_registry


class GovernedGateway:
    def __init__(self, registry: CatalogRegistry | None = None):
        self.registry = registry or configured_registry()

    def _binding(self, logical_table: str) -> CatalogBinding:
        return self.registry.binding(logical_table)

    def _operation(
        self,
        *,
        operation: str,
        sql: str,
        parameters: dict[str, Any],
        parameter_types: dict[str, str],
        tables: dict[str, str],
        max_rows: int = 1000,
    ) -> dict[str, Any]:
        bindings = {name: self._binding(name) for name in tables}
        data_sources = {binding.data_source_uid for binding in bindings.values()}
        if len(data_sources) != 1:
            raise RuntimeError("CRM operation spans multiple data sources")
        return MetaTable.execute_operation(
            {
                "operation": operation,
                "statement": {
                    "sql": sql,
                    "parameters": parameters,
                    # The current backend only normalizes temporal and JSON
                    # metadata. All scalar values are explicitly cast by SQL
                    # where PostgreSQL cannot infer them safely.
                    "parameter_types": {
                        key: value
                        for key, value in parameter_types.items()
                        if value in {"json", "jsonb"}
                    },
                },
                "scope": {
                    "data_source_uid": next(iter(data_sources)),
                    "tables": [
                        {"meta_table_uid": binding.meta_table_uid, "access": tables[name]}
                        for name, binding in bindings.items()
                    ],
                },
                "limits": {"max_rows": max_rows, "statement_timeout_ms": 15000},
            }
        )

    @staticmethod
    def _json(value: Any, *, expected: type, label: str) -> Any:
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"CRM {label} response is invalid JSON") from exc
        if not isinstance(value, expected):
            raise RuntimeError(f"CRM {label} response has an invalid shape")
        return value

    @staticmethod
    def _parameter(name: str, value: Any) -> tuple[Any, str, str]:
        json_fields = {
            "emails",
            "phones",
            "context_links",
            "logo_ref",
            "avatar_ref",
            "socials",
            "attachment_refs",
            "changes",
        }
        uuid_fields = {
            "owner_uid",
            "company_uid",
            "pipeline_uid",
            "stage_uid",
            "contact_uid",
            "deal_uid",
            "author_uid",
            "completed_by_uid",
            "created_by_uid",
            "updated_by_uid",
        }
        timestamp_fields = {"first_seen", "last_seen", "due_at", "occurred_at", "completed_at"}
        if name in json_fields:
            return json.dumps(value), "jsonb", f"%({name})s::jsonb"
        if name in uuid_fields:
            return None if value is None else str(value), "uuid", f"%({name})s::uuid"
        if name in timestamp_fields:
            return value, "timestamptz", f"%({name})s::timestamptz"
        if name == "expected_closing_date":
            return value, "date", f"%({name})s::date"
        if name == "amount":
            return value, "numeric", f"%({name})s::numeric"
        if isinstance(value, bool):
            return value, "boolean", f"%({name})s"
        if isinstance(value, int):
            return value, "bigint", f"%({name})s"
        return value, "string", f"%({name})s"
