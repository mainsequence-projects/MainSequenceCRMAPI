"""Pure CRM transfer serialization and spreadsheet-safe reporting."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import UTC, datetime
from typing import Any

EXPORT_ENTITY_TABLES = {
    "companies": "company",
    "contacts": "contact",
    "deals": "deal",
    "tasks": "task",
    "notes": "note",
    "tags": "tag",
}
EXPORT_TABLE_KEYS = {table: entity for entity, table in EXPORT_ENTITY_TABLES.items()}
EXPORT_TABLE_KEYS.update({"pipeline": "pipelines", "stage": "stages"})
ALL_EXPORT_TABLES = ("company", "contact", "tag", "pipeline", "stage", "deal", "note", "task")


def export_entity_names(entity_type: str | None) -> list[str]:
    return [EXPORT_ENTITY_TABLES[entity_type]] if entity_type else list(ALL_EXPORT_TABLES)


def export_record_key(table: str) -> str:
    return EXPORT_TABLE_KEYS[table]


def package_export(
    data: dict[str, Any], records: dict[str, list]
) -> tuple[dict[str, Any], dict[str, int]]:
    output = (
        {
            "format": "mainsequence.crm.portable@v1",
            "exported_at": datetime.now(UTC).isoformat(),
            "entities": records,
        }
        if data["format"] == "portable-json"
        else {
            "format": "mainsequence.crm.csv@v1",
            "entity_type": data["entity_type"],
            "records": records[data["entity_type"]],
        }
    )
    encoded = json.dumps(output, sort_keys=True, separators=(",", ":"), default=str)
    manifest = {
        "format": data["format"],
        "entity_type": data["entity_type"],
        "sha256": hashlib.sha256(encoded.encode()).hexdigest(),
        "output": output,
    }
    total = sum(len(rows) for rows in records.values())
    counts = {
        "total": total,
        "valid": total,
        "blocked": 0,
        "committed": total,
        "skipped": 0,
        "failed": 0,
    }
    return manifest, counts


def csv_safe(value: Any) -> str:
    text = str(value)
    stripped = text.lstrip()
    if stripped.startswith(("=", "+", "-", "@", "\t", "\r", "\n")) or (text and ord(text[0]) < 32):
        return "'" + text
    return text


def _issue_list(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise RuntimeError("CRM row issues have an invalid shape") from exc
    if not isinstance(value, list):
        raise RuntimeError("CRM row issues have an invalid shape")
    return value


def render_error_csv(rows: list[dict[str, Any]]) -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(
        ["row_uid", "entity_type", "ordinal", "external_id", "severity", "field", "code", "message"]
    )
    for row in rows:
        for issue in _issue_list(row.get("errors")) + _issue_list(row.get("warnings")):
            values = [
                str(row["uid"]),
                row["entity_type"],
                row["ordinal"],
                row.get("external_id") or "",
                issue.get("severity", "error"),
                issue.get("field") or "",
                issue.get("code", ""),
                issue.get("message", ""),
            ]
            writer.writerow([csv_safe(value) for value in values])
    return output.getvalue()


def render_export(manifest: dict[str, Any]) -> tuple[str, str, str]:
    output = manifest.get("output")
    if not isinstance(output, dict):
        raise RuntimeError("CRM export output has an invalid shape")
    encoded = json.dumps(output, sort_keys=True, separators=(",", ":"), default=str)
    if hashlib.sha256(encoded.encode()).hexdigest() != manifest.get("sha256"):
        raise RuntimeError("Export output failed digest verification")
    if manifest.get("format") == "csv":
        records = output.get("records", [])
        fields = sorted({key for record in records for key in record})
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for record in records:
            writer.writerow(
                {
                    key: csv_safe(
                        json.dumps(value, ensure_ascii=False)
                        if isinstance(value, (dict, list))
                        else value
                        if value is not None
                        else ""
                    )
                    for key, value in record.items()
                }
            )
        return stream.getvalue(), "text/csv; charset=utf-8", "crm-export.csv"
    return (
        json.dumps(output, ensure_ascii=False, indent=2, default=str),
        "application/json",
        "crm-export.json",
    )
