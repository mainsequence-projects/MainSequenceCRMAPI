"""Fixed Markdown documents; never executable templates or model requests."""

from __future__ import annotations

from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from .common import NonEmptyChanges, VersionCommand

MARKDOWN_BYTES_MAX = 65536


def validate_markdown(value: str) -> str:
    if not value.strip() or "\x00" in value or len(value.encode("utf-8")) > MARKDOWN_BYTES_MAX:
        raise ValueError("Provide non-empty Markdown of at most 64 KiB without NUL characters")
    return value  # Preserve whitespace, code and literal braces exactly.


class PromptFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)

    @field_validator("description")
    @classmethod
    def valid_description(cls, value: str | None) -> str | None:
        if value is not None and "\x00" in value:
            raise ValueError("Description cannot contain NUL characters")
        return value

    @field_validator("name")
    @classmethod
    def valid_name(cls, value: str) -> str:
        if not value.strip() or "\x00" in value:
            raise ValueError("Provide a name")
        return value.strip()


class PromptCreate(PromptFields):
    content_markdown: str = Field(min_length=1, max_length=MARKDOWN_BYTES_MAX)
    _markdown = field_validator("content_markdown")(validate_markdown)


class PromptSummary(PromptFields):
    uid: UUID
    created_at: AwareDatetime
    updated_at: AwareDatetime
    created_by_uid: UUID | None
    updated_by_uid: UUID | None
    version: int = Field(strict=True, ge=1)
    archived_at: AwareDatetime | None


class Prompt(PromptSummary):
    content_markdown: str = Field(min_length=1, max_length=MARKDOWN_BYTES_MAX)
    _markdown = field_validator("content_markdown")(validate_markdown)


class PromptChanges(NonEmptyChanges):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    content_markdown: str | None = Field(default=None, min_length=1, max_length=MARKDOWN_BYTES_MAX)
    _description = field_validator("description")(PromptFields.valid_description)

    @field_validator("name", "content_markdown")
    @classmethod
    def required_changes(cls, value: str | None, info) -> str:
        if value is None:
            raise ValueError("Required prompt fields cannot be null")
        if info.field_name == "content_markdown":
            return validate_markdown(value)
        return PromptFields.valid_name(value)


class PromptPatch(VersionCommand):
    changes: PromptChanges
