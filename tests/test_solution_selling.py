"""Contract and SQL-boundary tests for the optional methodology."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from api.crm.main import create_app
from src.crm.metatables import MODELS
from src.crm.repositories.records import VersionedRecordStore
from src.crm.solution_selling.models import (
    AssessmentCreate,
    DiagnosisMatrix,
    KeyPlayerPain,
    LeadCreate,
    PainChainLink,
    PrompterCreate,
    PrompterRenderRequest,
    ProspectingProfileCreate,
)
from src.crm.solution_selling.prompters import _validate_template, render_prompter


def test_module_route_mount_follows_persisted_config(config_file):
    config_file(solution_selling=False)
    disabled = create_app().openapi()["paths"]
    assert "/api/crm/v1/interactions/" in disabled
    assert not any("/solution-selling/" in path for path in disabled)
    config_file(solution_selling=True)
    enabled = create_app().openapi()["paths"]
    assert not any(path.startswith("/api/crm/v1/solution-selling/") for path in enabled)
    for resource in ("leads", "prospecting-profiles", "prompters", "assessments", "diagnoses"):
        path = f"/extensions/solution-selling/{resource}/"
        assert {"get", "post"} <= set(enabled[path])
        assert {"get", "patch"} <= set(enabled[f"{path}{{uid}}/"])
    assert "post" in enabled["/extensions/solution-selling/prompters/{uid}/render/"]


def test_matrix_is_nine_typed_cells_and_profile_template_is_unanswered():
    matrix = DiagnosisMatrix()
    assert len(matrix.model_dump()) == 3
    assert all(len(row) == 3 for row in matrix.model_dump().values())
    profile = ProspectingProfileCreate(
        name="Research lead", market_context="Asset management", role="Research lead",
        potential_pain="Slow deployment", diagnosis_template=matrix,
    )
    assert profile.diagnosis_template is not None
    with pytest.raises(ValidationError):
        ProspectingProfileCreate(
            name="Research lead", market_context="Asset management", role="Research lead",
            potential_pain="Slow deployment",
            diagnosis_template={"open": {"reasons": [{"question": "Why?", "answer": "Known"}]}},
        )


def test_pain_chain_validates_existing_key_players_and_direction():
    first, second = uuid.uuid4(), uuid.uuid4()
    base = {"deal_uid": uuid.uuid4(), "company_uid": uuid.uuid4()}
    player = KeyPlayerPain(contact_uid=first, pain="Delay", status="reported")
    other = KeyPlayerPain(contact_uid=second, pain="Cost", status="hypothesis")
    valid = AssessmentCreate(
        **base, key_players=[player, other],
        pain_chain=[PainChainLink(
            from_contact_uid=first, to_contact_uid=second,
            explanation="Delay raises cost", status="hypothesis",
        )],
    )
    assert len(valid.pain_chain) == 1
    with pytest.raises(ValidationError):
        AssessmentCreate(
            **base, key_players=[player],
            pain_chain=[PainChainLink(
                from_contact_uid=first, to_contact_uid=second,
                explanation="Invalid endpoint", status="hypothesis",
            )],
        )


def test_lead_is_contact_reference_not_person_copy():
    lead = LeadCreate(contact_uid=uuid.uuid4(), status="to_contact")
    assert "first_name" not in type(lead).model_fields
    with pytest.raises(ValidationError):
        LeadCreate(contact_uid=uuid.uuid4(), status="to_contact", first_name="Duplicate")


def test_prompter_template_is_restricted_and_bounded():
    PrompterCreate(name="Greeting", kind="intro_email", template="Hi {{ contact.first_name }}")
    _validate_template(
        "{% if profile %}{% for reason in profile.likely_reasons %}{{ reason }}{% endfor %}{% endif %}"
    )
    with pytest.raises(ValueError):
        _validate_template("{{ contact.__class__ }}")
    with pytest.raises(ValueError):
        _validate_template("{{ range(1000000) }}")
    with pytest.raises(ValueError):
        _validate_template("{% for character in company.description %}x{% endfor %}")
    with pytest.raises(ValueError):
        _validate_template("{% for a in profile.likely_reasons %}{% for b in profile.likely_impacts %}x{% endfor %}{% endfor %}")


class CapturingStore(VersionedRecordStore):
    def __init__(self):
        self.calls = []

    def _operation(self, **kwargs):
        self.calls.append(kwargs)
        return {"rows": [{"entity_uid": str(uuid.uuid4())}]}

    def detail(self, resource, uid):
        return {"uid": str(uid)}


def test_create_is_one_governed_write_with_activity_and_reference_gate():
    store = CapturingStore()
    store.create("leads", uuid.uuid4(), LeadCreate(contact_uid=uuid.uuid4(), status="to_contact"))
    operation = store.calls[0]
    assert operation["operation"] == "insert"
    assert operation["tables"] == {
        "contact": "read", "solution_selling_lead": "write", "activity_event": "write"
    }
    assert f'INSERT INTO "{MODELS["solution_selling_lead"].__tablename__}"' in operation["sql"]
    assert f'INSERT INTO "{MODELS["activity_event"].__tablename__}"' in operation["sql"]
    assert "NOT EXISTS" in operation["sql"]


def test_render_is_read_only_and_uses_explicit_company():
    contact_uid, company_uid, prompter_uid = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    class Core:
        def detail(self, resource, uid):
            if resource == "contacts" and uid == contact_uid:
                return {"uid": str(uid), "first_name": "Maria"}
            if resource == "companies" and uid == company_uid:
                return {"uid": str(uid), "name": "Example Capital"}
            raise AssertionError("Unexpected core lookup")

    class Methodology:
        def detail(self, resource, uid):
            assert resource == "prompters" and uid == prompter_uid
            return {"template": "Hi {{ contact.first_name }} at {{ company.name }}"}

    result = render_prompter(
        prompter_uid=prompter_uid,
        request=PrompterRenderRequest(contact_uid=contact_uid, company_uid=company_uid),
        actor_uid=uuid.uuid4(), sender_name="Jose", core=Core(), methodology=Methodology(),
    )
    assert result == "Hi Maria at Example Capital"


def test_prompter_http_create_and_versioned_patch_use_platform_policy():
    app = create_app()
    actor = uuid.uuid4()

    @app.middleware("http")
    async def signed_actor(request, call_next):
        request.state.user_uid = actor
        return await call_next(request)

    class Policy:
        def capabilities(self, actor_uid):
            assert actor_uid == actor
            return {"crm.read", "crm.create", "crm.edit"}

    class Directory:
        def is_selectable(self, actor_uid):
            return actor_uid == actor

        def display_name(self, actor_uid):
            return "Test actor"

    class Store:
        def __init__(self):
            self.record = None

        def create(self, resource, actor_uid, payload):
            assert resource == "prompters" and actor_uid == actor
            self.record = {"uid": str(uuid.uuid4()), "version": 1, **payload.model_dump(mode="json")}
            return self.record

        def detail(self, resource, uid):
            assert resource == "prompters" and uid == uuid.UUID(self.record["uid"])
            return self.record

        def update(self, resource, actor_uid, uid, expected_version, changes, candidate):
            assert expected_version == 1 and changes == {"description": "For introductions"}
            self.record = {**self.record, **candidate.model_dump(mode="json"), "version": 2}
            return self.record

    app.state.crm_policy = Policy()
    app.state.crm_directory = Directory()
    app.state.crm_record_store = Store()
    client = TestClient(app)
    created = client.post(
        "/extensions/solution-selling/prompters/",
        json={"name": "Greeting", "kind": "intro_email", "template": "Hi {{ contact.first_name }}"},
    )
    assert created.status_code == 201
    uid = created.json()["uid"]
    changed = client.patch(
        f"/extensions/solution-selling/prompters/{uid}/",
        json={"expected_version": 1, "changes": {"description": "For introductions"}},
    )
    assert changed.status_code == 200 and changed.json()["version"] == 2
    assert client.get("/extensions/solution-selling/leads/?contact_uid=not-a-uuid").status_code == 422
