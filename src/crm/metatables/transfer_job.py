"""SQLAlchemy MetaTable declaration for transfer_job records."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CHAR,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from mainsequence.meta_tables import PlatformManagedMetaTable, schema_table_name

from .base import Base


class TransferJob(PlatformManagedMetaTable, Base):
    __tablename__ = schema_table_name("mainsequence_crm", "transfer_job")
    __metatable_namespace__ = "mainsequence-crm"
    __metatable_identifier__ = "mainsequence_crm__transfer_job"
    __metatable_description__ = (
        "One durable import/export execution and its immutable accepted plan."
    )
    __metatable_labels__ = ["crm", "transfer-job"]
    __table_args__ = (
        ForeignKeyConstraint(
            ["source_connection_uid"],
            ["mainsequence_crm__source_connection.uid"],
            ondelete="RESTRICT",
            name="fk_mainsequence_crm__transfer_job_source_connecti",
        ),
        CheckConstraint(
            "direction IN ('import','export')", name="ck_mainsequence_crm__transfer_job_1"
        ),
        Index("ix_mainsequence_crm__transfer_job_1", "status", "created_at", "uid"),
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

    direction: Mapped[str] = mapped_column(
        String(10),
        primary_key=False,
        nullable=False,
        info={"label": "Direction", "description": "direction"},
    )

    adapter_id: Mapped[str] = mapped_column(
        String(100),
        primary_key=False,
        nullable=False,
        info={"label": "Adapter Id", "description": "adapter id"},
    )

    source_connection_uid: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(),
        primary_key=False,
        nullable=True,
        info={"label": "Source Connection Uid", "description": "source connection uid"},
    )

    initiator_uid: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        primary_key=False,
        nullable=False,
        info={"label": "Initiator Uid", "description": "initiator uid"},
    )

    status: Mapped[str] = mapped_column(
        String(30),
        primary_key=False,
        nullable=False,
        info={"label": "Status", "description": "status"},
    )

    input_manifest: Mapped[Any] = mapped_column(
        JSONB(),
        primary_key=False,
        nullable=False,
        info={"label": "Input Manifest", "description": "input manifest"},
    )

    mapping: Mapped[Any] = mapped_column(
        JSONB(),
        primary_key=False,
        nullable=False,
        info={"label": "Mapping", "description": "mapping"},
    )

    mapping_revision: Mapped[int] = mapped_column(
        Integer(),
        primary_key=False,
        nullable=False,
        info={"label": "Mapping Revision", "description": "mapping revision"},
    )

    plan_hash: Mapped[str | None] = mapped_column(
        CHAR(64),
        primary_key=False,
        nullable=True,
        info={"label": "Plan Hash", "description": "plan hash"},
    )

    validation_report: Mapped[Any] = mapped_column(
        JSONB(),
        primary_key=False,
        nullable=False,
        info={"label": "Validation Report", "description": "validation report"},
    )

    cancel_requested: Mapped[bool] = mapped_column(
        Boolean(),
        primary_key=False,
        nullable=False,
        info={"label": "Cancel Requested", "description": "cancel requested"},
    )

    lease_holder: Mapped[str | None] = mapped_column(
        String(255),
        primary_key=False,
        nullable=True,
        info={"label": "Lease Holder", "description": "lease holder"},
    )

    lease_epoch: Mapped[int] = mapped_column(
        BigInteger(),
        primary_key=False,
        nullable=False,
        info={"label": "Lease Epoch", "description": "lease epoch"},
    )

    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        primary_key=False,
        nullable=True,
        info={"label": "Lease Expires At", "description": "lease expires at"},
    )

    error_summary: Mapped[Any | None] = mapped_column(
        JSONB(),
        primary_key=False,
        nullable=True,
        info={"label": "Error Summary", "description": "error summary"},
    )

    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        primary_key=False,
        nullable=True,
        info={"label": "Expires At", "description": "expires at"},
    )

    output_manifest: Mapped[Any | None] = mapped_column(
        JSONB(),
        primary_key=False,
        nullable=True,
        info={"label": "Output Manifest", "description": "output manifest"},
    )
