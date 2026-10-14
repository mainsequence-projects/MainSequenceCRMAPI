"""Explicit, version-fenced Command Center prompter deletion requests."""

from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ExplicitPrompters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["explicit"]
    uids: list[UUID] = Field(min_length=1, max_length=200)

    @field_validator("uids")
    @classmethod
    def unique(cls, value: list[UUID]) -> list[UUID]:
        if len(set(value)) != len(value):
            raise ValueError("Select each prompter only once")
        return value


class PrompterDeleteOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_versions: dict[UUID, Annotated[int, Field(strict=True, ge=1, le=9223372036854775807)]]


class PrompterDeleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    selection: ExplicitPrompters
    options: PrompterDeleteOptions

    @model_validator(mode="after")
    def versions_match_selection(self) -> Self:
        if set(self.options.expected_versions) != set(self.selection.uids):
            raise ValueError("Supply the displayed version of every selected prompter")
        return self
