"""The reproduced startup failures retain safe causes without leaking SDK data."""

import json
import uuid
from types import SimpleNamespace

import pytest
import requests
from fastapi.testclient import TestClient

from api.crm.main import create_app
from mainsequence.client.exceptions import ServerError
from src.crm.models.bootstrap import Readiness
from src.crm.platform.catalog import CatalogValidationError

ACTOR = uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
UPSTREAM_REQUEST = "150c717a203ab421692f6d146a5fe394"


@pytest.fixture(autouse=True)
def no_external_http(monkeypatch):
    def refuse(*args, **kwargs):
        pytest.fail("Readiness failure tests must not contact a real backend")

    monkeypatch.setattr(requests.sessions.Session, "request", refuse)


def upstream_failure(*, code="authentication_unavailable", request_id=UPSTREAM_REQUEST):
    response = requests.Response()
    response.status_code = 503
    response.url = "https://private.example.test/?token=PRIVATE_TOKEN"
    response.headers["X-Request-ID"] = request_id
    return ServerError(
        "PRIVATE_TRACE Authorization: Bearer PRIVATE_TOKEN",
        response=response,
        payload={"code": code, "detail": "PRIVATE_TRACE PRIVATE_TOKEN"},
    )


def failing(error):
    def fail(*args):
        raise error

    return fail


def app_with_failure(*, stage, error):
    app = create_app()
    app.state.crm_registry = SimpleNamespace(validate=lambda: None)
    app.state.crm_policy = SimpleNamespace(capabilities=lambda _: {"crm.read"})
    app.state.crm_directory = SimpleNamespace(display_name=lambda _: "Fixture", is_selectable=lambda _: True)
    app.state.crm_bootstrap = SimpleNamespace(read=lambda _: pytest.fail("A failed catalog must block settings reads"))
    if stage == "catalog":
        app.state.crm_registry.validate = failing(error)
    else:
        app.state.crm_bootstrap.read = failing(error)
    return app


@pytest.mark.parametrize("path", ["readiness", "bootstrap"])
def test_gateway_failure_reaches_http_response_and_logs_without_secrets(path, signed_caller, caplog):
    app = app_with_failure(stage="catalog", error=upstream_failure())
    response = TestClient(app, headers=signed_caller(ACTOR)).get(f"/api/crm/v1/{path}/")
    assert response.status_code == 503
    body = response.json()
    document = body["readiness"] if path == "bootstrap" else body
    assert Readiness.model_validate(document).status.value == "not_ready"
    checks = {check["id"]: check for check in document["checks"]}
    assert "Upstream HTTP 503 (authentication_unavailable)" in checks["catalog"]["message"]
    assert "FastAPI authentication is temporarily unavailable" in checks["catalog"]["message"]
    assert UPSTREAM_REQUEST in checks["catalog"]["message"]
    assert checks["crm-settings"]["status"] == checks["bootstrap"]["status"] == "pending"
    assert checks["directory"]["status"] == "ready"
    record = next(record for record in caplog.records if getattr(record, "crm_stage", None) == "catalog")
    assert record.upstream_status == 503 and record.upstream_code == "authentication_unavailable"
    assert record.upstream_request_id == UPSTREAM_REQUEST
    assert uuid.UUID(record.crm_request_uid)
    if path == "bootstrap":
        assert body["error"]["request_uid"] == record.crm_request_uid
    assert record.exc_info is None
    for secret in ("PRIVATE_TOKEN", "PRIVATE_TRACE", "private.example.test"):
        assert secret not in response.text + caplog.text


def test_missing_binding_is_actionable_and_does_not_claim_settings_failed(signed_caller, caplog):
    message = (
        "CRM MetaTable catalog is incomplete. Missing active bindings: mainsequence_crm__prompt. "
        "Apply this version's CRM migrations; for hosted data use the migrate-crm deployment Job."
    )
    app = app_with_failure(stage="catalog", error=CatalogValidationError(message))
    response = TestClient(app, headers=signed_caller(ACTOR)).get("/api/crm/v1/bootstrap/")
    assert response.status_code == 503
    checks = {check["id"]: check for check in response.json()["readiness"]["checks"]}
    assert checks["catalog"]["message"] == message
    assert checks["crm-settings"]["status"] == "pending"
    assert message in caplog.text


def test_settings_failure_keeps_fresh_policy_check_and_upstream_correlation(signed_caller, caplog):
    app = app_with_failure(stage="bootstrap", error=upstream_failure())
    policy_calls = []
    app.state.crm_policy.capabilities = lambda actor: policy_calls.append(actor) or {"crm.read"}
    response = TestClient(app, headers=signed_caller(ACTOR)).get("/api/crm/v1/bootstrap/")
    assert response.status_code == 503
    checks = {check["id"]: check for check in response.json()["readiness"]["checks"]}
    assert checks["catalog"]["status"] == checks["authorization"]["status"] == "ready"
    assert checks["bootstrap"]["status"] == "failed"
    assert UPSTREAM_REQUEST in checks["bootstrap"]["message"]
    assert policy_calls == [ACTOR]
    assert "PRIVATE_TOKEN" not in response.text + caplog.text


@pytest.mark.parametrize("error", [
    RuntimeError("PRIVATE_TRACE PRIVATE_TOKEN"),
    upstream_failure(code="PRIVATE_TOKEN", request_id="PRIVATE_TRACE PRIVATE_TOKEN"),
])
def test_unknown_errors_and_untrusted_fields_stay_redacted(error, signed_caller, caplog):
    app = app_with_failure(stage="catalog", error=error)
    response = TestClient(app, headers=signed_caller(ACTOR)).get("/api/crm/v1/bootstrap/")
    assert response.status_code == 503
    assert "Active MetaTable catalog is unavailable" in response.text
    for secret in ("PRIVATE_TOKEN", "PRIVATE_TRACE", "private.example.test"):
        assert secret not in response.text + caplog.text


def test_final_bootstrap_read_uses_the_same_safe_diagnostic(monkeypatch, signed_caller, caplog):
    app = app_with_failure(stage="bootstrap", error=upstream_failure(request_id=f"{UPSTREAM_REQUEST}, {UPSTREAM_REQUEST}"))
    monkeypatch.setattr("api.crm.main.readiness", lambda *_: {"status": "ready", "checks": []})
    response = TestClient(app, headers=signed_caller(ACTOR)).get("/api/crm/v1/bootstrap/")
    assert response.status_code == 503
    assert "authentication_unavailable" in response.json()["error"]["message"]
    assert response.json()["error"]["message"].count(UPSTREAM_REQUEST) == 1
    assert "PRIVATE_TOKEN" not in response.text + caplog.text
    assert json.loads(response.content)["error"]["code"] == "CRM_NOT_READY"
