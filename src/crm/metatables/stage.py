"""SQLAlchemy MetaTable declaration for stage records."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from mainsequence.meta_tables import PlatformManagedMetaTable, schema_table_name

from .base import Base


class Stage(PlatformManagedMetaTable, Base):
    __tablename__ = schema_table_name("mainsequence_crm", "stage")
    __metatable_namespace__ = "mainsequence-crm"
    __metatable_identifier__ = "mainsequence_crm__stage"
    __metatable_description__ = "One ordered stage in a CRM pipeline."
    __metatable_labels__ = ["crm", "stage"]
    __table_args__ = (
        UniqueConstraint("pipeline_uid", "key", name="uq_mainsequence_crm__stage_pipeline_uid_key"),
        UniqueConstraint("pipeline_uid", "uid", name="uq_mainsequence_crm__stage_pipeline_uid_uid"),
        ForeignKeyConstraint(
            ["pipeline_uid"],
            ["mainsequence_crm__pipeline.uid"],
            ondelete="RESTRICT",
            name="fk_mainsequence_crm__stage_pipeline_uid",
        ),
        CheckConstraint("outcome IN ('open','won','lost')", name="ck_mainsequence_crm__stage_1"),
        CheckConstraint("position >= 0", name="ck_mainsequence_crm__stage_2"),
        Index("ix_mainsequence_crm__stage_1", "pipeline_uid", "position", "uid"),
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

    pipeline_uid: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        primary_key=False,
        nullable=False,
        info={"label": "Pipeline Uid", "description": "pipeline uid"},
    )

    key: Mapped[str] = mapped_column(
        String(100),
        primary_key=False,
        nullable=False,
        info={
            "label": "Key",
            "description": "Stable machine key; label changes do not change identity.",
        },
    )

    label: Mapped[str] = mapped_column(
        String(255),
        primary_key=False,
        nullable=False,
        info={"label": "Label", "description": "label"},
    )

    position: Mapped[int] = mapped_column(
        Integer(),
        primary_key=False,
        nullable=False,
        info={"label": "Position", "description": "position"},
    )

    outcome: Mapped[str] = mapped_column(
        String(10),
        primary_key=False,
        nullable=False,
        info={"label": "Outcome", "description": "open, won or lost; delayed defaults to open."},
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean(),
        primary_key=False,
        nullable=False,
        info={"label": "Is Active", "description": "is active"},
    )
