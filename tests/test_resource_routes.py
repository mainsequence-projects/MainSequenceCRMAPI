"""Focused checks for the governed CRM resource surface."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

from fastapi.testclient import TestClient

from api.crm.main import create_app
from src.crm.metatables import MODELS
from src.crm.models.pipelines import PipelineStages
from src.crm.repositories.gateway import GovernedGateway


def test_frontend_core_routes_are_registered():
    routes = {
        (method, path) for path, item in create_app().openapi()["paths"].items() for method in item
    }
    expected = {
        ("get", "/api/crm/v1/contacts/"),
        ("post", "/api/crm/v1/contacts/"),
        ("patch", "/api/crm/v1/contacts/{uid}/"),
        ("get", "/api/crm/v1/activity/{uid}/"),
        ("patch", "/api/crm/v1/settings/"),
        ("get", "/api/crm/v1/pipelines/{uid}/stages/"),
        ("get", "/api/crm/v1/pipelines/{uid}/board/"),
        ("get", "/api/crm/v1/pipelines/{uid}/stages/{stage_uid}/cards/"),
        ("post", "/api/crm/v1/deals/{uid}/move/"),
        ("post", "/api/crm/v1/contacts/{uid}/merge/preview/"),
        ("post", "/api/crm/v1/contacts/{uid}/merge/"),
        ("post", "/api/crm/v1/tasks/{uid}/complete/"),
        ("post", "/api/crm/v1/tasks/{uid}/reopen/"),
    }
    assert expected <= routes


def test_pipeline_stages_returns_active_stage_choices_without_board_cards(monkeypatch):
    from src.crm.repositories.deals.board import DealBoard

    pipeline_uid = uuid.UUID("00000000-0000-4000-8000-000000000001")
    stage_uid = uuid.UUID("00000000-0000-4000-8000-000000000002")
    stage = {
        "uid": str(stage_uid),
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "created_by_uid": None,
        "updated_by_uid": None,
        "version": 1,
        "pipeline_uid": str(pipeline_uid),
        "key": "opportunity",
        "label": "Opportunity",
        "position": 0,
        "outcome": "open",
        "is_active": True,
    }
    observed = {}

    def execute(_self, **kwargs):
        observed.update(kwargs)
        return {"rows": [{"board_version": 1, "stages": [stage]}]}

    monkeypatch.setattr(DealBoard, "_operation", execute)
    result = DealBoard(object(), object()).pipeline_stages(pipeline_uid)
    assert result == {"pipeline_uid": str(pipeline_uid), "board_version": 1, "stages": [stage]}
    assert observed["tables"] == {"pipeline": "read", "stage": "read"}
    assert "board_column" not in observed["sql"]

    app = create_app()

    class Policy:
        def capabilities(self, _actor_uid):
            return {"crm.read"}

    class Store:
        def pipeline_stages(self, uid):
            assert uid == pipeline_uid
            return result

    app.state.crm_policy = Policy()
    app.state.crm_directory = object()
    app.state.crm_resources = Store()

    @app.middleware("http")
    async def inject_identity(request, call_next):
        request.state.user_uid = uuid.uuid4()
        return await call_next(request)

    response = TestClient(app).get(f"/api/crm/v1/pipelines/{pipeline_uid}/stages/")
    assert response.status_code == 200
    assert response.json() == PipelineStages.model_validate(result).model_dump(mode="json")
    assert TestClient(app).get(f"/api/crm/v1/pipelines/{pipeline_uid}/stages/?page_size=25").status_code == 422


def test_http_query_validation_stops_before_repository_access():
    app = create_app()

    class Policy:
        def capabilities(self, _actor_uid):
            return {"crm.read", "crm.transfer.import"}

    app.state.crm_policy = Policy()
    app.state.crm_directory = object()

    @app.middleware("http")
    async def inject_identity(request, call_next):
        request.state.user_uid = uuid.uuid4()
        return await call_next(request)

    with TestClient(app) as client:
        cases = (
            ("/api/crm/v1/contacts/", {"filters": '{"has_open_tasks":1}'}),
            ("/api/crm/v1/contacts/discovery/", {"page_size": "25"}),
            (
                "/api/crm/v1/pipelines/00000000-0000-4000-8000-000000000001/board/",
                {"page_size": "101"},
            ),
            (
                "/api/crm/v1/pipelines/00000000-0000-4000-8000-000000000001/stages/00000000-0000-4000-8000-000000000002/cards/",
                {"cursor": "-1", "expected_board_version": "0"},
            ),
            ("/api/crm/v1/source-connections/", {"page_index": "-1"}),
        )
        for path, params in cases:
            response = client.get(path, params=params)
            assert response.status_code == 422, (path, response.text)
            assert response.json()["error"]["code"] == "CRM_REQUEST_ERROR"


def test_governed_operation_only_sends_backend_supported_parameter_metadata(monkeypatch, tmp_path):
    data_source_uid = uuid.uuid4()
    rows = []
    for number, logical in enumerate(("settings", "deal"), 1):
        model = MODELS[logical]
        rows.append(
            SimpleNamespace(
                uid=uuid.UUID(int=number),
                data_source_uid=data_source_uid,
                identifier=model.__metatable_identifier__,
                physical_table_name=model.__tablename__,
                physical_schema=None,
                provisioning_status="active",
                namespace="mainsequence-crm",
                migration_namespace="mainsequence-crm",
                management_mode="platform_managed",
                schema_management_mode="alembic_managed",
                migration_provider_key="crm-provider",
                alembic_revision="0004",
            )
        )
    captured = {}

    def execute(operation):
        captured.update(operation)
        return {"rows": []}

    monkeypatch.setattr("src.crm.repositories.gateway.MetaTable.execute_operation", execute)

    class Registry:
        def binding(self, logical):
            from src.crm.platform.catalog import CatalogBinding

            row = rows[("settings", "deal").index(logical)]
            return CatalogBinding(
                meta_table_uid=str(row.uid),
                data_source_uid=str(row.data_source_uid),
                physical_table_name=row.physical_table_name,
                migration_provider_key=row.migration_provider_key,
                alembic_revision=row.alembic_revision,
            )

    store = GovernedGateway(Registry())
    store._operation(
        operation="select",
        sql="SELECT %(uid)s, %(limit)s, %(payload)s::jsonb",
        parameters={"uid": str(uuid.uuid4()), "limit": 1, "payload": "{}"},
        parameter_types={"uid": "uuid", "limit": "integer", "payload": "jsonb"},
        tables={"settings": "read", "deal": "read"},
    )

    assert captured["statement"]["parameter_types"] == {"payload": "jsonb"}
    assert {item["access"] for item in captured["scope"]["tables"]} == {"read"}
    assert len(captured["scope"]["tables"]) == 2
