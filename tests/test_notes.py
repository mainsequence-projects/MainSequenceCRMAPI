"""Contact Notes through real MCP/REST and governed SQL on private PostgreSQL.

The transport and caller directory/policy are fixtures; no hosted data is used.
Each test reads its owned records back before transaction rollback/cluster cleanup.
"""

import importlib
import json
import uuid

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from test_mcp_tools import call, rpc
from test_prompts import collection_postgres as _postgres_fixture
from test_prompts import prompts_api as _api_fixture
from test_prompts import prompts_db as _db_fixture

collection_postgres = _postgres_fixture
prompts_api = _api_fixture
prompts_db = _db_fixture

BODY = "# Relationship context\n\nPrefers **email**.\n\n- Discuss next quarter\n- No sales opportunity yet\n"
DATE = "2026-10-16T14:32:18+02:00"


def contact(client):
    response = client.post("/api/crm/v1/contacts/", json={"first_name": "Disposable note fixture"})
    assert response.status_code == 201, response.text
    return response.json()["uid"]


def test_mcp_contact_note_create_edit_and_fresh_rest_reads(prompts_api, signed_caller):
    client, grants, calls, _store, actor = prompts_api
    uid = contact(client)
    delegated = signed_caller(uuid.uuid4(), requester={"sub": str(actor), "is_organization_admin": False})
    catalogue = {tool["name"]: tool for tool in rpc(client, "tools/list", headers=delegated)["tools"]}
    schema = catalogue["crm_notes_create"]["inputSchema"]["$defs"]["NoteCreate"]
    assert set(schema["required"]) == {"text", "occurred_at"}
    assert "Markdown" in schema["properties"]["text"]["description"]
    assert "title" in schema["properties"]
    update_schema = catalogue["crm_notes_update"]["inputSchema"]["$defs"]["NoteChanges"]
    assert "title" in update_schema["properties"]
    payload = {"contact_uid": uid, "title": "  Relationship summary  ", "text": BODY, "occurred_at": DATE}
    before = len(calls)
    result = call(client, "crm_notes_create", {"payload": payload}, headers=delegated)
    assert result["isError"] is False, result
    note = result["structuredContent"]["data"]
    assert note["contact_uid"] == uid and note["deal_uid"] is None
    assert note["text"] == BODY and note["author_uid"] == str(actor)
    assert note["version"] == 1 and note["status_key"] is None
    assert note["attachment_refs"] == []
    assert note["title"] == "Relationship summary"
    writes = [operation for operation in calls[before:] if operation["operation"] != "select"]
    assert len(writes) == 1, "Note and activity must be one governed atomic command"
    assert "mainsequence_crm__activity_event" in writes[0]["statement"]["sql"]
    path = f"/api/crm/v1/notes/{note['uid']}/"
    assert client.get(path).json() == note
    listing = client.get("/api/crm/v1/notes/", params={"filters": json.dumps({"contact_uid": uid})}).json()
    assert [item["uid"] for item in listing["items"]] == [note["uid"]]
    changed = client.patch(path, json={"expected_version": 1, "changes": {"text": BODY + "\nUpdated."}})
    assert changed.status_code == 200, changed.text
    assert changed.json()["occurred_at"] == note["occurred_at"]
    assert changed.json()["version"] == 2
    assert changed.json()["title"] == note["title"], "Omitted title is preserved"
    updated = call(client, "crm_notes_update", {"uid": note["uid"], "payload": {
        "expected_version": 2, "changes": {"title": "Quarterly context", "text": BODY + "\nVia MCP.", "occurred_at": "2026-10-15T08:00:00Z"},
    }}, headers=delegated)
    assert updated["isError"] is False, updated
    assert client.get(path).json() == updated["structuredContent"]["data"]
    assert client.patch(path, json={"expected_version": 1, "changes": {"text": "stale"}}).status_code == 409
    assert client.get(path).json()["text"] == BODY + "\nVia MCP."
    assert client.get(path).json()["title"] == "Quarterly context"
    searched = client.get("/api/crm/v1/notes/", params={"search": "QUARTERLY"}).json()
    assert [row["uid"] for row in searched["items"]] == [note["uid"]]
    cleared = call(client, "crm_notes_update", {"uid": note["uid"], "payload": {
        "expected_version": 3, "changes": {"title": None},
    }}, headers=delegated)
    assert cleared["isError"] is False, cleared
    assert client.get(path).json()["title"] is None
    assert client.get(path).json()["text"] == BODY + "\nVia MCP."
    grants.remove("crm.edit")
    before = len(calls)
    denied_edit = call(client, "crm_notes_update", {"uid": note["uid"], "payload": {
        "expected_version": 4, "changes": {"title": "Unauthorized"},
    }}, headers=delegated)
    assert denied_edit["isError"] is True
    assert len(calls) == before
    grants.remove("crm.create")
    before = len(calls)
    denied = call(client, "crm_notes_create", {"payload": payload}, headers=delegated)
    assert denied["isError"] is True
    assert len(calls) == before


@pytest.mark.parametrize("overrides", [
    {"contact_uid": None}, {"deal_uid": str(uuid.uuid4())},
    {"author_uid": str(uuid.uuid4())}, {"occurred_at": "2026-10-16T14:30:00"},
    *({"title": value} for value in ["", "  ", "😀" * 256, "a\nb", "a\0b"]),
])
def test_mcp_rejects_invalid_note_parents_authorship_and_dates(prompts_api, signed_caller, overrides):
    client, _grants, calls, _store, actor = prompts_api
    payload = {"contact_uid": contact(client), "text": BODY, "occurred_at": DATE, **overrides}
    before = len(calls)
    result = call(client, "crm_notes_create", {"payload": payload}, headers=signed_caller(
        uuid.uuid4(), requester={"sub": str(actor), "is_organization_admin": False},
    ))
    assert result["isError"] is True
    assert result["structuredContent"]["code"] == "invalid_arguments"
    assert len(calls) == before


def test_note_and_activity_rollback_together(prompts_api, prompts_db):
    client, _grants, _calls, store, actor = prompts_api
    uid = contact(client)
    created = client.post("/api/crm/v1/notes/", json={"contact_uid": uid, "text": BODY, "occurred_at": DATE})
    assert created.status_code == 201, created.text
    note = created.json()
    prompts_db.exec_driver_sql(
        "ALTER TABLE mainsequence_crm__activity_event ADD CONSTRAINT test_note_audit CHECK (kind <> 'updated')"
    )
    with pytest.raises(sa.exc.IntegrityError), prompts_db.begin_nested():
        store.update("notes", actor, uuid.UUID(note["uid"]), 1, {"title": "Must roll back", "text": "Must roll back", "contact_uid": uid})
    assert client.get(f"/api/crm/v1/notes/{note['uid']}/").json() == note


def test_note_title_migration_on_postgresql_and_future_columns(prompts_api, prompts_db):
    client, _grants, _calls, _store, _actor = prompts_api
    created = client.post("/api/crm/v1/notes/", json={
        "contact_uid": contact(client), "text": BODY, "occurred_at": DATE,
    })
    assert created.status_code == 201, created.text
    legacy = created.json()
    assert legacy["title"] is None
    revision = importlib.import_module("src.crm.migrations.versions.mainsequence_crm.0012_add_note_title")
    with Operations.context(MigrationContext.configure(prompts_db)):
        revision.downgrade()
        assert "title" not in {column["name"] for column in sa.inspect(prompts_db).get_columns(revision.TABLE)}
        revision.upgrade()
    path = f"/api/crm/v1/notes/{legacy['uid']}/"
    assert client.get(path).json() == legacy, "Migration must preserve old note content, dates and versions"
    for title in (" ", "😀" * 256):
        with pytest.raises((sa.exc.IntegrityError, sa.exc.DataError)), prompts_db.begin_nested():
            prompts_db.execute(sa.text("UPDATE mainsequence_crm__note SET title=:title"), {"title": title})
    title = "😀" * 255
    updated = client.patch(path, json={"expected_version": 1, "changes": {"title": title}})
    assert updated.status_code == 200, updated.text
    assert updated.json()["title"] == title
    # An independently deployed later schema must not leak unknown fields into
    # strict Note responses, including the read-back after a successful mutation.
    prompts_db.exec_driver_sql("ALTER TABLE mainsequence_crm__note ADD COLUMN future_note_field TEXT")
    assert client.get(path).json() == updated.json()
    listing = client.get("/api/crm/v1/notes/", params={"filters": json.dumps({"contact_uid": legacy["contact_uid"]})})
    assert listing.json()["items"] == [updated.json()]
    cleared = client.patch(path, json={"expected_version": 2, "changes": {"title": None}})
    assert cleared.status_code == 200, cleared.text
    assert client.get(path).json()["title"] is None
