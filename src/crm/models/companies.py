"""Pydantic CRM companies models."""

from __future__ import annotations

from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    conint,
    constr,
    field_validator,
)

from .common import AssetRef, ContextLink, NonEmptyChanges


class Company(BaseModel):
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
    name: constr(min_length=1, max_length=255)
    sector_key: constr(max_length=100) | None
    size_category: StrictInt | None
    linkedin_url: str | None
    website: str | None
    normalized_domain: constr(max_length=255) | None
    phone_number: constr(max_length=100) | None
    address: str | None
    zipcode: constr(max_length=40) | None
    city: constr(max_length=255) | None
    state_abbr: constr(max_length=100) | None
    country: constr(max_length=255) | None
    description: str | None
    revenue_text: str | None
    tax_identifier: constr(max_length=255) | None
    context_links: list[ContextLink] = Field(..., max_length=50)
    logo_ref: AssetRef | None
    source_created_at: AwareDatetime | None
    source_updated_at: AwareDatetime | None
    contact_count: conint(strict=True, ge=0)
    deal_count: conint(strict=True, ge=0)


class CompanyCreate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    owner_uid: UUID | None = None
    name: constr(min_length=1, max_length=255)
    sector_key: constr(max_length=100) | None = None
    size_category: StrictInt | None = None
    linkedin_url: str | None = None
    website: str | None = None
    phone_number: constr(max_length=100) | None = None
    address: str | None = None
    zipcode: constr(max_length=40) | None = None
    city: constr(max_length=255) | None = None
    state_abbr: constr(max_length=100) | None = None
    country: constr(max_length=255) | None = None
    description: str | None = None
    revenue_text: str | None = None
    tax_identifier: constr(max_length=255) | None = None
    context_links: list[ContextLink] | None = Field(None, max_length=50)
    logo_ref: AssetRef | None = None

    @field_validator("name", mode="before")
    @classmethod
    def trim_name(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class CompanyChanges(NonEmptyChanges):
    model_config = ConfigDict(
        extra="forbid",
    )
    owner_uid: UUID | None = None
    name: constr(min_length=1, max_length=255) | None = None
    sector_key: constr(max_length=100) | None = None
    size_category: StrictInt | None = None
    linkedin_url: str | None = None
    website: str | None = None
    phone_number: constr(max_length=100) | None = None
    address: str | None = None
    zipcode: constr(max_length=40) | None = None
    city: constr(max_length=255) | None = None
    state_abbr: constr(max_length=100) | None = None
    country: constr(max_length=255) | None = None
    description: str | None = None
    revenue_text: str | None = None
    tax_identifier: constr(max_length=255) | None = None
    context_links: list[ContextLink] | None = Field(None, max_length=50)
    logo_ref: AssetRef | None = None

    @field_validator("name", mode="before")
    @classmethod
    def trim_name(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class CompanyPatch(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    expected_version: conint(strict=True, ge=1)
    changes: CompanyChanges
