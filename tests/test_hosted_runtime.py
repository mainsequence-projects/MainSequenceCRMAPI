"""Hosted defaults authorize signed people without workload permission fallback."""

import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from test_application import _settings_row
from test_bootstrap_runtime import ReadyRegistry
from test_mcp_tools import ACTOR, AGENT, Store, call

from api.crm.main import create_app
from src.crm.platform.hosted_runtime import PlatformPolicy

WRITERS = str(uuid.UUID(int=701))
READERS = str(uuid.UUID(int=702))
OTHER = uuid.UUID(int=703)


def hosted_app(monkeypatch):
    monkeypatch.setenv("CRM_WRITER_TEAM_UIDS", WRITERS)
    monkeypatch.setenv("CRM_READER_TEAM_UIDS", READERS)
    app = create_app()
    app.state.crm_registry = ReadyRegistry()
    app.state.crm_bootstrap.store = SimpleNamespace(bootstrap_record=_settings_row)
    store = Store()
    app.state.crm_resources = store
    return app, store


def test_default_hosted_bootstrap_reads_signed_self_and_governed_settings(signed_caller, monkeypatch):
    app, _ = hosted_app(monkeypatch)
    monkeypatch.setattr("api.crm.main.resolve_assistant", _no_assistant)
    monkeypatch.setattr("src.crm.platform.hosted_runtime.User.get_by_uid", lambda uid: pytest.fail("Self needs no workload directory lookup"))
    with TestClient(app) as client:
        response = client.get("/api/crm/v1/bootstrap/", headers=signed_caller(ACTOR, team_uids=[WRITERS]))
    assert response.status_code == 200
    assert response.json()["readiness"]["status"] == "ready"
    assert response.json()["current_user"]["uid"] == str(ACTOR)
    assert "crm.create" in response.json()["capabilities"]
    assert "crm.configure" not in response.json()["capabilities"]


async def _no_assistant(origin):
    return {"enabled": False, "runtime": None, "agent_uid": None, "environment_uid": None, "display_name": "CRM assistant"}


def test_mcp_uses_requester_teams_and_never_workload_admin(signed_caller, monkeypatch):
    app, store = hosted_app(monkeypatch)
    with TestClient(app) as client:
        def headers(teams):
            return signed_caller(AGENT, is_organization_admin=True, team_uids=[WRITERS], requester={"sub": str(ACTOR), "team_uids": teams, "is_organization_admin": False})

        allowed = call(client, "crm_contacts_create", {"payload": {"first_name": "Ada", "owner_uid": str(ACTOR)}}, headers=headers([WRITERS]))
        assert allowed["structuredContent"]["code"] == "ok"
        assert store.calls[-1][2] == ACTOR
        denied = call(client, "crm_contacts_create", {"payload": {"first_name": "Denied"}}, headers=headers([]))
        assert denied["structuredContent"]["code"] == "forbidden"
        read = call(client, "crm_contacts_list", headers=headers([READERS]))
        assert read["structuredContent"]["code"] == "ok"
        denied = call(client, "crm_contacts_create", {"payload": {"first_name": "Reader"}}, headers=headers([READERS]))
        assert denied["structuredContent"]["code"] == "forbidden"
        assert len(store.calls) == 2


def test_mcp_accepts_direct_human_and_rechecks_capability(signed_caller, monkeypatch):
    app, store = hosted_app(monkeypatch)

    def lookup(uid):
        from mainsequence._request_identity import _caller_read_headers
        from mainsequence.client import User

        headers = _caller_read_headers(User.get_object_url(), User.get_object_url())
        assert "X-MainSequence-Caller-Assertion" in headers
        assert uid == str(ACTOR)
        return SimpleNamespace(is_active=True, identity_type="human")

    monkeypatch.setattr("api.crm.mcp_server.User.get_by_uid", lookup)
    with TestClient(app) as client:
        allowed = call(
            client,
            "crm_contacts_create",
            {"payload": {"first_name": "Ada", "owner_uid": str(ACTOR)}},
            headers=signed_caller(ACTOR, team_uids=[WRITERS]),
        )
        denied = call(
            client,
            "crm_contacts_create",
            {"payload": {"first_name": "Denied"}},
            headers=signed_caller(ACTOR, team_uids=[READERS]),
        )
    assert allowed["structuredContent"]["code"] == "ok"
    assert denied["structuredContent"]["code"] == "forbidden"
    assert len(store.calls) == 1


def test_mcp_rejects_unbound_workload_and_logs_reason(signed_caller, monkeypatch, caplog):
    app, store = hosted_app(monkeypatch)
    monkeypatch.setattr(
        "api.crm.mcp_server.User.get_by_uid",
        lambda uid: SimpleNamespace(is_active=True, identity_type="workload"),
    )
    with TestClient(app) as client:
        denied = call(
            client,
            "crm_contacts_list",
            headers=signed_caller(AGENT, team_uids=[WRITERS]),
        )
    assert denied["structuredContent"]["code"] == "forbidden"
    assert store.calls == []
    record = next(
        entry
        for entry in caplog.records
        if getattr(entry, "crm_mcp_denial_reason", None) == "unbound_workload"
    )
    assert record.crm_mcp_tool == "crm_contacts_list"
    assert record.crm_mcp_identity_mode == "direct_caller"
    assert record.crm_request_uid != "unknown"


def test_delegated_owner_lookup_does_not_use_workload_directory(signed_caller, monkeypatch):
    app, store = hosted_app(monkeypatch)
    monkeypatch.setattr("src.crm.platform.hosted_runtime.User.get_by_uid", lambda uid: pytest.fail("Must not borrow workload visibility"))
    headers = signed_caller(AGENT, requester={"sub": str(ACTOR), "team_uids": [WRITERS], "is_organization_admin": False})
    with TestClient(app, headers=headers) as client:
        result = call(client, "crm_contacts_create", {"payload": {"first_name": "Ada", "owner_uid": str(OTHER)}})
    assert result["structuredContent"]["code"] == "validation_error"
    assert store.calls == []


def test_signed_admin_and_ungranted_person_are_separate(signed_caller, monkeypatch):
    app, store = hosted_app(monkeypatch)
    with TestClient(app) as client:
        denied = client.post("/api/crm/v1/contacts/", headers=signed_caller(ACTOR), json={"first_name": "Denied"})
        allowed = client.post("/api/crm/v1/contacts/", headers=signed_caller(ACTOR, is_organization_admin=True), json={"first_name": "Admin"})
    assert denied.status_code == 403
    assert allowed.status_code == 201
    assert len(store.calls) == 1


def test_other_owner_is_read_through_caller_scoped_sdk_directory(signed_caller, monkeypatch):
    app, store = hosted_app(monkeypatch)
    def lookup(uid):
        from mainsequence._request_identity import _caller_read_headers
        from mainsequence.client import User
        headers = _caller_read_headers(User.get_object_url(), User.get_object_url())
        assert "X-MainSequence-Caller-Assertion" in headers
        assert uid == str(OTHER)
        return SimpleNamespace(is_active=True, identity_type="human")

    monkeypatch.setattr("src.crm.platform.hosted_runtime.User.get_by_uid", lookup)
    with TestClient(app, headers=signed_caller(ACTOR, team_uids=[WRITERS])) as client:
        response = client.post("/api/crm/v1/contacts/", json={"first_name": "Ada", "owner_uid": str(OTHER)})
    assert response.status_code == 201
    assert len(store.calls) == 1


def test_invalid_team_configuration_fails_at_startup(monkeypatch):
    monkeypatch.setenv("CRM_WRITER_TEAM_UIDS", "not-a-team-uuid")
    with pytest.raises(RuntimeError, match="CRM_WRITER_TEAM_UIDS"):
        PlatformPolicy.from_environment()
