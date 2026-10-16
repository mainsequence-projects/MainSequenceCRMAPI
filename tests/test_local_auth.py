"""The explicit local launcher presents its SDK sign-in, never request headers.

The CRM's installed request identity verifies that sign-in with the Main
Sequence backend, exactly as it verifies any direct Bearer caller locally.
"""

import os
import uuid
from threading import Event
from types import SimpleNamespace

import pytest
import requests
from fastapi.testclient import TestClient

from api.crm.local import create_app
from mainsequence.client.exceptions import AuthenticationError, ServerError, TransportError

ACTOR = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
OTHER = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"


class UnavailableRegistry:
    def validate(self):
        raise RuntimeError("Catalog unavailable")


class ReadyRegistry:
    def validate(self):
        pass


def local_client(app):
    return TestClient(app, client=("127.0.0.1", 50000))


def test_local_request_uses_signed_in_process_user(monkeypatch, local_sign_in):
    local_sign_in.as_user(SimpleNamespace(uid=ACTOR, username="local"))
    monkeypatch.setattr("api.crm.local.configured_registry", UnavailableRegistry)
    client = local_client(create_app())
    assert client.get("/healthz").status_code == 200
    assert local_sign_in.lookups == 0 and local_sign_in.backend.lookups == []
    response = client.get("/api/crm/v1/readiness/")
    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
    assert local_sign_in.lookups == 1
    assert local_sign_in.backend.lookups == ["Bearer local-session"]
    # The signed-in user's details are cached; the SDK verifies every request.
    assert client.get("/api/crm/v1/readiness/").status_code == 503
    assert local_sign_in.lookups == 1
    assert len(local_sign_in.backend.lookups) == 2
    for claimed in ({"X-User-UID": OTHER}, {"Authorization": "Bearer someone-else"}):
        assert client.get("/api/crm/v1/readiness/", headers=claimed).status_code == 401
    assert local_sign_in.lookups == 1
    assert len(local_sign_in.backend.lookups) == 2


def test_local_signin_cache_expires_and_revalidates(monkeypatch, local_sign_in):
    now = [100.0]
    local_sign_in.as_user(SimpleNamespace(uid=ACTOR, username="local"))
    monkeypatch.setattr("api.crm.local.time.monotonic", lambda: now[0])
    monkeypatch.setattr("api.crm.local.configured_registry", UnavailableRegistry)
    client = local_client(create_app())
    assert client.get("/api/crm/v1/readiness/").status_code == 503
    now[0] = 401.0
    assert client.get("/api/crm/v1/readiness/").status_code == 503
    assert local_sign_in.lookups == 2


def test_local_launcher_rejects_remote_and_invalid_signin(monkeypatch, local_sign_in):
    def rejected():
        raise AuthenticationError("Fixture credentials were refused")

    monkeypatch.setattr("api.crm.local.User.get_authenticated_user_details", rejected)
    app = create_app()
    app.state.crm_google_service = SimpleNamespace(
        callback=lambda **_: "/extensions/google/oauth/done/?google_status=failed"
    )
    assert TestClient(app, client=("198.51.100.1", 50000)).get("/healthz").status_code == 403
    client = local_client(app)
    # Not signed in: the Google callback and completion page still answer.
    assert client.get("/extensions/google/oauth/done/").status_code == 200
    callback = client.get("/extensions/google/oauth/callback/", follow_redirects=False)
    assert callback.status_code == 303
    assert client.get("/api/crm/v1/readiness/").status_code == 401
    assert local_sign_in.backend.lookups == []


@pytest.mark.parametrize("phase", ["user", "token"])
@pytest.mark.parametrize("failure", ["connection", "transport", "backend", "unknown"])
def test_local_signin_unavailable_is_not_bad_credentials(phase, failure, monkeypatch, local_sign_in, caplog):
    local_sign_in.as_user(SimpleNamespace(uid=ACTOR, username="local"))
    response = requests.Response()
    response.status_code = 503
    response.url = "https://private.invalid/?token=PRIVATE_TOKEN"
    errors = {
        "connection": requests.ConnectionError("PRIVATE_TOKEN"),
        "transport": TransportError("PRIVATE_TOKEN"),
        "backend": ServerError("PRIVATE_TOKEN", response=response),
        "unknown": RuntimeError("PRIVATE_TOKEN"),
    }

    def unavailable():
        raise errors[failure]

    target = "User.get_authenticated_user_details" if phase == "user" else "get_authorization_headers"
    monkeypatch.setattr(f"api.crm.local.{target}", unavailable)
    result = local_client(create_app()).get("/api/crm/v1/bootstrap/")
    assert result.status_code == 503
    error = result.json()["error"]
    assert error["code"] == "LOCAL_SIGN_IN_UNAVAILABLE"
    assert uuid.UUID(error["request_uid"])
    record = next(r for r in caplog.records if getattr(r, "crm_stage", None) == f"local-sign-in-{phase}")
    assert record.crm_request_uid == error["request_uid"]
    assert record.error_type == type(errors[failure]).__name__
    assert record.exc_info is None
    assert local_sign_in.backend.lookups == []
    assert "PRIVATE_TOKEN" not in result.text + caplog.text
    assert "private.invalid" not in result.text + caplog.text


def test_backend_refusal_or_outage_stops_the_request(monkeypatch, local_sign_in):
    local_sign_in.as_user(SimpleNamespace(uid=ACTOR, username="local"))
    monkeypatch.setattr("api.crm.local.configured_registry", UnavailableRegistry)
    client = local_client(create_app())
    local_sign_in.backend.status = 401
    assert client.get("/api/crm/v1/readiness/").status_code == 401
    local_sign_in.backend.status = 503
    assert client.get("/api/crm/v1/readiness/").status_code == 503


def test_local_policy_still_grants_only_the_signed_in_user(monkeypatch, local_sign_in):
    local_sign_in.as_user(SimpleNamespace(uid=ACTOR, username="local"))
    # The session now belongs to someone else (a new sign-in while details are cached).
    local_sign_in.backend.sign_in(OTHER, token=local_sign_in.token)
    monkeypatch.setattr("api.crm.local.configured_registry", ReadyRegistry)
    response = local_client(create_app()).get("/api/crm/v1/readiness/")
    assert response.status_code == 403
    assert "checks" not in response.json()


def test_local_signin_timeout_returns_a_specific_503(monkeypatch, local_sign_in):
    release = Event()
    monkeypatch.setattr("api.crm.local.LOCAL_SIGN_IN_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(
        "api.crm.local.User.get_authenticated_user_details",
        lambda: release.wait(1),
    )
    try:
        response = local_client(create_app()).get("/api/crm/v1/bootstrap/")
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "LOCAL_SIGN_IN_TIMEOUT"
    finally:
        release.set()


def test_local_launcher_installs_local_request_identity_once():
    app = create_app()
    assert app.state.mainsequence_request_identity == {
        "installed": True,
        "mode": "local",
        "public_ingress": (
            ("GET", "/healthz"),
            ("GET", "/extensions/google/oauth/callback/"),
            ("GET", "/extensions/google/oauth/done/"),
        ),
    }
    modules = [middleware.cls.__module__ for middleware in app.user_middleware]
    assert modules.count("mainsequence.server.fastapi") == 1
    # The local public routes were declared for this app only.
    assert "FASTAPI_PUBLIC_INGRESS" not in os.environ


def test_local_launcher_refuses_a_deployment_environment(signed_caller):
    with pytest.raises(RuntimeError, match="outside a Main Sequence deployment"):
        create_app()
