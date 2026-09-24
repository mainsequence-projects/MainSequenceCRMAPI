"""Typed, closed import mapping selected during CRM transfer review."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool


class ImportMapping(BaseModel):
    model_config = ConfigDict(extra="forbid")

    adapter_id: str
    source_connection_uid: UUID
    entity_type: str
    field_map: dict[str, str]
    owner_map: dict[str, UUID | None]
    stage_map: dict[str, UUID]
    status_map: dict[str, str]
    unknown_fields: Literal["preserve_with_warning", "block"]
    unresolved_owner_policy: Literal["block", "explicitly_unassigned"]
    duplicate_policy: Literal["source_id_only", "review_candidates"]
    update_policy: Literal["create_only", "update_if_unchanged_since_import", "explicit_overwrite"]
    date_format: Literal["iso8601", "YYYY-MM-DD", "DD/MM/YYYY", "MM/DD/YYYY"]
    source_timezone: str
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    empty_cell_policy: Literal["omit", "explicit_null"]
    boolean_map: dict[str, StrictBool | None]
