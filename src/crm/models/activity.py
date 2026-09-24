"""Pydantic CRM activity models."""

from __future__ import annotations

from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
)


class ActivityOrigin(Enum):
    live = "live"
    import_ = "import"
    system = "system"


class Activity(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    uid: UUID
    entity_type: str
    entity_uid: UUID
    kind: str
    occurred_at: AwareDatetime
    recorded_at: AwareDatetime
    actor_uid: UUID | None
    origin: ActivityOrigin
    summary: str
    changes: dict[str, Any]
