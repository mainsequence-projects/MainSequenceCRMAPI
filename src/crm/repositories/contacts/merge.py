"""ResourceMergeOperations for the governed CRM repository."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from typing import Any

from ...contracts import validate_payload
from ...metatables import MODELS
from ...models.socials import SocialLinks
from ..errors import ResourceConflict, ResourceNotFound
from ..gateway import GovernedGateway
from ..resources.reads import ResourceReads
from .affiliations import ContactAffiliations


class ContactMerge(GovernedGateway):
    def __init__(self, registry, reads: ResourceReads, affiliations: ContactAffiliations):
        super().__init__(registry)
        self.reads = reads
        self.contact_affiliations = affiliations

    @staticmethod
    def _merge_array(
        survivor: list[dict[str, Any]], loser: list[dict[str, Any]], key: str
    ) -> list[dict[str, Any]]:
        merged: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in [*survivor, *loser]:
            value = str(item.get(key, "")).strip()
            normalized = value.casefold() if key == "email" else value
            if normalized and normalized not in seen:
                seen.add(normalized)
                merged.append(item)
        return merged

    def _merge_plan(
        self,
        survivor_uid: uuid.UUID,
        loser_uid: uuid.UUID,
        field_resolutions: dict[str, str],
    ) -> dict[str, Any]:
        if survivor_uid == loser_uid:
            raise ValueError("A contact cannot be merged into itself")
        survivor = self.reads.detail("contacts", survivor_uid)
        loser = self.reads.detail("contacts", loser_uid)
        if survivor["archived_at"] is not None or loser["archived_at"] is not None:
            raise ResourceConflict("Archived contacts cannot be merged")

        scalar_fields = (
            "first_name",
            "last_name",
            "title",
            "company_uid",
            "owner_uid",
            "gender",
            "background",
            "status_key",
            "has_newsletter",
            "avatar_ref",
        )
        proposed = dict(survivor)
        for field in scalar_fields:
            choice = field_resolutions.get(field)
            survivor_value = survivor.get(field)
            loser_value = loser.get(field)
            proposed[field] = (
                loser_value
                if choice == "loser"
                else survivor_value
                if survivor_value not in (None, "")
                else loser_value
            )
        proposed_socials = {}
        for platform in SocialLinks.model_fields:
            choice = field_resolutions.get(f"socials.{platform}")
            survivor_value = survivor["socials"].get(platform)
            loser_value = loser["socials"].get(platform)
            selected = (
                survivor_value
                if choice == "survivor"
                else loser_value
                if choice == "loser"
                else survivor_value
                if survivor_value is not None
                else loser_value
            )
            if selected is not None:
                proposed_socials[platform] = selected
        proposed["socials"] = proposed_socials
        proposed["emails"] = self._merge_array(survivor["emails"], loser["emails"], "email")
        proposed["phones"] = self._merge_array(survivor["phones"], loser["phones"], "number")
        proposed["tag_uids"] = sorted(set(survivor["tag_uids"]) | set(loser["tag_uids"]))
        for field, pick in (("first_seen", min), ("last_seen", max)):
            values = [value for value in (survivor.get(field), loser.get(field)) if value]
            proposed[field] = (
                pick(values, key=lambda value: datetime.fromisoformat(value)) if values else None
            )
        proposed["display_name"] = " ".join(
            value for value in (proposed.get("first_name"), proposed.get("last_name")) if value
        ).strip()
        proposed["company_name"] = (
            loser["company_name"]
            if proposed.get("company_uid") == loser.get("company_uid")
            else survivor["company_name"]
        )
        for contact_uid, contact in ((survivor_uid, survivor), (loser_uid, loser)):
            timeline = self.contact_affiliations.affiliations(contact_uid, 0, 1)["items"]
            primary = timeline[0] if timeline and timeline[0]["is_primary"] else None
            if (str(primary["company_uid"]) if primary else None) != (
                str(contact["company_uid"]) if contact["company_uid"] else None
            ):
                raise ResourceConflict("Contact primary company and affiliation history disagree")
        proposed["open_task_count"] = survivor["open_task_count"] + loser["open_task_count"]
        if (
            len(proposed["emails"]) > 20
            or len(proposed["phones"]) > 20
            or len(proposed["tag_uids"]) > 100
        ):
            raise ResourceConflict("Merged contact exceeds a configured field limit")

        note = MODELS["note"].__tablename__
        task = MODELS["task"].__tablename__
        deal_contact = MODELS["deal_contact"].__tablename__
        contact_tag = MODELS["contact_tag"].__tablename__
        source_identity = MODELS["source_identity"].__tablename__
        affiliation = MODELS["contact_company_affiliation"].__tablename__
        counts_result = self._operation(
            operation="select",
            sql=(
                f'SELECT (SELECT count(*) FROM "{note}" n WHERE '
                "n.contact_uid=CAST(%(loser_uid)s AS uuid)) AS notes, "
                f'(SELECT count(*) FROM "{task}" t WHERE '
                "t.contact_uid=CAST(%(loser_uid)s AS uuid)) AS tasks, "
                f'(SELECT count(*) FROM "{deal_contact}" d WHERE '
                "d.contact_uid=CAST(%(loser_uid)s AS uuid)) AS deals, "
                f'(SELECT count(*) FROM "{contact_tag}" ct WHERE '
                "ct.contact_uid=CAST(%(loser_uid)s AS uuid)) AS tags, "
                f"(SELECT count(*) FROM \"{source_identity}\" si WHERE si.entity_type='contact' "
                "AND si.target_uid=CAST(%(loser_uid)s AS uuid)) AS source_identities, "
                f'(SELECT count(*) FROM "{affiliation}" a WHERE '
                "a.contact_uid=CAST(%(loser_uid)s AS uuid)) AS affiliations"
            ),
            parameters={"loser_uid": str(loser_uid)},
            parameter_types={},
            tables={
                "note": "read",
                "task": "read",
                "deal_contact": "read",
                "contact_tag": "read",
                "source_identity": "read",
                "contact_company_affiliation": "read",
            },
            max_rows=1,
        )
        rows = counts_result.get("rows")
        if not isinstance(rows, list) or len(rows) != 1:
            raise ResourceNotFound("CRM merge counts are unavailable")
        state = rows[0]
        counts = {
            key: int(state[key])
            for key in ("notes", "tasks", "deals", "tags", "source_identities", "affiliations")
        }
        fingerprint = {
            "survivor_uid": str(survivor_uid),
            "loser_uid": str(loser_uid),
            "survivor_version": survivor["version"],
            "loser_version": loser["version"],
            "field_resolutions": field_resolutions,
            "proposed_contact": proposed,
            "related_counts": counts,
        }
        plan_hash = hashlib.sha256(
            json.dumps(
                fingerprint,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode()
        ).hexdigest()
        preview = validate_payload(
            "MergePreview",
            {
                "survivor_uid": str(survivor_uid),
                "loser_uid": str(loser_uid),
                "survivor_version": survivor["version"],
                "loser_version": loser["version"],
                "plan_hash": plan_hash,
                "proposed_contact": proposed,
                "related_counts": counts,
                "warnings": [],
            },
        )
        return preview

    def merge_preview(
        self,
        survivor_uid: uuid.UUID,
        loser_uid: uuid.UUID,
        field_resolutions: dict[str, str],
    ) -> dict[str, Any]:
        return self._merge_plan(survivor_uid, loser_uid, field_resolutions)

    def merge_contacts(
        self,
        actor_uid: uuid.UUID,
        survivor_uid: uuid.UUID,
        command: dict[str, Any],
    ) -> dict[str, Any]:
        loser_uid = uuid.UUID(command["loser_uid"])
        preview = self._merge_plan(survivor_uid, loser_uid, command["field_resolutions"])
        if (
            preview["survivor_version"] != command["expected_version"]
            or preview["loser_version"] != command["loser_expected_version"]
            or preview["plan_hash"] != command["plan_hash"]
        ):
            raise ResourceConflict("Contact merge preview is stale")

        command_uid = uuid.uuid4()
        contact = MODELS["contact"].__tablename__
        contact_tag = MODELS["contact_tag"].__tablename__
        deal_contact = MODELS["deal_contact"].__tablename__
        note = MODELS["note"].__tablename__
        task = MODELS["task"].__tablename__
        source_identity = MODELS["source_identity"].__tablename__
        affiliation = MODELS["contact_company_affiliation"].__tablename__
        redirect = MODELS["entity_redirect"].__tablename__
        activity = MODELS["activity_event"].__tablename__
        proposed = preview["proposed_contact"]
        persisted_fields = (
            "owner_uid",
            "company_uid",
            "first_name",
            "last_name",
            "title",
            "gender",
            "background",
            "avatar_ref",
            "socials",
            "emails",
            "phones",
            "first_seen",
            "last_seen",
            "has_newsletter",
            "status_key",
            "source_created_at",
            "source_updated_at",
        )
        parameters: dict[str, Any] = {
            "actor_uid": str(actor_uid),
            "survivor_uid": str(survivor_uid),
            "loser_uid": str(loser_uid),
            "expected_version": command["expected_version"],
            "loser_expected_version": command["loser_expected_version"],
            "command_uid": str(command_uid),
            "event_uid": str(uuid.uuid5(command_uid, "activity")),
            "redirect_uid": str(uuid.uuid5(command_uid, "redirect")),
            "event_changes": json.dumps(
                {
                    "retired_uid": str(loser_uid),
                    "field_resolutions": command["field_resolutions"],
                }
            ),
        }
        parameter_types: dict[str, str] = {"event_changes": "jsonb"}
        assignments: list[str] = []
        for name in persisted_fields:
            parameter_value, parameter_type, expression = self._parameter(name, proposed[name])
            parameters[f"merged_{name}"] = parameter_value
            parameter_types[f"merged_{name}"] = parameter_type
            assignments.append(f"{name}={expression.replace(f'%({name})s', f'%(merged_{name})s')}")
        sql = (
            f'WITH locked_loser AS (SELECT uid FROM "{contact}" l WHERE '
            "l.uid=CAST(%(loser_uid)s AS uuid) AND l.archived_at IS NULL "
            "AND l.version=CAST(%(loser_expected_version)s AS bigint) FOR UPDATE), "
            f'survivor AS (UPDATE "{contact}" c SET {", ".join(assignments)}, '
            "updated_at=NOW(), updated_by_uid=CAST(%(actor_uid)s AS uuid), version=c.version+1 "
            "FROM locked_loser l WHERE c.uid=CAST(%(survivor_uid)s AS uuid) "
            "AND c.archived_at IS NULL AND c.version=CAST(%(expected_version)s AS bigint) "
            "RETURNING c.*), "
            f'tags_added AS (INSERT INTO "{contact_tag}" '
            "(uid, contact_uid, tag_uid, created_at) SELECT "
            "md5(s.uid::text || ct.tag_uid::text)::uuid, s.uid, ct.tag_uid, NOW() "
            f'FROM survivor s JOIN "{contact_tag}" ct ON '
            "ct.contact_uid=CAST(%(loser_uid)s AS uuid) "
            "ON CONFLICT (contact_uid, tag_uid) DO NOTHING RETURNING uid), "
            f'tags_removed AS (DELETE FROM "{contact_tag}" ct USING survivor s '
            "WHERE ct.contact_uid=CAST(%(loser_uid)s AS uuid) RETURNING ct.uid), "
            f'deal_links_added AS (INSERT INTO "{deal_contact}" '
            "(uid, deal_uid, contact_uid, created_at) SELECT "
            "md5(dc.deal_uid::text || s.uid::text)::uuid, dc.deal_uid, s.uid, NOW() "
            f'FROM survivor s JOIN "{deal_contact}" dc ON '
            "dc.contact_uid=CAST(%(loser_uid)s AS uuid) "
            "ON CONFLICT (deal_uid, contact_uid) DO NOTHING RETURNING uid), "
            f'deal_links_removed AS (DELETE FROM "{deal_contact}" dc USING survivor s '
            "WHERE dc.contact_uid=CAST(%(loser_uid)s AS uuid) RETURNING dc.uid), "
            f'notes_changed AS (UPDATE "{note}" n SET contact_uid=s.uid, updated_at=NOW(), '
            "updated_by_uid=CAST(%(actor_uid)s AS uuid), version=n.version+1 FROM survivor s "
            "WHERE n.contact_uid=CAST(%(loser_uid)s AS uuid) RETURNING n.uid), "
            f'tasks_changed AS (UPDATE "{task}" t SET contact_uid=s.uid, updated_at=NOW(), '
            "updated_by_uid=CAST(%(actor_uid)s AS uuid), version=t.version+1 FROM survivor s "
            "WHERE t.contact_uid=CAST(%(loser_uid)s AS uuid) RETURNING t.uid), "
            f'sources_changed AS (UPDATE "{source_identity}" si SET target_uid=s.uid, '
            "updated_at=NOW() FROM survivor s WHERE si.entity_type='contact' "
            "AND si.target_uid=CAST(%(loser_uid)s AS uuid) RETURNING si.uid), "
            f'affiliations_demoted AS (UPDATE "{affiliation}" a SET is_primary=FALSE, '
            "version=a.version+1,updated_at=NOW(),updated_by_uid=%(actor_uid)s::uuid "
            "FROM survivor s WHERE a.contact_uid=s.uid "
            "AND a.is_primary AND a.company_uid IS DISTINCT FROM s.company_uid "
            "RETURNING a.uid), "
            f'affiliations_moved AS (UPDATE "{affiliation}" a SET contact_uid=s.uid, '
            "is_primary=(a.is_primary AND a.company_uid=s.company_uid AND NOT EXISTS ("
            f'SELECT 1 FROM "{affiliation}" own WHERE '
            "own.contact_uid=s.uid AND own.is_primary AND own.archived_at IS NULL "
            "AND own.company_uid=s.company_uid)),version=a.version+1,updated_at=NOW(),"
            "updated_by_uid=%(actor_uid)s::uuid FROM survivor s "
            "CROSS JOIN (SELECT count(*) FROM affiliations_demoted) demoted "
            "WHERE a.contact_uid=CAST(%(loser_uid)s AS uuid) RETURNING a.uid), "
            f'retired AS (DELETE FROM "{contact}" l USING survivor s, '
            "(SELECT count(*) FROM affiliations_moved) moved "
            "WHERE l.uid=CAST(%(loser_uid)s AS uuid) "
            "AND l.version=CAST(%(loser_expected_version)s AS bigint) RETURNING l.uid), "
            f'redirected AS (INSERT INTO "{redirect}" '
            "(uid, entity_type, from_uid, to_uid, created_at, command_uid) SELECT "
            "CAST(%(redirect_uid)s AS uuid), 'contact', r.uid, "
            "CAST(%(survivor_uid)s AS uuid), NOW(), CAST(%(command_uid)s AS uuid) "
            "FROM retired r RETURNING uid) "
            f'INSERT INTO "{activity}" '
            "(uid, entity_type, entity_uid, kind, occurred_at, recorded_at, "
            "actor_uid, origin, command_uid, summary, changes, source_attribution) SELECT "
            "CAST(%(event_uid)s AS uuid), 'contact', "
            "CAST(%(survivor_uid)s AS uuid), 'merged', NOW(), NOW(), "
            "CAST(%(actor_uid)s AS uuid), 'live', CAST(%(command_uid)s AS uuid), "
            "'Merged contacts', %(event_changes)s::jsonb, NULL FROM retired r RETURNING entity_uid"
        )
        result = self._operation(
            operation="insert",
            sql=sql,
            parameters=parameters,
            parameter_types=parameter_types,
            tables={
                "contact": "write",
                "contact_tag": "write",
                "deal_contact": "write",
                "note": "write",
                "task": "write",
                "source_identity": "write",
                "contact_company_affiliation": "write",
                "entity_redirect": "write",
                "activity_event": "write",
            },
            max_rows=1,
        )
        if not result.get("rows"):
            raise ResourceConflict("Contact merge preview is stale")
        survivor = self.reads.detail("contacts", survivor_uid)
        return validate_payload(
            "MergeResult",
            {
                "command_uid": str(command_uid),
                "survivor": survivor,
                "retired_uid": str(loser_uid),
            },
        )
