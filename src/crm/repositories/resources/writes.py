"""Shared governed create, update, and archive commands."""

from __future__ import annotations

import json
import uuid
from typing import Any

from ...metatables import MODELS
from ..errors import ResourceConflict
from ..gateway import GovernedGateway
from .catalog import RESOURCE_SPECS
from .reads import ResourceReads


class ResourceMutations(GovernedGateway):
    def __init__(self, registry, reads: ResourceReads):
        super().__init__(registry)
        self.reads = reads

    @staticmethod
    def _create_values(resource: str, data: dict[str, Any], actor_uid: uuid.UUID) -> dict[str, Any]:
        nullable_defaults = {
            "companies": {
                "owner_uid": None,
                "sector_key": None,
                "size_category": None,
                "linkedin_url": None,
                "website": None,
                "normalized_domain": None,
                "phone_number": None,
                "address": None,
                "zipcode": None,
                "city": None,
                "state_abbr": None,
                "country": None,
                "description": None,
                "revenue_text": None,
                "tax_identifier": None,
                "context_links": [],
                "logo_ref": None,
                "source_created_at": None,
                "source_updated_at": None,
            },
            "contacts": {
                "owner_uid": None,
                "company_uid": None,
                "first_name": None,
                "last_name": None,
                "title": None,
                "gender": None,
                "background": None,
                "avatar_ref": None,
                "socials": {},
                "emails": [],
                "phones": [],
                "first_seen": None,
                "last_seen": None,
                "has_newsletter": None,
                "status_key": None,
                "source_created_at": None,
                "source_updated_at": None,
            },
            "deals": {
                "owner_uid": None,
                "company_uid": None,
                "category_key": None,
                "description": None,
                "amount": None,
                "expected_closing_date": None,
                "source_created_at": None,
                "source_updated_at": None,
            },
            "tasks": {
                "owner_uid": None,
                "type_key": "follow-up",
                "due_at": None,
                "completed_at": None,
                "completed_by_uid": None,
                "source_created_at": None,
                "source_updated_at": None,
            },
            "notes": {
                "contact_uid": None,
                "deal_uid": None,
                "author_uid": str(actor_uid),
                "source_author_label": None,
                "status_key": None,
                "legacy_type": None,
                "attachment_refs": [],
            },
            "tags": {"tone": None, "legacy_color": None},
        }[resource]
        values = {**nullable_defaults, **data}
        if resource == "tags":
            values["normalized_name"] = values["name"].strip().casefold()
        return values

    def create(
        self,
        resource: str,
        actor_uid: uuid.UUID,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        definition = RESOURCE_SPECS[resource]
        command_uid = uuid.uuid4()
        entity_uid = uuid.uuid4()
        values = self._create_values(resource, data, actor_uid)
        relation_values = (
            values.pop("tag_uids" if resource == "contacts" else "contact_uids", [])
            if resource in {"contacts", "deals"}
            else []
        )
        columns = [
            "uid",
            "created_at",
            "updated_at",
            "created_by_uid",
            "updated_by_uid",
            "version",
            "archived_at",
        ]
        expressions = [
            "%(entity_uid)s::uuid",
            "NOW()",
            "NOW()",
            "%(actor_uid)s::uuid",
            "%(actor_uid)s::uuid",
            "1",
            "NULL",
        ]
        parameters: dict[str, Any] = {
            "entity_uid": str(entity_uid),
            "actor_uid": str(actor_uid),
            "command_uid": str(command_uid),
            "event_uid": str(uuid.uuid5(command_uid, "activity")),
            "summary": f"Created {definition.item_label.lower()}",
        }
        parameter_types = {
            "entity_uid": "uuid",
            "actor_uid": "uuid",
            "command_uid": "uuid",
            "event_uid": "uuid",
            "summary": "string",
        }
        for name, value in values.items():
            columns.append(name)
            parameter_value, parameter_type, expression = self._parameter(name, value)
            parameters[name] = parameter_value
            parameter_types[name] = parameter_type
            expressions.append(expression)
        if resource == "deals":
            columns.append("position")
            deal_table = MODELS["deal"].__tablename__
            expressions.append(
                f'(SELECT COALESCE(max(existing.position) + 1, 0) FROM "{deal_table}" existing '
                "WHERE existing.stage_uid=CAST(%(stage_uid)s AS uuid) "
                "AND existing.archived_at IS NULL)"
            )
        gate_predicates, reference_tables = self._create_predicates(
            resource, values, relation_values
        )
        entity_table = MODELS[definition.logical_table].__tablename__
        activity_table = MODELS["activity_event"].__tablename__
        ctes = [
            "gate AS (SELECT 1 AS ready WHERE TRUE" + gate_predicates + ")",
            f'created AS (INSERT INTO "{entity_table}" ({", ".join(columns)}) '
            f"SELECT {', '.join(expressions)} FROM gate RETURNING *)",
        ]
        relation_table = None
        if resource in {"contacts", "deals"}:
            relation_logical = "contact_tag" if resource == "contacts" else "deal_contact"
            relation_table = MODELS[relation_logical].__tablename__
            relation_field = "tag_uid" if resource == "contacts" else "contact_uid"
            parent_field = "contact_uid" if resource == "contacts" else "deal_uid"
            parameters["relation_uids"] = json.dumps(relation_values)
            parameter_types["relation_uids"] = "jsonb"
            ctes.append(
                f'links AS (INSERT INTO "{relation_table}" '
                f"(uid, {parent_field}, {relation_field}, created_at) "
                "SELECT md5(created.uid::text || refs.value)::uuid, "
                "created.uid, refs.value::uuid, NOW() "
                "FROM created CROSS JOIN jsonb_array_elements_text(%(relation_uids)s::jsonb) refs "
                "RETURNING uid)"
            )
            reference_tables[relation_logical] = "write"
        if resource == "contacts" and values.get("company_uid") is not None:
            affiliation_table = MODELS["contact_company_affiliation"].__tablename__
            parameters["affiliation_uid"] = str(uuid.uuid5(command_uid, "initial-affiliation"))
            ctes.append(
                f'affiliation_created AS (INSERT INTO "{affiliation_table}" '
                "(uid, contact_uid, company_uid, created_at, updated_at, "
                "created_by_uid, updated_by_uid, version, archived_at, status, is_primary, "
                "started_period, ended_period, job_title) "
                "SELECT %(affiliation_uid)s::uuid, created.uid, "
                "created.company_uid, NOW(), NOW(), %(actor_uid)s::uuid, %(actor_uid)s::uuid, "
                "1, NULL, 'current', TRUE, NULL, NULL, NULL FROM created RETURNING uid)"
            )
            reference_tables["contact_company_affiliation"] = "write"
        if resource == "notes" and values.get("contact_uid"):
            contact_table = MODELS["contact"].__tablename__
            ctes.append(
                f'contact_seen AS (UPDATE "{contact_table}" c SET last_seen=GREATEST('
                "COALESCE(c.last_seen, '-infinity'::timestamptz), %(occurred_at)s::timestamptz), "
                "updated_at=NOW(), updated_by_uid=%(actor_uid)s::uuid, version=c.version+1 "
                "FROM created WHERE c.uid=created.contact_uid RETURNING c.uid)"
            )
            reference_tables["contact"] = "write"
        if resource == "deals":
            pipeline_table = MODELS["pipeline"].__tablename__
            ctes.append(
                f'board_changed AS (UPDATE "{pipeline_table}" p SET board_version=p.board_version+1, '
                "updated_at=NOW(), updated_by_uid=%(actor_uid)s::uuid, version=p.version+1 "
                "FROM created WHERE p.uid=created.pipeline_uid RETURNING p.uid)"
            )
            reference_tables["pipeline"] = "write"
        parameters["entity_type"] = definition.logical_table
        parameter_types["entity_type"] = "string"
        sql = (
            "WITH " + ", ".join(ctes) + f' INSERT INTO "{activity_table}" '
            "(uid, entity_type, entity_uid, kind, occurred_at, recorded_at, "
            "actor_uid, origin, command_uid, summary, changes, source_attribution) "
            "SELECT %(event_uid)s::uuid, %(entity_type)s, created.uid, "
            "'created', NOW(), NOW(), %(actor_uid)s::uuid, 'live', %(command_uid)s::uuid, "
            "%(summary)s, '{}'::jsonb, NULL FROM created RETURNING entity_uid"
        )
        tables = {
            definition.logical_table: "write",
            "activity_event": "write",
            **reference_tables,
        }
        result = self._operation(
            operation="insert",
            sql=sql,
            parameters=parameters,
            parameter_types=parameter_types,
            tables=tables,
            max_rows=1,
        )
        if not result.get("rows"):
            raise ResourceConflict("CRM create precondition failed")
        return self.reads.detail(resource, entity_uid)

    def update(
        self,
        resource: str,
        actor_uid: uuid.UUID,
        uid: uuid.UUID,
        expected_version: int,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        definition = RESOURCE_SPECS[resource]
        command_uid = uuid.uuid4()
        data = dict(data)
        if resource == "tags":
            data["normalized_name"] = data["name"].strip().casefold()
        relation_key = "tag_uids" if resource == "contacts" else "contact_uids"
        relation_values = (
            data.pop(relation_key, None) if resource in {"contacts", "deals"} else None
        )
        parameters: dict[str, Any] = {
            "actor_uid": str(actor_uid),
            "entity_uid": str(uid),
            "expected_version": expected_version,
            "command_uid": str(command_uid),
            "event_uid": str(uuid.uuid5(command_uid, "activity")),
            "entity_type": definition.logical_table,
            "summary": f"Updated {definition.item_label.lower()}",
        }
        parameter_types = {
            "actor_uid": "uuid",
            "entity_uid": "uuid",
            "expected_version": "bigint",
            "command_uid": "uuid",
            "event_uid": "uuid",
            "entity_type": "string",
            "summary": "string",
        }
        assignments = []
        for name, value in data.items():
            parameter_value, parameter_type, expression = self._parameter(name, value)
            parameters[name] = parameter_value
            parameter_types[name] = parameter_type
            assignments.append(f"{name}={expression}")
        entity_table = MODELS[definition.logical_table].__tablename__
        activity_table = MODELS["activity_event"].__tablename__
        gate_extra, reference_tables = self._create_predicates(
            resource,
            data,
            relation_values if isinstance(relation_values, list) else [],
            allow_existing_archived_company=resource == "contacts",
        )
        entity_exists = (
            f'AND EXISTS (SELECT 1 FROM "{entity_table}" current '
            "WHERE current.uid=CAST(%(entity_uid)s AS uuid) "
            "AND current.version=CAST(%(expected_version)s AS bigint))"
        )
        ctes = [
            *(
                [
                    f'prior_company AS (SELECT company_uid FROM "{entity_table}" '
                    "WHERE uid=%(entity_uid)s::uuid "
                    "AND version=%(expected_version)s::bigint)"
                ]
                if resource == "contacts"
                else []
            ),
            "gate AS (SELECT 1 AS ready WHERE TRUE " + entity_exists + gate_extra + ")",
            f'changed AS (UPDATE "{entity_table}" target SET '
            + ", ".join(
                assignments
                + [
                    "updated_at=NOW()",
                    "updated_by_uid=%(actor_uid)s::uuid",
                    "version=target.version+1",
                ]
            )
            + " FROM gate WHERE target.uid=CAST(%(entity_uid)s AS uuid) "
            "AND target.version=CAST(%(expected_version)s AS bigint) RETURNING target.*)",
        ]
        if relation_values is not None:
            logical = "contact_tag" if resource == "contacts" else "deal_contact"
            relation_table = MODELS[logical].__tablename__
            relation_field = "tag_uid" if resource == "contacts" else "contact_uid"
            parent_field = "contact_uid" if resource == "contacts" else "deal_uid"
            parameters["relation_uids"] = json.dumps(relation_values)
            parameter_types["relation_uids"] = "jsonb"
            ctes.extend(
                [
                    f'links_added AS (INSERT INTO "{relation_table}" '
                    f"(uid, {parent_field}, {relation_field}, created_at) "
                    "SELECT md5(changed.uid::text || refs.value)::uuid, "
                    "changed.uid, refs.value::uuid, NOW() FROM changed CROSS JOIN "
                    "jsonb_array_elements_text(%(relation_uids)s::jsonb) refs "
                    f"ON CONFLICT ({parent_field}, {relation_field}) DO NOTHING RETURNING uid)",
                    f'links_removed AS (DELETE FROM "{relation_table}" old USING changed '
                    f"WHERE old.{parent_field}=changed.uid "
                    f"AND old.{relation_field} NOT IN (SELECT value::uuid FROM "
                    "jsonb_array_elements_text(%(relation_uids)s::jsonb)) RETURNING old.uid)",
                ]
            )
            reference_tables[logical] = "write"
        if resource == "contacts":
            affiliation_table = MODELS["contact_company_affiliation"].__tablename__
            parameters["affiliation_uid"] = str(uuid.uuid5(command_uid, "new-affiliation"))
            ctes.extend(
                [
                    f'prior_affiliation_closed AS (UPDATE "{affiliation_table}" a '
                    "SET status='former', is_primary=FALSE, version=a.version+1, "
                    "updated_at=NOW(), updated_by_uid=%(actor_uid)s::uuid "
                    "FROM changed, prior_company WHERE a.contact_uid=changed.uid "
                    "AND a.is_primary=TRUE "
                    "AND a.archived_at IS NULL AND prior_company.company_uid "
                    "IS DISTINCT FROM changed.company_uid RETURNING a.uid)",
                    f'new_affiliation AS (INSERT INTO "{affiliation_table}" '
                    "(uid, contact_uid, company_uid, created_at, updated_at, "
                    "created_by_uid, updated_by_uid, version, archived_at, status, is_primary, "
                    "started_period, ended_period, job_title) "
                    "SELECT %(affiliation_uid)s::uuid, changed.uid, "
                    "changed.company_uid, NOW(), NOW(), %(actor_uid)s::uuid, %(actor_uid)s::uuid, "
                    "1, NULL, 'current', TRUE, NULL, NULL, NULL "
                    "FROM changed CROSS JOIN prior_company "
                    "CROSS JOIN (SELECT count(*) FROM prior_affiliation_closed) prior_closed "
                    "WHERE changed.company_uid IS NOT NULL "
                    "AND prior_company.company_uid IS DISTINCT FROM changed.company_uid "
                    "RETURNING uid)",
                ]
            )
            reference_tables["contact_company_affiliation"] = "write"
        if resource == "deals":
            pipeline_table = MODELS["pipeline"].__tablename__
            ctes.append(
                f'board_changed AS (UPDATE "{pipeline_table}" p SET board_version=p.board_version+1, '
                "updated_at=NOW(), updated_by_uid=%(actor_uid)s::uuid, version=p.version+1 "
                "FROM changed WHERE p.uid=changed.pipeline_uid RETURNING p.uid)"
            )
            reference_tables["pipeline"] = "write"
        parameters["event_changes"] = json.dumps(data)
        parameter_types["event_changes"] = "jsonb"
        sql = (
            "WITH " + ", ".join(ctes) + f' INSERT INTO "{activity_table}" '
            "(uid, entity_type, entity_uid, kind, occurred_at, recorded_at, "
            "actor_uid, origin, command_uid, summary, changes, source_attribution) "
            "SELECT %(event_uid)s::uuid, %(entity_type)s, changed.uid, "
            "'updated', NOW(), NOW(), %(actor_uid)s::uuid, 'live', %(command_uid)s::uuid, "
            "%(summary)s, %(event_changes)s::jsonb, NULL FROM changed RETURNING entity_uid"
        )
        result = self._operation(
            operation="insert",
            sql=sql,
            parameters=parameters,
            parameter_types=parameter_types,
            tables={
                definition.logical_table: "write",
                "activity_event": "write",
                **reference_tables,
            },
            max_rows=1,
        )
        if not result.get("rows"):
            raise ResourceConflict("Record version or relationship precondition failed")
        return self.reads.detail(resource, uid)

    def archive(
        self,
        resource: str,
        actor_uid: uuid.UUID,
        uid: uuid.UUID,
        expected_version: int,
        archived: bool,
    ) -> dict[str, Any]:
        definition = RESOURCE_SPECS[resource]
        verb = "archive" if archived else "restore"
        command_uid = uuid.uuid4()
        entity_table = MODELS[definition.logical_table].__tablename__
        activity_table = MODELS["activity_event"].__tablename__
        archived_expression = "NOW()" if archived else "NULL"
        parameters = {
            "actor_uid": str(actor_uid),
            "entity_uid": str(uid),
            "expected_version": expected_version,
            "command_uid": str(command_uid),
            "event_uid": str(uuid.uuid5(command_uid, "activity")),
            "entity_type": definition.logical_table,
            "summary": f"{verb.title()}d {definition.item_label.lower()}",
        }
        parameter_types = {
            key: "uuid"
            if key.endswith("_uid")
            else "bigint"
            if key == "expected_version"
            else "string"
            for key in parameters
        }
        ctes = [
            "gate AS (SELECT 1 AS ready WHERE TRUE AND EXISTS (SELECT 1 FROM "
            f'"{entity_table}" current WHERE '
            "current.uid=CAST(%(entity_uid)s AS uuid) "
            "AND current.version=CAST(%(expected_version)s AS bigint)))",
            f'changed AS (UPDATE "{entity_table}" target SET archived_at={archived_expression}, '
            "updated_at=NOW(), updated_by_uid=%(actor_uid)s::uuid, version=target.version+1 FROM gate "
            "WHERE target.uid=%(entity_uid)s::uuid "
            "AND target.version=CAST(%(expected_version)s AS bigint) RETURNING target.*)",
        ]
        reference_tables: dict[str, str] = {}
        if resource == "deals":
            pipeline_table = MODELS["pipeline"].__tablename__
            ctes.append(
                f'board_changed AS (UPDATE "{pipeline_table}" p SET board_version=p.board_version+1, '
                "updated_at=NOW(), updated_by_uid=%(actor_uid)s::uuid, version=p.version+1 "
                "FROM changed WHERE p.uid=changed.pipeline_uid RETURNING p.uid)"
            )
            reference_tables["pipeline"] = "write"
        sql = (
            "WITH " + ", ".join(ctes) + f' INSERT INTO "{activity_table}" '
            "(uid, entity_type, entity_uid, kind, occurred_at, recorded_at, "
            "actor_uid, origin, command_uid, summary, changes, source_attribution) "
            "SELECT %(event_uid)s::uuid, %(entity_type)s, changed.uid, "
            f"'{verb}d', NOW(), NOW(), %(actor_uid)s::uuid, 'live', %(command_uid)s::uuid, "
            "%(summary)s, '{}'::jsonb, NULL FROM changed RETURNING entity_uid"
        )
        result = self._operation(
            operation="insert",
            sql=sql,
            parameters=parameters,
            parameter_types=parameter_types,
            tables={
                definition.logical_table: "write",
                "activity_event": "write",
                **reference_tables,
            },
            max_rows=1,
        )
        if not result.get("rows"):
            raise ResourceConflict("Record version precondition failed")
        return self.reads.detail(resource, uid)

    def _create_predicates(
        self,
        resource: str,
        values: dict[str, Any],
        relation_values: list[str],
        *,
        allow_existing_archived_company: bool = False,
    ) -> tuple[str, dict[str, str]]:
        predicates: list[str] = []
        tables: dict[str, str] = {}
        references = {
            "companies": (("owner_uid", None),),
            "contacts": (("company_uid", "company"),),
            "deals": (
                ("company_uid", "company"),
                ("pipeline_uid", "pipeline"),
                ("stage_uid", "stage"),
            ),
            "tasks": (("contact_uid", "contact"),),
            "notes": (("contact_uid", "contact"), ("deal_uid", "deal")),
            "tags": (),
        }[resource]
        for field, logical_table in references:
            if logical_table is None or values.get(field) is None:
                continue
            table = MODELS[logical_table].__tablename__
            active_company = ""
            if resource == "contacts" and field == "company_uid":
                active_company = (
                    " AND (ref_company_uid.archived_at IS NULL OR "
                    "ref_company_uid.uid=(SELECT company_uid FROM prior_company))"
                    if allow_existing_archived_company
                    else " AND ref_company_uid.archived_at IS NULL"
                )
            predicates.append(
                f'AND EXISTS (SELECT 1 FROM "{table}" ref_{field} '
                f"WHERE ref_{field}.uid=CAST(%({field})s AS uuid){active_company})"
            )
            tables[logical_table] = "read"
        if resource == "deals":
            stage = MODELS["stage"].__tablename__
            predicates.append(
                f'AND EXISTS (SELECT 1 FROM "{stage}" stage_pipeline '
                "WHERE stage_pipeline.uid=CAST(%(stage_uid)s AS uuid) "
                "AND stage_pipeline.pipeline_uid=CAST(%(pipeline_uid)s AS uuid) "
                "AND stage_pipeline.is_active=TRUE)"
            )
        if resource == "notes":
            if bool(values.get("contact_uid")) == bool(values.get("deal_uid")):
                raise ValueError("A note must have exactly one parent")
        if relation_values:
            logical = "tag" if resource == "contacts" else "contact"
            table = MODELS[logical].__tablename__
            predicates.append(
                f'AND (SELECT count(*) FROM "{table}" related WHERE '
                "related.archived_at IS NULL "
                "AND related.uid IN (SELECT value::uuid FROM "
                "jsonb_array_elements_text(%(relation_uids)s::jsonb))) = "
                "jsonb_array_length(%(relation_uids)s::jsonb)"
            )
            tables[logical] = "read"
        return (" " + " ".join(predicates)) if predicates else "", tables
