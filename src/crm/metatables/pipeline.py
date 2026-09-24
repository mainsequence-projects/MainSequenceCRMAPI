"""SQLAlchemy MetaTable declaration for pipeline records."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    String,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from mainsequence.meta_tables import PlatformManagedMetaTable, schema_table_name

from .base import Base


class Pipeline(PlatformManagedMetaTable, Base):
    __tablename__ = schema_table_name("mainsequence_crm", "pipeline")
    __metatable_namespace__ = "mainsequence-crm"
    __metatable_identifier__ = "mainsequence_crm__pipeline"
    __metatable_description__ = "One sales pipeline; v1 creates one default pipeline."
    __metatable_labels__ = ["crm", "pipeline"]
    __table_args__ = (
        CheckConstraint("board_version > 0", name="ck_mainsequence_crm__pipeline_1"),
        CheckConstraint("version > 0", name="ck_mainsequence_crm__pipeline_2"),
        Index(
            "ix_mainsequence_crm__pipeline_default",
            "is_default",
            unique=True,
            postgresql_where=text("is_default = true"),
        ),
    )

    uid: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        primary_key=True,
        nullable=False,
        info={
            "label": "Uid",
            "description": "Stable application record UUID; never an Atomic bigint.",
        },
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        primary_key=False,
        nullable=False,
        info={
            "label": "Created At",
            "description": "Creation time in this application; source dates are preserved separately where needed.",
        },
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        primary_key=False,
        nullable=False,
        info={"label": "Updated At", "description": "updated at"},
    )

    created_by_uid: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(),
        primary_key=False,
        nullable=True,
        info={
            "label": "Created By Uid",
            "description": "Existing platform user UID, nullable only for preserved historical/system origin.",
        },
    )

    updated_by_uid: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(),
        primary_key=False,
        nullable=True,
        info={"label": "Updated By Uid", "description": "updated by uid"},
    )

    version: Mapped[int] = mapped_column(
        BigInteger(),
        primary_key=False,
        nullable=False,
        info={
            "label": "Version",
            "description": "Optimistic entity version, positive and incremented by each successful edit.",
        },
    )

    name: Mapped[str] = mapped_column(
        String(255),
        primary_key=False,
        nullable=False,
        info={"label": "Name", "description": "name"},
    )

    is_default: Mapped[bool] = mapped_column(
        Boolean(),
        primary_key=False,
        nullable=False,
        info={"label": "Is Default", "description": "is default"},
    )

    board_version: Mapped[int] = mapped_column(
        BigInteger(),
        primary_key=False,
        nullable=False,
        info={"label": "Board Version", "description": "board version"},
    )
