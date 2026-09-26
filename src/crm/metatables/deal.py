"""SQLAlchemy MetaTable declaration for deal records."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CHAR,
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from mainsequence.meta_tables import PlatformManagedMetaTable, schema_table_name

from .base import Base


class Deal(PlatformManagedMetaTable, Base):
    __tablename__ = schema_table_name("mainsequence_crm", "deal")
    __metatable_namespace__ = "mainsequence-crm"
    __metatable_identifier__ = "mainsequence_crm__deal"
    __metatable_description__ = "One sales opportunity in one pipeline stage."
    __metatable_labels__ = ["crm", "deal"]
    __table_args__ = (
        UniqueConstraint("uid", "company_uid", name="uq_mainsequence_crm__deal_uid_company_uid"),
        ForeignKeyConstraint(
            ["company_uid"],
            ["mainsequence_crm__company.uid"],
            ondelete="RESTRICT",
            name="fk_mainsequence_crm__deal_company_uid",
        ),
        ForeignKeyConstraint(
            ["pipeline_uid"],
            ["mainsequence_crm__pipeline.uid"],
            ondelete="RESTRICT",
            name="fk_mainsequence_crm__deal_pipeline_uid",
        ),
        ForeignKeyConstraint(
            ["pipeline_uid", "stage_uid"],
            ["mainsequence_crm__stage.pipeline_uid", "mainsequence_crm__stage.uid"],
            ondelete="RESTRICT",
            name="fk_mainsequence_crm__deal_pipeline_uid_stage_uid",
        ),
        CheckConstraint("length(trim(name)) > 0", name="ck_mainsequence_crm__deal_1"),
        CheckConstraint("amount IS NULL OR amount >= 0", name="ck_mainsequence_crm__deal_2"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="ck_mainsequence_crm__deal_3"),
        CheckConstraint("position >= 0", name="ck_mainsequence_crm__deal_4"),
        Index(
            "ix_mainsequence_crm__deal_1",
            "pipeline_uid",
            "stage_uid",
            "archived_at",
            "position",
            "uid",
        ),
        Index("ix_mainsequence_crm__deal_2", "company_uid"),
        Index("ix_mainsequence_crm__deal_3", "owner_uid", "expected_closing_date"),
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

    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        primary_key=False,
        nullable=True,
        info={"label": "Archived At", "description": "Archive marker, not a hard-delete request."},
    )

    owner_uid: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(),
        primary_key=False,
        nullable=True,
        info={"label": "Owner Uid", "description": "owner uid"},
    )

    company_uid: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(),
        primary_key=False,
        nullable=True,
        info={"label": "Company Uid", "description": "company uid"},
    )

    pipeline_uid: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        primary_key=False,
        nullable=False,
        info={"label": "Pipeline Uid", "description": "pipeline uid"},
    )

    stage_uid: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        primary_key=False,
        nullable=False,
        info={"label": "Stage Uid", "description": "stage uid"},
    )

    name: Mapped[str] = mapped_column(
        String(255),
        primary_key=False,
        nullable=False,
        info={"label": "Name", "description": "name"},
    )

    category_key: Mapped[str | None] = mapped_column(
        String(100),
        primary_key=False,
        nullable=True,
        info={"label": "Category Key", "description": "category key"},
    )

    description: Mapped[str | None] = mapped_column(
        Text(),
        primary_key=False,
        nullable=True,
        info={"label": "Description", "description": "description"},
    )

    amount: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 4),
        primary_key=False,
        nullable=True,
        info={
            "label": "Amount",
            "description": "Exact decimal; API uses string. Never parse via float or silently round.",
        },
    )

    currency: Mapped[str] = mapped_column(
        CHAR(3),
        primary_key=False,
        nullable=False,
        info={
            "label": "Currency",
            "description": "Source configured currency or an explicit operator selection.",
        },
    )

    expected_closing_date: Mapped[date | None] = mapped_column(
        Date(),
        primary_key=False,
        nullable=True,
        info={"label": "Expected Closing Date", "description": "expected closing date"},
    )

    position: Mapped[int] = mapped_column(
        BigInteger(),
        primary_key=False,
        nullable=False,
        info={"label": "Position", "description": "position"},
    )

    source_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        primary_key=False,
        nullable=True,
        info={"label": "Source Created At", "description": "source created at"},
    )

    source_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        primary_key=False,
        nullable=True,
        info={"label": "Source Updated At", "description": "source updated at"},
    )
