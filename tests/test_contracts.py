"""Local contract checks; these do not claim platform integration success."""

import uuid

from fastapi.testclient import TestClient

from api.crm.main import create_app
from src.crm.metatables import MODELS, Base
from src.crm.models.bootstrap import Readiness
from src.crm.models.errors import Error

ACTOR = uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")


def test_dictionary_has_twenty_six_managed_tables_without_application_tenant():
    assert len(MODELS) == len(Base.metadata.tables) == 26
    for name, model in MODELS.items():
        assert model.__tablename__ == f"mainsequence_crm__{name}"
        assert model.__metatable_namespace__ == "mainsequence-crm"
        assert all(
            "label" in column.info and "description" in column.info
            for column in model.__table__.columns
        )
        assert "workspace_uid" not in model.__table__.columns
        assert all(
            fk.referred_table.name != "mainsequence_crm__workspace"
            for fk in model.__table__.foreign_key_constraints
        )
    assert "settings" in MODELS and "workspace" not in MODELS


def test_platform_identity_required_even_if_header_is_forged():
    app = create_app()
    client = TestClient(app)
    assert client.get("/healthz").status_code == 200
    response = client.get("/api/crm/v1/readiness/", headers={"X-User-Uid": str(ACTOR)})
    assert response.status_code == 401
    Error.model_validate(response.json())


def test_readiness_fails_closed_without_platform_adapters(monkeypatch):
    app = create_app()

    class UnavailableRegistry:
        def validate(self):
            raise RuntimeError("Catalog unavailable")

    app.state.crm_registry = UnavailableRegistry()

    @app.middleware("http")
    async def platform_identity(request, call_next):
        request.state.user_uid = ACTOR
        return await call_next(request)

    client = TestClient(app)
    response = client.get("/api/crm/v1/readiness/")
    assert response.status_code == 503
    payload = response.json()
    Readiness.model_validate(payload)
    assert payload["status"] == "not_ready"
    assert {c["id"] for c in payload["checks"] if c["status"] == "failed"} >= {
        "policy",
        "directory",
        "bootstrap",
        "catalog",
        "crm-settings",
    }
    bootstrap = client.get("/api/crm/v1/bootstrap/")
    assert bootstrap.status_code == 503
    Error.model_validate({"error": bootstrap.json()["error"]})
    Readiness.model_validate(bootstrap.json()["readiness"])


def test_policy_denial_does_not_disclose_readiness_checks(monkeypatch):
    app = create_app()

    class Registry:
        def validate(self):
            pass

        def validate_settings(self):
            pass

    app.state.crm_registry = Registry()

    class Deny:
        def capabilities(self, actor_uid):
            return set()

    app.state.crm_policy = Deny()

    @app.middleware("http")
    async def platform_identity(request, call_next):
        request.state.user_uid = ACTOR
        return await call_next(request)

    response = TestClient(app).get("/api/crm/v1/readiness/")
    assert response.status_code == 403
    assert "checks" not in response.json()
