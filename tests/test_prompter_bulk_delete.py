"""Authorized discovery, explicit selection and atomic prompter deletion."""

import json
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from api.crm.main import create_app
from api.crm.prompter_discovery import prompter_discovery
from src.crm.repositories.errors import ResourceConflict
from src.crm.repositories.records import VersionedRecordStore

BASE = "/extensions/solution-selling/prompters/"


@pytest.fixture
def bulk_client(signed_caller):
    actor = uuid.uuid4()
    app = create_app()
    capabilities = {"crm.read", "crm.archive"}

    class Policy:
        def capabilities(self, uid):
            assert uid == actor
            return capabilities

    class Store:
        def __init__(self):
            self.versions = {uuid.uuid4(): 1, uuid.uuid4(): 2}
            self.writes = 0

        def preflight_delete_prompters(self, versions):
            allowed = all(self.versions.get(uid) == version for uid, version in versions.items())
            return {"allowed": allowed, "matched_count": len(versions) if allowed else 0,
                    "blockers": [] if allowed else ["Stale selection"]}

        def delete_prompters(self, uid, versions):
            assert uid == actor
            if not self.preflight_delete_prompters(versions)["allowed"]:
                raise ResourceConflict("Stale selection")
            self.writes += 1
            for selected in versions:
                del self.versions[selected]
            return {"deleted_count": len(versions)}

    store = Store()
    app.state.crm_record_store = store
    app.state.crm_directory = object()
    app.state.crm_policy = Policy()
    return TestClient(app, headers=signed_caller(actor)), store, capabilities


def payload(versions):
    return {"selection": {"mode": "explicit", "uids": [str(uid) for uid in versions]},
            "options": {"expected_versions": {str(uid): version for uid, version in versions.items()}}}


def test_bulk_discovery_preflight_execute_and_reauthorization(bulk_client):
    client, store, capabilities = bulk_client
    action = client.get(BASE + "discovery/").json()["bulk_actions"][0]
    assert action["id"] == "delete" and action["selection_modes"] == ["explicit"]
    body = payload(store.versions)
    assert client.post(action["preflight_endpoint"], json=body).json()["allowed"] is True
    capabilities.remove("crm.archive")
    assert client.get(BASE + "discovery/").json()["bulk_actions"] == []
    assert client.post(action["preflight_endpoint"], json=body).status_code == 403
    assert client.post(action["endpoint"], json=body).status_code == 403
    assert store.writes == 0
    capabilities.add("crm.archive")
    response = client.post(action["endpoint"], json=body)
    assert response.status_code == 200 and response.json() == {"deleted_count": 2}
    assert store.writes == 1 and not store.versions
    assert client.post(action["endpoint"], json=body).status_code == 409


def test_stale_or_missing_selection_does_not_delete_other_rows(bulk_client):
    client, store, _ = bulk_client
    before = store.versions.copy()
    for versions in ({**before, next(iter(before)): 99}, {**before, uuid.uuid4(): 1}):
        body = payload(versions)
        assert client.post(BASE + "bulk-delete/preflight/", json=body).json()["allowed"] is False
        assert client.post(BASE + "bulk-delete/", json=body).status_code == 409
        assert store.versions == before and store.writes == 0


def test_invalid_and_all_matching_selection_rejected_before_write(bulk_client):
    client, store, _ = bulk_client
    valid = payload(store.versions)
    bodies = [
        {"selection": {"mode": "all_matching", "query": {"filters": {}}}, "options": {}},
        {"selection": {"mode": "explicit", "uids": []}, "options": {"expected_versions": {}}},
        {**valid, "options": {"expected_versions": {}}},
        {**valid, "selection": {"mode": "explicit", "uids": valid["selection"]["uids"] * 2}},
        {**valid, "options": {"expected_versions": {key: True for key in valid["options"]["expected_versions"]}}},
        {**valid, "options": {"expected_versions": {key: 2**63 for key in valid["options"]["expected_versions"]}}},
    ]
    for body in bodies:
        assert client.post(BASE + "bulk-delete/", json=body).status_code == 422
    assert store.writes == 0
    assert client.get(BASE + "discovery/?page_size=25").status_code == 422


def test_one_governed_statement_locks_selection_and_records_every_deletion():
    calls = []

    class Store(VersionedRecordStore):
        def __init__(self):
            pass

        def _operation(self, **kwargs):
            calls.append(kwargs)
            return {"rows": [{"entity_uid": str(uid)} for uid in versions]}

    versions = {uuid.uuid4(): 1, uuid.uuid4(): 3}
    assert Store().delete_prompters(uuid.uuid4(), versions) == {"deleted_count": 2}
    assert len(calls) == 1
    sql = calls[0]["sql"]
    assert "FOR UPDATE OF t" in sql and "gate AS" in sql
    assert "r.version=l.version" in sql and "t.version=r.version" in sql
    assert 'INSERT INTO "mainsequence_crm__activity_event"' in sql
    assert "archived_at=NOW()" in sql and "version=t.version+1" in sql


def test_published_sdk_contracts_and_indexed_fixtures():
    static = Path(__file__).resolve().parents[2] / "main-sequence-crm-5f1b0619-9997-449c-b986-36990ae49e14"
    root = static / "node_modules/@dev-mainsequence/command-center-sdk/contracts"
    manifest = json.loads((root / "manifest.json").read_text())
    schemas = [json.loads((root / item["file"]).read_text()) for item in manifest["schemas"]]
    registry = Registry().with_resources((schema["$id"], Resource.from_contents(schema)) for schema in schemas)
    for item, schema in zip(manifest["schemas"], schemas):
        if "bulk_action" not in item["contract"] and "resource_discovery" not in item["contract"]:
            continue
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema, registry=registry)
        for file in item["fixtures"]["valid"]:
            validator.validate(json.loads((root / file).read_text()))
        for file in item["fixtures"]["invalid"]:
            assert list(validator.iter_errors(json.loads((root / file).read_text())))
        if "resource_discovery" in item["contract"]:
            for can_delete in (True, False):
                validator.validate(prompter_discovery(can_delete=can_delete))
        if "bulk_action_execution" in item["contract"]:
            validator.validate(payload({uuid.uuid4(): 1}))
