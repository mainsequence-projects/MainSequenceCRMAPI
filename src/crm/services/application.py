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

from sqlalchemy import select

from metatables import MetaTable
from metatables.compiled_sql.v1 import compile_sqlalchemy_statement

from ..google_workspace.config import google_workspace_enabled
from ..metatables import MODELS
from ..platform.catalog import CatalogRegistry, configured_registry
from ..platform.diagnostics import observe_stage
from ..platform.runtime import CAPABILITIES, DirectoryPort, PolicyPort
from ..solution_selling.config import solution_selling_enabled


class SettingsStorePort(Protocol):
    """Governed read boundary for CRM application configuration."""

    def bootstrap_record(self) -> Mapping[str, Any]: ...


class CatalogSettingsStore:
    """Read settings through finalized MetaTable bindings."""

    def __init__(self, registry: CatalogRegistry | None = None):
        self.registry = registry or configured_registry()

    def bootstrap_record(self) -> Mapping[str, Any]:
        settings = MODELS["settings"].__table__
        pipeline = MODELS["pipeline"].__table__
        with observe_stage("catalog", cache_hit="bindings" in getattr(self.registry, "__dict__", {})):
            data_source_uid = self.registry.data_source_uid
        with observe_stage("metatables"):
            response = MetaTable.execute_operation(
                compile_sqlalchemy_statement(
                    select(
                        settings.c.default_currency,
                        settings.c.timezone,
                        settings.c.configuration,
                        settings.c.configuration_version,
                        pipeline.c.uid.label("default_pipeline_uid"),
                    )
                    .select_from(settings.join(pipeline, pipeline.c.is_default.is_(True)))
                    .where(settings.c.key == "default")
                    .limit(2),
                    operation="select",
                    data_source_uid=data_source_uid,
                    limits={"max_rows": 2, "statement_timeout_ms": 5000},
                )
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
        with observe_stage("permissions"):
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
            "modules": {
                "solution_selling": solution_selling_enabled(),
                "google_workspace": google_workspace_enabled(),
            },
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
