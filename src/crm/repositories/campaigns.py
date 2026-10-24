"""Governed persistence for the Campaigns module.

Every write is one final-INSERT DML statement: the gate checks versions and
relationships, dependent CTEs change Tasks, progress and participants, and the
activity row proves the whole change committed. Domain rules stay in
``src.crm.campaigns``; this module only binds them to SQL.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from src.crm.metatables import MODELS
from src.crm.repositories.errors import ResourceConflict, ResourceNotFound
from src.crm.repositories.gateway import GovernedGateway

ACTIVITY_COLUMNS = (
    "(uid, entity_type, entity_uid, kind, occurred_at, recorded_at, actor_uid, origin, "
    "command_uid, summary, changes, source_attribution)"
)
CONTACT_NAME = (
    "COALESCE(NULLIF(trim(concat_ws(' ', ct.first_name, ct.last_name)), ''), "
    "ct.emails->0->>'email', 'Unnamed contact')"
)
OPEN_STATES = "('open','waiting','blocked')"
# Appended to every Task created from a step so core views can recognize campaign work.
PROGRESS_COLUMNS = (
    "step_uid, task_uid, prompt_assignment, state, outcome_key, result, evidence, wake_at, "
    "blocked_reason, prepared_with, completed_at, created_at, updated_at"
)


def _table(logical: str) -> str:
    return f'"{MODELS[logical].__tablename__}"'


def _uuids(values: list[uuid.UUID] | list[str]) -> str:
    return json.dumps([str(value) for value in values])


def _in_uuids(column: str, parameter: str) -> str:
    return f"{column} IN (SELECT value::uuid FROM jsonb_array_elements_text(%({parameter})s::jsonb))"


def _progress_projection(alias: str) -> str:
    return (
        f"(SELECT COALESCE(jsonb_agg((to_jsonb(g) - 'uid' - 'participant_uid') "
        f"ORDER BY g.created_at, g.step_uid), '[]'::jsonb) FROM {_table('campaign_progress')} g "
        f"WHERE g.participant_uid={alias}.uid)"
    )


def _participant_projection() -> str:
    return (
        f"SELECT p.*, {CONTACT_NAME} AS contact_display_name, "
        f"{_progress_projection('p')} AS progress "
        f"FROM {_table('campaign_participant')} p "
        f"JOIN {_table('contact')} ct ON ct.uid=p.contact_uid"
    )


def _page(
    gateway: GovernedGateway,
    *,
    base: str,
    where: str,
    order: str,
    params: dict[str, Any],
    types: dict[str, str],
    page_index: int,
    page_size: int,
    label: str,
) -> dict[str, Any]:
    params = {**params, "limit": page_size, "offset": page_index * page_size}
    sql = (
        f"WITH q AS ({base} WHERE {where}), "
        f"paged AS (SELECT q.*, row_number() OVER (ORDER BY {order}) AS __row FROM q "
        f"ORDER BY {order} LIMIT %(limit)s::integer OFFSET %(offset)s::integer) "
        "SELECT COALESCE((SELECT jsonb_agg(to_jsonb(paged) - '__row' ORDER BY __row) FROM paged), "
        "'[]'::jsonb) AS items, (SELECT count(*) FROM q) AS total_items"
    )
    result = gateway._operation(operation="select", sql=sql, parameters=params, parameter_types=types, max_rows=1)
    rows = result.get("rows")
    if not isinstance(rows, list) or len(rows) != 1:
        raise RuntimeError(f"Invalid CRM {label} collection response")
    items = gateway._json(rows[0]["items"], expected=list, label=label)
    total = int(rows[0]["total_items"])
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


def _search(params: dict[str, Any], search: str | None, *fields: str) -> str:
    if not search:
        return "TRUE"
    escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_").casefold()
    params["search"] = f"%{escaped}%"
    return "(" + " OR ".join(
        f"lower(coalesce({field}::text, '')) LIKE %(search)s ESCAPE '\\'" for field in fields
    ) + ")"


class CampaignStore(GovernedGateway):
    """One gateway for campaign definitions, step prompts, participants and progress."""

    # ----- reads -----------------------------------------------------------

    def campaign_collection(self, *, page_index: int, page_size: int, search: str | None,
                            filters: dict[str, Any]) -> dict[str, Any]:
        params: dict[str, Any] = {}
        clauses = []
        archived = filters.get("archived", False)
        if archived is True:
            clauses.append("t.archived_at IS NOT NULL")
        elif archived is False:
            clauses.append("t.archived_at IS NULL")
        for key in ("status", "owner_uid"):
            if filters.get(key) is not None:
                params[f"f_{key}"] = str(filters[key])
                clauses.append(f"t.{key}=%(f_{key})s" + ("::uuid" if key.endswith("_uid") else ""))
        clauses.append(_search(params, search, "t.name", "t.objective"))
        participant = _table("campaign_participant")
        base = (
            "SELECT t.*, (SELECT COALESCE(jsonb_object_agg(x.status, x.n), '{}'::jsonb) FROM "
            f"(SELECT status, count(*) AS n FROM {participant} WHERE campaign_uid=t.uid "
            f"GROUP BY status) x) AS participant_counts FROM {_table('campaign')} t"
        )
        return _page(self, base=base, where=" AND ".join(clauses), order="q.updated_at DESC, q.uid DESC",
                     params=params, types={}, page_index=page_index, page_size=page_size, label="campaigns")

    def campaign_detail(self, uid: uuid.UUID) -> dict[str, Any]:
        """The campaign row plus all its steps (including retired), transitions and counts."""
        step, transition, participant = _table("campaign_step"), _table("campaign_transition"), _table("campaign_participant")
        sql = (
            f"WITH c AS (SELECT * FROM {_table('campaign')} WHERE uid=%(uid)s::uuid) "
            "SELECT to_jsonb(c) AS item, "
            f"(SELECT COALESCE(jsonb_agg(to_jsonb(s) ORDER BY s.created_at, s.uid), '[]'::jsonb) "
            f"FROM {step} s WHERE s.campaign_uid=c.uid) AS steps, "
            f"(SELECT COALESCE(jsonb_agg(to_jsonb(t) ORDER BY t.created_at, t.uid), '[]'::jsonb) "
            f"FROM {transition} t WHERE t.campaign_uid=c.uid) AS transitions, "
            "(SELECT COALESCE(jsonb_object_agg(x.status, x.n), '{}'::jsonb) FROM (SELECT status, "
            f"count(*) AS n FROM {participant} WHERE campaign_uid=c.uid GROUP BY status) x) "
            "AS participant_counts FROM c"
        )
        result = self._operation(operation="select", sql=sql, parameters={"uid": str(uid)}, parameter_types={}, max_rows=1)
        rows = result.get("rows")
        if not isinstance(rows, list) or not rows:
            raise ResourceNotFound("Campaign not found")
        row = rows[0]
        item = self._json(row["item"], expected=dict, label="campaign")
        item["steps"] = self._json(row["steps"], expected=list, label="campaign steps")
        item["transitions"] = self._json(row["transitions"], expected=list, label="campaign transitions")
        item["participant_counts"] = self._json(row["participant_counts"], expected=dict, label="campaign counts")
        return item

    def step_prompts_by_uid(self, uids: list[uuid.UUID]) -> dict[str, dict[str, Any]]:
        if not uids:
            return {}
        sql = (
            "SELECT p.uid, p.version, p.archived_at, sp.inputs, sp.result_fields "
            f"FROM {_table('prompt')} p JOIN {_table('campaign_step_prompt')} sp ON sp.uid=p.uid "
            f"WHERE {_in_uuids('p.uid', 'uids')}"
        )
        result = self._operation(operation="select", sql=sql, parameters={"uids": _uuids(uids)},
                                 parameter_types={"uids": "jsonb"}, max_rows=len(uids))
        prompts = {}
        for row in result.get("rows") or []:
            prompts[str(row["uid"])] = {
                "version": int(row["version"]),
                "archived": row.get("archived_at") is not None,
                "inputs": self._json(row["inputs"], expected=list, label="prompt inputs"),
                "result_fields": self._json(row["result_fields"], expected=list, label="prompt result fields"),
            }
        return prompts

    def comparisons(self, campaign_uid: uuid.UUID) -> list[dict[str, Any]]:
        """Descriptive per-variant counts, grouped by step and comparison key, computed server-side."""
        progress, participant = _table("campaign_progress"), _table("campaign_participant")
        window = "make_interval(secs => (a.prompt_assignment->'comparison'->>'observation_window_seconds')::bigint)"
        assigned_at = "(a.prompt_assignment->>'assigned_at')::timestamptz"
        matured = f"{assigned_at} + {window} <= NOW()"
        success = (
            f"EXISTS (SELECT 1 FROM {progress} m WHERE m.participant_uid=a.participant_uid "
            "AND m.step_uid=(a.prompt_assignment->'comparison'->>'metric_step_uid')::uuid "
            "AND m.state='completed' AND m.outcome_key IN (SELECT jsonb_array_elements_text("
            f"a.prompt_assignment->'comparison'->'success_outcome_keys')) AND m.completed_at <= {assigned_at} + {window})"
        )
        sql = (
            "SELECT a.step_uid, a.prompt_assignment->'comparison'->>'key' AS comparison_key, "
            "a.prompt_assignment->>'variant_key' AS variant_key, count(*) AS assigned, "
            "count(*) FILTER (WHERE a.state='completed') AS completed, "
            "count(*) FILTER (WHERE a.state='cancelled') AS cancelled, "
            f"count(*) FILTER (WHERE {matured}) AS matured, "
            f"count(*) FILTER (WHERE {matured} AND {success}) AS successes, "
            "count(*) FILTER (WHERE (a.prompt_assignment->>'comparison_changed')::boolean) AS changed_exposures "
            f"FROM {progress} a JOIN {participant} p ON p.uid=a.participant_uid "
            "WHERE p.campaign_uid=%(uid)s::uuid AND jsonb_typeof(a.prompt_assignment->'comparison') = 'object' "
            "GROUP BY 1, 2, 3 ORDER BY 1, 2, 3"
        )
        result = self._operation(operation="select", sql=sql, parameters={"uid": str(campaign_uid)},
                                 parameter_types={}, max_rows=1000)
        return [dict(row) for row in result.get("rows") or []]

    def step_prompt_collection(self, *, page_index: int, page_size: int, search: str | None,
                               filters: dict[str, Any]) -> dict[str, Any]:
        params: dict[str, Any] = {}
        archived = filters.get("archived", False)
        clauses = ["t.archived_at IS NOT NULL" if archived is True else "t.archived_at IS NULL" if archived is False else "TRUE"]
        clauses.append(_search(params, search, "t.name", "t.description"))
        columns = ", ".join(
            f"t.{column.name}" for column in MODELS["prompt"].__table__.columns if column.name != "content_markdown"
        )
        base = (
            f"SELECT {columns}, sp.inputs, sp.result_fields FROM {_table('prompt')} t "
            f"JOIN {_table('campaign_step_prompt')} sp ON sp.uid=t.uid"
        )
        return _page(self, base=base, where=" AND ".join(clauses), order="q.updated_at DESC, q.uid DESC",
                     params=params, types={}, page_index=page_index, page_size=page_size, label="step prompts")

    def step_prompt_detail(self, uid: uuid.UUID) -> dict[str, Any]:
        sql = (
            f"SELECT to_jsonb(t) || jsonb_build_object('inputs', sp.inputs, 'result_fields', sp.result_fields) AS item "
            f"FROM {_table('prompt')} t JOIN {_table('campaign_step_prompt')} sp ON sp.uid=t.uid "
            "WHERE t.uid=%(uid)s::uuid"
        )
        result = self._operation(operation="select", sql=sql, parameters={"uid": str(uid)}, parameter_types={}, max_rows=1)
        rows = result.get("rows")
        if not isinstance(rows, list) or not rows:
            raise ResourceNotFound("Campaign step prompt not found")
        return self._json(rows[0]["item"], expected=dict, label="step prompt")

    def participant_collection(self, *, page_index: int, page_size: int, search: str | None,
                               filters: dict[str, Any]) -> dict[str, Any]:
        params: dict[str, Any] = {}
        clauses = []
        for key in ("campaign_uid", "contact_uid", "status"):
            if filters.get(key) is not None:
                params[f"f_{key}"] = str(filters[key])
                clauses.append(f"p.{key}=%(f_{key})s" + ("::uuid" if key.endswith("_uid") else ""))
        if filters.get("attention"):
            progress = _table("campaign_progress")
            clauses.append(
                f"(EXISTS (SELECT 1 FROM {progress} g WHERE g.participant_uid=p.uid AND g.state='blocked') "
                "OR (p.status='active' AND p.next_step_uid IS NOT NULL AND p.eligible_at <= NOW() "
                f"AND NOT EXISTS (SELECT 1 FROM {progress} g WHERE g.participant_uid=p.uid AND g.step_uid=p.next_step_uid)))"
            )
        clauses.append(_search(params, search, "ct.first_name", "ct.last_name"))
        return _page(self, base=_participant_projection(), where=" AND ".join(clauses) or "TRUE", order="q.updated_at DESC, q.uid DESC",
                     params=params, types={}, page_index=page_index, page_size=page_size, label="participants")

    def participant_detail(self, uid: uuid.UUID) -> dict[str, Any]:
        sql = f"WITH item AS ({_participant_projection()} WHERE p.uid=%(uid)s::uuid) SELECT to_jsonb(item) AS item FROM item"
        result = self._operation(operation="select", sql=sql, parameters={"uid": str(uid)}, parameter_types={}, max_rows=1)
        rows = result.get("rows")
        if not isinstance(rows, list) or not rows:
            raise ResourceNotFound("Campaign participant not found")
        return self._json(rows[0]["item"], expected=dict, label="participant")

    def graph_impact(self, campaign_uid: uuid.UUID, *, affected_step_uids: list[uuid.UUID],
                     retired_step_uids: list[uuid.UUID]) -> dict[str, Any]:
        """Read-only: open work and scheduled next steps a candidate graph would affect."""
        progress, participant = _table("campaign_progress"), _table("campaign_participant")
        params = {"uid": str(campaign_uid), "affected": _uuids(affected_step_uids), "retired": _uuids(retired_step_uids)}
        sql = (
            f"WITH work AS (SELECT g.participant_uid, g.step_uid, g.task_uid, g.state FROM {progress} g "
            f"JOIN {participant} p ON p.uid=g.participant_uid WHERE p.campaign_uid=%(uid)s::uuid "
            f"AND g.state IN {OPEN_STATES} AND {_in_uuids('g.step_uid', 'affected')}), "
            f"scheduled AS (SELECT p.uid AS participant_uid, p.next_step_uid FROM {participant} p "
            "WHERE p.campaign_uid=%(uid)s::uuid AND p.status='active' "
            f"AND {_in_uuids('p.next_step_uid', 'retired')}) "
            "SELECT (SELECT count(*) FROM work) AS open_work_count, "
            "COALESCE((SELECT jsonb_agg(to_jsonb(w)) FROM (SELECT * FROM work LIMIT 100) w), '[]'::jsonb) AS open_work, "
            "(SELECT count(*) FROM scheduled) AS scheduled_count, "
            "COALESCE((SELECT jsonb_agg(to_jsonb(s)) FROM (SELECT * FROM scheduled LIMIT 100) s), '[]'::jsonb) AS scheduled"
        )
        result = self._operation(operation="select", sql=sql, parameters=params,
                                 parameter_types={"affected": "jsonb", "retired": "jsonb"}, max_rows=1)
        row = (result.get("rows") or [{}])[0]
        return {
            "open_work_count": int(row.get("open_work_count", 0)),
            "open_work": self._json(row.get("open_work", []), expected=list, label="impact"),
            "scheduled_to_retired_count": int(row.get("scheduled_count", 0)),
            "scheduled_to_retired": self._json(row.get("scheduled", []), expected=list, label="impact"),
        }

    def task_version(self, task_uid: uuid.UUID) -> dict[str, Any]:
        sql = f"SELECT uid, version, completed_at, archived_at FROM {_table('task')} WHERE uid=%(uid)s::uuid"
        result = self._operation(operation="select", sql=sql, parameters={"uid": str(task_uid)}, parameter_types={}, max_rows=1)
        rows = result.get("rows")
        if not isinstance(rows, list) or not rows:
            raise ResourceNotFound("Task not found")
        return dict(rows[0])

    # ----- write helpers ---------------------------------------------------

    @staticmethod
    def _audit(actor_uid: uuid.UUID, *, entity_type: str, kind: str, summary: str,
               changes: dict[str, Any] | None = None) -> tuple[dict[str, Any], dict[str, str]]:
        command_uid = uuid.uuid4()
        params = {
            "actor_uid": str(actor_uid),
            "command_uid": str(command_uid),
            "event_uid": str(uuid.uuid5(command_uid, "activity")),
            "entity_type": entity_type,
            "kind": kind,
            "summary": summary,
            "event_changes": json.dumps(changes or {}, default=str),
        }
        return params, {"event_changes": "jsonb"}

    @staticmethod
    def _activity(source: str) -> str:
        """SELECT one activity row from ``source``; its first alias supplies the entity UID."""
        entity = source.split()[0] + ".uid"
        return (
            f"SELECT %(event_uid)s::uuid, %(entity_type)s, {entity}, %(kind)s, NOW(), NOW(), "
            "%(actor_uid)s::uuid, 'live', %(command_uid)s::uuid, %(summary)s, %(event_changes)s::jsonb, NULL::jsonb "
            f"FROM {source}"
        )

    def _write(self, sql: str, params: dict[str, Any], types: dict[str, str], *, conflict: str,
               max_rows: int = 1) -> list[dict[str, Any]]:
        result = self._operation(operation="insert", sql=sql, parameters=params, parameter_types=types, max_rows=max_rows)
        rows = result.get("rows")
        if not rows:
            raise ResourceConflict(conflict)
        return rows

    # ----- campaign writes -------------------------------------------------

    def create_campaign(self, actor_uid: uuid.UUID, data: dict[str, Any]) -> dict[str, Any]:
        uid = uuid.uuid4()
        params, types = self._audit(actor_uid, entity_type="campaign", kind="created", summary="Created campaign")
        params.update(uid=str(uid), name=data["name"], objective=data["objective"],
                      owner_uid=str(data["owner_uid"]), context=json.dumps(data.get("context", {})))
        types["context"] = "jsonb"
        sql = (
            f"WITH created AS (INSERT INTO {_table('campaign')} (uid, created_at, updated_at, created_by_uid, "
            "updated_by_uid, version, archived_at, name, objective, owner_uid, context, status, entry_step_uid) "
            "VALUES (%(uid)s::uuid, NOW(), NOW(), %(actor_uid)s::uuid, %(actor_uid)s::uuid, 1, NULL, %(name)s, "
            "%(objective)s, %(owner_uid)s::uuid, %(context)s::jsonb, 'draft', NULL) RETURNING uid) "
            f"INSERT INTO {_table('activity_event')} {ACTIVITY_COLUMNS} {self._activity('created')} RETURNING entity_uid"
        )
        self._write(sql, params, types, conflict="Campaign create precondition failed")
        return self.campaign_detail(uid)

    def update_campaign(self, actor_uid: uuid.UUID, uid: uuid.UUID, expected_version: int,
                        changes: dict[str, Any]) -> dict[str, Any]:
        params, types = self._audit(actor_uid, entity_type="campaign", kind="updated", summary="Updated campaign", changes=changes)
        params.update(uid=str(uid), expected_version=expected_version)
        assignments = []
        for name, value in changes.items():
            if name == "context":
                params[name] = json.dumps(value)
                types[name] = "jsonb"
                assignments.append(f"{name}=%({name})s::jsonb")
            elif name == "owner_uid":
                params[name] = str(value)
                assignments.append(f"{name}=%({name})s::uuid")
            else:
                params[name] = value
                assignments.append(f"{name}=%({name})s")
        activation = changes.get("status") == "active"
        ctes = [
            f"changed AS (UPDATE {_table('campaign')} c SET {', '.join(assignments)}, updated_at=NOW(), "
            "updated_by_uid=%(actor_uid)s::uuid, version=c.version+1 WHERE c.uid=%(uid)s::uuid "
            "AND c.version=%(expected_version)s::bigint AND c.archived_at IS NULL RETURNING c.uid, c.entry_step_uid)",
        ]
        if activation:
            # Participants enrolled while the campaign was a draft receive the entry step now.
            ctes.append(
                f"scheduled AS (UPDATE {_table('campaign_participant')} p SET next_step_uid=changed.entry_step_uid, "
                "eligible_at=NOW(), updated_at=NOW(), updated_by_uid=%(actor_uid)s::uuid, version=p.version+1 "
                "FROM changed WHERE p.campaign_uid=changed.uid AND p.status='active' AND p.next_step_uid IS NULL "
                f"AND NOT EXISTS (SELECT 1 FROM {_table('campaign_progress')} g WHERE g.participant_uid=p.uid) "
                "RETURNING p.uid)"
            )
        source = "changed" + (" CROSS JOIN (SELECT count(*) FROM scheduled) scheduled_count" if activation else "")
        sql = (
            "WITH " + ", ".join(ctes) + f" INSERT INTO {_table('activity_event')} {ACTIVITY_COLUMNS} "
            f"{self._activity(source)} RETURNING entity_uid"
        )
        self._write(sql, params, types, conflict="Campaign version precondition failed")
        return self.campaign_detail(uid)

    def archive_campaign(self, actor_uid: uuid.UUID, uid: uuid.UUID, expected_version: int, archived: bool) -> dict[str, Any]:
        verb = "archive" if archived else "restore"
        params, types = self._audit(actor_uid, entity_type="campaign", kind=f"{verb}d", summary=f"{verb.title()}d campaign")
        params.update(uid=str(uid), expected_version=expected_version)
        sql = (
            f"WITH changed AS (UPDATE {_table('campaign')} c SET archived_at={'NOW()' if archived else 'NULL'}, "
            "updated_at=NOW(), updated_by_uid=%(actor_uid)s::uuid, version=c.version+1 "
            "WHERE c.uid=%(uid)s::uuid AND c.version=%(expected_version)s::bigint RETURNING c.uid) "
            f"INSERT INTO {_table('activity_event')} {ACTIVITY_COLUMNS} {self._activity('changed')} RETURNING entity_uid"
        )
        self._write(sql, params, types, conflict="Campaign version precondition failed")
        return self.campaign_detail(uid)

    def save_graph(
        self,
        actor_uid: uuid.UUID,
        campaign_uid: uuid.UUID,
        expected_version: int,
        *,
        entry_step_uid: uuid.UUID | None,
        steps: list[dict[str, Any]],
        layout_steps: list[dict[str, Any]],
        transitions: list[dict[str, Any]],
        kept_transition_uids: list[uuid.UUID],
        changed_step_uids: list[uuid.UUID],
        retired_step_uids: list[uuid.UUID],
        comparison_changed_step_uids: list[uuid.UUID],
        cancel_retired_work: bool,
    ) -> dict[str, Any]:
        """Apply one complete graph change against the campaign version.

        ``steps`` and ``transitions`` contain only new or changed records so
        unchanged definitions keep their versions and open briefings;
        ``layout_steps`` carry position-only edits that never bump a version.
        """
        campaign, step, transition = _table("campaign"), _table("campaign_step"), _table("campaign_transition")
        progress, task, prompt, step_prompt = _table("campaign_progress"), _table("task"), _table("prompt"), _table("campaign_step_prompt")
        params, types = self._audit(
            actor_uid, entity_type="campaign", kind="graph_updated", summary="Updated campaign graph",
            changes={"steps": len(steps), "transitions": len(transitions), "retired_steps": len(retired_step_uids)},
        )
        params.update(
            campaign_uid=str(campaign_uid), expected_version=expected_version,
            entry_step_uid=None if entry_step_uid is None else str(entry_step_uid),
            steps=json.dumps(steps, default=str), layout_steps=json.dumps(layout_steps, default=str),
            transitions=json.dumps(transitions, default=str),
            kept_transitions=_uuids(kept_transition_uids), changed=_uuids(changed_step_uids),
            retired=_uuids(retired_step_uids), comparison_changed=_uuids(comparison_changed_step_uids),
            cancel=cancel_retired_work,
        )
        types.update(steps="jsonb", layout_steps="jsonb", transitions="jsonb", kept_transitions="jsonb", changed="jsonb",
                     retired="jsonb", comparison_changed="jsonb")
        nullable = lambda key: f"NULLIF(s->'{key}', 'null'::jsonb)"  # noqa: E731
        step_values = (
            "(s->>'uid')::uuid, NOW(), NOW(), %(actor_uid)s::uuid, %(actor_uid)s::uuid, 1, "
            "CASE WHEN (s->>'archived')::boolean THEN NOW() END, %(campaign_uid)s::uuid, s->>'title', s->>'task_text', "
            f"s->'prompt_variants', {nullable('prompt_comparison')}, s->>'completion_mode', (s->>'owner_uid')::uuid, "
            "s->>'task_type_key', (s->>'due_after_seconds')::bigint, s->'input_bindings', s->>'completion_criteria', "
            f"s->'outcomes', {nullable('position')}"
        )
        step_updates = ", ".join(
            f"{column}=EXCLUDED.{column}" for column in (
                "title", "task_text", "prompt_variants", "prompt_comparison", "completion_mode", "owner_uid",
                "task_type_key", "due_after_seconds", "input_bindings", "completion_criteria", "outcomes", "position",
            )
        )
        retired = _in_uuids("g.step_uid", "retired")
        changed = _in_uuids("g.step_uid", "changed")
        compared = _in_uuids("g.step_uid", "comparison_changed")
        open_work = "g.state IN ('open','waiting')"
        sql = (
            f"WITH locked AS MATERIALIZED (SELECT c.uid FROM {campaign} c WHERE c.uid=%(campaign_uid)s::uuid "
            "AND c.version=%(expected_version)s::bigint AND c.archived_at IS NULL FOR UPDATE), "
            "gate AS (SELECT 1 AS ready FROM locked WHERE "
            f"NOT EXISTS (SELECT 1 FROM jsonb_array_elements(%(steps)s::jsonb) s JOIN {step} existing "
            "ON existing.uid=(s->>'uid')::uuid WHERE existing.campaign_uid<>%(campaign_uid)s::uuid) "
            f"AND NOT EXISTS (SELECT 1 FROM jsonb_array_elements(%(transitions)s::jsonb) t JOIN {transition} existing "
            "ON existing.uid=(t->>'uid')::uuid WHERE existing.campaign_uid<>%(campaign_uid)s::uuid) "
            "AND NOT EXISTS (SELECT 1 FROM jsonb_array_elements(%(steps)s::jsonb) s "
            f"CROSS JOIN jsonb_array_elements(s->'prompt_variants') v LEFT JOIN {prompt} p ON p.uid=(v->>'prompt_uid')::uuid "
            f"LEFT JOIN {step_prompt} sp ON sp.uid=p.uid WHERE (s->>'archived')::boolean IS NOT TRUE "
            "AND (p.uid IS NULL OR p.archived_at IS NOT NULL OR sp.uid IS NULL))), "
            f"steps_saved AS (INSERT INTO {step} AS target (uid, created_at, updated_at, created_by_uid, updated_by_uid, "
            "version, archived_at, campaign_uid, title, task_text, prompt_variants, prompt_comparison, completion_mode, "
            "owner_uid, task_type_key, due_after_seconds, input_bindings, completion_criteria, outcomes, position) "
            f"SELECT {step_values} FROM gate, jsonb_array_elements(%(steps)s::jsonb) s "
            f"ON CONFLICT (uid) DO UPDATE SET {step_updates}, archived_at=CASE WHEN EXCLUDED.archived_at IS NULL "
            "THEN NULL ELSE COALESCE(target.archived_at, EXCLUDED.archived_at) END, updated_at=NOW(), "
            "updated_by_uid=%(actor_uid)s::uuid, version=target.version+1 RETURNING uid), "
            f"layout_saved AS (UPDATE {step} s SET position=NULLIF(l.value->'position', 'null'::jsonb), updated_at=NOW(), "
            "updated_by_uid=%(actor_uid)s::uuid FROM gate, jsonb_array_elements(%(layout_steps)s::jsonb) l "
            "WHERE s.uid=(l.value->>'uid')::uuid AND s.campaign_uid=%(campaign_uid)s::uuid RETURNING s.uid), "
            f"transitions_removed AS (DELETE FROM {transition} t USING gate WHERE t.campaign_uid=%(campaign_uid)s::uuid "
            f"AND NOT {_in_uuids('t.uid', 'kept_transitions')} RETURNING t.uid), "
            f"transitions_saved AS (INSERT INTO {transition} AS target (uid, created_at, updated_at, created_by_uid, "
            "updated_by_uid, version, archived_at, campaign_uid, from_step_uid, outcome_key, to_step_uid, delay_seconds) "
            "SELECT (t->>'uid')::uuid, NOW(), NOW(), %(actor_uid)s::uuid, %(actor_uid)s::uuid, 1, NULL, "
            "%(campaign_uid)s::uuid, (t->>'from_step_uid')::uuid, t->>'outcome_key', (t->>'to_step_uid')::uuid, "
            "(t->>'delay_seconds')::bigint FROM gate, jsonb_array_elements(%(transitions)s::jsonb) t "
            "CROSS JOIN (SELECT count(*) FROM transitions_removed) removed CROSS JOIN (SELECT count(*) FROM steps_saved) saved "
            "ON CONFLICT (uid) DO UPDATE SET from_step_uid=EXCLUDED.from_step_uid, outcome_key=EXCLUDED.outcome_key, "
            "to_step_uid=EXCLUDED.to_step_uid, delay_seconds=EXCLUDED.delay_seconds, updated_at=NOW(), "
            "updated_by_uid=%(actor_uid)s::uuid, version=target.version+1 RETURNING uid), "
            # One update per affected progress row: block, cancel or flag exposure, never twice.
            f"work_changed AS (UPDATE {progress} g SET "
            f"state=CASE WHEN %(cancel)s::boolean AND {retired} AND g.state IN {OPEN_STATES} THEN 'cancelled' "
            f"WHEN {open_work} AND ({retired} OR {changed}) THEN 'blocked' ELSE g.state END, "
            f"blocked_reason=CASE WHEN %(cancel)s::boolean AND {retired} THEN g.blocked_reason "
            f"WHEN {open_work} AND {retired} THEN 'step_retired' WHEN {open_work} AND {changed} THEN 'step_changed' "
            "ELSE g.blocked_reason END, "
            f"prompt_assignment=CASE WHEN {compared} AND jsonb_typeof(g.prompt_assignment->'comparison') = 'object' THEN "
            "jsonb_set(g.prompt_assignment, '{comparison_changed}', 'true'::jsonb) ELSE g.prompt_assignment END, "
            f"updated_at=NOW() FROM gate WHERE ({retired} OR {changed} OR {compared}) "
            f"AND EXISTS (SELECT 1 FROM {_table('campaign_participant')} p WHERE p.uid=g.participant_uid "
            "AND p.campaign_uid=%(campaign_uid)s::uuid) RETURNING g.uid, g.task_uid, g.state), "
            f"tasks_archived AS (UPDATE {task} t SET archived_at=COALESCE(t.archived_at, NOW()), updated_at=NOW(), "
            "updated_by_uid=%(actor_uid)s::uuid, version=t.version+1 FROM work_changed w WHERE t.uid=w.task_uid "
            "AND w.state='cancelled' AND %(cancel)s::boolean RETURNING t.uid), "
            f"changed AS (UPDATE {campaign} c SET entry_step_uid=%(entry_step_uid)s::uuid, updated_at=NOW(), "
            "updated_by_uid=%(actor_uid)s::uuid, version=c.version+1 FROM gate, "
            "(SELECT count(*) FROM transitions_saved) ts, (SELECT count(*) FROM tasks_archived) ta, "
            "(SELECT count(*) FROM layout_saved) ls WHERE c.uid=%(campaign_uid)s::uuid RETURNING c.uid) "
            f"INSERT INTO {_table('activity_event')} {ACTIVITY_COLUMNS} {self._activity('changed')} RETURNING entity_uid"
        )
        self._write(sql, params, types, conflict="Campaign graph version or prompt precondition failed")
        return self.campaign_detail(campaign_uid)

    # ----- step prompt writes ---------------------------------------------

    def create_step_prompt(self, actor_uid: uuid.UUID, data: dict[str, Any]) -> dict[str, Any]:
        uid = uuid.uuid4()
        params, types = self._audit(actor_uid, entity_type="prompt", kind="created", summary="Created campaign step prompt",
                                    changes={"campaign_step_prompt": True})
        params.update(uid=str(uid), name=data["name"], description=data.get("description"),
                      content_markdown=data["content_markdown"], inputs=json.dumps(data.get("inputs", [])),
                      result_fields=json.dumps(data.get("result_fields", [])))
        types.update(inputs="jsonb", result_fields="jsonb")
        sql = (
            f"WITH created AS (INSERT INTO {_table('prompt')} (uid, created_at, updated_at, created_by_uid, updated_by_uid, "
            "version, archived_at, name, description, content_markdown) VALUES (%(uid)s::uuid, NOW(), NOW(), "
            "%(actor_uid)s::uuid, %(actor_uid)s::uuid, 1, NULL, %(name)s, %(description)s, %(content_markdown)s) RETURNING uid), "
            f"extended AS (INSERT INTO {_table('campaign_step_prompt')} (uid, inputs, result_fields) "
            "SELECT created.uid, %(inputs)s::jsonb, %(result_fields)s::jsonb FROM created RETURNING uid) "
            f"INSERT INTO {_table('activity_event')} {ACTIVITY_COLUMNS} {self._activity('extended')} RETURNING entity_uid"
        )
        self._write(sql, params, types, conflict="Step prompt create precondition failed")
        return self.step_prompt_detail(uid)

    def specialize_prompt(self, actor_uid: uuid.UUID, prompt_uid: uuid.UUID, expected_version: int,
                          data: dict[str, Any]) -> dict[str, Any]:
        """Add the subtype to an existing Agent Prompt under its own version fence."""
        params, types = self._audit(actor_uid, entity_type="prompt", kind="updated", summary="Specialized prompt for campaigns",
                                    changes={"campaign_step_prompt": True})
        params.update(uid=str(prompt_uid), expected_version=expected_version, description=data.get("description"),
                      set_description=data.get("description") is not None,
                      inputs=json.dumps(data.get("inputs", [])), result_fields=json.dumps(data.get("result_fields", [])))
        types.update(inputs="jsonb", result_fields="jsonb")
        sql = (
            f"WITH changed AS (UPDATE {_table('prompt')} p SET description=CASE WHEN %(set_description)s::boolean "
            "THEN %(description)s ELSE p.description END, updated_at=NOW(), updated_by_uid=%(actor_uid)s::uuid, "
            "version=p.version+1 WHERE p.uid=%(uid)s::uuid AND p.version=%(expected_version)s::bigint "
            f"AND p.archived_at IS NULL AND NOT EXISTS (SELECT 1 FROM {_table('campaign_step_prompt')} sp WHERE sp.uid=p.uid) "
            "RETURNING p.uid), "
            f"extended AS (INSERT INTO {_table('campaign_step_prompt')} (uid, inputs, result_fields) "
            "SELECT changed.uid, %(inputs)s::jsonb, %(result_fields)s::jsonb FROM changed RETURNING uid) "
            f"INSERT INTO {_table('activity_event')} {ACTIVITY_COLUMNS} {self._activity('extended')} RETURNING entity_uid"
        )
        self._write(sql, params, types, conflict="Prompt version precondition failed or already specialized")
        return self.step_prompt_detail(prompt_uid)

    def update_step_prompt(self, actor_uid: uuid.UUID, uid: uuid.UUID, expected_version: int,
                           changes: dict[str, Any]) -> dict[str, Any]:
        event_changes = {key: (True if key == "content_markdown" else value) for key, value in changes.items()}
        if "content_markdown" in event_changes:
            event_changes = {**{k: v for k, v in event_changes.items() if k != "content_markdown"}, "content_markdown_changed": True}
        params, types = self._audit(actor_uid, entity_type="prompt", kind="updated", summary="Updated campaign step prompt",
                                    changes=event_changes)
        params.update(uid=str(uid), expected_version=expected_version)
        prompt_assignments = []
        for name in ("name", "description", "content_markdown"):
            if name in changes:
                params[name] = changes[name]
                prompt_assignments.append(f"{name}=%({name})s")
        extension_assignments = []
        for name in ("inputs", "result_fields"):
            if name in changes:
                params[name] = json.dumps(changes[name])
                types[name] = "jsonb"
                extension_assignments.append(f"{name}=%({name})s::jsonb")
        contract_changed = bool(extension_assignments) or "content_markdown" in changes
        params["contract_changed"] = contract_changed
        progress = _table("campaign_progress")
        ctes = [
            f"changed AS (UPDATE {_table('prompt')} p SET {', '.join(prompt_assignments + ['updated_at=NOW()'])}, "
            "updated_by_uid=%(actor_uid)s::uuid, version=p.version+1 WHERE p.uid=%(uid)s::uuid "
            "AND p.version=%(expected_version)s::bigint AND p.archived_at IS NULL "
            f"AND EXISTS (SELECT 1 FROM {_table('campaign_step_prompt')} sp WHERE sp.uid=p.uid) RETURNING p.uid)",
        ]
        if extension_assignments:
            ctes.append(
                f"extended AS (UPDATE {_table('campaign_step_prompt')} sp SET {', '.join(extension_assignments)} "
                "FROM changed WHERE sp.uid=changed.uid RETURNING sp.uid)"
            )
        # A changed instruction or contract is a changed exposure for open work and compared assignments.
        ctes.append(
            f"work_flagged AS (UPDATE {progress} g SET "
            f"state=CASE WHEN g.state IN ('open','waiting') THEN 'blocked' ELSE g.state END, "
            "blocked_reason=CASE WHEN g.state IN ('open','waiting') THEN 'prompt_changed' ELSE g.blocked_reason END, "
            "prompt_assignment=CASE WHEN jsonb_typeof(g.prompt_assignment->'comparison') = 'object' THEN jsonb_set(g.prompt_assignment, "
            "'{comparison_changed}', 'true'::jsonb) ELSE g.prompt_assignment END, updated_at=NOW() "
            "FROM changed WHERE %(contract_changed)s::boolean AND (g.prompt_assignment->>'prompt_uid')::uuid=changed.uid "
            "RETURNING g.uid)"
        )
        source = "changed CROSS JOIN (SELECT count(*) FROM work_flagged) flagged" + (
            " CROSS JOIN (SELECT count(*) FROM extended) ext" if extension_assignments else ""
        )
        sql = (
            "WITH " + ", ".join(ctes) + f" INSERT INTO {_table('activity_event')} {ACTIVITY_COLUMNS} "
            f"{self._activity(source)} RETURNING entity_uid"
        )
        self._write(sql, params, types, conflict="Prompt version precondition failed")
        return self.step_prompt_detail(uid)

    # ----- participant writes ---------------------------------------------

    def create_participant(self, actor_uid: uuid.UUID, data: dict[str, Any]) -> dict[str, Any]:
        uid = uuid.uuid4()
        params, types = self._audit(actor_uid, entity_type="campaign_participant", kind="created", summary="Enrolled contact",
                                    changes={"campaign_uid": str(data["campaign_uid"]), "contact_uid": str(data["contact_uid"])})
        params.update(uid=str(uid), campaign_uid=str(data["campaign_uid"]), contact_uid=str(data["contact_uid"]),
                      context=json.dumps(data.get("context", {})))
        types["context"] = "jsonb"
        participant = _table("campaign_participant")
        sql = (
            f"WITH locked AS MATERIALIZED (SELECT c.uid, c.entry_step_uid FROM {_table('campaign')} c "
            "WHERE c.uid=%(campaign_uid)s::uuid AND c.archived_at IS NULL FOR UPDATE), "
            "gate AS (SELECT locked.uid AS campaign_uid, locked.entry_step_uid FROM locked WHERE "
            f"EXISTS (SELECT 1 FROM {_table('contact')} ct WHERE ct.uid=%(contact_uid)s::uuid AND ct.archived_at IS NULL) "
            f"AND NOT EXISTS (SELECT 1 FROM {participant} p WHERE p.campaign_uid=locked.uid AND p.contact_uid=%(contact_uid)s::uuid)), "
            f"created AS (INSERT INTO {participant} (uid, created_at, updated_at, created_by_uid, updated_by_uid, version, "
            "archived_at, campaign_uid, contact_uid, status, context, next_step_uid, eligible_at, finished_at) "
            "SELECT %(uid)s::uuid, NOW(), NOW(), %(actor_uid)s::uuid, %(actor_uid)s::uuid, 1, NULL, gate.campaign_uid, "
            "%(contact_uid)s::uuid, 'active', %(context)s::jsonb, gate.entry_step_uid, "
            "CASE WHEN gate.entry_step_uid IS NULL THEN NULL ELSE NOW() END, NULL FROM gate RETURNING uid) "
            f"INSERT INTO {_table('activity_event')} {ACTIVITY_COLUMNS} {self._activity('created')} RETURNING entity_uid"
        )
        self._write(sql, params, types, conflict="Contact is already enrolled, archived, or the campaign is unavailable")
        return self.participant_detail(uid)

    def update_participant(self, actor_uid: uuid.UUID, uid: uuid.UUID, expected_version: int,
                           changes: dict[str, Any]) -> dict[str, Any]:
        params, types = self._audit(actor_uid, entity_type="campaign_participant", kind="updated",
                                    summary="Updated participant", changes=changes)
        params.update(uid=str(uid), expected_version=expected_version)
        participant, progress, task, step = _table("campaign_participant"), _table("campaign_progress"), _table("task"), _table("campaign_step")
        assignments = []
        if "context" in changes:
            params["context"] = json.dumps(changes["context"])
            types["context"] = "jsonb"
            assignments.append("context=%(context)s::jsonb")
        withdrawing = changes.get("status") == "withdrawn"
        if "status" in changes:
            params["status"] = changes["status"]
            assignments.append("status=%(status)s")
            if withdrawing:
                assignments.append("finished_at=NOW()")
                assignments.append("next_step_uid=NULL")
                assignments.append("eligible_at=NULL")
        reroute = "next_step_uid" in changes and not withdrawing
        gate_extra = ""
        if reroute:
            params["next_step_uid"] = str(changes["next_step_uid"])
            assignments.append("next_step_uid=%(next_step_uid)s::uuid")
            assignments.append("eligible_at=NOW()")
            gate_extra = (
                f" AND EXISTS (SELECT 1 FROM {step} s WHERE s.uid=%(next_step_uid)s::uuid AND s.campaign_uid=p.campaign_uid "
                f"AND s.archived_at IS NULL) AND NOT EXISTS (SELECT 1 FROM {progress} g WHERE g.participant_uid=p.uid "
                "AND g.step_uid=%(next_step_uid)s::uuid)"
            )
        ctes = [
            f"locked AS MATERIALIZED (SELECT p.uid FROM {participant} p WHERE p.uid=%(uid)s::uuid "
            f"AND p.version=%(expected_version)s::bigint AND p.status IN ('active','paused'){gate_extra} FOR UPDATE)",
        ]
        if withdrawing:
            ctes.extend([
                f"work_cancelled AS (UPDATE {progress} g SET state='cancelled', updated_at=NOW() FROM locked "
                f"WHERE g.participant_uid=locked.uid AND g.state IN {OPEN_STATES} RETURNING g.task_uid)",
                f"tasks_archived AS (UPDATE {task} t SET archived_at=COALESCE(t.archived_at, NOW()), updated_at=NOW(), "
                "updated_by_uid=%(actor_uid)s::uuid, version=t.version+1 FROM work_cancelled w WHERE t.uid=w.task_uid RETURNING t.uid)",
            ])
        dependency = " CROSS JOIN (SELECT count(*) FROM tasks_archived) ta" if withdrawing else ""
        ctes.append(
            f"changed AS (UPDATE {participant} p SET {', '.join(assignments)}, updated_at=NOW(), "
            f"updated_by_uid=%(actor_uid)s::uuid, version=p.version+1 FROM locked{dependency} WHERE p.uid=locked.uid RETURNING p.uid)"
        )
        sql = (
            "WITH " + ", ".join(ctes) + f" INSERT INTO {_table('activity_event')} {ACTIVITY_COLUMNS} "
            f"{self._activity('changed')} RETURNING entity_uid"
        )
        self._write(sql, params, types, conflict="Participant version, lifecycle or next-step precondition failed")
        return self.participant_detail(uid)

    # ----- progression -----------------------------------------------------

    def advance(self, actor_uid: uuid.UUID, participant_uid: uuid.UUID, expected_version: int, *,
                step_uid: uuid.UUID, step_version: int, prompt_assignment: dict[str, Any]) -> dict[str, Any]:
        """Create the eligible Task and its progress association exactly once."""
        participant, progress, task, step, campaign = (
            _table("campaign_participant"), _table("campaign_progress"), _table("task"), _table("campaign_step"), _table("campaign"),
        )
        params, types = self._audit(actor_uid, entity_type="campaign_participant", kind="advanced", summary="Created campaign task",
                                    changes={"step_uid": str(step_uid), "variant_key": prompt_assignment["variant_key"]})
        task_uid = uuid.uuid4()
        params.update(
            participant_uid=str(participant_uid), expected_version=expected_version, step_uid=str(step_uid),
            step_version=step_version, task_uid=str(task_uid),
            progress_uid=str(uuid.uuid5(participant_uid, str(step_uid))),
            prompt_uid=str(prompt_assignment["prompt_uid"]), prompt_version=prompt_assignment["assigned_prompt_version"],
            prompt_assignment=json.dumps(prompt_assignment, default=str),
            task_event_uid=str(uuid.uuid5(uuid.UUID(params["command_uid"]), "task-activity")),
        )
        types["prompt_assignment"] = "jsonb"
        sql = (
            f"WITH locked AS MATERIALIZED (SELECT p.uid, p.campaign_uid, p.contact_uid FROM {participant} p "
            "WHERE p.uid=%(participant_uid)s::uuid AND p.version=%(expected_version)s::bigint AND p.status='active' "
            "AND p.next_step_uid=%(step_uid)s::uuid AND (p.eligible_at IS NULL OR p.eligible_at <= NOW()) FOR UPDATE), "
            "gate AS (SELECT l.uid AS participant_uid, l.contact_uid, s.title, s.task_text, "
            "COALESCE(s.owner_uid, c.owner_uid) AS owner_uid, COALESCE(s.task_type_key, 'follow-up') AS type_key, "
            "CASE WHEN s.due_after_seconds IS NULL THEN NULL ELSE NOW() + make_interval(secs => s.due_after_seconds) END AS due_at "
            f"FROM locked l JOIN {campaign} c ON c.uid=l.campaign_uid JOIN {step} s ON s.uid=%(step_uid)s::uuid "
            "WHERE c.status='active' AND c.archived_at IS NULL AND s.campaign_uid=c.uid AND s.archived_at IS NULL "
            "AND s.version=%(step_version)s::bigint "
            f"AND EXISTS (SELECT 1 FROM {_table('prompt')} pr WHERE pr.uid=%(prompt_uid)s::uuid "
            "AND pr.version=%(prompt_version)s::bigint AND pr.archived_at IS NULL) "
            f"AND NOT EXISTS (SELECT 1 FROM {progress} g WHERE g.participant_uid=l.uid AND g.step_uid=%(step_uid)s::uuid)), "
            f"task_created AS (INSERT INTO {task} (uid, created_at, updated_at, created_by_uid, updated_by_uid, version, "
            "archived_at, contact_uid, owner_uid, type_key, text, due_at, completed_at, completed_by_uid, source_created_at, "
            "source_updated_at) SELECT %(task_uid)s::uuid, NOW(), NOW(), %(actor_uid)s::uuid, %(actor_uid)s::uuid, 1, NULL, "
            "gate.contact_uid, gate.owner_uid, gate.type_key, gate.title || E'\\n\\n' || gate.task_text, gate.due_at, "
            "NULL, NULL, NULL, NULL FROM gate RETURNING uid), "
            f"progress_created AS (INSERT INTO {progress} (uid, participant_uid, {PROGRESS_COLUMNS}) "
            "SELECT %(progress_uid)s::uuid, gate.participant_uid, %(step_uid)s::uuid, task_created.uid, "
            "%(prompt_assignment)s::jsonb, 'open', NULL, '{}'::jsonb, '[]'::jsonb, NULL, NULL, NULL, NULL, NOW(), NOW() "
            "FROM gate, task_created RETURNING uid), "
            # next_step_uid keeps pointing at the current step until completion routes onward,
            # so a repeated advance finds the existing instance instead of nothing scheduled.
            f"changed AS (UPDATE {participant} p SET updated_at=NOW(), "
            "updated_by_uid=%(actor_uid)s::uuid, version=p.version+1 FROM progress_created WHERE p.uid=%(participant_uid)s::uuid "
            "RETURNING p.uid) "
            f"INSERT INTO {_table('activity_event')} {ACTIVITY_COLUMNS} {self._activity('changed')} "
            "UNION ALL SELECT %(task_event_uid)s::uuid, 'task', task_created.uid, 'created', NOW(), NOW(), %(actor_uid)s::uuid, "
            "'live', %(command_uid)s::uuid, 'Created campaign task', '{}'::jsonb, NULL::jsonb FROM task_created, changed "
            "RETURNING entity_uid"
        )
        self._write(sql, params, types, conflict="Participant is not eligible for this step, or it was already advanced", max_rows=2)
        return self.participant_detail(participant_uid)

    def complete(self, actor_uid: uuid.UUID, *, participant_uid: uuid.UUID, expected_version: int, step_uid: uuid.UUID,
                 task_uid: uuid.UUID, task_expected_version: int, campaign_version: int, step_version: int,
                 outcome_key: str, result: dict[str, Any], evidence: list[dict[str, Any]],
                 prepared_with: dict[str, Any]) -> dict[str, Any]:
        """Settle the Task, record the result and select the live transition atomically."""
        participant, progress, task, transition, step, campaign = (
            _table("campaign_participant"), _table("campaign_progress"), _table("task"),
            _table("campaign_transition"), _table("campaign_step"), _table("campaign"),
        )
        params, types = self._audit(actor_uid, entity_type="campaign_participant", kind="step_completed",
                                    summary="Completed campaign step", changes={"step_uid": str(step_uid), "outcome_key": outcome_key})
        params.update(
            participant_uid=str(participant_uid), expected_version=expected_version, step_uid=str(step_uid),
            task_uid=str(task_uid), task_expected_version=task_expected_version, campaign_version=campaign_version,
            step_version=step_version, outcome_key=outcome_key, result=json.dumps(result), evidence=json.dumps(evidence, default=str),
            prepared_with=json.dumps(prepared_with, default=str),
            task_event_uid=str(uuid.uuid5(uuid.UUID(params["command_uid"]), "task-activity")),
        )
        types.update(result="jsonb", evidence="jsonb", prepared_with="jsonb")
        sql = (
            f"WITH locked AS MATERIALIZED (SELECT p.uid, p.campaign_uid FROM {participant} p WHERE p.uid=%(participant_uid)s::uuid "
            "AND p.version=%(expected_version)s::bigint AND p.status='active' FOR UPDATE), "
            f"route AS (SELECT t.to_step_uid, t.delay_seconds FROM {transition} t JOIN {step} s ON s.uid=t.from_step_uid "
            f"JOIN {campaign} c ON c.uid=s.campaign_uid JOIN locked l ON l.campaign_uid=c.uid "
            "WHERE t.from_step_uid=%(step_uid)s::uuid AND t.outcome_key=%(outcome_key)s AND c.version=%(campaign_version)s::bigint "
            "AND s.version=%(step_version)s::bigint AND c.status='active' AND c.archived_at IS NULL), "
            "gate AS (SELECT l.uid AS participant_uid, r.to_step_uid, r.delay_seconds FROM locked l CROSS JOIN route r "
            f"WHERE EXISTS (SELECT 1 FROM {progress} g WHERE g.participant_uid=l.uid AND g.step_uid=%(step_uid)s::uuid "
            f"AND g.task_uid=%(task_uid)s::uuid AND g.state IN {OPEN_STATES})), "
            f"task_done AS (UPDATE {task} t SET completed_at=COALESCE(t.completed_at, NOW()), "
            "completed_by_uid=COALESCE(t.completed_by_uid, %(actor_uid)s::uuid), updated_at=NOW(), updated_by_uid=%(actor_uid)s::uuid, "
            "version=t.version+1 FROM gate WHERE t.uid=%(task_uid)s::uuid AND t.version=%(task_expected_version)s::bigint "
            "AND t.archived_at IS NULL RETURNING t.uid), "
            f"progress_done AS (UPDATE {progress} g SET state='completed', outcome_key=%(outcome_key)s, result=%(result)s::jsonb, "
            "evidence=g.evidence || %(evidence)s::jsonb, prepared_with=%(prepared_with)s::jsonb, blocked_reason=NULL, wake_at=NULL, "
            "completed_at=NOW(), updated_at=NOW() FROM gate, task_done WHERE g.participant_uid=gate.participant_uid "
            "AND g.step_uid=%(step_uid)s::uuid RETURNING g.uid), "
            f"changed AS (UPDATE {participant} p SET next_step_uid=gate.to_step_uid, "
            "eligible_at=CASE WHEN gate.to_step_uid IS NULL THEN NULL ELSE NOW() + make_interval(secs => gate.delay_seconds) END, "
            "status=CASE WHEN gate.to_step_uid IS NULL THEN 'completed' ELSE p.status END, "
            "finished_at=CASE WHEN gate.to_step_uid IS NULL THEN NOW() ELSE p.finished_at END, updated_at=NOW(), "
            "updated_by_uid=%(actor_uid)s::uuid, version=p.version+1 FROM gate, progress_done WHERE p.uid=gate.participant_uid "
            "RETURNING p.uid) "
            f"INSERT INTO {_table('activity_event')} {ACTIVITY_COLUMNS} {self._activity('changed')} "
            "UNION ALL SELECT %(task_event_uid)s::uuid, 'task', task_done.uid, 'completed', NOW(), NOW(), %(actor_uid)s::uuid, "
            "'live', %(command_uid)s::uuid, 'Completed campaign task', '{}'::jsonb, NULL::jsonb FROM task_done, changed "
            "RETURNING entity_uid"
        )
        self._write(sql, params, types, conflict="Completion precondition failed: version, task, lifecycle or route changed", max_rows=2)
        return self.participant_detail(participant_uid)

    def record(self, actor_uid: uuid.UUID, *, participant_uid: uuid.UUID, expected_version: int, step_uid: uuid.UUID,
               kind: str, evidence: list[dict[str, Any]], wake_at: str | None = None, blocked_reason: str | None = None,
               result: dict[str, Any] | None = None, outcome_key: str | None = None,
               prepared_with: dict[str, Any] | None = None) -> dict[str, Any]:
        """Record a wait, a block, observed facts or a stale result without routing."""
        participant, progress = _table("campaign_participant"), _table("campaign_progress")
        params, types = self._audit(actor_uid, entity_type="campaign_participant", kind=f"progress_{kind}",
                                    summary=f"Recorded campaign task {kind}", changes={"step_uid": str(step_uid)})
        params.update(
            participant_uid=str(participant_uid), expected_version=expected_version, step_uid=str(step_uid),
            evidence=json.dumps(evidence, default=str), wake_at=wake_at, blocked_reason=blocked_reason,
            result=None if result is None else json.dumps(result), outcome_key=outcome_key,
            prepared_with=None if prepared_with is None else json.dumps(prepared_with, default=str),
            record_kind=kind,
        )
        types.update(evidence="jsonb", result="jsonb", prepared_with="jsonb")
        state = {
            "wait": "'waiting'", "block": "'blocked'", "report": "g.state", "stale_result": "'blocked'",
        }[kind]
        sql = (
            f"WITH locked AS MATERIALIZED (SELECT p.uid FROM {participant} p WHERE p.uid=%(participant_uid)s::uuid "
            "AND p.version=%(expected_version)s::bigint AND p.status IN ('active','paused') FOR UPDATE), "
            f"recorded AS (UPDATE {progress} g SET state={state}, "
            "wake_at=CASE WHEN %(record_kind)s::text='wait' THEN %(wake_at)s::timestamptz "
            "WHEN %(record_kind)s::text='report' THEN g.wake_at ELSE NULL END, "
            "blocked_reason=CASE WHEN %(record_kind)s::text IN ('block','stale_result') THEN %(blocked_reason)s::text "
            "WHEN %(record_kind)s::text='report' THEN g.blocked_reason ELSE NULL END, "
            "evidence=g.evidence || %(evidence)s::jsonb, "
            "result=CASE WHEN %(result)s::jsonb IS NULL THEN g.result ELSE g.result || %(result)s::jsonb END, "
            "outcome_key=COALESCE(%(outcome_key)s::text, g.outcome_key), "
            "prepared_with=COALESCE(%(prepared_with)s::jsonb, g.prepared_with), updated_at=NOW() "
            f"FROM locked WHERE g.participant_uid=locked.uid AND g.step_uid=%(step_uid)s::uuid AND g.state IN {OPEN_STATES} "
            "RETURNING g.participant_uid), "
            f"changed AS (UPDATE {participant} p SET updated_at=NOW(), updated_by_uid=%(actor_uid)s::uuid, version=p.version+1 "
            "FROM recorded WHERE p.uid=recorded.participant_uid RETURNING p.uid) "
            f"INSERT INTO {_table('activity_event')} {ACTIVITY_COLUMNS} {self._activity('changed')} RETURNING entity_uid"
        )
        self._write(sql, params, types, conflict="Participant version or task state precondition failed")
        return self.participant_detail(participant_uid)

    def reconcile_reopen(self, actor_uid: uuid.UUID, *, participant_uid: uuid.UUID, expected_version: int,
                         step_uid: uuid.UUID, task_uid: uuid.UUID, task_expected_version: int) -> dict[str, Any]:
        participant, progress, task = _table("campaign_participant"), _table("campaign_progress"), _table("task")
        params, types = self._audit(actor_uid, entity_type="campaign_participant", kind="progress_reopened",
                                    summary="Reopened campaign task for reconciliation", changes={"step_uid": str(step_uid)})
        params.update(participant_uid=str(participant_uid), expected_version=expected_version, step_uid=str(step_uid),
                      task_uid=str(task_uid), task_expected_version=task_expected_version)
        sql = (
            f"WITH locked AS MATERIALIZED (SELECT p.uid FROM {participant} p WHERE p.uid=%(participant_uid)s::uuid "
            "AND p.version=%(expected_version)s::bigint AND p.status IN ('active','paused') FOR UPDATE), "
            f"task_open AS (UPDATE {task} t SET completed_at=NULL, completed_by_uid=NULL, archived_at=NULL, updated_at=NOW(), "
            "updated_by_uid=%(actor_uid)s::uuid, version=t.version+1 FROM locked WHERE t.uid=%(task_uid)s::uuid "
            "AND t.version=%(task_expected_version)s::bigint RETURNING t.uid), "
            f"reopened AS (UPDATE {progress} g SET state='open', blocked_reason=NULL, wake_at=NULL, completed_at=NULL, updated_at=NOW() "
            "FROM locked, task_open WHERE g.participant_uid=locked.uid AND g.step_uid=%(step_uid)s::uuid "
            "AND g.task_uid=task_open.uid AND g.state IN ('blocked','waiting','completed') RETURNING g.participant_uid), "
            f"changed AS (UPDATE {participant} p SET updated_at=NOW(), updated_by_uid=%(actor_uid)s::uuid, version=p.version+1 "
            "FROM reopened WHERE p.uid=reopened.participant_uid RETURNING p.uid) "
            f"INSERT INTO {_table('activity_event')} {ACTIVITY_COLUMNS} {self._activity('changed')} RETURNING entity_uid"
        )
        self._write(sql, params, types, conflict="Reopen precondition failed: version or task state changed")
        return self.participant_detail(participant_uid)

    def reconcile_cancel(self, actor_uid: uuid.UUID, *, participant_uid: uuid.UUID, expected_version: int,
                         step_uid: uuid.UUID, task_uid: uuid.UUID, task_expected_version: int,
                         next_step_uid: uuid.UUID | None, finish: bool) -> dict[str, Any]:
        """Archive the instance (never falsely complete it) and reroute or finish the participant."""
        participant, progress, task, step = _table("campaign_participant"), _table("campaign_progress"), _table("task"), _table("campaign_step")
        params, types = self._audit(actor_uid, entity_type="campaign_participant", kind="progress_cancelled",
                                    summary="Cancelled campaign task", changes={"step_uid": str(step_uid), "finish": finish,
                                                                                 "next_step_uid": None if next_step_uid is None else str(next_step_uid)})
        params.update(participant_uid=str(participant_uid), expected_version=expected_version, step_uid=str(step_uid),
                      task_uid=str(task_uid), task_expected_version=task_expected_version,
                      next_step_uid=None if next_step_uid is None else str(next_step_uid), finish=finish)
        sql = (
            f"WITH locked AS MATERIALIZED (SELECT p.uid, p.campaign_uid FROM {participant} p WHERE p.uid=%(participant_uid)s::uuid "
            "AND p.version=%(expected_version)s::bigint AND p.status IN ('active','paused') FOR UPDATE), "
            "gate AS (SELECT l.uid FROM locked l WHERE %(finish)s::boolean OR EXISTS (SELECT 1 FROM "
            f"{step} s WHERE s.uid=%(next_step_uid)s::uuid AND s.campaign_uid=l.campaign_uid AND s.archived_at IS NULL "
            f"AND NOT EXISTS (SELECT 1 FROM {progress} g WHERE g.participant_uid=l.uid AND g.step_uid=s.uid))), "
            f"task_archived AS (UPDATE {task} t SET archived_at=COALESCE(t.archived_at, NOW()), updated_at=NOW(), "
            "updated_by_uid=%(actor_uid)s::uuid, version=t.version+1 FROM gate WHERE t.uid=%(task_uid)s::uuid "
            "AND t.version=%(task_expected_version)s::bigint RETURNING t.uid), "
            f"cancelled AS (UPDATE {progress} g SET state='cancelled', updated_at=NOW() FROM gate, task_archived "
            "WHERE g.participant_uid=gate.uid AND g.step_uid=%(step_uid)s::uuid AND g.task_uid=task_archived.uid "
            f"AND g.state IN {OPEN_STATES} RETURNING g.participant_uid), "
            f"changed AS (UPDATE {participant} p SET next_step_uid=CASE WHEN %(finish)s::boolean THEN NULL ELSE %(next_step_uid)s::uuid END, "
            "eligible_at=CASE WHEN %(finish)s::boolean THEN NULL ELSE NOW() END, "
            "status=CASE WHEN %(finish)s::boolean THEN 'completed' ELSE p.status END, "
            "finished_at=CASE WHEN %(finish)s::boolean THEN NOW() ELSE p.finished_at END, updated_at=NOW(), "
            "updated_by_uid=%(actor_uid)s::uuid, version=p.version+1 FROM cancelled WHERE p.uid=cancelled.participant_uid RETURNING p.uid) "
            f"INSERT INTO {_table('activity_event')} {ACTIVITY_COLUMNS} {self._activity('changed')} RETURNING entity_uid"
        )
        self._write(sql, params, types, conflict="Cancel precondition failed: version, task state or next step unavailable")
        return self.participant_detail(participant_uid)
