"""SQLAlchemy MetaTable declaration for note records."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from mainsequence.meta_tables import PlatformManagedMetaTable, schema_table_name

from .base import Base


class Note(PlatformManagedMetaTable, Base):
    __tablename__ = schema_table_name("mainsequence_crm", "note")
    __metatable_namespace__ = "mainsequence-crm"
    __metatable_identifier__ = "mainsequence_crm__note"
    __metatable_description__ = "One note attached to exactly one contact or deal."
    __metatable_labels__ = ["crm", "note"]
    __table_args__ = (
        ForeignKeyConstraint(
            ["contact_uid"],
            ["mainsequence_crm__contact.uid"],
            ondelete="RESTRICT",
            name="fk_mainsequence_crm__note_contact_uid",
        ),
        ForeignKeyConstraint(
            ["deal_uid"],
            ["mainsequence_crm__deal.uid"],
            ondelete="RESTRICT",
            name="fk_mainsequence_crm__note_deal_uid",
        ),
        CheckConstraint(
            "(contact_uid IS NULL) <> (deal_uid IS NULL)", name="ck_mainsequence_crm__note_1"
        ),
        CheckConstraint("length(trim(text)) > 0", name="ck_mainsequence_crm__note_2"),
        CheckConstraint(
            "jsonb_typeof(attachment_refs) = 'array'", name="ck_mainsequence_crm__note_3"
        ),
        Index("ix_mainsequence_crm__note_1", "contact_uid", "occurred_at", "uid"),
        Index("ix_mainsequence_crm__note_2", "deal_uid", "occurred_at", "uid"),
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

    contact_uid: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(),
        primary_key=False,
        nullable=True,
        info={"label": "Contact Uid", "description": "contact uid"},
    )

    deal_uid: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(),
        primary_key=False,
        nullable=True,
        info={"label": "Deal Uid", "description": "deal uid"},
    )

    author_uid: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(),
        primary_key=False,
        nullable=True,
        info={"label": "Author Uid", "description": "author uid"},
    )

    source_author_label: Mapped[str | None] = mapped_column(
        String(255),
        primary_key=False,
        nullable=True,
        info={
            "label": "Source Author Label",
            "description": "Historic unresolved attribution, rendered as imported source attribution.",
        },
    )

    text: Mapped[str] = mapped_column(
        Text(),
        primary_key=False,
        nullable=False,
        info={"label": "Text", "description": "text"},
    )

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        primary_key=False,
        nullable=False,
        info={"label": "Occurred At", "description": "occurred at"},
    )

    status_key: Mapped[str | None] = mapped_column(
        String(100),
        primary_key=False,
        nullable=True,
        info={"label": "Status Key", "description": "status key"},
    )

    legacy_type: Mapped[str | None] = mapped_column(
        String(100),
        primary_key=False,
        nullable=True,
        info={"label": "Legacy Type", "description": "legacy type"},
    )

    attachment_refs: Mapped[Any] = mapped_column(
        JSONB(),
        primary_key=False,
        nullable=False,
        info={"label": "Attachment Refs", "description": "attachment refs"},
    )
