"""Governed task state transitions."""

from __future__ import annotations

import uuid
from typing import Any

from ..metatables import MODELS
from .errors import ResourceConflict
from .gateway import GovernedGateway
from .resources.reads import ResourceReads


class TaskRepository(GovernedGateway):
    def __init__(self, registry, reads: ResourceReads):
        super().__init__(registry)
        self.reads = reads

    def task_completion(
        self,
        actor_uid: uuid.UUID,
        uid: uuid.UUID,
        expected_version: int,
        completed: bool,
    ) -> dict[str, Any]:
        verb = "complete" if completed else "reopen"
        command_uid = uuid.uuid4()
        task = MODELS["task"].__tablename__
        activity = MODELS["activity_event"].__tablename__
        completed_at = "NOW()" if completed else "NULL"
        completed_by = "CAST(%(actor_uid)s AS uuid)" if completed else "NULL"
        parameters = {
            "actor_uid": str(actor_uid),
            "entity_uid": str(uid),
            "expected_version": expected_version,
            "command_uid": str(command_uid),
            "event_uid": str(uuid.uuid5(command_uid, "activity")),
            "summary": "Completed task" if completed else "Reopened task",
        }
        types = {key: "uuid" if key.endswith("_uid") else "string" for key in parameters}
        progress = MODELS["campaign_progress"].__tablename__
        # A core completion never supplies a campaign outcome, and a reopen never
        # replays downstream work: linked progress becomes blocked for reconciliation.
        campaign_guard = (
            "state='blocked', blocked_reason='outcome_required' WHERE g.state IN ('open','waiting')"
            if completed
            else "state='blocked', blocked_reason='task_reopened' WHERE g.state='completed'"
        )
        sql = (
            f'WITH changed AS (UPDATE "{task}" target SET completed_at={completed_at}, '
            f"completed_by_uid={completed_by}, updated_at=NOW(), "
            "updated_by_uid=CAST(%(actor_uid)s AS uuid), version=target.version+1 "
            "WHERE target.uid=CAST(%(entity_uid)s AS uuid) "
            "AND target.version=CAST(%(expected_version)s AS bigint) RETURNING target.*), "
            f'campaign_blocked AS (UPDATE "{progress}" g SET updated_at=NOW(), {campaign_guard} '
            "AND g.task_uid=CAST(%(entity_uid)s AS uuid) RETURNING g.uid) "
            f'INSERT INTO "{activity}" (uid, entity_type, entity_uid, '
            "kind, occurred_at, recorded_at, actor_uid, origin, command_uid, summary, changes, "
            "source_attribution) SELECT CAST(%(event_uid)s AS uuid), 'task', "
            f"changed.uid, '{verb}d', NOW(), NOW(), CAST(%(actor_uid)s AS uuid), 'live', "
            "CAST(%(command_uid)s AS uuid), %(summary)s, '{}'::jsonb, NULL FROM changed "
            "CROSS JOIN (SELECT count(*) FROM campaign_blocked) campaign_guard "
            "RETURNING entity_uid"
        )
        result = self._operation(
            operation="insert",
            sql=sql,
            parameters=parameters,
            parameter_types=types,
            max_rows=1,
        )
        if not result.get("rows"):
            raise ResourceConflict("Task version precondition failed")
        return self.reads.detail("tasks", uid)
