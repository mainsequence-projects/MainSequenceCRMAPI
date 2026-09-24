"""Closed Pydantic schemas for HTTP URL parameters only."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DiscoveryQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    search: str | None = None
    filters: str = "{}"

    @field_validator("search")
    @classmethod
    def normalize_search(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if len(value) > 200:
            raise ValueError("Search exceeds 200 characters")
        return value or None


class CollectionQuery(DiscoveryQuery):
    ordering: str | None = None
    page_index: int = Field(default=0, ge=0)
    page_size: int = Field(default=25, ge=1, le=100)


class PageQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_index: int = Field(default=0, ge=0)
    page_size: int = Field(default=25, ge=1, le=100)


class BoardQuery(DiscoveryQuery):
    page_size: int = Field(default=25, ge=1, le=100)


class StageCardsQuery(BoardQuery):
    expected_board_version: int = Field(ge=0)
    cursor: int = Field(default=0, ge=0)
