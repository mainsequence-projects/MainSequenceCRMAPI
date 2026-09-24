"""Pydantic CRM tasks models."""

from __future__ import annotations

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


class Task(BaseModel):
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
    contact_uid: UUID
    owner_uid: UUID | None
    type_key: constr(max_length=100)
    text: constr(min_length=1, max_length=100000)
    due_at: AwareDatetime | None
    completed_at: AwareDatetime | None
    completed_by_uid: UUID | None
    source_created_at: AwareDatetime | None
    source_updated_at: AwareDatetime | None


class TaskCreate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    contact_uid: UUID
    owner_uid: UUID | None = None
    type_key: constr(max_length=100) | None = None
    text: constr(min_length=1, max_length=100000)
    due_at: AwareDatetime | None = None


class TaskChanges(NonEmptyChanges):
    model_config = ConfigDict(
        extra="forbid",
    )
    contact_uid: UUID | None = None
    owner_uid: UUID | None = None
    type_key: constr(max_length=100) | None = None
    text: constr(min_length=1, max_length=100000) | None = None
    due_at: AwareDatetime | None = None


class TaskPatch(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    expected_version: conint(strict=True, ge=1)
    changes: TaskChanges
