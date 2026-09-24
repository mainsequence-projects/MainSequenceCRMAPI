"""Governed reads and commands for contact-company affiliation periods."""

from __future__ import annotations

import uuid
from typing import Any

from ...contracts import validate_payload
from ...metatables import MODELS
from ...models.affiliations import AffiliationFields, period_bounds
from ..errors import ResourceConflict, ResourceNotFound
from ..gateway import GovernedGateway
from ..resources.reads import ResourceReads


class ContactAffiliations(GovernedGateway):
    def __init__(self, registry, reads: ResourceReads):
        super().__init__(registry)
        self.reads = reads

    def transition_company(
        self,
        actor_uid: uuid.UUID,
        contact_uid: uuid.UUID,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        data = validate_payload("AffiliationTransition", payload)
        current = self.reads.detail("contacts", contact_uid)
        if current["version"] != data["expected_contact_version"]:
            raise ResourceConflict("Contact version precondition failed")
        timeline = self.affiliations(contact_uid, 0, 1)["items"]
        primary = timeline[0] if timeline and timeline[0]["is_primary"] else None
        if bool(primary) != (data["previous_status"] is not None):
            raise ValueError("Specify how the previous primary affiliation should continue")
        if primary and current["company_uid"] != primary["company_uid"]:
            raise ResourceConflict("Primary affiliation and contact projection disagree")
        if primary and primary["started_period"] and data["previous_ended_period"]:
            if (
                period_bounds(primary["started_period"])[0]
                > period_bounds(data["previous_ended_period"])[1]
            ):
                raise ValueError("Previous end period precedes its start period")
        if not primary and current["company_uid"] is not None:
            raise ResourceConflict("Primary affiliation is missing")
        if (
            primary
            and data["previous_status"] == "current"
            and data["new_company_uid"] == primary["company_uid"]
        ):
            raise ValueError("Select a different company or end the previous period")
        command_uid = uuid.uuid4()
        new_uid = uuid.uuid4()
        contact = MODELS["contact"].__tablename__
        company = MODELS["company"].__tablename__
        affiliation = MODELS["contact_company_affiliation"].__tablename__
        activity = MODELS["activity_event"].__tablename__
        params = {
            **data,
            "actor_uid": str(actor_uid),
            "contact_uid": str(contact_uid),
            "new_uid": str(new_uid),
            "old_uid": str(primary["uid"]) if primary else None,
            "old_version": primary["version"] if primary else None,
            "new_company_uid": str(data["new_company_uid"]) if data["new_company_uid"] else None,
            "command_uid": str(command_uid),
            "event_uid": str(uuid.uuid5(command_uid, "activity")),
        }
        sql = (
            f'WITH gate AS (UPDATE "{contact}" c SET '
            "company_uid=%(new_company_uid)s::uuid,version=c.version+1,"
            "updated_at=NOW(),updated_by_uid=%(actor_uid)s::uuid "
            "WHERE c.uid=%(contact_uid)s::uuid AND c.archived_at IS NULL "
            "AND c.version=%(expected_contact_version)s::bigint AND ("
            "%(old_uid)s::uuid IS NULL AND NOT EXISTS ("
            f'SELECT 1 FROM "{affiliation}" existing WHERE '
            "existing.contact_uid=%(contact_uid)s::uuid AND existing.is_primary "
            "AND existing.archived_at IS NULL) OR EXISTS ("
            f'SELECT 1 FROM "{affiliation}" existing WHERE '
            "existing.uid=%(old_uid)s::uuid AND existing.contact_uid=%(contact_uid)s::uuid "
            "AND existing.version=%(old_version)s::bigint AND existing.is_primary "
            "AND existing.archived_at IS NULL)) AND (%(new_company_uid)s::uuid IS NULL OR EXISTS ("
            f'SELECT 1 FROM "{company}" target WHERE '
            "target.uid=%(new_company_uid)s::uuid AND target.archived_at IS NULL)) "
            "RETURNING c.uid), "
            f'old_demoted AS (UPDATE "{affiliation}" a SET is_primary=FALSE, '
            "status=%(previous_status)s,ended_period=%(previous_ended_period)s,"
            "version=a.version+1,updated_at=NOW(),updated_by_uid=%(actor_uid)s::uuid "
            "FROM gate WHERE a.uid=%(old_uid)s::uuid "
            "AND a.version=%(old_version)s::bigint RETURNING a.uid), "
            "contact_changed AS (SELECT gate.uid FROM gate WHERE "
            "(%(old_uid)s::uuid IS NULL OR (SELECT count(*) FROM old_demoted)=1) "
            "), "
            f'new_affiliation AS (INSERT INTO "{affiliation}" '
            "(uid,contact_uid,company_uid,created_at,updated_at,created_by_uid,"
            "updated_by_uid,version,archived_at,status,is_primary,started_period,ended_period,job_title) "
            "SELECT %(new_uid)s::uuid,contact_changed.uid,"
            "%(new_company_uid)s::uuid,NOW(),NOW(),%(actor_uid)s::uuid,%(actor_uid)s::uuid,"
            "1,NULL,'current',TRUE,%(new_started_period)s,NULL,%(new_job_title)s "
            "FROM contact_changed CROSS JOIN (SELECT count(*) FROM old_demoted) prior "
            "WHERE %(new_company_uid)s::uuid IS NOT NULL RETURNING uid) "
            f'INSERT INTO "{activity}" '
            "(uid,entity_type,entity_uid,kind,occurred_at,recorded_at,actor_uid,"
            "origin,command_uid,summary,changes,source_attribution) "
            "SELECT %(event_uid)s::uuid,'contact',contact_changed.uid,"
            "'company-transition',NOW(),NOW(),%(actor_uid)s::uuid,'live',"
            "%(command_uid)s::uuid,'Changed primary company','{}'::jsonb,NULL "
            "FROM contact_changed RETURNING entity_uid"
        )
        result = self._operation(
            operation="insert",
            sql=sql,
            parameters=params,
            parameter_types={},
            tables={
                "contact": "write",
                "company": "read",
                "contact_company_affiliation": "write",
                "activity_event": "write",
            },
            max_rows=1,
        )
        if not result.get("rows"):
            raise ResourceConflict("Company transition precondition failed")
        return self.reads.detail("contacts", contact_uid)

    def create_affiliation(
        self,
        actor_uid: uuid.UUID,
        contact_uid: uuid.UUID,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        data = validate_payload("AffiliationCreate", payload)
        command_uid = uuid.uuid4()
        affiliation_uid = uuid.uuid4()
        contact = MODELS["contact"].__tablename__
        company = MODELS["company"].__tablename__
        affiliation = MODELS["contact_company_affiliation"].__tablename__
        activity = MODELS["activity_event"].__tablename__
        params = {
            **data,
            "actor_uid": str(actor_uid),
            "contact_uid": str(contact_uid),
            "affiliation_uid": str(affiliation_uid),
            "command_uid": str(command_uid),
            "event_uid": str(uuid.uuid5(command_uid, "activity")),
        }
        params["company_uid"] = str(data["company_uid"])
        sql = (
            f'WITH contact_changed AS (UPDATE "{contact}" c SET '
            "company_uid=CASE WHEN %(is_primary)s THEN %(company_uid)s::uuid ELSE c.company_uid END, "
            "version=c.version+1, updated_at=NOW(), updated_by_uid=%(actor_uid)s::uuid "
            "WHERE c.uid=%(contact_uid)s::uuid AND c.archived_at IS NULL "
            "AND c.version=%(expected_contact_version)s::bigint "
            "AND (NOT %(is_primary)s OR c.company_uid IS NULL) AND EXISTS ("
            f'SELECT 1 FROM "{company}" company WHERE '
            "company.uid=%(company_uid)s::uuid AND company.archived_at IS NULL) "
            "RETURNING c.uid), "
            f'changed AS (INSERT INTO "{affiliation}" '
            "(uid,contact_uid,company_uid,created_at,updated_at,created_by_uid,"
            "updated_by_uid,version,archived_at,status,is_primary,started_period,ended_period,job_title) "
            "SELECT %(affiliation_uid)s::uuid,contact_changed.uid,"
            "%(company_uid)s::uuid,NOW(),NOW(),%(actor_uid)s::uuid,%(actor_uid)s::uuid,1,NULL,"
            "%(status)s,%(is_primary)s,%(started_period)s,%(ended_period)s,%(job_title)s "
            "FROM contact_changed RETURNING uid,contact_uid) "
            f'INSERT INTO "{activity}" '
            "(uid,entity_type,entity_uid,kind,occurred_at,recorded_at,actor_uid,"
            "origin,command_uid,summary,changes,source_attribution) "
            "SELECT %(event_uid)s::uuid,'contact',changed.contact_uid,"
            "'affiliation-created',NOW(),NOW(),%(actor_uid)s::uuid,'live',"
            "%(command_uid)s::uuid,'Added company affiliation','{}'::jsonb,NULL "
            "FROM changed RETURNING entity_uid"
        )
        result = self._operation(
            operation="insert",
            sql=sql,
            parameters=params,
            parameter_types={},
            tables={
                "contact": "write",
                "company": "read",
                "contact_company_affiliation": "write",
                "activity_event": "write",
            },
            max_rows=1,
        )
        if not result.get("rows"):
            raise ResourceConflict("Affiliation create precondition failed")
        return self.affiliation_detail(contact_uid, affiliation_uid)

    def patch_affiliation(
        self,
        actor_uid: uuid.UUID,
        contact_uid: uuid.UUID,
        affiliation_uid: uuid.UUID,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        data = validate_payload("AffiliationPatch", payload)
        existing = self.affiliation_detail(contact_uid, affiliation_uid)
        candidate = {key: existing[key] for key in AffiliationFields.model_fields}
        candidate.update(data["changes"])
        validated = AffiliationFields.model_validate(candidate).model_dump(mode="json")
        command_uid = uuid.uuid4()
        contact = MODELS["contact"].__tablename__
        affiliation = MODELS["contact_company_affiliation"].__tablename__
        activity = MODELS["activity_event"].__tablename__
        params = {
            **{
                key: validated[key]
                for key in ("status", "started_period", "ended_period", "job_title")
            },
            "actor_uid": str(actor_uid),
            "contact_uid": str(contact_uid),
            "affiliation_uid": str(affiliation_uid),
            "expected_version": data["expected_version"],
            "expected_contact_version": data["expected_contact_version"],
            "command_uid": str(command_uid),
            "event_uid": str(uuid.uuid5(command_uid, "activity")),
        }
        sql = (
            f'WITH contact_changed AS (UPDATE "{contact}" c SET version=c.version+1, '
            "updated_at=NOW(),updated_by_uid=%(actor_uid)s::uuid "
            "WHERE c.uid=%(contact_uid)s::uuid AND c.archived_at IS NULL "
            "AND c.version=%(expected_contact_version)s::bigint AND EXISTS ("
            f'SELECT 1 FROM "{affiliation}" a WHERE '
            "a.uid=%(affiliation_uid)s::uuid AND a.contact_uid=%(contact_uid)s::uuid "
            "AND a.archived_at IS NULL AND a.version=%(expected_version)s::bigint) RETURNING c.uid), "
            f'changed AS (UPDATE "{affiliation}" a SET status=%(status)s, '
            "started_period=%(started_period)s,ended_period=%(ended_period)s,"
            "job_title=%(job_title)s,version=a.version+1,updated_at=NOW(),"
            "updated_by_uid=%(actor_uid)s::uuid FROM contact_changed "
            "WHERE a.uid=%(affiliation_uid)s::uuid "
            "AND a.version=%(expected_version)s::bigint RETURNING a.uid,a.contact_uid) "
            f'INSERT INTO "{activity}" '
            "(uid,entity_type,entity_uid,kind,occurred_at,recorded_at,actor_uid,"
            "origin,command_uid,summary,changes,source_attribution) "
            "SELECT %(event_uid)s::uuid,'contact',changed.contact_uid,"
            "'affiliation-updated',NOW(),NOW(),%(actor_uid)s::uuid,'live',"
            "%(command_uid)s::uuid,'Updated company affiliation','{}'::jsonb,NULL "
            "FROM changed WHERE EXISTS (SELECT 1 FROM contact_changed) RETURNING entity_uid"
        )
        result = self._operation(
            operation="insert",
            sql=sql,
            parameters=params,
            parameter_types={},
            tables={
                "contact": "write",
                "contact_company_affiliation": "write",
                "activity_event": "write",
            },
            max_rows=1,
        )
        if not result.get("rows"):
            raise ResourceConflict("Affiliation version precondition failed")
        return self.affiliation_detail(contact_uid, affiliation_uid)

    def affiliations(
        self,
        contact_uid: uuid.UUID,
        page_index: int = 0,
        page_size: int = 25,
    ) -> dict[str, Any]:
        if page_index < 0 or not 1 <= page_size <= 100:
            raise ValueError("Invalid affiliation page")
        contact = MODELS["contact"].__tablename__
        relation = MODELS["contact_company_affiliation"].__tablename__
        company = MODELS["company"].__tablename__
        result = self._operation(
            operation="select",
            sql=(
                f"SELECT jsonb_build_object('uid',a.uid, "
                "'contact_uid',a.contact_uid,'company_uid',a.company_uid,'company_name',c.name, "
                "'version',a.version,'status',a.status,'is_primary',a.is_primary, "
                "'started_period',a.started_period,'ended_period',a.ended_period, "
                f"'job_title',a.job_title) AS item FROM \"{relation}\" a "
                f'JOIN "{company}" c ON c.uid=a.company_uid '
                "WHERE a.contact_uid=%(contact_uid)s::uuid "
                "AND a.archived_at IS NULL "
                f'AND EXISTS (SELECT 1 FROM "{contact}" person WHERE person.uid=a.contact_uid) '
                "ORDER BY a.is_primary DESC, a.started_period DESC NULLS LAST, a.uid "
                "LIMIT %(limit)s::integer OFFSET %(offset)s::integer"
            ),
            parameters={
                "contact_uid": str(contact_uid),
                "limit": page_size + 1,
                "offset": page_index * page_size,
            },
            parameter_types={},
            tables={"contact_company_affiliation": "read", "contact": "read", "company": "read"},
            max_rows=page_size + 1,
        )
        rows = result.get("rows") or []
        items = [
            validate_payload(
                "Affiliation", self._json(row["item"], expected=dict, label="affiliation")
            )
            for row in rows[:page_size]
        ]
        return {
            "items": items,
            "next_page_index": page_index + 1 if len(rows) > page_size else None,
        }

    def affiliation_detail(
        self, contact_uid: uuid.UUID, affiliation_uid: uuid.UUID
    ) -> dict[str, Any]:
        relation = MODELS["contact_company_affiliation"].__tablename__
        company = MODELS["company"].__tablename__
        result = self._operation(
            operation="select",
            sql=(
                "SELECT jsonb_build_object('uid',a.uid, "
                "'contact_uid',a.contact_uid,'company_uid',a.company_uid,'company_name',c.name, "
                "'version',a.version,'status',a.status,'is_primary',a.is_primary, "
                "'started_period',a.started_period,'ended_period',a.ended_period, "
                f"'job_title',a.job_title) AS item FROM \"{relation}\" a "
                f'JOIN "{company}" c ON c.uid=a.company_uid '
                "WHERE a.contact_uid=%(contact_uid)s::uuid "
                "AND a.uid=%(affiliation_uid)s::uuid AND a.archived_at IS NULL"
            ),
            parameters={
                "contact_uid": str(contact_uid),
                "affiliation_uid": str(affiliation_uid),
            },
            parameter_types={},
            tables={"contact_company_affiliation": "read", "company": "read"},
            max_rows=1,
        )
        rows = result.get("rows") or []
        if len(rows) != 1:
            raise ResourceNotFound("Affiliation not found")
        return validate_payload(
            "Affiliation", self._json(rows[0]["item"], expected=dict, label="affiliation")
        )
