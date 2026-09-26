"""Regression gates for authored CRM models and explicit HTTP contracts."""

from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError

from api.crm.main import create_app
from src.crm.contracts import CONTRACT_MODELS
from src.crm.metatables import MODELS
from src.crm.models.common import VersionCommand
from src.crm.models.contacts import ContactCreate
from src.crm.models.queries import QueryScope
from src.crm.repositories.resources.store import GovernedResourceStore

API = Path(__file__).resolve().parents[1]


def test_models_are_python_classes_not_runtime_json_definitions():
    crm_root = API / "src/crm"
    assert {path.name for path in crm_root.glob("*.py")} == {
        "__init__.py", "config.py", "assistant_runtime.py"
    }
    for package in (
        "models",
        "contracts",
        "metatables",
        "migrations",
        "repositories",
        "platform",
        "services",
        "portability",
    ):
        assert (crm_root / package / "__init__.py").is_file()
    assert not (API / "src/crm/models.py").exists()
    assert not (API / "src/crm/data_dictionary.json").exists()
    assert not (API / "src/crm/crm-domain.schema.json").exists()
    assert not (API / "src/crm/import-mapping.schema.json").exists()
    assert len(MODELS) == 26
    for logical_name, model in MODELS.items():
        expected_module = (
            "src.crm.metatables.solution_selling"
            if logical_name.startswith("solution_selling")
            else "src.crm.metatables.google_oauth"
            if logical_name.startswith("google_oauth")
            else f"src.crm.metatables.{logical_name}"
        )
        assert model.__module__ == expected_module
        assert logical_name in model.__tablename__
        assert len(model.__table__.columns) > 0
    for model in CONTRACT_MODELS.values():
        assert issubclass(model, BaseModel)
        assert model.__module__.startswith("src.crm.models.")


def test_repository_layout_keeps_http_and_ui_metadata_out_of_persistence():
    repositories = API / "src/crm/repositories"
    for old_name in ("queries.py", "resource_definitions.py", "transfer_store.py"):
        assert not (repositories / old_name).exists()
    assert (API / "api/crm/query.py").is_file()
    assert (API / "api/crm/discovery.py").is_file()
    assert issubclass(QueryScope, BaseModel)
    assert GovernedResourceStore.__bases__ == (object,)
    for concept in ("companies", "contacts", "deals"):
        assert (repositories / concept / "reads.py").is_file()


def test_every_json_mutation_has_a_named_pydantic_request_schema():
    paths = create_app().openapi()["paths"]
    expected = {
        ("post", "/contacts/"): "ContactCreate",
        ("patch", "/contacts/{uid}/"): "ContactPatch",
        ("post", "/companies/"): "CompanyCreate",
        ("patch", "/companies/{uid}/"): "CompanyPatch",
        ("post", "/deals/"): "DealCreate",
        ("patch", "/deals/{uid}/"): "DealPatch",
        ("post", "/tasks/"): "TaskCreate",
        ("patch", "/tasks/{uid}/"): "TaskPatch",
        ("post", "/notes/"): "NoteCreate",
        ("patch", "/notes/{uid}/"): "NotePatch",
        ("post", "/tags/"): "TagCreate",
        ("patch", "/tags/{uid}/"): "TagPatch",
        ("post", "/contacts/{uid}/archive/"): "VersionCommand",
        ("post", "/tasks/{uid}/complete/"): "VersionCommand",
        ("patch", "/settings/"): "SettingsPatch",
        ("post", "/deals/{uid}/move/"): "MoveDeal",
        ("post", "/contacts/{uid}/merge/preview/"): "MergePreviewRequest",
        ("post", "/contacts/{uid}/merge/"): "MergeExecuteRequest",
        ("post", "/source-connections/"): "SourceConnectionCreate",
        ("post", "/imports/"): "CreateImport",
        ("put", "/imports/{uid}/mapping/"): "ImportMapping",
        ("post", "/imports/{uid}/commit/"): "ImportCommitRequest",
    }
    for (method, suffix), model_name in expected.items():
        body = paths[f"/api/crm/v1{suffix}"][method]["requestBody"]
        schema = body["content"]["application/json"]["schema"]
        assert schema["$ref"] == f"#/components/schemas/{model_name}"
    for path, operations in paths.items():
        if not path.startswith("/api/crm/v1/"):
            continue
        for operation in operations.values():
            body = operation.get("requestBody")
            if body and "application/json" in body["content"]:
                assert "$ref" in body["content"]["application/json"]["schema"]


@pytest.mark.parametrize("value", ["1", True, 1.0])
def test_version_commands_reject_coerced_numbers(value):
    with pytest.raises(ValidationError):
        VersionCommand.model_validate({"expected_version": value})


@pytest.mark.parametrize("value", ["true", 1, 0])
def test_boolean_fields_reject_coercion(value):
    with pytest.raises(ValidationError):
        ContactCreate.model_validate({"first_name": "Ada", "has_newsletter": value})
