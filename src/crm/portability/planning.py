"""Pure import-row assessment, independent of MetaTable persistence."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from ..models.affiliations import AffiliationFields


def assess_staged_rows(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    issues: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    for row in rows:
        payload = row["raw_payload"]
        row_issues: list[dict[str, Any]] = []
        if not payload:
            row_issues.append(
                {
                    "field": None,
                    "code": "EMPTY_ROW",
                    "message": "The source row is empty",
                    "severity": "error",
                }
            )
        if row["entity_type"] == "contact_company_affiliation":
            try:
                AffiliationFields.model_validate(
                    {
                        field: payload[field]
                        for field in AffiliationFields.model_fields
                        if field in payload
                    }
                )
            except ValueError:
                row_issues.append(
                    {
                        "field": "started_period",
                        "code": "INVALID_AFFILIATION",
                        "message": "Affiliation company, status, or period is invalid",
                        "severity": "error",
                    }
                )
            row_issues.append(
                {
                    "field": None,
                    "code": "AFFILIATION_IMPORT_NOT_IMPLEMENTED",
                    "message": "Affiliation import execution is not available; staged history cannot be committed",
                    "severity": "error",
                }
            )
        for item in row_issues:
            issues.append(
                {
                    "row_uid": str(row["uid"]),
                    "entity_type": row["entity_type"],
                    "ordinal": int(row["ordinal"]),
                    **item,
                }
            )
        decisions.append(
            {
                "uid": str(row["uid"]),
                "state": "blocked" if row_issues else "valid",
                "errors": row_issues,
                "warnings": [],
            }
        )
    return issues, decisions


def sealed_plan_hash(
    input_sha256: str | None,
    mapping: dict[str, Any],
    mapping_revision: int,
    rows: list[dict[str, Any]],
) -> str:
    canonical = {
        "input_sha256": input_sha256,
        "mapping": mapping,
        "mapping_revision": mapping_revision,
        "rows": [row["raw_hash"] for row in rows],
    }
    return hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
