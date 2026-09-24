"""Pydantic CRM tags models."""

from __future__ import annotations

from enum import Enum
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    StrictInt,
    conint,
    constr,
)

from .common import NonEmptyChanges


class TagTone(Enum):
    neutral = "neutral"
    info = "info"
    success = "success"
    warning = "warning"
    danger = "danger"


class Tag(BaseModel):
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
    name: constr(min_length=1, max_length=100)
    normalized_name: constr(max_length=100)
    tone: TagTone
    legacy_color: constr(max_length=100) | None


class TagCreate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: constr(min_length=1, max_length=100)
    tone: TagTone | None = None


class TagChanges(NonEmptyChanges):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: constr(min_length=1, max_length=100) | None = None
    tone: TagTone | None = None


class TagPatch(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    expected_version: conint(strict=True, ge=1)
    changes: TagChanges
