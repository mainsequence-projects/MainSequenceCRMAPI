"""Pydantic CRM errors models."""

from __future__ import annotations

from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    constr,
)


class ErrorField(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    path: str
    code: str
    message: str


class ErrorDetail(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    code: constr(min_length=1)
    message: str
    request_uid: UUID
    fields: list[ErrorField] | None = None


class Error(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    error: ErrorDetail
