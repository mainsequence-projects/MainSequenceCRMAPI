"""Typed contact payloads and contact-specific invariants."""

from __future__ import annotations

from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    field_validator,
    model_validator,
)

from .common import AssetRef, Email, Phone
from .socials import SocialLinks, SocialLinksPatch


class ContactCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    owner_uid: UUID | None = None
    company_uid: UUID | None = None
    first_name: str | None = Field(default=None, max_length=255)
    last_name: str | None = Field(default=None, max_length=255)
    title: str | None = Field(default=None, max_length=255)
    gender: str | None = Field(default=None, max_length=100)
    background: str | None = None
    avatar_ref: AssetRef | None = None
    socials: SocialLinks = Field(default_factory=SocialLinks)
    emails: list[Email] = Field(default_factory=list, max_length=20)
    phones: list[Phone] = Field(default_factory=list, max_length=20)
    first_seen: AwareDatetime | None = None
    last_seen: AwareDatetime | None = None
    has_newsletter: StrictBool | None = None
    status_key: str | None = Field(default=None, max_length=100)
    tag_uids: list[UUID] = Field(default_factory=list, max_length=100)

    @field_validator("first_name", "last_name", mode="before")
    @classmethod
    def trim_name(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip() or None
        return value

    @model_validator(mode="after")
    def valid_identity_and_methods(self) -> ContactCreate:
        if not (self.first_name or self.last_name or self.emails):
            raise ValueError("A name or email is required")
        if len({item.email.casefold() for item in self.emails}) != len(self.emails):
            raise ValueError("Contact emails must be unique")
        if len({item.number for item in self.phones}) != len(self.phones):
            raise ValueError("Contact phone numbers must be unique")
        if len(set(self.tag_uids)) != len(self.tag_uids):
            raise ValueError("Contact tags must be unique")
        return self


class ContactChanges(BaseModel):
    model_config = ConfigDict(extra="forbid")

    owner_uid: UUID | None = None
    company_uid: UUID | None = None
    first_name: str | None = Field(default=None, max_length=255)
    last_name: str | None = Field(default=None, max_length=255)
    title: str | None = Field(default=None, max_length=255)
    gender: str | None = Field(default=None, max_length=100)
    background: str | None = None
    avatar_ref: AssetRef | None = None
    socials: SocialLinksPatch | None = None
    emails: list[Email] | None = Field(default=None, max_length=20)
    phones: list[Phone] | None = Field(default=None, max_length=20)
    first_seen: AwareDatetime | None = None
    last_seen: AwareDatetime | None = None
    has_newsletter: StrictBool | None = None
    status_key: str | None = Field(default=None, max_length=100)
    tag_uids: list[UUID] | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def has_changes(self) -> ContactChanges:
        if not self.model_fields_set:
            raise ValueError("At least one contact field must change")
        return self


class ContactPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: StrictInt = Field(ge=1)
    changes: ContactChanges


class Contact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    uid: UUID
    created_at: AwareDatetime
    updated_at: AwareDatetime
    created_by_uid: UUID | None
    updated_by_uid: UUID | None
    version: StrictInt = Field(ge=1)
    archived_at: AwareDatetime | None
    owner_uid: UUID | None
    company_uid: UUID | None
    first_name: str | None
    last_name: str | None
    title: str | None
    gender: str | None
    background: str | None
    avatar_ref: AssetRef | None
    socials: SocialLinks
    emails: list[Email] = Field(max_length=20)
    phones: list[Phone] = Field(max_length=20)
    first_seen: AwareDatetime | None
    last_seen: AwareDatetime | None
    has_newsletter: StrictBool | None
    status_key: str | None
    source_created_at: AwareDatetime | None
    source_updated_at: AwareDatetime | None
    tag_uids: list[UUID] = Field(max_length=100)
    display_name: str
    company_name: str | None
    open_task_count: StrictInt = Field(ge=0)
