"""Shared governed persistence for versioned core and extension records."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from src.crm.metatables import MODELS
from src.crm.models.interactions import Interaction, InteractionCreate
from src.crm.repositories.errors import ResourceConflict, ResourceNotFound
from src.crm.repositories.gateway import GovernedGateway
from src.crm.solution_selling.models import (
    AssessmentCreate,
    DiagnosisCreate,
    LeadCreate,
    PrompterCreate,
    ProspectingProfileCreate,
    SolutionSelling,
    SolutionSellingDiagnosis,
    SolutionSellingLead,
    SolutionSellingPrompter,
    SolutionSellingProspectingProfile,
)


@dataclass(frozen=True)
class RecordSpec:
    table: str
    create: type[BaseModel]
    read: type[BaseModel]
    search: tuple[str, ...]
    filters: tuple[str, ...]
    order: str


RECORDS: dict[str, RecordSpec] = {
    "interactions": RecordSpec(
        "interaction",
        InteractionCreate,
        Interaction,
        ("subject",),
        ("company_uid", "contact_uid", "deal_uid", "kind", "status"),
        "scheduled_at",
    ),
    "assessments": RecordSpec(
        "solution_selling",
        AssessmentCreate,
        SolutionSelling,
        ("pain_summary", "vision_summary"),
        ("company_uid", "deal_uid"),
        "updated_at",
    ),
    "diagnoses": RecordSpec(
        "solution_selling_diagnosis",
        DiagnosisCreate,
        SolutionSellingDiagnosis,
        ("business_issue", "conclusion"),
        ("interaction_uid", "contact_uid", "solution_selling_uid"),
        "updated_at",
    ),
    "prospecting-profiles": RecordSpec(
        "solution_selling_prospecting_profile",
        ProspectingProfileCreate,
        SolutionSellingProspectingProfile,
        ("name", "market_context", "role", "potential_pain"),
        ("market_context", "role"),
        "updated_at",
    ),
    "leads": RecordSpec(
        "solution_selling_lead",
        LeadCreate,
        SolutionSellingLead,
        ("notes",),
        ("contact_uid", "profile_uid", "owner_uid", "status"),
        "updated_at",
    ),
    "prompters": RecordSpec(
        "solution_selling_prompter",
        PrompterCreate,
        SolutionSellingPrompter,
        ("name", "kind", "description"),
        ("kind",),
        "updated_at",
    ),
}

JSON_FIELDS = {
    "key_players",
    "pain_chain",
    "matrix",
    "likely_reasons",
    "likely_impacts",
    "diagnosis_template",
}
TIMESTAMP_FIELDS = {"scheduled_at", "occurred_at"}
REFERENCE_FIELDS = {
    "interactions": {"company_uid": "company", "contact_uid": "contact", "deal_uid": "deal"},
    "assessments": {
        "company_uid": "company", "deal_uid": "deal", "pain_contact_uid": "contact",
        "power_contact_uid": "contact", "sponsor_contact_uid": "contact",
    },
    "diagnoses": {
        "interaction_uid": "interaction", "contact_uid": "contact",
        "solution_selling_uid": "solution_selling",
    },
    "leads": {
        "contact_uid": "contact", "profile_uid": "solution_selling_prospecting_profile",
        "next_task_uid": "task",
    },
}


class VersionedRecordStore(GovernedGateway):
    """One small gateway; domain rules stay in Pydantic and SQL predicates."""

    def collection(
        self,
        resource: str,
        *,
        page_index: int,
        page_size: int,
        search: str | None,
        filters: dict[str, str],
    ) -> dict[str, Any]:
        spec = RECORDS[resource]
        if set(filters) - set(spec.filters):
            raise ValueError("Unsupported collection filter")
        table = MODELS[spec.table].__tablename__
        conditions = ["t.archived_at IS NULL"]
        params: dict[str, Any] = {"limit": page_size, "offset": page_index * page_size}
        for name, value in filters.items():
            params[f"f_{name}"] = value
            cast = "::uuid" if name.endswith("_uid") else ""
            conditions.append(f"t.{name}=%(f_{name})s{cast}")
        if search:
            params["search"] = (
                "%"
                + search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_").casefold()
                + "%"
            )
            conditions.append(
                "("
                + " OR ".join(
                    f"lower(coalesce(t.{field}::text, '')) LIKE %(search)s ESCAPE '\\'"
                    for field in spec.search
                )
                + ")"
            )
        where = " AND ".join(conditions)
        sql = (
            f'WITH q AS (SELECT t.* FROM "{table}" t WHERE {where}), '
            "paged AS (SELECT q.*, row_number() OVER () AS __row FROM q "
            f"ORDER BY {spec.order} DESC NULLS LAST, uid DESC "
            "LIMIT %(limit)s::integer OFFSET %(offset)s::integer) "
            "SELECT COALESCE((SELECT jsonb_agg(to_jsonb(paged) - '__row' ORDER BY __row) "
            "FROM paged), '[]'::jsonb) AS items, (SELECT count(*) FROM q) AS total_items"
        )
        result = self._operation(
            operation="select",
            sql=sql,
            parameters=params,
            parameter_types={},
            tables={spec.table: "read"},
            max_rows=1,
        )
        rows = result.get("rows")
        if not isinstance(rows, list) or len(rows) != 1:
            raise RuntimeError("Invalid CRM collection response")
        items = self._json(rows[0]["items"], expected=list, label=resource)
        items = [spec.read.model_validate(item).model_dump(mode="json") for item in items]
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

    def detail(self, resource: str, uid: uuid.UUID) -> dict[str, Any]:
        spec = RECORDS[resource]
        table = MODELS[spec.table].__tablename__
        result = self._operation(
            operation="select",
            sql=f'SELECT to_jsonb(t) AS item FROM "{table}" t WHERE t.uid=%(uid)s::uuid AND t.archived_at IS NULL',
            parameters={"uid": str(uid)},
            parameter_types={},
            tables={spec.table: "read"},
            max_rows=1,
        )
        rows = result.get("rows")
        if not isinstance(rows, list) or not rows:
            raise ResourceNotFound(f"{resource} record not found")
        item = self._json(rows[0]["item"], expected=dict, label=resource)
        return spec.read.model_validate(item).model_dump(mode="json")

    @staticmethod
    def _bound(name: str, value: Any) -> tuple[Any, str]:
        if name in JSON_FIELDS:
            return (None if value is None else json.dumps(value), f"%({name})s::jsonb")
        if name.endswith("_uid"):
            return (value, f"%({name})s::uuid")
        if name in TIMESTAMP_FIELDS:
            return (value, f"%({name})s::timestamptz")
        return value, f"%({name})s"

    @staticmethod
    def _predicate(
        resource: str, data: dict[str, Any], *, creating: bool
    ) -> tuple[str, dict[str, str]]:
        """Cross-record invariants checked in the same governed write statement."""
        clauses: list[str] = []
        refs: dict[str, str] = {}
        for field, logical in REFERENCE_FIELDS.get(resource, {}).items():
            if data.get(field) is None:
                continue
            table = MODELS[logical].__tablename__
            clauses.append(
                f'EXISTS (SELECT 1 FROM "{table}" ref WHERE ref.uid=%({field})s::uuid '
                "AND ref.archived_at IS NULL)"
            )
            refs[logical] = "read"
        if creating and resource in {"assessments", "leads"}:
            key = "deal_uid" if resource == "assessments" else "contact_uid"
            table = MODELS[RECORDS[resource].table].__tablename__
            clauses.append(
                f'NOT EXISTS (SELECT 1 FROM "{table}" duplicate '
                f'WHERE duplicate.{key}=%({key})s::uuid)'
            )
        if resource == "assessments" and data.get("key_players"):
            contact = MODELS["contact"].__tablename__
            clauses.append(
                "NOT EXISTS (SELECT 1 FROM jsonb_array_elements(%(key_players)s::jsonb) p "
                f"LEFT JOIN \"{contact}\" c ON c.uid=(p->>'contact_uid')::uuid "
                "WHERE c.uid IS NULL OR c.archived_at IS NOT NULL)"
            )
            refs["contact"] = "read"
        if resource == "leads" and data.get("next_task_uid"):
            task = MODELS["task"].__tablename__
            clauses.append(
                f'EXISTS (SELECT 1 FROM "{task}" task WHERE task.uid=%(next_task_uid)s::uuid '
                "AND task.contact_uid=%(contact_uid)s::uuid AND task.completed_at IS NULL "
                "AND task.archived_at IS NULL)"
            )
            refs["task"] = "read"
        if resource == "diagnoses" and data.get("solution_selling_uid"):
            assessment = MODELS["solution_selling"].__tablename__
            interaction = MODELS["interaction"].__tablename__
            clauses.append(
                f'EXISTS (SELECT 1 FROM "{assessment}" s JOIN "{interaction}" i '
                "ON i.company_uid=s.company_uid AND (i.deal_uid IS NULL OR i.deal_uid=s.deal_uid) "
                "WHERE s.uid=%(solution_selling_uid)s::uuid "
                "AND i.uid=%(interaction_uid)s::uuid "
                "AND s.archived_at IS NULL AND i.archived_at IS NULL)"
            )
            refs["solution_selling"] = "read"
            refs["interaction"] = "read"
        if resource == "interactions" and not creating:
            diagnosis = MODELS["solution_selling_diagnosis"].__tablename__
            assessment = MODELS["solution_selling"].__tablename__
            clauses.append(
                f'NOT EXISTS (SELECT 1 FROM "{diagnosis}" d JOIN "{assessment}" s '
                "ON s.uid=d.solution_selling_uid WHERE d.interaction_uid=%(uid)s::uuid "
                "AND (s.company_uid IS DISTINCT FROM %(company_uid)s::uuid OR "
                "(%(deal_uid)s::uuid IS NOT NULL AND s.deal_uid IS DISTINCT FROM %(deal_uid)s::uuid)))"
            )
            refs["solution_selling_diagnosis"] = "read"
            refs["solution_selling"] = "read"
        return (" AND " + " AND ".join(clauses) if clauses else ""), refs

    def create(self, resource: str, actor_uid: uuid.UUID, payload: BaseModel) -> dict[str, Any]:
        spec = RECORDS[resource]
        data = payload.model_dump(mode="json")
        uid, command_uid = uuid.uuid4(), uuid.uuid4()
        table = MODELS[spec.table].__tablename__
        activity = MODELS["activity_event"].__tablename__
        columns = [
            "uid",
            "created_at",
            "updated_at",
            "created_by_uid",
            "updated_by_uid",
            "version",
            "archived_at",
        ]
        values = [
            "%(uid)s::uuid",
            "NOW()",
            "NOW()",
            "%(actor_uid)s::uuid",
            "%(actor_uid)s::uuid",
            "1",
            "NULL",
        ]
        params: dict[str, Any] = {
            "uid": str(uid),
            "actor_uid": str(actor_uid),
            "event_uid": str(uuid.uuid4()),
            "command_uid": str(command_uid),
            "entity_type": spec.table,
        }
        for name, value in data.items():
            columns.append(name)
            params[name], bound = self._bound(name, value)
            values.append(bound)
        predicate, refs = self._predicate(resource, data, creating=True)
        sql = (
            f"WITH gate AS (SELECT 1 WHERE TRUE {predicate}), "
            f'created AS (INSERT INTO "{table}" ({", ".join(columns)}) '
            f"SELECT {', '.join(values)} FROM gate RETURNING uid) "
            f'INSERT INTO "{activity}" (uid, entity_type, entity_uid, kind, occurred_at, '
            "recorded_at, actor_uid, origin, command_uid, summary, changes, source_attribution) "
            "SELECT %(event_uid)s::uuid, %(entity_type)s, created.uid, 'created', NOW(), NOW(), "
            "%(actor_uid)s::uuid, 'live', %(command_uid)s::uuid, 'Created record', '{}'::jsonb, NULL "
            "FROM created RETURNING entity_uid"
        )
        result = self._operation(
            operation="insert",
            sql=sql,
            parameters=params,
            parameter_types={name: "jsonb" for name in JSON_FIELDS if name in params},
            tables={**refs, spec.table: "write", "activity_event": "write"},
            max_rows=1,
        )
        if not result.get("rows"):
            raise ResourceConflict("Relationship precondition failed")
        return self.detail(resource, uid)

    def update(
        self,
        resource: str,
        actor_uid: uuid.UUID,
        uid: uuid.UUID,
        expected_version: int,
        data: dict[str, Any],
        candidate: BaseModel,
    ) -> dict[str, Any]:
        spec = RECORDS[resource]
        table = MODELS[spec.table].__tablename__
        activity = MODELS["activity_event"].__tablename__
        complete = candidate.model_dump(mode="json")
        params: dict[str, Any] = {
            "uid": str(uid),
            "actor_uid": str(actor_uid),
            "expected_version": expected_version,
            "event_uid": str(uuid.uuid4()),
            "command_uid": str(uuid.uuid4()),
            "entity_type": spec.table,
            "event_changes": json.dumps(data),
        }
        assignments: list[str] = []
        for name, value in data.items():
            params[name], bound = self._bound(name, value)
            assignments.append(f"{name}={bound}")
        # Predicates use the full candidate, including unchanged relationship keys.
        for name, value in complete.items():
            if name not in params:
                params[name], _ = self._bound(name, value)
        predicate, refs = self._predicate(resource, complete, creating=False)
        sql = (
            f"WITH gate AS (SELECT 1 WHERE TRUE {predicate}), "
            f'changed AS (UPDATE "{table}" t SET {", ".join(assignments)}, '
            "updated_at=NOW(), updated_by_uid=%(actor_uid)s::uuid, version=t.version+1 "
            "FROM gate WHERE t.uid=%(uid)s::uuid AND t.version=%(expected_version)s::bigint "
            "AND t.archived_at IS NULL RETURNING t.uid) "
            f'INSERT INTO "{activity}" (uid, entity_type, entity_uid, kind, occurred_at, '
            "recorded_at, actor_uid, origin, command_uid, summary, changes, source_attribution) "
            "SELECT %(event_uid)s::uuid, %(entity_type)s, changed.uid, 'updated', NOW(), NOW(), "
            "%(actor_uid)s::uuid, 'live', %(command_uid)s::uuid, 'Updated record', "
            "%(event_changes)s::jsonb, NULL FROM changed RETURNING entity_uid"
        )
        result = self._operation(
            operation="insert",
            sql=sql,
            parameters=params,
            parameter_types={name: "jsonb" for name in JSON_FIELDS if name in params}
            | {"event_changes": "jsonb"},
            tables={**refs, spec.table: "write", "activity_event": "write"},
            max_rows=1,
        )
        if not result.get("rows"):
            raise ResourceConflict("Record version or relationship precondition failed")
        return self.detail(resource, uid)
