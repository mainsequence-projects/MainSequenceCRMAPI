"""Shared fixtures: persisted CRM configuration and verified caller identity."""

from __future__ import annotations

import json
import time
from pathlib import Path
from types import SimpleNamespace

import jwt
import pytest
import requests
import yaml
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import mainsequence.server.fastapi as request_identity
from mainsequence.server.caller_assertions import (
    ASSERTION_HEADER,
    ASSERTION_TYPE,
    CallerAssertionVerifier,
)
from src.crm.config import crm_config

ROOT = Path(__file__).resolve().parents[1]
ISSUER = "https://platform.example.test"
RELEASE_UID = "5a0c1b0e-8f3a-4c1d-9e2b-7d6f5a4b3c21"
ENVIRONMENT_UID = "0d6e3f7a-2b1c-4d5e-8f9a-1b2c3d4e5f60"
LOCAL_BACKEND = "http://backend.example.test"
# Deployment values that select and configure caller verification.
CALLER_ENVIRONMENT = (
    "APP_NAME",
    "FASTAPI_PUBLIC_BASE_URL",
    "FASTAPI_PUBLIC_INGRESS",
    "MAINSEQUENCE_CALLER_AUTH_MODE",
    "MAINSEQUENCE_CALLER_ASSERTION_ISSUER",
    "MAINSEQUENCE_CALLER_ASSERTION_JWKS_URL",
    "MAINSEQUENCE_ORGANIZATION_ENVIRONMENT_UID",
)


@pytest.fixture(autouse=True)
def outside_a_deployment(monkeypatch):
    """Create every app in local caller mode unless a test opts into a deployment."""
    for name in CALLER_ENVIRONMENT:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def deployment_public_ingress(monkeypatch) -> tuple[tuple[str, str], ...]:
    """Pass the workflow's public_ingress as Main Sequence does: FASTAPI_PUBLIC_INGRESS.

    Returns the declared pairs in the form the platform launcher compares.
    """
    workflow = yaml.safe_load(
        (ROOT / ".mainsequence" / "workflows" / "crm-api.yaml").read_text(encoding="utf-8")
    )
    api = next(item for item in workflow["resources"] if item["key"] == "crm-api")
    routes = api["spec"]["public_ingress"]
    monkeypatch.setenv("FASTAPI_PUBLIC_INGRESS", json.dumps(routes))
    return tuple((route["method"], route["path"]) for route in routes)


@pytest.fixture
def config_file(tmp_path, monkeypatch):
    path = tmp_path / "crm.yaml"
    monkeypatch.setattr("src.crm.config.CONFIG_PATH", path)

    def write(*, solution_selling=True, google_workspace=True):
        path.write_text(
            "extensions:\n"
            f"  solution_selling:\n    active: {str(solution_selling).lower()}\n"
            f"  google_workspace:\n    active: {str(google_workspace).lower()}\n",
            encoding="utf-8",
        )
        crm_config.cache_clear()

    write()
    yield write
    crm_config.cache_clear()


class SignedCaller:
    """The platform's signing key for caller assertions, and its key endpoint."""

    kid = "crm-test"

    def __init__(self):
        self.key = Ed25519PrivateKey.generate()
        self.keys_available = True

    def public_keys(self) -> dict:
        if not self.keys_available:
            raise ConnectionError("The platform's caller-key endpoint is unreachable")
        public = jwt.algorithms.OKPAlgorithm.to_jwk(self.key.public_key(), as_dict=True)
        jwk = {name: public[name] for name in ("kty", "crv", "x")}
        return {"keys": [{"kid": self.kid, "alg": "EdDSA", "use": "sig", **jwk}]}

    def __call__(self, user_uid, *, signing_key=None, **claims) -> dict[str, str]:
        """Headers of one request by ``user_uid``; ``claims`` override the signed ones."""
        now = int(time.time())
        payload = {
            "iss": ISSUER,
            "aud": f"urn:mainsequence:fapi:{RELEASE_UID}",
            "sub": str(user_uid),
            "resource_release_uid": RELEASE_UID,
            "organization_environment_uid": ENVIRONMENT_UID,
            "iat": now,
            "nbf": now,
            "exp": now + 120,
            **claims,
        }
        token = jwt.encode(
            payload,
            signing_key or self.key,
            algorithm="EdDSA",
            headers={"kid": self.kid, "typ": ASSERTION_TYPE},
        )
        return {ASSERTION_HEADER: token}


@pytest.fixture
def signed_caller(monkeypatch):
    """Deploy the app's caller verification and sign each request's caller assertion.

    The environment is what Main Sequence gives a deployed release. Only the
    download of the platform's public key is replaced; the SDK still checks
    every assertion's signature, issuer, release, Environment and lifetime.
    """
    caller = SignedCaller()
    deployment = {
        "APP_NAME": RELEASE_UID,
        "FASTAPI_PUBLIC_BASE_URL": "https://crm.example.test",
        "MAINSEQUENCE_CALLER_AUTH_MODE": "assertion",
        "MAINSEQUENCE_CALLER_ASSERTION_ISSUER": ISSUER,
        "MAINSEQUENCE_CALLER_ASSERTION_JWKS_URL": f"{ISSUER}/fastapi/caller-keys/",
        "MAINSEQUENCE_ORGANIZATION_ENVIRONMENT_UID": ENVIRONMENT_UID,
    }
    for name, value in deployment.items():
        monkeypatch.setenv(name, value)
    from_environment = CallerAssertionVerifier.from_environment
    monkeypatch.setattr(
        CallerAssertionVerifier,
        "from_environment",
        lambda: from_environment(fetch_jwks=caller.public_keys),
    )
    return caller


class LocalBackend:
    """The Main Sequence user lookup that local caller mode asks about each token."""

    def __init__(self):
        self.users: dict[str, dict] = {}
        self.lookups: list[str] = []
        self.status: int | None = None

    def sign_in(self, user_uid, *, token: str | None = None, username="local") -> dict[str, str]:
        token = token or f"token-{user_uid}"
        self.users[token] = {"uid": str(user_uid), "username": username}
        return {"Authorization": f"Bearer {token}"}

    def get(self, url, *, headers, timeout, allow_redirects):
        assert url == f"{LOCAL_BACKEND}/api/v1/users/me/"
        assert allow_redirects is False
        self.lookups.append(headers["Authorization"])
        user = self.users.get(headers["Authorization"].removeprefix("Bearer "))
        status = self.status or (200 if user else 401)
        return SimpleNamespace(status_code=status, json=lambda: user)


@pytest.fixture
def local_backend(monkeypatch):
    """Local caller mode against a stand-in for MAINSEQUENCE_ENDPOINT/api/v1/users/me/."""
    backend = LocalBackend()
    monkeypatch.setenv("MAINSEQUENCE_ENDPOINT", LOCAL_BACKEND)
    monkeypatch.setattr(
        request_identity,
        "requests",
        SimpleNamespace(get=backend.get, RequestException=requests.RequestException),
    )
    return backend


class LocalSignIn:
    """This process's SDK sign-in, as the loopback launcher reads it."""

    token = "local-session"

    def __init__(self, backend: LocalBackend):
        self.backend = backend
        self.user = None
        self.lookups = 0

    def as_user(self, user) -> None:
        """Sign in ``user``; the backend reports the same user for the session token."""
        self.user = user
        self.backend.sign_in(user.uid, token=self.token, username=user.username)

    def details(self):
        self.lookups += 1
        if self.user is None:
            raise RuntimeError("Not signed in")
        return self.user

    def authorization(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}


@pytest.fixture
def local_sign_in(monkeypatch, local_backend):
    session = LocalSignIn(local_backend)
    monkeypatch.setattr("api.crm.local.User.get_authenticated_user_details", session.details)
    monkeypatch.setattr("api.crm.local.get_authorization_headers", session.authorization)
    return session
