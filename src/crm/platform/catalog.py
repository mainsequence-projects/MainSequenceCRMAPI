"""Resolve migration-managed CRM MetaTables from the live platform catalog."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from functools import cached_property, lru_cache

from mainsequence.client import MetaTable

from ..metatables import MODELS


@dataclass(frozen=True)
class CatalogBinding:
    meta_table_uid: str
    data_source_uid: str
    physical_table_name: str
    migration_provider_key: str
    alembic_revision: str


class CatalogRegistry:
    """Bind only the active, provider-owned tables authored by this CRM."""

    @cached_property
    def bindings(self) -> dict[str, CatalogBinding]:
        expected = {
            model.__metatable_identifier__: model.__tablename__ for model in MODELS.values()
        }
        rows = MetaTable.filter(identifier__in=list(expected), provisioning_status="active")
        bindings: dict[str, CatalogBinding] = {}
        providers: set[str] = set()
        revisions: set[str] = set()
        data_sources: set[str] = set()
        seen_identifiers: set[str] = set()
        for row in rows:
            identifier = row.identifier
            if identifier not in expected or identifier in seen_identifiers:
                raise RuntimeError("CRM MetaTable catalog has unexpected or duplicate identifiers")
            seen_identifiers.add(identifier)
            physical = expected[identifier]
            if (
                row.physical_table_name != physical
                or row.physical_schema not in (None, "", "public")
                or row.namespace != "mainsequence-crm"
                or row.migration_namespace != "mainsequence-crm"
                or row.management_mode != "platform_managed"
                or row.schema_management_mode != "alembic_managed"
                or row.provisioning_status != "active"
            ):
                raise RuntimeError(f"CRM MetaTable {identifier} has an invalid catalog binding")
            try:
                table_uid = str(uuid.UUID(str(row.uid)))
                data_source_uid = str(uuid.UUID(str(row.data_source_uid)))
            except (TypeError, ValueError, AttributeError) as exc:
                raise RuntimeError(f"CRM MetaTable {identifier} has invalid UIDs") from exc
            provider = row.migration_provider_key
            revision = row.alembic_revision
            if not provider or not revision:
                raise RuntimeError(f"CRM MetaTable {identifier} has no finalized migration")
            providers.add(provider)
            revisions.add(revision)
            data_sources.add(data_source_uid)
            bindings[physical] = CatalogBinding(
                meta_table_uid=table_uid,
                data_source_uid=data_source_uid,
                physical_table_name=physical,
                migration_provider_key=provider,
                alembic_revision=revision,
            )
        if seen_identifiers != set(expected):
            raise RuntimeError("CRM MetaTable catalog is incomplete")
        if len(providers) != 1 or len(revisions) != 1 or len(data_sources) != 1:
            raise RuntimeError("CRM MetaTables span multiple providers, revisions or data sources")
        return bindings

    def binding(self, logical_name: str) -> CatalogBinding:
        return self.bindings[MODELS[logical_name].__tablename__]

    def validate(self) -> None:
        self.bindings

    def validate_settings(self) -> None:
        """Require one initialized application-settings row."""
        binding = self.binding("settings")
        response = MetaTable.execute_operation(
            {
                "operation": "select",
                "statement": {
                    "sql": f'SELECT key FROM "{binding.physical_table_name}" LIMIT 2',
                    "parameters": {},
                },
                "scope": {
                    "data_source_uid": binding.data_source_uid,
                    "tables": [{"meta_table_uid": binding.meta_table_uid, "access": "read"}],
                },
                "limits": {"max_rows": 2, "statement_timeout_ms": 5000},
            }
        )
        rows = response.get("rows")
        if not isinstance(rows, list) or len(rows) != 1 or rows[0].get("key") != "default":
            raise RuntimeError("CRM settings are not initialized")


@lru_cache(maxsize=1)
def configured_registry() -> CatalogRegistry:
    """Share one validated catalog snapshot per fresh API process."""
    return CatalogRegistry()
