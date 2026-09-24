"""SQLAlchemy MetaTable declaration for tag records."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from mainsequence.meta_tables import PlatformManagedMetaTable, schema_table_name

from .base import Base


class Tag(PlatformManagedMetaTable, Base):
    __tablename__ = schema_table_name("mainsequence_crm", "tag")
    __metatable_namespace__ = "mainsequence-crm"
    __metatable_identifier__ = "mainsequence_crm__tag"
    __metatable_description__ = "One reusable contact label."
    __metatable_labels__ = ["crm", "tag"]
    __table_args__ = (
        UniqueConstraint("normalized_name", name="uq_mainsequence_crm__tag_normalized_name"),
        CheckConstraint("length(trim(name)) > 0", name="ck_mainsequence_crm__tag_1"),
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

    name: Mapped[str] = mapped_column(
        String(100),
        primary_key=False,
        nullable=False,
        info={"label": "Name", "description": "name"},
    )

    normalized_name: Mapped[str] = mapped_column(
        String(100),
        primary_key=False,
        nullable=False,
        info={
            "label": "Normalized Name",
            "description": "NFKC + casefold + whitespace normalization for CRM-wide uniqueness.",
        },
    )

    tone: Mapped[str] = mapped_column(
        String(20),
        primary_key=False,
        nullable=False,
        info={
            "label": "Tone",
            "description": "neutral,info,success,warning,danger mapped to SDK tokens.",
        },
    )

    legacy_color: Mapped[str | None] = mapped_column(
        String(100),
        primary_key=False,
        nullable=True,
        info={
            "label": "Legacy Color",
            "description": "Preserved imported color; not injected as authored UI CSS.",
        },
    )
