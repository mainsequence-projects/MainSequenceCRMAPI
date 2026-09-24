"""Pydantic CRM deals models."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    conint,
    constr,
)

from .common import NonEmptyChanges


class Deal(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    uid: UUID
    created_at: AwareDatetime
    updated_at: AwareDatetime
    created_by_uid: UUID | None
    updated_by_uid: UUID | None
    version: StrictInt
    archived_at: AwareDatetime | None
    owner_uid: UUID | None
    company_uid: UUID | None
    pipeline_uid: UUID
    stage_uid: UUID
    name: constr(min_length=1, max_length=255)
    category_key: constr(max_length=100) | None
    description: str | None
    amount: constr(pattern=r"^(0|[1-9][0-9]{0,15})(\.[0-9]{1,4})?$") | None
    currency: constr(pattern=r"^[A-Z]{3}$", max_length=3)
    expected_closing_date: date | None
    position: StrictInt
    source_created_at: AwareDatetime | None
    source_updated_at: AwareDatetime | None
    contact_uids: list[UUID] = Field(..., max_length=100)


class DealCreate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    owner_uid: UUID | None = None
    company_uid: UUID | None = None
    pipeline_uid: UUID
    stage_uid: UUID
    name: constr(min_length=1, max_length=255)
    category_key: constr(max_length=100) | None = None
    description: str | None = None
    amount: constr(pattern=r"^(0|[1-9][0-9]{0,15})(\.[0-9]{1,4})?$") | None = None
    currency: constr(pattern=r"^[A-Z]{3}$", max_length=3)
    expected_closing_date: date | None = None
    contact_uids: list[UUID] | None = Field(None, max_length=100)


class DealChanges(NonEmptyChanges):
    model_config = ConfigDict(
        extra="forbid",
    )
    owner_uid: UUID | None = None
    company_uid: UUID | None = None
    name: constr(min_length=1, max_length=255) | None = None
    category_key: constr(max_length=100) | None = None
    description: str | None = None
    amount: constr(pattern=r"^(0|[1-9][0-9]{0,15})(\.[0-9]{1,4})?$") | None = None
    currency: constr(pattern=r"^[A-Z]{3}$", max_length=3) | None = None
    expected_closing_date: date | None = None
    contact_uids: list[UUID] | None = Field(None, max_length=100)


class DealPatch(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    expected_version: conint(strict=True, ge=1)
    changes: DealChanges


class MoveDeal(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    expected_version: conint(strict=True, ge=1)
    expected_board_version: conint(strict=True, ge=1)
    target_stage_uid: UUID
    before_deal_uid: UUID | None


class MoveResult(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    command_uid: UUID
    board_version: conint(strict=True, ge=1)
    deal: Deal
    invalidated_stage_uids: list[UUID] = Field(..., max_length=2)
