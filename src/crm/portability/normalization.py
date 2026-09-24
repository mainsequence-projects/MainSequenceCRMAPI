"""Tested pure helpers, not a complete importer or runtime gateway."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Mapping

_MONEY = re.compile(r"^(0|[1-9][0-9]{0,15})(\.[0-9]{1,4})?$")


def source_id(value: str | int) -> str:
    """Keep opaque IDs exact. Never accept bool or floating-point coercion."""
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError("A source identifier must be a string or an exact integer")
    result = str(value)
    if not result or not result.strip() or len(result) > 2048:
        raise ValueError("A source identifier must be nonblank and at most 2048 characters")
    return result


def decimal_money(value: str | int | Decimal) -> str:
    """Return exact JSON decimal text; reject silent rounding/truncation."""
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise ValueError("Money must not pass through a binary float")
    text = format(value, "f") if isinstance(value, Decimal) else str(value).strip()
    if not _MONEY.fullmatch(text):
        raise ValueError(
            "Expected a nonnegative decimal with <=16 integer and <=4 fractional digits"
        )
    return text


def mapped_boolean(value: Any, mapping: Mapping[str, bool | None]) -> bool | None:
    if value is None or isinstance(value, bool):
        return value
    key = str(value).strip().casefold()
    if key not in mapping:
        raise ValueError(f"Unmapped boolean spelling: {key!r}")
    result = mapping[key]
    if result is not None and not isinstance(result, bool):
        raise ValueError("Boolean mapping values must be booleans or null")
    return result


def aware_timestamp(value: str) -> str:
    """ISO offset-aware timestamps only; source-local interpretation is separate."""
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Expected an ISO timestamp with an explicit offset") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("An explicit offset is required; do not guess source timezone/DST")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def source_row_key(file_sha256: str, json_pointer: str) -> str:
    if not re.fullmatch(r"[a-f0-9]{64}", file_sha256):
        raise ValueError("Expected the server-computed SHA-256")
    if not json_pointer.startswith("/"):
        raise ValueError("Expected a stable absolute JSON pointer")
    digest = hashlib.sha256((file_sha256 + "\0" + json_pointer).encode()).hexdigest()
    return "file-row:" + digest


def formula_safe_csv_cell(value: Any) -> str:
    """For spreadsheet-facing reports only; JSON is the exact interchange format."""
    text = "" if value is None else str(value)
    candidate = text.lstrip(" \t\r\n\x00\x0b\x0c")
    if text.startswith(("\t", "\r", "\n")) or candidate.startswith(("=", "+", "-", "@")):
        return "'" + text
    return text
