"""Interaction people and governed write regression checks."""

import json
import uuid

import pytest
from pydantic import ValidationError

from src.crm.google_workspace.store import GoogleStore
from src.crm.models.interactions import InteractionCreate
from src.crm.repositories.records import VersionedRecordStore


class CaptureRecords(VersionedRecordStore):
    def __init__(self):
        self.calls = []

    def _operation(self, **kwargs):
        self.calls.append(kwargs)
        return {"rows": [{"entity_uid": str(uuid.uuid4())}]}

    def detail(self, resource, uid):
        return {"uid": str(uid)}


class CaptureGoogle(GoogleStore):
    def __init__(self):
        self.calls = []

    def _operation(self, **kwargs):
        self.calls.append(kwargs)
        return {"rows": [{"entity_uid": kwargs["parameters"]["uid"]}]}


def interaction(**changes):
    return {"subject": "Planning call", "kind": "meeting", "status": "planned",
            "participants": [{"email": "alex@example.com", "role": "organizer"}], **changes}


def test_people_are_required_but_company_is_optional():
    created = InteractionCreate.model_validate(interaction())
    assert created.company_uid is None
    assert created.participants[0].email == "alex@example.com"
    with pytest.raises(ValidationError, match="at least one person"):
        InteractionCreate.model_validate(interaction(participants=[]))
    with pytest.raises(ValidationError, match="Company"):
        InteractionCreate.model_validate(interaction(deal_uid=str(uuid.uuid4())))
    with pytest.raises(ValidationError, match="unique"):
        InteractionCreate.model_validate(interaction(participants=[{"email": "Alex@example.com"}, {"email": "alex@example.com"}]))
    with pytest.raises(ValidationError, match="unique"):
        InteractionCreate.model_validate(interaction(participants=[
            {"contact_uid": str(uuid.uuid4()), "email": "alex@example.com"},
            {"email": "ALEX@example.com"},
        ]))


def test_core_create_governs_linked_participant_contacts():
    store = CaptureRecords()
    contact_uid = uuid.uuid4()
    store.create("interactions", uuid.uuid4(), InteractionCreate.model_validate(
        interaction(participants=[{"contact_uid": str(contact_uid), "role": "attendee"}])
    ))
    operation = store.calls[0]
    assert "jsonb_array_elements(%(participants)s::jsonb)" in operation["sql"]
    assert json.loads(operation["parameters"]["participants"])[0]["contact_uid"] == str(contact_uid)


def test_calendar_import_writes_reviewed_people_without_company():
    store = CaptureGoogle()
    values = InteractionCreate.model_validate(interaction()).model_dump(mode="json")
    store.import_candidate(
        actor_uid=uuid.uuid4(), source_connection_uid=uuid.uuid4(),
        entity_type="interaction", external_id="calendar:primary:event-1",
        payload_hash="a" * 64, action="create", target_uid=None,
        expected_version=None, values=values,
    )
    operation = store.calls[0]
    assert "participants" in operation["sql"]
    assert "contact_uid" not in operation["sql"].split("updated_by_uid, version, archived_at,")[1].split(") SELECT")[0]
    assert operation["parameters"]["company_uid"] is None
    assert json.loads(operation["parameters"]["participants"])[0]["email"] == "alex@example.com"
