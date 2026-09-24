"""Contact social profiles are typed, independently editable, and mergeable."""

from __future__ import annotations

import uuid
from importlib import import_module

import pytest
from pydantic import ValidationError

from api.crm.main import create_app
from src.crm.contracts import normalized_create, normalized_patch
from src.crm.metatables import MODELS
from src.crm.models.contacts import ContactCreate, ContactPatch
from src.crm.models.merge import MergePreviewRequest
from src.crm.models.socials import SocialLinks
from src.crm.repositories.resources.store import GovernedResourceStore

SURVIVOR = uuid.UUID("33333333-3333-4333-8333-333333333333")
LOSER = uuid.UUID("44444444-4444-4444-8444-444444444444")
NOW = "2026-09-24T08:00:00+00:00"


def _contact(uid: uuid.UUID, socials: dict[str, str]) -> dict:
    return {
        "uid": str(uid),
        "created_at": NOW,
        "updated_at": NOW,
        "created_by_uid": None,
        "updated_by_uid": None,
        "version": 1,
        "archived_at": None,
        "owner_uid": None,
        "company_uid": None,
        "first_name": "Ada",
        "last_name": None,
        "title": None,
        "gender": None,
        "background": None,
        "avatar_ref": None,
        "socials": socials,
        "emails": [],
        "phones": [],
        "first_seen": None,
        "last_seen": None,
        "has_newsletter": None,
        "status_key": None,
        "source_created_at": None,
        "source_updated_at": None,
        "tag_uids": [],
        "display_name": "Ada",
        "company_name": None,
        "open_task_count": 0,
    }


def test_contact_socials_are_closed_pydantic_fields_and_sparsely_stored():
    assert "linkedin_url" not in ContactCreate.model_fields
    assert "linkedin_url" not in MODELS["contact"].__table__.columns
    assert "socials" in MODELS["contact"].__table__.columns
    assert MODELS["contact"].__table__.columns["socials"].nullable is False
    assert {"linkedin", "x", "instagram", "github", "wechat"} <= SocialLinks.model_fields.keys()
    created = normalized_create(
        "contact",
        {
            "first_name": "Ada",
            "socials": {
                "linkedin": "https://linkedin.com/in/ada",
                "github": "https://github.com/ada",
            },
        },
    )
    assert created["socials"] == {
        "linkedin": "https://linkedin.com/in/ada",
        "github": "https://github.com/ada",
    }
    assert normalized_create("contact", {"first_name": "Ada"})["socials"] == {}
    schema = create_app().openapi()["components"]["schemas"]
    assert "socials" in schema["ContactCreate"]["properties"]
    assert "linkedin_url" not in schema["ContactCreate"]["properties"]
    assert "linkedin" in schema["SocialLinks"]["properties"]


@pytest.mark.parametrize(
    "socials",
    [
        {"unknown_network": "https://example.org/profile"},
        {"linkedin": "javascript:alert(1)"},
        {"linkedin": ""},
        ["https://linkedin.com/in/ada"],
    ],
)
def test_invalid_socials_are_rejected(socials):
    with pytest.raises(ValidationError):
        ContactCreate.model_validate({"first_name": "Ada", "socials": socials})
    with pytest.raises(ValidationError):
        ContactPatch.model_validate({"expected_version": 1, "changes": {"socials": socials}})


def test_social_patch_changes_only_named_platforms_and_null_clears_one():
    existing = {
        "first_name": "Ada",
        "socials": {
            "linkedin": "https://linkedin.com/in/ada",
            "github": "https://github.com/ada",
        },
    }
    _, updated = normalized_patch(
        "contact",
        existing,
        {"expected_version": 1, "changes": {"socials": {"github": None, "x": "https://x.com/ada"}}},
    )
    assert updated["socials"] == {
        "linkedin": "https://linkedin.com/in/ada",
        "x": "https://x.com/ada",
    }
    _, cleared = normalized_patch(
        "contact", existing, {"expected_version": 1, "changes": {"socials": None}}
    )
    assert cleared["socials"] == {}
    with pytest.raises(ValidationError):
        ContactPatch.model_validate({"expected_version": 1, "changes": {"socials": {}}})
    with pytest.raises(ValidationError):
        ContactPatch.model_validate(
            {"expected_version": 1, "changes": {"linkedin_url": "https://linkedin.com/in/ada"}}
        )


def test_merge_unions_distinct_platforms_and_resolves_same_platform(monkeypatch):
    store = GovernedResourceStore()
    contacts = {
        SURVIVOR: _contact(SURVIVOR, {"linkedin": "https://linkedin.com/in/survivor"}),
        LOSER: _contact(
            LOSER,
            {
                "linkedin": "https://linkedin.com/in/loser",
                "github": "https://github.com/loser",
            },
        ),
    }
    monkeypatch.setattr(store.reads, "detail", lambda _resource, uid: contacts[uid])
    monkeypatch.setattr(store.affiliations_repo, "affiliations", lambda *_args: {"items": []})
    monkeypatch.setattr(
        store.merge_repo,
        "_operation",
        lambda **_call: {
            "rows": [
                {
                    "notes": 0,
                    "tasks": 0,
                    "deals": 0,
                    "tags": 0,
                    "source_identities": 0,
                    "affiliations": 0,
                }
            ]
        },
    )
    preview = store.merge_preview(SURVIVOR, LOSER, {})
    assert preview["proposed_contact"]["socials"] == {
        "linkedin": "https://linkedin.com/in/survivor",
        "github": "https://github.com/loser",
    }
    resolved = store.merge_preview(SURVIVOR, LOSER, {"socials.linkedin": "loser"})
    assert resolved["proposed_contact"]["socials"]["linkedin"] == ("https://linkedin.com/in/loser")
    assert preview["plan_hash"] != resolved["plan_hash"]
    cleared = store.merge_preview(SURVIVOR, LOSER, {"socials.github": "survivor"})
    assert "github" not in cleared["proposed_contact"]["socials"]
    MergePreviewRequest.model_validate(
        {"loser_uid": str(LOSER), "field_resolutions": {"socials.linkedin": "loser"}}
    )
    with pytest.raises(ValidationError):
        MergePreviewRequest.model_validate(
            {"loser_uid": str(LOSER), "field_resolutions": {"linkedin_url": "loser"}}
        )


def test_migration_rejects_bad_legacy_url_before_schema_change(monkeypatch):
    migration = import_module(
        "src.crm.migrations.versions.mainsequence_crm.0005_contact_social_links"
    )
    changes = []

    class Connection:
        def execute(self, _statement):
            return [("not-a-profile-url",)]

    class Operations:
        def get_bind(self):
            return Connection()

        def add_column(self, *_args):
            changes.append("add")

        def drop_column(self, *_args):
            changes.append("drop")

    monkeypatch.setattr(migration, "op", Operations())
    with pytest.raises(RuntimeError, match="invalid legacy LinkedIn URL"):
        migration.upgrade()
    assert changes == []
