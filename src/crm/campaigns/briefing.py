"""Input bindings, prompt assignment and result contracts. Pure functions, no I/O."""

from __future__ import annotations

from datetime import datetime
from random import Random
from typing import Any

from .models import PromptVariant

# Contact fields a prompt may read; no credentials, audit or storage metadata.
CONTACT_FIELDS = frozenset({
    "uid", "display_name", "first_name", "last_name", "title", "company_uid", "company_name",
    "status_key", "emails", "phones", "socials", "background", "last_seen",
})


def choose_variant(variants: list[PromptVariant], rng: Random) -> PromptVariant:
    """Weighted random selection; a single variant is always chosen."""
    if len(variants) == 1:
        return variants[0]
    point = rng.random() * 100
    cumulative = 0
    for variant in variants:
        cumulative += variant.allocation_percent
        if point < cumulative:
            return variant
    return variants[-1]


def _walk(value: Any, parts: list[str]) -> tuple[bool, Any]:
    for part in parts:
        if isinstance(value, dict) and part in value:
            value = value[part]
        elif isinstance(value, list) and part.isdigit() and int(part) < len(value):
            value = value[int(part)]
        else:
            return False, None
    return True, value


def resolve_binding(
    path: str,
    *,
    campaign: dict[str, Any],
    contact: dict[str, Any],
    participant: dict[str, Any],
    previous_results: dict[str, dict[str, Any]],
) -> tuple[bool, Any]:
    """Return (found, value) for a documented data path; never evaluates code."""
    parts = path.split(".")
    root = parts[0]
    if root == "campaign":
        if len(parts) == 2 and parts[1] in {"name", "objective"}:
            return True, campaign.get(parts[1])
        if len(parts) >= 3 and parts[1] == "context":
            return _walk(campaign.get("context", {}), parts[2:])
        return False, None
    if root == "contact":
        if len(parts) >= 2 and parts[1] in CONTACT_FIELDS:
            return _walk(contact, parts[1:])
        return False, None
    if root == "participant":
        if len(parts) >= 3 and parts[1] == "context":
            return _walk(participant.get("context", {}), parts[2:])
        return False, None
    if root == "previous" and len(parts) >= 4 and parts[2] == "result":
        result = previous_results.get(parts[1])
        if result is None:
            return False, None
        return _walk(result, parts[3:])
    return False, None


def value_matches(value: Any, expected: str) -> bool:
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "datetime":
        if not isinstance(value, str):
            return False
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return False
        return parsed.tzinfo is not None
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    return False


def resolve_inputs(
    *,
    declared: list[dict[str, Any]],
    bindings: dict[str, str],
    campaign: dict[str, Any],
    contact: dict[str, Any],
    participant: dict[str, Any],
    previous_results: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Resolve each declared prompt input; a missing required value is a diagnostic."""
    inputs: dict[str, Any] = {}
    diagnostics: list[dict[str, str]] = []
    for field in declared:
        key = field["key"]
        path = bindings.get(key)
        if path is None:
            if field.get("required", True):
                diagnostics.append({"code": "input_unbound", "message": f"Required input '{key}' has no binding"})
            continue
        found, value = resolve_binding(
            path, campaign=campaign, contact=contact, participant=participant, previous_results=previous_results
        )
        if not found or value is None:
            if field.get("required", True):
                diagnostics.append({"code": "input_missing", "message": f"Required input '{key}' is absent at {path}"})
            continue
        if not value_matches(value, field["type"]):
            diagnostics.append({"code": "input_type", "message": f"Input '{key}' at {path} is not a {field['type']}"})
            continue
        inputs[key] = value
    return inputs, diagnostics


def validate_result(result: dict[str, Any], declared: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Strict result contract: declared keys only, required present, types matching."""
    problems: list[dict[str, str]] = []
    fields = {field["key"]: field for field in declared}
    for key in result:
        if key not in fields:
            problems.append({"path": f"result.{key}", "code": "unknown_field", "message": "Invalid value"})
    for key, field in fields.items():
        if key not in result:
            if field.get("required", True):
                problems.append({"path": f"result.{key}", "code": "missing", "message": "Invalid value"})
            continue
        if not value_matches(result[key], field["type"]):
            problems.append({"path": f"result.{key}", "code": "type", "message": "Invalid value"})
    return problems
