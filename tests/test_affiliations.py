"""Contact-company history contracts and governed command boundaries."""

from __future__ import annotations

import json
import uuid

import pytest

from api.crm.transfer_routes import _parse_rows
from src.crm.models.affiliations import (
    AffiliationCreate,
    AffiliationPatch,
    AffiliationTransition,
    period_bounds,
)
from src.crm.repositories.resources.store import GovernedResourceStore, ResourceConflict
from src.crm.repositories.transfers.store import GovernedTransferStore

ACTOR = uuid.UUID("22222222-2222-4222-8222-222222222222")
CONTACT = uuid.UUID("33333333-3333-4333-8333-333333333333")
COMPANY = uuid.UUID("44444444-4444-4444-8444-444444444444")
NEW_COMPANY = uuid.UUID("55555555-5555-4555-8555-555555555555")
AFFILIATION = uuid.UUID("66666666-6666-4666-8666-666666666666")


def _affiliation(**changes):
    value = {
        "uid": str(AFFILIATION),
        "contact_uid": str(CONTACT),
        "company_uid": str(COMPANY),
        "company_name": "Example",
        "version": 2,
        "status": "current",
        "is_primary": True,
        "started_period": "2020-03",
        "ended_period": None,
        "job_title": "Engineer",
    }
    value.update(changes)
    return value


def _store(monkeypatch):
    store = GovernedResourceStore()
    calls = []
    monkeypatch.setattr(
        store.reads, "detail", lambda *args: {"version": 3, "company_uid": str(COMPANY)}
    )
    monkeypatch.setattr(store.affiliations_repo, "affiliation_detail", lambda *args: _affiliation())
    monkeypatch.setattr(
        store.affiliations_repo, "affiliations", lambda *args: {"items": [_affiliation()]}
    )

    def execute(**call):
        calls.append(call)
        return {"rows": [{"entity_uid": str(AFFILIATION)}]}

    for repository in (store.affiliations_repo, store.mutations, store.merge_repo):
        monkeypatch.setattr(repository, "_operation", execute)
    return store, calls


def test_period_precision_and_chronology_are_validated():
    assert str(period_bounds("2024")[0]) == "2024-01-01"
    assert str(period_bounds("2024-02")[1]) == "2024-02-29"
    for value in ("2024-13", "2024-02-30", "2024-2", "2024-01-01T00:00:00Z"):
        with pytest.raises(ValueError):
            period_bounds(value)
    with pytest.raises(ValueError):
        AffiliationCreate.model_validate(
            {
                "company_uid": str(COMPANY),
                "status": "former",
                "is_primary": False,
                "started_period": "2025",
                "ended_period": "2024-12",
                "expected_contact_version": 1,
            }
        )
    with pytest.raises(ValueError):
        AffiliationCreate.model_validate(
            {
                "company_uid": str(COMPANY),
                "status": "current",
                "is_primary": True,
                "ended_period": "2024",
                "expected_contact_version": 1,
            }
        )
    with pytest.raises(ValueError):
        AffiliationPatch.model_validate(
            {"expected_version": 1, "expected_contact_version": 1, "changes": {}}
        )


def test_create_affiliation_is_versioned_without_workspace_scope(monkeypatch):
    store, calls = _store(monkeypatch)
    result = store.create_affiliation(
        ACTOR,
        CONTACT,
        {
            "company_uid": str(NEW_COMPANY),
            "status": "current",
            "is_primary": False,
            "started_period": "2023",
            "expected_contact_version": 3,
        },
    )
    assert result["uid"] == str(AFFILIATION)
    call = calls[0]
    assert call["tables"] == {
        "contact": "write",
        "company": "read",
        "contact_company_affiliation": "write",
        "activity_event": "write",
    }
    assert "c.version=%(expected_contact_version)s::bigint" in call["sql"]
    assert "company.archived_at IS NULL" in call["sql"]
    assert "%(started_period)s" in call["sql"]
    assert "workspace_uid" not in call["sql"]


def test_legacy_contact_company_writes_preserve_history(monkeypatch):
    store, calls = _store(monkeypatch)
    store.create(
        "contacts",
        ACTOR,
        {
            "first_name": "Alex",
            "company_uid": str(COMPANY),
        },
    )
    created = calls.pop()
    assert "affiliation_created AS (INSERT INTO" in created["sql"]
    assert created["tables"]["contact_company_affiliation"] == "write"
    assert "ref_company_uid.archived_at IS NULL" in created["sql"]

    store.update(
        "contacts",
        ACTOR,
        CONTACT,
        3,
        {
            "company_uid": str(NEW_COMPANY),
        },
    )
    updated = calls.pop()
    assert "prior_affiliation_closed AS (UPDATE" in updated["sql"]
    assert "new_affiliation AS (INSERT INTO" in updated["sql"]
    assert "ref_company_uid.archived_at IS NULL OR" in updated["sql"]
    assert updated["tables"]["contact_company_affiliation"] == "write"


def test_company_contact_count_includes_concurrent_current_affiliations():
    store = GovernedResourceStore()
    sql, tables = store.reads._select_sql("companies")
    assert "count(DISTINCT c.uid)" in sql
    assert "a.status='current'" in sql
    assert tables["contact_company_affiliation"] == "read"


def test_transition_preserves_prior_stint_and_updates_projection(monkeypatch):
    store, calls = _store(monkeypatch)
    store.transition_company(
        ACTOR,
        CONTACT,
        {
            "expected_contact_version": 3,
            "previous_status": "former",
            "previous_ended_period": "2024-06",
            "new_company_uid": str(NEW_COMPANY),
            "new_started_period": "2024-07",
            "new_job_title": "Director",
        },
    )
    call = calls[0]
    assert "old_demoted AS (UPDATE" in call["sql"]
    assert "new_affiliation AS (INSERT INTO" in call["sql"]
    assert "company_uid=%(new_company_uid)s::uuid" in call["sql"]
    assert call["parameters"]["previous_ended_period"] == "2024-06"
    assert call["tables"]["contact_company_affiliation"] == "write"

    with pytest.raises(ValueError, match="precedes"):
        store.transition_company(
            ACTOR,
            CONTACT,
            {
                "expected_contact_version": 3,
                "previous_status": "former",
                "previous_ended_period": "2019",
                "new_company_uid": str(NEW_COMPANY),
            },
        )


def test_patch_cannot_turn_primary_into_former(monkeypatch):
    store, calls = _store(monkeypatch)
    with pytest.raises(ValueError):
        store.patch_affiliation(
            ACTOR,
            CONTACT,
            AFFILIATION,
            {
                "expected_version": 2,
                "expected_contact_version": 3,
                "changes": {"status": "former", "ended_period": "2024"},
            },
        )
    assert calls == []


def test_transition_requires_explicit_previous_disposition():
    with pytest.raises(ValueError):
        AffiliationTransition.model_validate(
            {
                "expected_contact_version": 3,
                "previous_status": "current",
                "previous_ended_period": "2024",
                "new_company_uid": str(NEW_COMPANY),
            }
        )


def test_merge_moves_all_loser_affiliations_before_retiring_contact(monkeypatch):
    store, calls = _store(monkeypatch)
    loser = uuid.uuid4()
    proposed = {
        "owner_uid": None,
        "company_uid": str(COMPANY),
        "first_name": "Alex",
        "last_name": "Example",
        "title": None,
        "gender": None,
        "background": None,
        "avatar_ref": None,
        "socials": {},
        "emails": [],
        "phones": [],
        "first_seen": None,
        "last_seen": None,
        "has_newsletter": None,
        "status_key": None,
        "source_created_at": None,
        "source_updated_at": None,
    }
    plan = {
        "survivor_version": 3,
        "loser_version": 2,
        "plan_hash": "a" * 64,
        "proposed_contact": proposed,
    }
    monkeypatch.setattr(store.merge_repo, "_merge_plan", lambda *args: plan)
    monkeypatch.setattr(
        store.merge_repo, "_operation", lambda **call: calls.append(call) or {"rows": []}
    )
    with pytest.raises(ResourceConflict, match="stale"):
        store.merge_contacts(
            ACTOR,
            CONTACT,
            {
                "loser_uid": str(loser),
                "field_resolutions": {},
                "expected_version": 3,
                "loser_expected_version": 2,
                "plan_hash": "a" * 64,
            },
        )
    sql = calls[0]["sql"]
    assert "affiliations_demoted AS (UPDATE" in sql
    assert "affiliations_moved AS (UPDATE" in sql
    assert "(SELECT count(*) FROM affiliations_moved) moved" in sql
    assert calls[0]["tables"]["contact_company_affiliation"] == "write"


def test_portable_contact_export_preserves_affiliation_periods(monkeypatch):
    store = GovernedTransferStore()
    output = {}

    def execute(**call):
        if call["operation"] == "select":
            if call["tables"] == {"contact": "read"}:
                return {"rows": [{"item": {"uid": str(CONTACT), "company_uid": str(COMPANY)}}]}
            return {
                "rows": [
                    {
                        "item": {
                            "uid": str(AFFILIATION),
                            "contact_uid": str(CONTACT),
                            "company_uid": str(COMPANY),
                            "started_period": "2020-03",
                            "ended_period": "2024",
                            "status": "former",
                        }
                    }
                ]
            }
        output.update(json.loads(call["parameters"]["output"]))
        return {
            "rows": [
                {
                    "uid": str(uuid.uuid4()),
                    "direction": "export",
                    "status": "succeeded",
                    "mapping_revision": 1,
                    "plan_hash": None,
                    "validation_report": {"counts": {}},
                    "cancel_requested": False,
                    "created_at": "2026-09-23T00:00:00Z",
                    "updated_at": "2026-09-23T00:00:00Z",
                }
            ]
        }

    monkeypatch.setattr(store.exports, "_operation", execute)
    store.create_export(
        ACTOR,
        {
            "format": "portable-json",
            "entity_type": "contacts",
            "filters": {},
            "search": "",
            "consistency": "best_effort",
            "include_archived": False,
        },
    )
    records = output["output"]["entities"]["contact_company_affiliations"]
    assert records[0]["started_period"] == "2020-03"
    assert records[0]["ended_period"] == "2024"
    staged, label = _parse_rows(
        "mainsequence-portable-v1",
        None,
        json.dumps(output["output"]).encode(),
    )
    assert label == "bundle"
    affiliation = next(
        row for row in staged if row["__entity_type"] == "contact_company_affiliation"
    )
    assert affiliation["started_period"] == "2020-03"
    assert affiliation["ended_period"] == "2024"


def test_portable_upload_stages_each_relationship_with_its_own_type(monkeypatch):
    store = GovernedTransferStore()
    staged = {}
    monkeypatch.setattr(
        store.jobs,
        "_job_row",
        lambda *args: {
            "direction": "import",
            "status": "uploading",
            "version": 1,
            "input_manifest": {"entity_type": None},
        },
    )

    def execute(**call):
        staged.update(call)
        return {
            "rows": [
                {
                    "uid": str(uuid.uuid4()),
                    "direction": "import",
                    "status": "staged",
                    "mapping_revision": 2,
                    "plan_hash": None,
                    "validation_report": {"counts": {}},
                    "cancel_requested": False,
                    "created_at": "2026-09-23T00:00:00Z",
                    "updated_at": "2026-09-23T00:00:00Z",
                }
            ]
        }

    monkeypatch.setattr(store.jobs, "_operation", execute)
    store.stage_upload(
        ACTOR,
        uuid.uuid4(),
        "crm.json",
        "application/json",
        "a" * 64,
        [
            {"__entity_type": "contact", "uid": str(CONTACT)},
            {
                "__entity_type": "contact_company_affiliation",
                "contact_uid": str(CONTACT),
                "started_period": "2020-03",
            },
        ],
        "bundle",
    )
    row_types = [row["entity_type"] for row in json.loads(staged["parameters"]["rows"])]
    assert row_types == ["contact", "contact_company_affiliation"]


def test_import_validation_blocks_affiliation_until_execution_exists(monkeypatch):
    store = GovernedTransferStore()
    captured = {}
    monkeypatch.setattr(
        store.planning,
        "_job_row",
        lambda *args: {
            "mapping": {"field_map": {}},
            "mapping_revision": 2,
            "version": 1,
            "input_manifest": {"sha256": "a" * 64},
        },
    )
    monkeypatch.setattr(store.planning, "plan", lambda *args: {"blocked": True})

    def execute(**call):
        if call["operation"] == "select":
            return {
                "rows": [
                    {
                        "uid": str(AFFILIATION),
                        "entity_type": "contact_company_affiliation",
                        "ordinal": 0,
                        "raw_hash": "b" * 64,
                        "raw_payload": {
                            "company_uid": str(COMPANY),
                            "status": "former",
                            "started_period": "2020-03",
                            "ended_period": "2024",
                        },
                    }
                ]
            }
        captured.update(call)
        return {"rows": [{"uid": str(AFFILIATION)}]}

    monkeypatch.setattr(store.planning, "_operation", execute)
    assert store.validate_import(ACTOR, uuid.uuid4()) == {"blocked": True}
    decisions = json.loads(captured["parameters"]["decisions"])
    assert decisions[0]["state"] == "blocked"
    assert decisions[0]["errors"][0]["code"] == "AFFILIATION_IMPORT_NOT_IMPLEMENTED"
