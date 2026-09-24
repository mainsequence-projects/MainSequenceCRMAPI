"""Pydantic CRM bulk models."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    conint,
)


class BulkResult(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    command_uid: UUID
    affected_count: conint(strict=True, ge=0)
    affected_uids: list[UUID] = Field(..., max_length=200)
    status: Literal["completed"]
