"""SQLAlchemy MetaTable declaration for entity_redirect records."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from mainsequence.meta_tables import PlatformManagedMetaTable, schema_table_name

from .base import Base


class EntityRedirect(PlatformManagedMetaTable, Base):
    __tablename__ = schema_table_name("mainsequence_crm", "entity_redirect")
    __metatable_namespace__ = "mainsequence-crm"
    __metatable_identifier__ = "mainsequence_crm__entity_redirect"
    __metatable_description__ = (
        "One retired public identity pointing to a surviving entity after a merge."
    )
    __metatable_labels__ = ["crm", "entity-redirect"]
    __table_args__ = (
        UniqueConstraint(
            "entity_type", "from_uid", name="uq_mainsequence_crm__entity_redirect_entity_type_"
        ),
        CheckConstraint("from_uid <> to_uid", name="ck_mainsequence_crm__entity_redirect_1"),
        Index("ix_mainsequence_crm__entity_redirect_1", "entity_type", "to_uid"),
    )

    uid: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        primary_key=True,
        nullable=False,
        info={"label": "Uid", "description": "uid"},
    )

    entity_type: Mapped[str] = mapped_column(
        String(30),
        primary_key=False,
        nullable=False,
        info={"label": "Entity Type", "description": "entity type"},
    )

    from_uid: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        primary_key=False,
        nullable=False,
        info={"label": "From Uid", "description": "from uid"},
    )

    to_uid: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        primary_key=False,
        nullable=False,
        info={"label": "To Uid", "description": "to uid"},
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        primary_key=False,
        nullable=False,
        info={"label": "Created At", "description": "created at"},
    )

    command_uid: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        primary_key=False,
        nullable=False,
        info={"label": "Command Uid", "description": "command uid"},
    )
