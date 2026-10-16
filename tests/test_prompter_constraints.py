"""Subject/body contracts, read-only previews and real isolated governed writes."""

import uuid
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from pydantic import ValidationError
from test_mcp_tools import ACTOR, Policy, WorkflowReads, app_for, call, delegated
from test_resource_collections import SOURCE
from test_resource_collections import collection_postgres as _postgres

from api.crm.main import create_app
from metatables import MetaTableCompiledSQLOperation
from src.crm.repositories.records import VersionedRecordStore
from src.crm.solution_selling.models import PrompterConstraints, PrompterCreate
from src.crm.solution_selling.prompters import validate_draft

collection_postgres = _postgres
BASE = "/extensions/solution-selling/prompters/"


@pytest.mark.parametrize("limit", [0, -1, 32769, True, 1.5, "200"])
def test_constraints_require_positive_bounded_strict_integers(limit):
    for field in ("max_characters", "max_subject_characters"):
        with pytest.raises(ValidationError):
            PrompterConstraints.model_validate({field: limit})


def test_unknown_constraints_and_empty_subject_template_are_rejected():
    with pytest.raises(ValidationError):
        PrompterConstraints.model_validate({"channel": "email"})
    with pytest.raises(ValidationError):
        PrompterCreate(name="Probe", kind="open label", template="Body", subject_template="")


def test_unicode_counts_exact_boundary_and_absent_subject_are_independent():
    constraints = PrompterConstraints(max_characters=4, max_subject_characters=2)
    result = validate_draft(text="😀é\n ", subject=None, constraints=constraints)
    assert result.character_count == 4 and result.is_valid
    assert result.subject_character_count is None
    result = validate_draft(text="😀é\n x", subject="😀ab", constraints=constraints)
    assert result.text == "😀é\n x" and result.subject == "😀ab"
    assert [(i.field, i.actual, i.limit) for i in result.violations] == [
        ("text", 5, 4),
        ("subject", 3, 2),
    ]
    assert not result.is_valid


def test_subject_rendering_and_edited_validation_match_rest_and_mcp(signed_caller):
    store = WorkflowReads()
    store.data["prompters"].update(
        subject_template="For {{ contact.first_name }} at {{ company.name }}",
        constraints={"max_characters": 5, "max_subject_characters": 3},
    )
    app = app_for(Policy("crm.read"), store)
    app.state.crm_record_store = store
    with TestClient(app, headers=delegated(signed_caller)) as client:
        args = {
            "uid": store.prompter,
            "payload": {
                "contact_uid": store.data["contacts"]["uid"],
                "company_uid": store.company,
            },
        }
        rest = client.post(f"{BASE}{store.prompter}/render/", json=args["payload"])
        assert rest.status_code == 200
        preview = rest.json()
        assert preview["subject"] == "For Ada at Example Company"
        assert preview["text"] == "Hi Ada at Example Company"
        assert not preview["is_valid"] and len(preview["violations"]) == 2
        assert call(client, "crm_prompters_render", args)["structuredContent"] == {
            "code": "ok",
            "data": preview,
        }
        store.calls.clear()
        edited = {"text": "😀é\n ", "subject": "😀a"}
        response = client.post(f"{BASE}{store.prompter}/validate/", json=edited)
        assert response.status_code == 200 and response.json()["is_valid"]
        assert store.calls == [("prompters", store.prompter)]
        assert call(client, "crm_prompters_validate", {"uid": store.prompter, "payload": edited})[
            "structuredContent"
        ] == {"code": "ok", "data": response.json()}
        # The saved limit is read again, even when text has not changed.
        store.data["prompters"]["constraints"]["max_characters"] = 1
        assert not client.post(f"{BASE}{store.prompter}/validate/", json=edited).json()["is_valid"]
        assert (
            client.post(f"{BASE}{store.prompter}/validate/", json={"text": "x" * 32769}).status_code
            == 422
        )


@pytest.mark.parametrize("source", ["{{ inputs.missing }}", "{{ contact.__class__ }}", "{{ x("])
def test_subject_uses_the_same_strict_sandbox_and_redacted_errors(signed_caller, source):
    store = WorkflowReads()
    store.data["prompters"]["subject_template"] = source
    app = app_for(Policy("crm.read"), store)
    app.state.crm_record_store = store
    with TestClient(app, headers=delegated(signed_caller)) as client:
        result = call(
            client,
            "crm_prompters_render",
            {
                "uid": store.prompter,
                "payload": {
                    "contact_uid": store.data["contacts"]["uid"],
                    "company_uid": store.company,
                },
            },
        )
        assert result["isError"] and result["structuredContent"]["code"] == "validation_error"
        assert source not in str(result)


def test_validation_requires_read_permission_and_module_enablement(signed_caller, config_file):
    store = WorkflowReads()
    app = app_for(Policy(), store)
    app.state.crm_record_store = store
    with TestClient(app, headers=delegated(signed_caller)) as client:
        assert (
            client.post(f"{BASE}{store.prompter}/validate/", json={"text": "Body"}).status_code
            == 403
        )
        assert call(
            client, "crm_prompters_validate", {"uid": store.prompter, "payload": {"text": "Body"}}
        )["isError"]
    assert not store.calls
    config_file(solution_selling=False)
    assert f"{BASE}{{uid}}/validate/" not in create_app().openapi()["paths"]


def test_real_atomic_create_update_readback_and_cleanup(
    collection_postgres, monkeypatch, signed_caller
):
    """Actual CRM CTEs on a private PostgreSQL; only transport/identity ports mocked."""

    def no_network(*args, **kwargs):
        pytest.fail("Disposable prompter checks must never call a hosted service")

    monkeypatch.setattr("requests.sessions.Session.request", no_network)
    with collection_postgres.connect() as db:
        transaction = db.begin()
        try:

            def execute(payload):
                MetaTableCompiledSQLOperation.model_validate(payload)
                assert payload["data_source_uid"] == SOURCE
                rows = (
                    db.exec_driver_sql(
                        payload["statement"]["sql"], payload["statement"]["parameters"]
                    )
                    .mappings()
                    .all()
                )
                return {"rows": [dict(row) for row in rows]}

            monkeypatch.setattr("src.crm.repositories.gateway.MetaTable.execute_operation", execute)
            store = VersionedRecordStore(SimpleNamespace(data_source_uid=SOURCE))
            actor = ACTOR
            app = create_app()
            app.state.crm_policy = Policy("crm.read", "crm.create", "crm.edit")
            app.state.crm_directory = object()
            app.state.crm_record_store = store
            with TestClient(app, headers=signed_caller(actor)) as client:
                created = client.post(
                    BASE,
                    json={
                        "name": "Owned disposable fixture",
                        "kind": "any purpose",
                        "template": "Hello",
                    },
                )
                assert created.status_code == 201, created.text
                item = created.json()
                assert (
                    item["subject_template"] is None
                    and item["constraints"]["max_characters"] is None
                )
                path = f"{BASE}{item['uid']}/"
                updated = client.patch(
                    path,
                    json={
                        "expected_version": 1,
                        "changes": {
                            "subject_template": "Greeting",
                            "constraints": {"max_characters": 200, "max_subject_characters": 20},
                        },
                    },
                )
                assert updated.status_code == 200, updated.text
                assert client.get(path).json() == updated.json()
                assert (
                    client.patch(
                        path, json={"expected_version": 1, "changes": {"name": "Stale"}}
                    ).status_code
                    == 409
                )
                db.exec_driver_sql(
                    "ALTER TABLE mainsequence_crm__activity_event ADD CONSTRAINT test_prompter_audit CHECK (kind <> 'updated') NOT VALID"
                )
                with pytest.raises(sa.exc.IntegrityError), db.begin_nested():
                    store.update(
                        "prompters",
                        actor,
                        uuid.UUID(item["uid"]),
                        2,
                        {"subject_template": "Must roll back"},
                        PrompterCreate(
                            name="Owned disposable fixture", kind="any purpose", template="Hello"
                        ),
                    )
                assert client.get(path).json() == updated.json()
                db.exec_driver_sql(
                    "ALTER TABLE mainsequence_crm__activity_event DROP CONSTRAINT test_prompter_audit"
                )
                cleared = client.patch(
                    path,
                    json={
                        "expected_version": 2,
                        "changes": {"subject_template": None, "constraints": {}},
                    },
                )
                assert cleared.status_code == 200 and cleared.json()["subject_template"] is None
                assert cleared.json()["constraints"] == {
                    "max_characters": None,
                    "max_subject_characters": None,
                }
                for changes in ({"constraints": None}, {"constraints": {"max_characters": True}}):
                    assert (
                        client.patch(
                            path, json={"expected_version": 3, "changes": changes}
                        ).status_code
                        == 422
                    )
        finally:
            # Roll back every owned fixture and audit row; no ordinary database is touched.
            transaction.rollback()
        assert (
            db.exec_driver_sql(
                "SELECT count(*) FROM mainsequence_crm__solution_selling_prompter"
            ).scalar_one()
            == 0
        )
