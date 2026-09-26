"""Typed semantic scopes shared by CRM callers and data access."""

from __future__ import annotations

from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StringConstraints,
    model_validator,
)


class QueryScope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    search: str | None = None
    filters: dict[str, Any] = Field(default_factory=dict)
    ordering: str | None = None
    page_index: StrictInt = Field(default=0, ge=0)
    page_size: StrictInt = Field(default=25, ge=1, le=100)


class SemanticFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def reject_null_and_non_string_uuid_values(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            raise ValueError("Filters must be a JSON object")
        for key, item in value.items():
            if item is None:
                raise ValueError(f"filters.{key} cannot be null")
            if key.endswith("_uid") and not isinstance(item, str):
                raise ValueError(f"filters.{key} must be a UUID string")
        return value


ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Archived = StrictBool | Literal["all"]


class ContactFilters(SemanticFilters):
    company_uid: UUID | None = None
    owner_uid: UUID | None = None
    status_key: ShortText | None = None
    tag_uid: UUID | None = None
    has_open_tasks: StrictBool | None = None
    seen_window: ShortText | None = None
    archived: Archived | None = None


class CompanyFilters(SemanticFilters):
    owner_uid: UUID | None = None
    sector: ShortText | None = None
    country: ShortText | None = None
    archived: Archived | None = None


class DealFilters(SemanticFilters):
    pipeline_uid: UUID | None = None
    stage_uid: UUID | None = None
    company_uid: UUID | None = None
    contact_uid: UUID | None = None
    owner_uid: UUID | None = None
    currency: ShortText | None = None
    archived: Archived | None = None


class TaskFilters(SemanticFilters):
    contact_uid: UUID | None = None
    owner_uid: UUID | None = None
    type_key: ShortText | None = None
    completion: ShortText | None = None
    due_window: ShortText | None = None
    archived: Archived | None = None


class NoteFilters(SemanticFilters):
    contact_uid: UUID | None = None
    deal_uid: UUID | None = None
    author_uid: UUID | None = None
    archived: Archived | None = None

    @model_validator(mode="after")
    def single_parent(self) -> NoteFilters:
        if self.contact_uid is not None and self.deal_uid is not None:
            raise ValueError("Choose one note parent")
        return self


class TagFilters(SemanticFilters):
    archived: Archived | None = None


class ActivityFilters(SemanticFilters):
    entity_type: ShortText | None = None
    entity_uid: UUID | None = None
    actor_uid: UUID | None = None
    origin: ShortText | None = None
    occurred_window: ShortText | None = None


class TransferFilters(SemanticFilters):
    direction: ShortText | None = None
    status: ShortText | None = None
    mine: StrictBool | None = None


class PipelineFilters(SemanticFilters):
    pass


FILTER_MODELS: dict[str, type[SemanticFilters]] = {
    "contacts": ContactFilters,
    "companies": CompanyFilters,
    "deals": DealFilters,
    "tasks": TaskFilters,
    "notes": NoteFilters,
    "tags": TagFilters,
    "activity": ActivityFilters,
    "transfers": TransferFilters,
    "pipelines": PipelineFilters,
}
