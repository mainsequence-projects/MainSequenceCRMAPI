"""Validation and normalization at the CRM domain boundary."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from .registry import model_for


class DomainValidationError(ValueError):
    def __init__(self, fields: list[dict[str, str]]):
        super().__init__("CRM payload validation failed")
        self.fields = fields


def _validated(definition: str, payload: Any, *, exclude_unset: bool) -> dict[str, Any]:
    model = model_for(definition)
    try:
        return model.model_validate(payload).model_dump(mode="json", exclude_unset=exclude_unset)
    except ValidationError as exc:
        raise DomainValidationError(
            [
                {
                    "path": ".".join(map(str, issue["loc"])),
                    "code": issue["type"],
                    "message": "Invalid value",
                }
                for issue in exc.errors(include_context=False, include_url=False)
            ]
        ) from exc


def validate_payload(definition: str, payload: Any) -> dict[str, Any]:
    """Validate with the authored Pydantic class and return JSON-safe values."""
    return _validated(definition, payload, exclude_unset=True)


def normalized_create(entity: str, payload: dict[str, Any]) -> dict[str, Any]:
    if entity not in {"contact", "company"}:
        raise ValueError("Unsupported CRM entity")
    data = _validated(f"{entity.title()}Create", payload, exclude_unset=False)
    if entity == "company" and data.get("context_links") is None:
        data["context_links"] = []
    if entity == "contact":
        data["socials"] = {
            key: value for key, value in data["socials"].items() if value is not None
        }
    return data


def normalized_patch(
    entity: str, existing: dict[str, Any], payload: dict[str, Any]
) -> tuple[int, dict[str, Any]]:
    if entity not in {"contact", "company"}:
        raise ValueError("Unsupported CRM entity")
    patch = validate_payload(f"{entity.title()}Patch", payload)
    create_fields = model_for(f"{entity.title()}Create").model_fields
    candidate = {key: existing[key] for key in create_fields if key in existing}
    changes = patch["changes"]
    if entity == "contact" and "socials" in changes:
        social_changes = changes["socials"]
        changes["socials"] = (
            {**candidate.get("socials", {}), **social_changes} if social_changes is not None else {}
        )
    candidate.update(changes)
    return patch["expected_version"], normalized_create(entity, candidate)
