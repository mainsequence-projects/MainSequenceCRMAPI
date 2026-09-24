"""SQLAlchemy MetaTable declaration for source_connection records."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from mainsequence.meta_tables import PlatformManagedMetaTable, schema_table_name

from .base import Base


class SourceConnection(PlatformManagedMetaTable, Base):
    __tablename__ = schema_table_name("mainsequence_crm", "source_connection")
    __metatable_namespace__ = "mainsequence-crm"
    __metatable_identifier__ = "mainsequence_crm__source_connection"
    __metatable_description__ = (
        "One named external CRM/source-account identity, not OAuth credentials."
    )
    __metatable_labels__ = ["crm", "source-connection"]
    __table_args__ = (
        UniqueConstraint(
            "adapter_id",
            "source_account_key",
            name="uq_mainsequence_crm__source_connection_adapter_id",
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

    adapter_id: Mapped[str] = mapped_column(
        String(100),
        primary_key=False,
        nullable=False,
        info={"label": "Adapter Id", "description": "adapter id"},
    )

    source_account_key: Mapped[str] = mapped_column(
        String(255),
        primary_key=False,
        nullable=False,
        info={"label": "Source Account Key", "description": "source account key"},
    )

    configuration: Mapped[Any] = mapped_column(
        JSONB(),
        primary_key=False,
        nullable=False,
        info={"label": "Configuration", "description": "Nonsecret mapping defaults only."},
    )
