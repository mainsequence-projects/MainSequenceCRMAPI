"""SQLAlchemy MetaTable declaration for transfer_row records."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CHAR,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from mainsequence.meta_tables import PlatformManagedMetaTable, schema_table_name

from .base import Base


class TransferRow(PlatformManagedMetaTable, Base):
    __tablename__ = schema_table_name("mainsequence_crm", "transfer_row")
    __metatable_namespace__ = "mainsequence-crm"
    __metatable_identifier__ = "mainsequence_crm__transfer_row"
    __metatable_description__ = "One staged input row or staged export row, with resumable outcome."
    __metatable_labels__ = ["crm", "transfer-row"]
    __table_args__ = (
        UniqueConstraint(
            "job_uid",
            "entity_type",
            "ordinal",
            name="uq_mainsequence_crm__transfer_row_job_uid_entity_",
        ),
        ForeignKeyConstraint(
            ["job_uid"],
            ["mainsequence_crm__transfer_job.uid"],
            ondelete="RESTRICT",
            name="fk_mainsequence_crm__transfer_row_job_uid",
        ),
        CheckConstraint("ordinal >= 0", name="ck_mainsequence_crm__transfer_row_1"),
        CheckConstraint(
            "state IN ('staged','valid','blocked','committed','skipped','failed')",
            name="ck_mainsequence_crm__transfer_row_2",
        ),
        Index("ix_mainsequence_crm__transfer_row_1", "job_uid", "state", "ordinal", "uid"),
    )

    uid: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        primary_key=True,
        nullable=False,
        info={"label": "Uid", "description": "uid"},
    )

    job_uid: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        primary_key=False,
        nullable=False,
        info={"label": "Job Uid", "description": "job uid"},
    )

    entity_type: Mapped[str] = mapped_column(
        String(30),
        primary_key=False,
        nullable=False,
        info={"label": "Entity Type", "description": "entity type"},
    )

    ordinal: Mapped[int] = mapped_column(
        BigInteger(),
        primary_key=False,
        nullable=False,
        info={"label": "Ordinal", "description": "ordinal"},
    )

    external_id: Mapped[str | None] = mapped_column(
        Text(),
        primary_key=False,
        nullable=True,
        info={"label": "External Id", "description": "external id"},
    )

    raw_payload: Mapped[Any] = mapped_column(
        JSONB(),
        primary_key=False,
        nullable=False,
        info={"label": "Raw Payload", "description": "raw payload"},
    )

    raw_hash: Mapped[str] = mapped_column(
        CHAR(64),
        primary_key=False,
        nullable=False,
        info={"label": "Raw Hash", "description": "raw hash"},
    )

    normalized_payload: Mapped[Any | None] = mapped_column(
        JSONB(),
        primary_key=False,
        nullable=True,
        info={"label": "Normalized Payload", "description": "normalized payload"},
    )

    normalized_hash: Mapped[str | None] = mapped_column(
        CHAR(64),
        primary_key=False,
        nullable=True,
        info={"label": "Normalized Hash", "description": "normalized hash"},
    )

    target_uid: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(),
        primary_key=False,
        nullable=True,
        info={"label": "Target Uid", "description": "target uid"},
    )

    state: Mapped[str] = mapped_column(
        String(20),
        primary_key=False,
        nullable=False,
        info={"label": "State", "description": "state"},
    )

    decision: Mapped[str | None] = mapped_column(
        String(20),
        primary_key=False,
        nullable=True,
        info={"label": "Decision", "description": "create,update,skip,conflict,blocked"},
    )

    errors: Mapped[Any] = mapped_column(
        JSONB(),
        primary_key=False,
        nullable=False,
        info={"label": "Errors", "description": "errors"},
    )

    warnings: Mapped[Any] = mapped_column(
        JSONB(),
        primary_key=False,
        nullable=False,
        info={"label": "Warnings", "description": "warnings"},
    )

    attempts: Mapped[int] = mapped_column(
        Integer(),
        primary_key=False,
        nullable=False,
        info={"label": "Attempts", "description": "attempts"},
    )

    committed_command_uid: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(),
        primary_key=False,
        nullable=True,
        info={"label": "Committed Command Uid", "description": "committed command uid"},
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        primary_key=False,
        nullable=False,
        info={"label": "Created At", "description": "created at"},
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        primary_key=False,
        nullable=False,
        info={"label": "Updated At", "description": "updated at"},
    )
