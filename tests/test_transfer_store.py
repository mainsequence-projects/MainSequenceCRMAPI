"""Focused transfer tests; MetaTable calls are captured, not platform claims."""

from __future__ import annotations

import json
import uuid

import pytest

from api.crm.main import create_app
from src.crm.models.queries import QueryScope
from src.crm.repositories.transfers.store import GovernedTransferStore

ACTOR = uuid.UUID("22222222-2222-4222-8222-222222222222")
JOB = uuid.UUID("33333333-3333-4333-8333-333333333333")
CONNECTION = uuid.UUID("55555555-5555-4555-8555-555555555555")
NOW = "2026-09-22T12:00:00Z"


def _job(**changes):
    value = {
        "uid": str(JOB),
        "version": 1,
        "direction": "import",
        "adapter_id": "generic-csv-v1",
        "initiator_uid": str(ACTOR),
        "status": "staged",
        "mapping_revision": 2,
        "plan_hash": None,
        "validation_report": {"counts": {}},
        "cancel_requested": False,
        "created_at": NOW,
        "updated_at": NOW,
        "input_manifest": {"entity_type": "contact"},
        "mapping": {},
    }
    value.update(changes)
    return value


def _result(row):
    return {"rows": [row]}


def _assert_governed(call, operation):
    assert call["operation"] == operation
    sql = call["sql"]
    assert "workspace" not in sql
    assert "workspace" not in call["tables"]
    assert call["tables"]["transfer_job"] == "write"


def test_source_and_import_creation_use_record_fences(monkeypatch):
    store = GovernedTransferStore()
    calls = []
    source = {
        "uid": str(uuid.uuid4()),
        "name": "Atomic export",
        "adapter_id": "generic-csv-v1",
        "source_account_key": "account-1",
        "version": 1,
    }

    def execute(**call):
        if call["operation"] == "select":
            return {"rows": []}
        calls.append(call)
        return _result(source if len(calls) == 1 else _job(status="uploading", mapping_revision=1))

    monkeypatch.setattr(store.connections, "_operation", execute)
    monkeypatch.setattr(store.jobs, "_operation", execute)
    created = store.create_source_connection(
        ACTOR,
        {
            "name": "Atomic export",
            "adapter_id": "generic-csv-v1",
            "source_account_key": "account-1",
        },
    )
    assert created["source_account_key"] == "account-1"
    imported = store.create_import(
        ACTOR,
        {
            "adapter_id": "generic-csv-v1",
            "source_connection_uid": str(CONNECTION),
            "entity_type": "contact",
            "display_name": "contacts.csv",
        },
    )
    assert imported["status"] == "uploading"
    assert calls[0]["tables"]["source_connection"] == "write"
    assert calls[1]["tables"]["transfer_job"] == "write"
    for call in calls:
        assert call["operation"] == "insert"
        assert "workspace" not in call["sql"]
        assert call["sql"].rstrip().endswith("RETURNING *")


def test_upload_and_mapping_are_durable_governed_commands(monkeypatch):
    store = GovernedTransferStore()
    writes = []

    def execute(**call):
        if call["operation"] == "select":
            return {"rows": [_job()]}
        writes.append(call)
        return _result(_job(status="staged", mapping_revision=3))

    monkeypatch.setattr(store.jobs, "_operation", execute)
    uploaded = store.stage_upload(
        ACTOR,
        JOB,
        "contacts.csv",
        "text/csv",
        "a" * 64,
        [{"source_id": "900719925474099312345", "first_name": "Ada"}],
        "contact",
    )
    assert uploaded["status"] == "staged"
    mapping = {
        "adapter_id": "generic-csv-v1",
        "source_connection_uid": str(CONNECTION),
        "entity_type": "contact",
        "field_map": {"first_name": "first_name"},
        "owner_map": {},
        "stage_map": {},
        "status_map": {},
        "unknown_fields": "block",
        "unresolved_owner_policy": "block",
        "duplicate_policy": "source_id_only",
        "update_policy": "create_only",
        "date_format": "iso8601",
        "source_timezone": "Europe/Vienna",
        "currency": "EUR",
        "empty_cell_policy": "omit",
        "boolean_map": {},
    }
    saved = store.save_mapping(ACTOR, JOB, mapping)
    assert saved["mapping_revision"] == 3
    assert len(writes) == 2
    for call in writes:
        _assert_governed(call, "update")
    upload_rows = json.loads(writes[0]["parameters"]["rows"])
    assert upload_rows[0]["external_id"] == "900719925474099312345"
    assert writes[0]["tables"]["transfer_row"] == "write"


def test_transition_is_fenced_by_owner_and_state(monkeypatch):
    store = GovernedTransferStore()
    calls = []

    def execute(**call):
        if call["operation"] == "select":
            return {"rows": []}
        calls.append(call)
        return _result(_job(status="queued"))

    monkeypatch.setattr(store.jobs, "_operation", execute)
    result = store.jobs._transition(
        ACTOR,
        JOB,
        {"validated"},
        "queued",
        cancel=False,
    )
    assert result["status"] == "queued"
    _assert_governed(calls[0], "update")
    sql = calls[0]["sql"]
    assert "initiator_uid=%(actor_uid)s::uuid" in sql
    assert "status = ANY" in sql


def test_only_verified_transfer_routes_are_mounted():
    openapi = create_app().openapi()
    routes = {
        (method.upper(), path)
        for path, operations in openapi["paths"].items()
        for method in operations
    }
    required = {
        ("GET", "/api/crm/v1/source-connections/"),
        ("POST", "/api/crm/v1/source-connections/"),
        ("GET", "/api/crm/v1/transfers/"),
        ("POST", "/api/crm/v1/imports/"),
        ("POST", "/api/crm/v1/imports/{uid}/file/"),
        ("PUT", "/api/crm/v1/imports/{uid}/mapping/"),
        ("POST", "/api/crm/v1/imports/{uid}/validate/"),
        ("GET", "/api/crm/v1/imports/{uid}/plan/"),
        ("POST", "/api/crm/v1/imports/{uid}/commit/"),
    }
    assert required <= routes
    assert ("POST", "/api/crm/v1/exports/") not in routes
    assert ("GET", "/api/crm/v1/exports/{uid}/download/") not in routes
    assert "Idempotency-Key" not in json.dumps(openapi)


def test_direct_transfer_repository_call_still_rejects_unsafe_ordering():
    store = GovernedTransferStore()
    with pytest.raises(ValueError, match="ordering"):
        store.transfers(
            ACTOR,
            QueryScope(filters={}, page_index=0, page_size=25, ordering="uid; DROP TABLE jobs"),
        )
