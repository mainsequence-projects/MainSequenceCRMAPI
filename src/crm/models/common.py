"""Pydantic CRM common models."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import (
    AnyUrl,
    BaseModel,
    ConfigDict,
    EmailStr,
    RootModel,
    conint,
    constr,
    field_validator,
    model_validator,
)


class AssetRef(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    kind: Literal["external_link"]
    url: AnyUrl
    title: constr(max_length=255)
    mime_type: constr(max_length=255) | None = None
    source_verified: Literal[False]


class ContactMethodType(Enum):
    work = "work"
    home = "home"
    other = "other"


class Email(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    email: EmailStr
    type: ContactMethodType

    @field_validator("email", mode="before")
    @classmethod
    def strip_email(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class Phone(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    number: constr(min_length=1, max_length=100)
    type: ContactMethodType

    @field_validator("number", mode="before")
    @classmethod
    def strip_number(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class ContextLink(RootModel[AnyUrl]):
    root: AnyUrl


class VersionCommand(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    expected_version: conint(strict=True, ge=1)


class NonEmptyChanges(BaseModel):
    """Patch payloads must name at least one field to change."""

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def has_changes(self):
        if not self.model_fields_set:
            raise ValueError("At least one field must change")
        return self
