"""The CRM installs Main Sequence request identity once and takes its caller from it.

PodDeploymentOrchestrator serves a FastAPI release only when
``app.state.mainsequence_request_identity`` declares the installed integration,
the caller-verification mode the deployment selects and exactly the
deployment's public ingress. Every protected route then reads the verified
caller with ``User.get_logged_user()`` through ``authenticated_actor``.
"""

import json
import time
import uuid

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import HTTPException
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from api.crm.main import create_app
from mainsequence.server.caller_assertions import ASSERTION_HEADER
from mainsequence.server.fastapi import install_request_identity
from src.crm.platform.runtime import authenticated_actor

ACTOR = uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
OTHER = uuid.UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
GOOGLE_PUBLIC_INGRESS = (
    ("GET", "/extensions/google/oauth/callback/"),
    ("GET", "/extensions/google/oauth/done/"),
)


class Policy:
    def __init__(self):
        self.actors = []

    def capabilities(self, actor_uid):
        self.actors.append(actor_uid)
        return {"crm.read"}


class Directory:
    def display_name(self, actor_uid):
        return "Verified caller"

    def is_selectable(self, actor_uid):
        return True


def principals(headers=()):
    """GET /principals/, which returns the caller the CRM resolved; and its policy."""
    app = create_app()
    policy = Policy()
    app.state.crm_policy = policy
    app.state.crm_directory = Directory()
    return TestClient(app).get("/api/crm/v1/principals/", headers=headers), policy


def test_deployed_app_declares_what_the_launcher_requires(signed_caller, deployment_public_ingress):
    assert deployment_public_ingress == GOOGLE_PUBLIC_INGRESS
    assert create_app().state.mainsequence_request_identity == {
        "installed": True,
        "mode": "assertion",
        "public_ingress": deployment_public_ingress,
    }


def test_public_ingress_routes_are_mounted_where_the_launcher_looks(deployment_public_ingress):
    # The launcher and the SDK accept a declared pair only as an APIRoute listed
    # in app.routes; FastAPI 0.141 lists an included router as a single entry.
    app = create_app()
    for method, path in deployment_public_ingress:
        assert any(
            isinstance(route, APIRoute) and route.path == path and method in route.methods
            for route in app.routes
        ), (method, path)
    with TestClient(app) as client:  # Building the middleware stack checks them again.
        assert client.get("/extensions/google/oauth/done/").status_code == 401


def test_deployment_markers_alone_select_assertion_mode(signed_caller, monkeypatch):
    monkeypatch.delenv("MAINSEQUENCE_CALLER_AUTH_MODE")
    assert create_app().state.mainsequence_request_identity["mode"] == "assertion"


@pytest.mark.parametrize(
    ("marker", "value"),
    [
        ("APP_NAME", "5a0c1b0e-8f3a-4c1d-9e2b-7d6f5a4b3c21"),
        ("FASTAPI_PUBLIC_BASE_URL", "https://crm.example.test"),
        ("MAINSEQUENCE_CALLER_ASSERTION_ISSUER", "https://platform.example.test"),
        ("MAINSEQUENCE_CALLER_ASSERTION_JWKS_URL", "https://platform.example.test/keys/"),
    ],
)
def test_a_deployment_without_trust_configuration_does_not_start(monkeypatch, marker, value):
    # Any deployment marker selects assertion mode. Without the rest of the
    # trusted configuration callers cannot be verified, so the app fails to build.
    monkeypatch.setenv(marker, value)
    with pytest.raises(RuntimeError):
        create_app()


def test_deployed_configuration_cannot_select_local_mode(signed_caller, monkeypatch):
    monkeypatch.setenv("MAINSEQUENCE_CALLER_AUTH_MODE", "local")
    with pytest.raises(RuntimeError, match="caller authentication mode"):
        create_app()


def test_app_outside_a_deployment_declares_local_mode():
    assert create_app().state.mainsequence_request_identity == {
        "installed": True,
        "mode": "local",
        "public_ingress": (),
    }


def test_request_identity_is_installed_once_and_runs_first():
    first, second = create_app(), create_app()
    for app in (first, second):
        modules = [middleware.cls.__module__ for middleware in app.user_middleware]
        assert modules.count("mainsequence.server.fastapi") == 1
        assert modules[0] == "mainsequence.server.fastapi"
    with pytest.raises(RuntimeError, match="already installed"):
        install_request_identity(first)


def test_signed_caller_is_the_crm_actor(signed_caller):
    # A platform UID header naming someone else cannot change the verified caller.
    response, policy = principals({**signed_caller(ACTOR), "X-User-UID": str(OTHER)})
    assert response.status_code == 200
    assert response.json()["items"][0]["uid"] == str(ACTOR)
    assert policy.actors == [ACTOR]


def _rejected_headers(signed_caller, case):
    now = int(time.time())
    other_release = str(uuid.uuid4())
    return {
        "missing": {},
        "malformed": {ASSERTION_HEADER: "not-a-caller-assertion"},
        "expired": signed_caller(ACTOR, iat=now - 600, nbf=now - 600, exp=now - 480),
        "other_release": signed_caller(
            ACTOR,
            aud=f"urn:mainsequence:fapi:{other_release}",
            resource_release_uid=other_release,
        ),
        "other_environment": signed_caller(ACTOR, organization_environment_uid=str(uuid.uuid4())),
        "invalid_teams": signed_caller(ACTOR, team_uids="not-a-list"),
        "legacy_teams": signed_caller(ACTOR, team_uids=[]),
        "legacy_requester_teams": signed_caller(OTHER, requester={
            "sub": str(ACTOR), "team_uids": [], "is_organization_admin": False,
        }),
        "invalid_admin_flag": signed_caller(ACTOR, is_organization_admin="true"),
        "unknown_signer": signed_caller(ACTOR, signing_key=Ed25519PrivateKey.generate()),
        "duplicate": [*signed_caller(ACTOR).items(), *signed_caller(ACTOR).items()],
        "uid_header_only": {"X-User-UID": str(ACTOR)},
        "numeric_user_id": {**signed_caller(ACTOR), "X-User-ID": "42"},
    }[case]


@pytest.mark.parametrize(
    "case",
    [
        "missing",
        "malformed",
        "expired",
        "other_release",
        "other_environment",
        "invalid_teams",
        "legacy_teams",
        "legacy_requester_teams",
        "invalid_admin_flag",
        "unknown_signer",
        "duplicate",
        "uid_header_only",
        "numeric_user_id",
    ],
)
def test_request_without_a_valid_caller_never_reaches_crm_code(signed_caller, case):
    response, policy = principals(_rejected_headers(signed_caller, case))
    assert response.status_code == 401
    assert set(response.json()) == {"detail"}
    assert policy.actors == []


def test_unreachable_caller_keys_return_503(signed_caller):
    signed_caller.keys_available = False
    response, policy = principals(signed_caller(ACTOR))
    assert response.status_code == 503
    assert policy.actors == []


def test_a_public_route_has_no_crm_caller(signed_caller, monkeypatch):
    # Even a protected route declared as public ingress by mistake gets no caller:
    # the platform's admission strips credentials and CRM code fails closed.
    readiness = "/api/crm/v1/readiness/"
    monkeypatch.setenv("FASTAPI_PUBLIC_INGRESS", json.dumps([{"method": "GET", "path": readiness}]))
    app = create_app()
    policy = Policy()
    app.state.crm_policy = policy
    headers = {"X-Public-Ingress": "1", **signed_caller(ACTOR)}
    response = TestClient(app).get(readiness, headers=headers)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "IDENTITY_REQUIRED"
    assert policy.actors == []


def test_local_bearer_caller_is_the_crm_actor(local_backend):
    response, policy = principals(local_backend.sign_in(ACTOR))
    assert response.status_code == 200
    assert response.json()["items"][0]["uid"] == str(ACTOR)
    assert policy.actors == [ACTOR]
    assert local_backend.lookups == [f"Bearer token-{ACTOR}"]


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer refused"},
        {"Authorization": "Basic YWRtaW46YWRtaW4="},
        {"X-User-UID": str(ACTOR)},
    ],
)
def test_local_request_without_a_valid_bearer_is_rejected(local_backend, headers):
    response, policy = principals(headers)
    assert response.status_code == 401
    assert policy.actors == []


def test_local_bearer_cannot_claim_another_uid(local_backend):
    response, policy = principals({**local_backend.sign_in(ACTOR), "X-User-UID": str(OTHER)})
    assert response.status_code == 401
    assert policy.actors == []


def test_local_backend_outage_returns_503(local_backend):
    local_backend.status = 502
    response, policy = principals(local_backend.sign_in(ACTOR))
    assert response.status_code == 503
    assert policy.actors == []


def test_authenticated_actor_fails_closed_outside_a_verified_request():
    with pytest.raises(HTTPException) as caught:
        authenticated_actor()
    assert caught.value.status_code == 401


def test_delegated_rest_uses_verified_requester(signed_caller):
    response, policy = principals(signed_caller(OTHER, requester={
        "sub": str(ACTOR), "is_organization_admin": False,
    }))
    assert response.status_code == 200
    assert response.json()["items"][0]["uid"] == str(ACTOR)
    assert policy.actors == [ACTOR]
