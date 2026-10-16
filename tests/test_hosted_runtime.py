"""Hosted defaults authorize signed people without workload permission fallback."""

import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from test_application import _settings_row
from test_bootstrap_runtime import ReadyRegistry
from test_mcp_tools import ACTOR, AGENT, Store, call

from api.crm.main import create_app
from mainsequence.client import User
from src.crm.platform.hosted_runtime import PlatformPolicy

WRITERS = str(uuid.UUID(int=701))
READERS = str(uuid.UUID(int=702))
OTHER = uuid.UUID(int=703)


@pytest.fixture(autouse=True)
def memberships(monkeypatch):
    """Replace only the SDK's platform membership fetch, not its scoped helper."""
    backend = SimpleNamespace(people={}, calls=[], error=None)

    def fetch(cls, person_uid, team_uids, assertion):
        assert assertion
        backend.calls.append((person_uid, frozenset(team_uids)))
        if backend.error is not None:
            raise backend.error
        return set(backend.people.get(person_uid, ())) & set(team_uids)

    monkeypatch.setattr(User, "_team_memberships", classmethod(fetch))
    return backend


def hosted_app(monkeypatch):
    monkeypatch.setenv("CRM_WRITER_TEAM_UIDS", WRITERS)
    monkeypatch.setenv("CRM_READER_TEAM_UIDS", READERS)
    app = create_app()
    app.state.crm_registry = ReadyRegistry()
    app.state.crm_bootstrap.store = SimpleNamespace(bootstrap_record=_settings_row)
    store = Store()
    app.state.crm_resources = store
    return app, store


def test_default_hosted_bootstrap_reads_signed_self_and_governed_settings(signed_caller, monkeypatch, memberships):
    app, _ = hosted_app(monkeypatch)
    memberships.people[str(ACTOR)] = {WRITERS}
    monkeypatch.setattr("api.crm.main.resolve_assistant", _no_assistant)
    monkeypatch.setattr("src.crm.platform.hosted_runtime.User.get_by_uid", lambda uid: pytest.fail("Self needs no workload directory lookup"))
    with TestClient(app) as client:
        response = client.get("/api/crm/v1/bootstrap/", headers=signed_caller(ACTOR))
    assert response.status_code == 200
    assert response.json()["readiness"]["status"] == "ready"
    assert response.json()["current_user"]["uid"] == str(ACTOR)
    assert "crm.create" in response.json()["capabilities"]
    assert "crm.configure" not in response.json()["capabilities"]


async def _no_assistant(origin):
    return {"enabled": False, "runtime": None, "agent_uid": None, "environment_uid": None, "display_name": "CRM assistant"}


def test_mcp_uses_requester_teams_and_never_workload_admin(signed_caller, monkeypatch, memberships):
    app, store = hosted_app(monkeypatch)
    memberships.people[str(AGENT)] = {WRITERS}
    with TestClient(app) as client:
        def headers(teams):
            memberships.people[str(ACTOR)] = set(teams)
            return signed_caller(AGENT, is_organization_admin=True, requester={"sub": str(ACTOR), "is_organization_admin": False})

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
    assert {uid for uid, _ in memberships.calls} == {str(ACTOR)}


def test_mcp_accepts_direct_human_and_rechecks_capability(signed_caller, monkeypatch, memberships):
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
        memberships.people[str(ACTOR)] = {WRITERS}
        allowed = call(
            client,
            "crm_contacts_create",
            {"payload": {"first_name": "Ada", "owner_uid": str(ACTOR)}},
            headers=signed_caller(ACTOR),
        )
        memberships.people[str(ACTOR)] = {READERS}
        denied = call(
            client,
            "crm_contacts_create",
            {"payload": {"first_name": "Denied"}},
            headers=signed_caller(ACTOR),
        )
    assert allowed["structuredContent"]["code"] == "ok"
    assert denied["structuredContent"]["code"] == "forbidden"
    assert len(store.calls) == 1


def test_mcp_rejects_unbound_workload_and_logs_reason(signed_caller, monkeypatch, caplog, memberships):
    app, store = hosted_app(monkeypatch)
    memberships.people[str(AGENT)] = {WRITERS}
    monkeypatch.setattr(
        "api.crm.mcp_server.User.get_by_uid",
        lambda uid: SimpleNamespace(is_active=True, identity_type="workload"),
    )
    with TestClient(app) as client:
        denied = call(
            client,
            "crm_contacts_list",
            headers=signed_caller(AGENT),
        )
    assert denied["structuredContent"]["code"] == "forbidden"
    assert store.calls == []
    assert memberships.calls == []
    record = next(
        entry
        for entry in caplog.records
        if getattr(entry, "crm_mcp_denial_reason", None) == "unbound_workload"
    )
    assert record.crm_mcp_tool == "crm_contacts_list"
    assert record.crm_mcp_identity_mode == "direct_caller"
    assert record.crm_request_uid != "unknown"


def test_delegated_owner_lookup_does_not_use_workload_directory(signed_caller, monkeypatch, memberships):
    app, store = hosted_app(monkeypatch)
    memberships.people[str(ACTOR)] = {WRITERS}
    monkeypatch.setattr("src.crm.platform.hosted_runtime.User.get_by_uid", lambda uid: pytest.fail("Must not borrow workload visibility"))
    headers = signed_caller(AGENT, requester={"sub": str(ACTOR), "is_organization_admin": False})
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


def test_policy_rechecks_membership_even_within_one_request(signed_caller, monkeypatch, memberships):
    app, _ = hosted_app(monkeypatch)
    memberships.people[str(ACTOR)] = {WRITERS}

    @app.get("/test-policy-freshness/")
    def probe():
        before = app.state.crm_policy.capabilities(ACTOR)
        memberships.people[str(ACTOR)] = set()
        after = app.state.crm_policy.capabilities(ACTOR)
        return {"before": sorted(before), "after": sorted(after)}

    with TestClient(app) as client:
        response = client.get("/test-policy-freshness/", headers=signed_caller(ACTOR))
    assert response.status_code == 200
    assert "crm.create" in response.json()["before"]
    assert response.json()["after"] == []
    assert memberships.calls == [(str(ACTOR), frozenset({READERS, WRITERS}))] * 2


def test_membership_failure_cannot_use_workload_permissions(signed_caller, monkeypatch, memberships):
    app, store = hosted_app(monkeypatch)
    memberships.people[str(AGENT)] = {WRITERS}
    memberships.error = ConnectionError("Membership service unavailable")
    headers = signed_caller(AGENT, is_organization_admin=True, requester={
        "sub": str(ACTOR), "is_organization_admin": False,
    })
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post("/api/crm/v1/contacts/", headers=headers, json={"first_name": "Denied"})
    assert response.status_code == 503
    assert store.calls == []
    assert memberships.calls == [(str(ACTOR), frozenset({READERS, WRITERS}))]


def test_other_owner_is_read_through_caller_scoped_sdk_directory(signed_caller, monkeypatch, memberships):
    app, store = hosted_app(monkeypatch)
    memberships.people[str(ACTOR)] = {WRITERS}
    def lookup(uid):
        from mainsequence._request_identity import _caller_read_headers
        from mainsequence.client import User
        headers = _caller_read_headers(User.get_object_url(), User.get_object_url())
        assert "X-MainSequence-Caller-Assertion" in headers
        assert uid == str(OTHER)
        return SimpleNamespace(is_active=True, identity_type="human")

    monkeypatch.setattr("src.crm.platform.hosted_runtime.User.get_by_uid", lookup)
    with TestClient(app, headers=signed_caller(ACTOR)) as client:
        response = client.post("/api/crm/v1/contacts/", json={"first_name": "Ada", "owner_uid": str(OTHER)})
    assert response.status_code == 201
    assert len(store.calls) == 1


def test_invalid_team_configuration_fails_at_startup(monkeypatch):
    monkeypatch.setenv("CRM_WRITER_TEAM_UIDS", "not-a-team-uuid")
    with pytest.raises(RuntimeError, match="CRM_WRITER_TEAM_UIDS"):
        PlatformPolicy.from_environment()


@pytest.mark.parametrize("matches,expected", [
    ([(str(ACTOR), True)], "ok"),
    ([], "forbidden"),
    ([(str(OTHER), True)], "forbidden"),
    ([(str(ACTOR), False)], "forbidden"),
    ([(str(ACTOR), True), (str(ACTOR), True)], "forbidden"),
])
def test_mcp_human_directory_projection_requires_exact_type_proof(
    signed_caller, monkeypatch, memberships, matches, expected,
):
    app, store = hosted_app(monkeypatch)
    memberships.people[str(ACTOR)] = {READERS}
    monkeypatch.setattr(
        "api.crm.mcp_server.User.get_by_uid",
        lambda uid: SimpleNamespace(uid=uid, is_active=True, identity_type=None),
    )
    def human_filter(**filters):
        from mainsequence._request_identity import _caller_read_headers
        from mainsequence.client import User
        assert "X-MainSequence-Caller-Assertion" in _caller_read_headers(
            User.get_object_url(), User.get_object_url(),
        )
        assert filters == {"uid": str(ACTOR), "identity_type": "human"}
        return [SimpleNamespace(uid=uid, is_active=active) for uid, active in matches]
    monkeypatch.setattr("api.crm.mcp_server.User.filter", human_filter)
    with TestClient(app) as client:
        result = call(client, "crm_contacts_list", headers=signed_caller(ACTOR))
    assert result["structuredContent"]["code"] == expected
    assert len(store.calls) == (1 if expected == "ok" else 0)
