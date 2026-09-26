"""SQLAlchemy MetaTable declaration for activity_event records."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from mainsequence.meta_tables import PlatformManagedMetaTable, schema_table_name

from .base import Base


class ActivityEvent(PlatformManagedMetaTable, Base):
    __tablename__ = schema_table_name("mainsequence_crm", "activity_event")
    __metatable_namespace__ = "mainsequence-crm"
    __metatable_identifier__ = "mainsequence_crm__activity_event"
    __metatable_description__ = (
        "One immutable successful domain mutation or imported-history observation."
    )
    __metatable_labels__ = ["crm", "activity-event"]
    __table_args__ = (
        UniqueConstraint(
            "command_uid",
            "entity_type",
            "entity_uid",
            "kind",
            name="uq_mainsequence_crm__activity_event_command_uid_e",
        ),
        CheckConstraint(
            "origin IN ('live','import','system')", name="ck_mainsequence_crm__activity_event_1"
        ),
        Index("ix_mainsequence_crm__activity_event_1", "occurred_at", "uid"),
        Index(
            "ix_mainsequence_crm__activity_event_2",
            "entity_type",
            "entity_uid",
            "occurred_at",
            "uid",
        ),
    )

    uid: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        primary_key=True,
        nullable=False,
        info={"label": "Uid", "description": "uid"},
    )

    entity_type: Mapped[str] = mapped_column(
        String(100),
        primary_key=False,
        nullable=False,
        info={"label": "Entity Type", "description": "entity type"},
    )

    entity_uid: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        primary_key=False,
        nullable=False,
        info={
            "label": "Entity Uid",
            "description": "No FK: original entity identity survives merge/archive.",
        },
    )

    kind: Mapped[str] = mapped_column(
        String(100),
        primary_key=False,
        nullable=False,
        info={"label": "Kind", "description": "kind"},
    )

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        primary_key=False,
        nullable=False,
        info={"label": "Occurred At", "description": "occurred at"},
    )

    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        primary_key=False,
        nullable=False,
        info={"label": "Recorded At", "description": "recorded at"},
    )

    actor_uid: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(),
        primary_key=False,
        nullable=True,
        info={"label": "Actor Uid", "description": "actor uid"},
    )

    origin: Mapped[str] = mapped_column(
        String(20),
        primary_key=False,
        nullable=False,
        info={
            "label": "Origin",
            "description": "live,import,system; never fabricate historical editing activity.",
        },
    )

    command_uid: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        primary_key=False,
        nullable=False,
        info={"label": "Command Uid", "description": "command uid"},
    )

    summary: Mapped[str] = mapped_column(
        Text(),
        primary_key=False,
        nullable=False,
        info={"label": "Summary", "description": "summary"},
    )

    changes: Mapped[Any] = mapped_column(
        JSONB(),
        primary_key=False,
        nullable=False,
        info={
            "label": "Changes",
            "description": "Allowlisted before/after values subject to configured retention; no credentials.",
        },
    )

    source_attribution: Mapped[Any | None] = mapped_column(
        JSONB(),
        primary_key=False,
        nullable=True,
        info={"label": "Source Attribution", "description": "source attribution"},
    )
