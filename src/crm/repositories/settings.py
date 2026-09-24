"""Governed singleton CRM configuration writes."""

from __future__ import annotations

import json
import uuid
from typing import Any

from ..metatables import MODELS
from .errors import ResourceConflict
from .gateway import GovernedGateway


class SettingsRepository(GovernedGateway):
    def update_settings(
        self,
        actor_uid: uuid.UUID,
        expected_version: int,
        settings: dict[str, Any],
    ) -> None:
        command_uid = uuid.uuid4()
        settings_table = MODELS["settings"].__tablename__
        activity = MODELS["activity_event"].__tablename__
        configuration = {
            key: settings[key]
            for key in ("company_sectors", "contact_statuses", "deal_categories", "task_types")
        }
        parameters = {
            "actor_uid": str(actor_uid),
            "expected_version": expected_version,
            "default_currency": settings["default_currency"],
            "timezone": settings["timezone"],
            "configuration": json.dumps(configuration),
            "command_uid": str(command_uid),
            "event_uid": str(uuid.uuid5(command_uid, "activity")),
        }
        sql = (
            f'WITH changed AS (UPDATE "{settings_table}" SET '
            "configuration_version=configuration_version+1, default_currency=%(default_currency)s, "
            "timezone=%(timezone)s, configuration=%(configuration)s::jsonb, updated_at=NOW() "
            "WHERE key='default' "
            "AND configuration_version=CAST(%(expected_version)s AS bigint) RETURNING *) "
            f'INSERT INTO "{activity}" (uid, entity_type, entity_uid, '
            "kind, occurred_at, recorded_at, actor_uid, origin, command_uid, summary, changes, "
            "source_attribution) SELECT CAST(%(event_uid)s AS uuid), 'settings', "
            "changed.uid, 'settings-updated', NOW(), NOW(), "
            "CAST(%(actor_uid)s AS uuid), 'live', "
            "CAST(%(command_uid)s AS uuid), 'Updated CRM settings', '{}'::jsonb, NULL "
            "FROM changed RETURNING entity_uid"
        )
        result = self._operation(
            operation="insert",
            sql=sql,
            parameters=parameters,
            parameter_types={"configuration": "jsonb"},
            tables={"settings": "write", "activity_event": "write"},
            max_rows=1,
        )
        if not result.get("rows"):
            raise ResourceConflict("Settings version precondition failed")
