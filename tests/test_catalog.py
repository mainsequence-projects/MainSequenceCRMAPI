"""Fresh-process catalog resolution; live platform remains a separate gate."""

import uuid
from types import SimpleNamespace

import pytest

from src.crm.metatables import MODELS
from src.crm.platform.catalog import CatalogRegistry


def catalog_rows(**overrides):
    rows = []
    for model in MODELS.values():
        values = {
            "uid": uuid.uuid5(uuid.NAMESPACE_DNS, model.__tablename__),
            "data_source_uid": uuid.UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd"),
            "identifier": model.__metatable_identifier__,
            "physical_table_name": model.__tablename__,
            "physical_schema": None,
            "provisioning_status": "active",
            "namespace": "mainsequence-crm",
            "migration_namespace": "mainsequence-crm",
            "management_mode": "platform_managed",
            "schema_management_mode": "alembic_managed",
            "migration_provider_key": "crm-provider-test",
            "alembic_revision": "0004",
        }
        if model is next(iter(MODELS.values())):
            values.update(overrides)
        rows.append(SimpleNamespace(**values))
    return rows


def test_fresh_registry_queries_public_catalog_and_uses_governed_read(monkeypatch):
    filtered = []

    def fetch(**filters):
        filtered.append(filters)
        return catalog_rows()

    monkeypatch.setattr("src.crm.platform.catalog.MetaTable.filter", fetch)
    registry = CatalogRegistry()
    registry.validate()
    assert len(registry.bindings) == len(MODELS)
    assert filtered == [
        {
            "identifier__in": [model.__metatable_identifier__ for model in MODELS.values()],
            "provisioning_status": "active",
        }
    ]
    observed = []

    def fake_execute(operation):
        observed.append(operation)
        return {"rows": [{"key": "default"}]}

    monkeypatch.setattr("src.crm.platform.catalog.MetaTable.execute_operation", fake_execute)
    registry.validate_settings()
    assert len(observed) == 1
    assert observed[0]["scope"]["tables"][0]["access"] == "read"
    assert observed[0]["statement"]["parameters"] == {}
    assert observed[0]["statement"]["sql"].endswith("LIMIT 2")
    assert len(filtered) == 1


@pytest.mark.parametrize("rows", [[], [{"key": "default"}, {"key": "default"}]])
def test_settings_validation_requires_exactly_one_row(monkeypatch, rows):
    monkeypatch.setattr(
        "src.crm.platform.catalog.MetaTable.filter", lambda **filters: catalog_rows()
    )
    monkeypatch.setattr(
        "src.crm.platform.catalog.MetaTable.execute_operation", lambda operation: {"rows": rows}
    )
    with pytest.raises(RuntimeError, match="not initialized"):
        CatalogRegistry().validate_settings()


def test_missing_binding_fails_before_execution(monkeypatch):
    monkeypatch.setattr(
        "src.crm.platform.catalog.MetaTable.filter", lambda **filters: catalog_rows()[1:]
    )
    with pytest.raises(RuntimeError, match="incomplete"):
        CatalogRegistry().validate()


@pytest.mark.parametrize(
    "change",
    [
        {"provisioning_status": "reserved"},
        {"migration_namespace": "other"},
        {"physical_table_name": "wrong_table"},
        {"schema_management_mode": "external_registered"},
        {"alembic_revision": "0001"},
    ],
)
def test_mismatched_binding_fails_closed(monkeypatch, change):
    monkeypatch.setattr(
        "src.crm.platform.catalog.MetaTable.filter", lambda **filters: catalog_rows(**change)
    )
    with pytest.raises(RuntimeError):
        CatalogRegistry().validate()
