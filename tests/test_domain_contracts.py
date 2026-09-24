"""Pydantic domain validation and normalization regressions."""

from __future__ import annotations

import pytest

from src.crm.contracts import DomainValidationError, normalized_create, normalized_patch


def contact_input() -> dict:
    return {
        "first_name": "Alex",
        "last_name": "Example",
        "company_uid": "11111111-1111-4111-8111-111111111111",
        "owner_uid": "22222222-2222-4222-8222-222222222222",
        "emails": [{"email": "alex@example.org", "type": "work"}],
        "has_newsletter": False,
        "tag_uids": ["33333333-3333-4333-8333-333333333333"],
    }


def test_valid_contact_preserves_false_and_normalizes_names():
    payload = contact_input()
    payload["first_name"] = "  Alex  "
    result = normalized_create("contact", payload)
    assert result["first_name"] == "Alex"
    assert result["has_newsletter"] is False
    assert payload["first_name"] == "  Alex  "


def test_contact_requires_real_identity_after_trim():
    for payload in (
        {"first_name": "  ", "emails": []},
        {"first_name": None, "last_name": None, "emails": []},
    ):
        with pytest.raises(DomainValidationError):
            normalized_create("contact", payload)


def test_patch_validates_complete_result_and_blocks_server_fields():
    existing = normalized_create("contact", contact_input())
    version, updated = normalized_patch(
        "contact",
        existing,
        {"expected_version": 2, "changes": {"has_newsletter": False, "company_uid": None}},
    )
    assert version == 2 and updated["has_newsletter"] is False
    with pytest.raises(DomainValidationError):
        normalized_patch(
            "contact",
            existing,
            {
                "expected_version": 2,
                "changes": {"workspace_uid": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"},
            },
        )


def test_company_blank_and_duplicate_contact_methods():
    with pytest.raises(DomainValidationError):
        normalized_create("company", {"name": "  "})
    with pytest.raises(DomainValidationError):
        normalized_create(
            "contact",
            {
                "emails": [
                    {"email": " A@example.org ", "type": "work"},
                    {"email": "a@example.org", "type": "home"},
                ]
            },
        )


def test_unknown_fields_and_empty_patches_are_rejected():
    with pytest.raises(DomainValidationError):
        normalized_create("contact", {"first_name": "Alex", "workspace_uid": "forged"})
    with pytest.raises(DomainValidationError):
        normalized_patch(
            "contact",
            normalized_create("contact", contact_input()),
            {
                "expected_version": 1,
                "changes": {},
            },
        )
