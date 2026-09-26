"""Core CRM conversation contracts; independent of sales methodology."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, StrictInt, conint, constr

from .common import NonEmptyChanges


class InteractionFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company_uid: UUID
    contact_uid: UUID | None = None
    deal_uid: UUID | None = None
    subject: constr(min_length=1, max_length=255)
    kind: Literal["call", "meeting", "workshop", "email"]
    status: Literal["planned", "completed", "cancelled"]
    scheduled_at: AwareDatetime | None = None
    occurred_at: AwareDatetime | None = None
    objective: str | None = None
    research_notes: str | None = None
    discussion_plan: str | None = None
    outcome_notes: str | None = None
    next_steps: str | None = None


class InteractionCreate(InteractionFields):
    pass


class Interaction(InteractionFields):
    uid: UUID
    created_at: AwareDatetime
    updated_at: AwareDatetime
    created_by_uid: UUID | None
    updated_by_uid: UUID | None
    version: StrictInt
    archived_at: AwareDatetime | None


class InteractionChanges(NonEmptyChanges):
    model_config = ConfigDict(extra="forbid")

    company_uid: UUID | None = None
    contact_uid: UUID | None = None
    deal_uid: UUID | None = None
    subject: constr(min_length=1, max_length=255) | None = None
    kind: Literal["call", "meeting", "workshop", "email"] | None = None
    status: Literal["planned", "completed", "cancelled"] | None = None
    scheduled_at: AwareDatetime | None = None
    occurred_at: AwareDatetime | None = None
    objective: str | None = None
    research_notes: str | None = None
    discussion_plan: str | None = None
    outcome_notes: str | None = None
    next_steps: str | None = None


class InteractionPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: conint(strict=True, ge=1)
    changes: InteractionChanges
