"""Application service and explicit local-runtime integration checks."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

from fastapi.testclient import TestClient

from api.crm.local import create_app
from src.crm.metatables import MODELS
from src.crm.models.bootstrap import Bootstrap
from src.crm.platform.local_runtime import LocalSdkUserPolicy

ACTOR = uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
OTHER_ACTOR = uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaab")
PIPELINE = uuid.UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
DATA_SOURCE = uuid.UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")


def _catalog_rows():
    rows = []
    for number, model in enumerate(MODELS.values(), 1):
        rows.append(
            SimpleNamespace(
                uid=uuid.UUID(int=number),
                data_source_uid=DATA_SOURCE,
                identifier=model.__metatable_identifier__,
                physical_table_name=model.__tablename__,
                physical_schema=None,
                provisioning_status="active",
                namespace="mainsequence-crm",
                migration_namespace="mainsequence-crm",
                management_mode="platform_managed",
                schema_management_mode="alembic_managed",
                migration_provider_key="crm-provider",
                alembic_revision="0003",
            )
        )
    return rows


def _settings_row():
    return {
        "default_currency": "EUR",
        "timezone": "Europe/Vienna",
        "configuration_version": 1,
        "configuration": {
            "company_sectors": [{"value": "software", "label": "Software"}],
            "contact_statuses": [{"value": "warm", "label": "Warm"}],
            "deal_categories": [{"value": "new-business", "label": "New business"}],
            "task_types": [{"value": "follow-up", "label": "Follow up"}],
        },
        "default_pipeline_uid": str(PIPELINE),
    }


def test_local_runtime_is_ready_and_bootstrap_is_a_governed_read(monkeypatch):
    monkeypatch.setattr(
        "src.crm.platform.catalog.MetaTable.filter", lambda **filters: _catalog_rows()
    )
    monkeypatch.setattr(
        "api.crm.local.User.get_authenticated_user_details",
        lambda: SimpleNamespace(
            uid=str(ACTOR),
            username="local@example.test",
            email="local@example.test",
            first_name="Local",
            last_name="Operator",
        ),
    )
    operations = []

    def execute(operation):
        operations.append(operation)
        sql = operation["statement"]["sql"]
        if sql.startswith("SELECT key FROM"):
            return {"rows": [{"key": "default"}]}
        assert 'JOIN "mainsequence_crm__pipeline"' in sql
        assert operation["statement"]["parameters"] == {}
        assert {table["access"] for table in operation["scope"]["tables"]} == {"read"}
        assert len(operation["scope"]["tables"]) == 2
        return {"rows": [_settings_row()]}

    monkeypatch.setattr("src.crm.services.application.MetaTable.execute_operation", execute)
    app = create_app()
    client = TestClient(app, client=("127.0.0.1", 50000))

    readiness = client.get("/api/crm/v1/readiness/")
    assert readiness.status_code == 200
    assert readiness.json()["status"] == "ready"
    assert all(check["status"] == "ready" for check in readiness.json()["checks"])
    assert "atomic-commands" not in {check["id"] for check in readiness.json()["checks"]}

    response = client.get("/api/crm/v1/bootstrap/")
    assert response.status_code == 200
    payload = response.json()
    Bootstrap.model_validate(payload)
    assert "workspace_uid" not in payload
    assert payload["current_user"] == {
        "uid": str(ACTOR),
        "display_name": "Local Operator",
        "selectable": True,
    }
    assert payload["default_pipeline_uid"] == str(PIPELINE)
    assert "crm.read" in payload["capabilities"]
    assert any("mainsequence_crm__settings" in item["statement"]["sql"] for item in operations)
    assert any(item["statement"]["sql"].endswith("LIMIT 2") for item in operations)


def test_local_policy_is_bound_to_authenticated_actor():
    policy = LocalSdkUserPolicy(ACTOR)
    assert "crm.read" in policy.capabilities(ACTOR)
    assert policy.capabilities(OTHER_ACTOR) == set()
