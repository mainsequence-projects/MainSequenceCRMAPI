"""CRM application services built on governed Main Sequence reads.

The services in this module do not resolve authentication.  They receive the
request-bound actor and CRM application configuration from the ASGI wiring,
then re-check policy at the service boundary before reading MetaTables.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping
from typing import Any, Protocol

from mainsequence.client import MetaTable

from ..metatables import MODELS
from ..platform.catalog import CatalogBinding, CatalogRegistry, configured_registry
from ..platform.runtime import CAPABILITIES, DirectoryPort, PolicyPort


class SettingsStorePort(Protocol):
    """Governed read boundary for CRM application configuration."""

    def bootstrap_record(self) -> Mapping[str, Any]: ...


class CatalogSettingsStore:
    """Read settings through finalized MetaTable bindings."""

    def __init__(self, registry: CatalogRegistry | None = None):
        self.registry = registry or configured_registry()

    def _required_bindings(self) -> tuple[CatalogBinding, CatalogBinding]:
        return self.registry.binding("settings"), self.registry.binding("pipeline")

    def bootstrap_record(self) -> Mapping[str, Any]:
        settings_binding, pipeline_binding = self._required_bindings()
        settings_table = MODELS["settings"].__tablename__
        pipeline_table = MODELS["pipeline"].__tablename__
        response = MetaTable.execute_operation(
            {
                "operation": "select",
                "statement": {
                    "sql": (
                        "SELECT s.default_currency, s.timezone, s.configuration, "
                        "s.configuration_version, p.uid AS default_pipeline_uid "
                        f'FROM "{settings_table}" AS s '
                        f'JOIN "{pipeline_table}" AS p ON p.is_default = TRUE '
                        "WHERE s.key = 'default' LIMIT 2"
                    ),
                    "parameters": {},
                },
                "scope": {
                    "data_source_uid": settings_binding.data_source_uid,
                    "tables": [
                        {
                            "meta_table_uid": settings_binding.meta_table_uid,
                            "access": "read",
                        },
                        {
                            "meta_table_uid": pipeline_binding.meta_table_uid,
                            "access": "read",
                        },
                    ],
                },
                "limits": {"max_rows": 2, "statement_timeout_ms": 5000},
            }
        )
        rows = response.get("rows")
        if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], Mapping):
            raise RuntimeError("CRM settings or default pipeline have not been initialized")
        return rows[0]


class BootstrapService:
    """Return the safe startup document for an authorized CRM actor."""

    def __init__(
        self,
        *,
        policy: PolicyPort,
        directory: DirectoryPort,
        store: SettingsStorePort,
    ):
        self.policy = policy
        self.directory = directory
        self.store = store

    def validate(self, actor_uid: uuid.UUID) -> None:
        self.read(actor_uid)

    def read(self, actor_uid: uuid.UUID) -> dict[str, Any]:
        capabilities = set(self.policy.capabilities(actor_uid))
        if not capabilities <= CAPABILITIES:
            raise RuntimeError("Policy returned an unknown CRM capability")
        if "crm.read" not in capabilities:
            raise PermissionError("CRM read access denied")
        record = self.store.bootstrap_record()
        settings = self._settings(record)
        default_pipeline_uid = self._uuid(record, "default_pipeline_uid")
        display_name = self.directory.display_name(actor_uid).strip()
        if not display_name:
            raise RuntimeError("Directory returned an empty display name")
        return {
            "application_version": "0.1.0",
            "current_user": {
                "uid": str(actor_uid),
                "display_name": display_name,
                "selectable": bool(self.directory.is_selectable(actor_uid)),
            },
            "capabilities": sorted(capabilities),
            "settings": settings,
            "default_pipeline_uid": str(default_pipeline_uid),
            "limits": {
                "list_page_max": 100,
                "bulk_explicit_max": 200,
                "upload_bytes_max": 20 * 1024 * 1024,
                "transfer_rows_max": 20_000,
            },
        }

    @staticmethod
    def _uuid(record: Mapping[str, Any], field: str) -> uuid.UUID:
        try:
            return uuid.UUID(str(record[field]))
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise RuntimeError(f"CRM {field} is invalid") from exc

    @staticmethod
    def _settings(record: Mapping[str, Any]) -> dict[str, Any]:
        try:
            version = int(record["configuration_version"])
            currency = str(record["default_currency"]).strip()
            timezone = str(record["timezone"]).strip()
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError("CRM settings are incomplete") from exc
        if version < 1 or len(currency) != 3 or not currency.isalpha() or not timezone:
            raise RuntimeError("CRM settings are invalid")
        raw_configuration = record.get("configuration")
        if isinstance(raw_configuration, str):
            try:
                raw_configuration = json.loads(raw_configuration)
            except json.JSONDecodeError as exc:
                raise RuntimeError("CRM configuration is invalid JSON") from exc
        if not isinstance(raw_configuration, Mapping):
            raise RuntimeError("CRM configuration is invalid")
        settings: dict[str, Any] = {
            "configuration_version": version,
            "default_currency": currency.upper(),
            "timezone": timezone,
        }
        for key in (
            "company_sectors",
            "contact_statuses",
            "deal_categories",
            "task_types",
        ):
            values = raw_configuration.get(key)
            if not isinstance(values, list) or len(values) > 100:
                raise RuntimeError(f"CRM {key} configuration is invalid")
            normalized = []
            for option in values:
                if not isinstance(option, Mapping):
                    raise RuntimeError(f"CRM {key} configuration is invalid")
                value = option.get("value")
                label = option.get("label")
                if (
                    not isinstance(value, str)
                    or not value
                    or not isinstance(label, str)
                    or not label
                ):
                    raise RuntimeError(f"CRM {key} configuration is invalid")
                normalized.append({"value": value, "label": label})
            settings[key] = normalized
        return settings
