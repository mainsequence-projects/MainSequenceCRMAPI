"""Pydantic CRM pipelines models."""

from __future__ import annotations

from enum import Enum
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    conint,
    constr,
)

from .common import NonEmptyChanges
from .deals import Deal


class Pipeline(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    uid: UUID
    created_at: AwareDatetime
    updated_at: AwareDatetime
    created_by_uid: UUID | None
    updated_by_uid: UUID | None
    version: StrictInt
    name: constr(min_length=1, max_length=255)
    is_default: StrictBool
    board_version: StrictInt


class PipelineCreate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: constr(min_length=1, max_length=255)
    is_default: StrictBool | None = None


class PipelineChanges(NonEmptyChanges):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: constr(min_length=1, max_length=255) | None = None
    is_default: StrictBool | None = None


class PipelinePatch(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    expected_version: conint(strict=True, ge=1)
    changes: PipelineChanges


class StageOutcome(Enum):
    open = "open"
    won = "won"
    lost = "lost"


class Stage(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    uid: UUID
    created_at: AwareDatetime
    updated_at: AwareDatetime
    created_by_uid: UUID | None
    updated_by_uid: UUID | None
    version: StrictInt
    pipeline_uid: UUID
    key: constr(max_length=100)
    label: constr(max_length=255)
    position: StrictInt
    outcome: StageOutcome
    is_active: StrictBool


class StageCreate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    pipeline_uid: UUID
    key: constr(max_length=100)
    label: constr(max_length=255)
    outcome: StageOutcome
    is_active: StrictBool | None = None
    position: conint(strict=True, ge=0)


class StageChanges(NonEmptyChanges):
    model_config = ConfigDict(
        extra="forbid",
    )
    label: constr(max_length=255) | None = None
    outcome: StageOutcome | None = None
    is_active: StrictBool | None = None


class StagePatch(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    expected_version: conint(strict=True, ge=1)
    changes: StageChanges


class StageCreateCommand(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    expected_board_version: conint(strict=True, ge=1)
    stage: StageCreate


class StageCommandChanges(NonEmptyChanges):
    model_config = ConfigDict(
        extra="forbid",
    )
    label: constr(max_length=255) | None = None
    outcome: StageOutcome | None = None
    is_active: StrictBool | None = None


class StagePatchCommand(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    expected_version: conint(strict=True, ge=1)
    changes: StageCommandChanges
    expected_board_version: conint(strict=True, ge=1)


class ReorderStages(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    expected_board_version: conint(strict=True, ge=1)
    stage_uids: list[UUID] = Field(..., min_length=1)


class BoardColumn(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    stage: Stage
    items: list[Deal] = Field(..., max_length=100)
    total_items: conint(strict=True, ge=0)
    next_cursor: str | None
    amounts_by_currency: dict[
        constr(pattern=r"^[A-Z]{3}$"), constr(pattern=r"^[0-9]+(\.[0-9]{1,4})?$")
    ]


class Board(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    pipeline_uid: UUID
    board_version: conint(strict=True, ge=1)
    columns: list[BoardColumn] = Field(..., max_length=100)
