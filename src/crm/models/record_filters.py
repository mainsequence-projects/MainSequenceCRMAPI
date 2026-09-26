"""Closed HTTP filter contract for Interaction and extension lists."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, constr


class RecordFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company_uid: UUID | None = None
    contact_uid: UUID | None = None
    deal_uid: UUID | None = None
    interaction_uid: UUID | None = None
    solution_selling_uid: UUID | None = None
    profile_uid: UUID | None = None
    owner_uid: UUID | None = None
    kind: constr(max_length=100) | None = None
    status: constr(max_length=50) | None = None
    market_context: constr(max_length=255) | None = None
    role: constr(max_length=255) | None = None
