"""Typed CRM note payloads."""

from __future__ import annotations

from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictInt, model_validator

from .common import AssetRef


class NoteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contact_uid: UUID | None = None
    deal_uid: UUID | None = None
    text: str = Field(min_length=1, max_length=100_000)
    occurred_at: AwareDatetime
    status_key: str | None = Field(default=None, max_length=100)
    attachment_refs: list[AssetRef] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def exactly_one_parent(self) -> NoteCreate:
        if (self.contact_uid is None) == (self.deal_uid is None):
            raise ValueError("A note must belong to one contact or one deal")
        return self


class NoteChanges(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str | None = Field(default=None, min_length=1, max_length=100_000)
    occurred_at: AwareDatetime | None = None
    status_key: str | None = Field(default=None, max_length=100)
    attachment_refs: list[AssetRef] | None = Field(default=None, max_length=20)

    @model_validator(mode="after")
    def has_changes(self) -> NoteChanges:
        if not self.model_fields_set:
            raise ValueError("At least one note field must change")
        return self


class NotePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: StrictInt = Field(ge=1)
    changes: NoteChanges


class Note(BaseModel):
    model_config = ConfigDict(extra="forbid")

    uid: UUID
    created_at: AwareDatetime
    updated_at: AwareDatetime
    created_by_uid: UUID | None
    updated_by_uid: UUID | None
    version: StrictInt = Field(ge=1)
    archived_at: AwareDatetime | None
    contact_uid: UUID | None
    deal_uid: UUID | None
    author_uid: UUID | None
    source_author_label: str | None
    text: str = Field(min_length=1, max_length=100_000)
    occurred_at: AwareDatetime
    status_key: str | None
    legacy_type: str | None
    attachment_refs: list[AssetRef] = Field(max_length=20)
