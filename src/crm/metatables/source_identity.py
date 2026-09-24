"""SQLAlchemy MetaTable declaration for source_identity records."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CHAR,
    BigInteger,
    DateTime,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from mainsequence.meta_tables import PlatformManagedMetaTable, schema_table_name

from .base import Base


class SourceIdentity(PlatformManagedMetaTable, Base):
    __tablename__ = schema_table_name("mainsequence_crm", "source_identity")
    __metatable_namespace__ = "mainsequence-crm"
    __metatable_identifier__ = "mainsequence_crm__source_identity"
    __metatable_description__ = "One permanent source key mapped to one current target record."
    __metatable_labels__ = ["crm", "source-identity"]
    __table_args__ = (
        UniqueConstraint(
            "source_connection_uid",
            "entity_type",
            "external_id",
            name="uq_mainsequence_crm__source_identity_source_conne",
        ),
        ForeignKeyConstraint(
            ["source_connection_uid"],
            ["mainsequence_crm__source_connection.uid"],
            ondelete="RESTRICT",
            name="fk_mainsequence_crm__source_identity_source_conne",
        ),
        Index("ix_mainsequence_crm__source_identity_1", "entity_type", "target_uid"),
    )

    uid: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        primary_key=True,
        nullable=False,
        info={"label": "Uid", "description": "uid"},
    )

    source_connection_uid: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        primary_key=False,
        nullable=False,
        info={"label": "Source Connection Uid", "description": "source connection uid"},
    )

    entity_type: Mapped[str] = mapped_column(
        String(30),
        primary_key=False,
        nullable=False,
        info={"label": "Entity Type", "description": "entity type"},
    )

    external_id: Mapped[str] = mapped_column(
        Text(),
        primary_key=False,
        nullable=False,
        info={
            "label": "External Id",
            "description": "Opaque original ID string; source account/type disambiguate it.",
        },
    )

    target_uid: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        primary_key=False,
        nullable=False,
        info={
            "label": "Target Uid",
            "description": "Polymorphic target validated by service; merge redirects it.",
        },
    )

    source_payload_hash: Mapped[str] = mapped_column(
        CHAR(64),
        primary_key=False,
        nullable=False,
        info={"label": "Source Payload Hash", "description": "source payload hash"},
    )

    source_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        primary_key=False,
        nullable=True,
        info={"label": "Source Updated At", "description": "source updated at"},
    )

    last_imported_target_version: Mapped[int | None] = mapped_column(
        BigInteger(),
        primary_key=False,
        nullable=True,
        info={
            "label": "Last Imported Target Version",
            "description": "last imported target version",
        },
    )

    last_import_job_uid: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        primary_key=False,
        nullable=False,
        info={"label": "Last Import Job Uid", "description": "last import job uid"},
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
