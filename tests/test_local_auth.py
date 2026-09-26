"""The explicit local launcher binds a real SDK sign-in, never request headers."""

from types import SimpleNamespace

from fastapi.testclient import TestClient

from api.crm.local import create_app


def test_local_request_uses_signed_in_process_user(monkeypatch):
    calls = []

    def signed_user():
        calls.append(True)
        return SimpleNamespace(uid="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", username="local")

    monkeypatch.setattr("api.crm.local.User.get_authenticated_user_details", signed_user)

    class UnavailableRegistry:
        def validate(self):
            raise RuntimeError("Catalog unavailable")

        def resolve_workspace_uid(self):
            raise RuntimeError("CRM dataset unavailable")

    monkeypatch.setattr("api.crm.local.configured_registry", UnavailableRegistry)
    client = TestClient(create_app(), client=("127.0.0.1", 50000))
    assert client.get("/healthz").status_code == 200
    assert not calls
    response = client.get("/api/crm/v1/readiness/")
    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
    assert calls == [True]
    assert client.get("/api/crm/v1/readiness/").status_code == 503
    assert calls == [True]
    assert (
        client.get(
            "/api/crm/v1/readiness/", headers={"X-User-UID": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"}
        ).status_code
        == 401
    )
    assert calls == [True]


def test_local_signin_cache_expires_and_revalidates(monkeypatch):
    now = [100.0]
    calls = []

    def signed_user():
        calls.append(True)
        return SimpleNamespace(uid="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", username="local")

    class UnavailableRegistry:
        def validate(self):
            raise RuntimeError("Catalog unavailable")

    monkeypatch.setattr("api.crm.local.time.monotonic", lambda: now[0])
    monkeypatch.setattr("api.crm.local.User.get_authenticated_user_details", signed_user)
    monkeypatch.setattr("api.crm.local.configured_registry", UnavailableRegistry)
    client = TestClient(create_app(), client=("127.0.0.1", 50000))
    assert client.get("/api/crm/v1/readiness/").status_code == 503
    now[0] = 131.0
    assert client.get("/api/crm/v1/readiness/").status_code == 503
    assert calls == [True, True]


def test_local_launcher_rejects_remote_and_invalid_signin(monkeypatch):
    def invalid():
        raise RuntimeError("expired credential")

    monkeypatch.setattr("api.crm.local.User.get_authenticated_user_details", invalid)
    app = create_app()
    assert TestClient(app, client=("198.51.100.1", 50000)).get("/healthz").status_code == 403
    assert (
        TestClient(app, client=("127.0.0.1", 50000)).get("/api/crm/v1/readiness/").status_code
        == 401
    )
