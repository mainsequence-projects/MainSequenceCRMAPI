"""Pydantic CRM merge models."""

from __future__ import annotations

from enum import Enum
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    conint,
    constr,
    field_validator,
)

from .contacts import Contact
from .socials import SocialLinks

MERGE_SCALAR_FIELDS = frozenset(
    {
        "first_name",
        "last_name",
        "title",
        "company_uid",
        "owner_uid",
        "gender",
        "background",
        "status_key",
        "has_newsletter",
        "avatar_ref",
    }
)
MERGE_SOCIAL_FIELDS = frozenset(f"socials.{key}" for key in SocialLinks.model_fields)


class MergeFieldResolution(Enum):
    survivor = "survivor"
    loser = "loser"


def validate_merge_fields(
    value: dict[str, MergeFieldResolution],
) -> dict[str, MergeFieldResolution]:
    if set(value) - MERGE_SCALAR_FIELDS - MERGE_SOCIAL_FIELDS:
        raise ValueError("Unsupported contact merge field")
    return value


class MergePreviewRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    loser_uid: UUID
    field_resolutions: dict[str, MergeFieldResolution]

    @field_validator("field_resolutions")
    @classmethod
    def allowed_fields(
        cls, value: dict[str, MergeFieldResolution]
    ) -> dict[str, MergeFieldResolution]:
        return validate_merge_fields(value)


class MergeExecuteRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    loser_uid: UUID
    field_resolutions: dict[str, MergeFieldResolution]
    expected_version: conint(strict=True, ge=1)
    loser_expected_version: conint(strict=True, ge=1)
    plan_hash: constr(pattern=r"^[a-f0-9]{64}$")

    @field_validator("field_resolutions")
    @classmethod
    def allowed_fields(
        cls, value: dict[str, MergeFieldResolution]
    ) -> dict[str, MergeFieldResolution]:
        return validate_merge_fields(value)


class RelatedCounts(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    notes: conint(strict=True, ge=0)
    tasks: conint(strict=True, ge=0)
    deals: conint(strict=True, ge=0)
    tags: conint(strict=True, ge=0)
    source_identities: conint(strict=True, ge=0)
    affiliations: conint(strict=True, ge=0)


class MergePreview(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    survivor_uid: UUID
    loser_uid: UUID
    survivor_version: conint(strict=True, ge=1)
    loser_version: conint(strict=True, ge=1)
    plan_hash: constr(pattern=r"^[a-f0-9]{64}$")
    proposed_contact: Contact
    related_counts: RelatedCounts
    warnings: list[str]


class MergeResult(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    command_uid: UUID
    survivor: Contact
    retired_uid: UUID
