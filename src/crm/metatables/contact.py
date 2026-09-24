"""SQLAlchemy MetaTable declaration for contact records."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from mainsequence.meta_tables import PlatformManagedMetaTable, schema_table_name

from .base import Base


class Contact(PlatformManagedMetaTable, Base):
    __tablename__ = schema_table_name("mainsequence_crm", "contact")
    __metatable_namespace__ = "mainsequence-crm"
    __metatable_identifier__ = "mainsequence_crm__contact"
    __metatable_description__ = "One tracked person, with typed email/phone arrays."
    __metatable_labels__ = ["crm", "contact"]
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_uid"],
            ["mainsequence_crm__company.uid"],
            ondelete="RESTRICT",
            name="fk_mainsequence_crm__contact_company_uid",
        ),
        CheckConstraint("version > 0", name="ck_mainsequence_crm__contact_1"),
        CheckConstraint("jsonb_typeof(emails) = 'array'", name="ck_mainsequence_crm__contact_2"),
        CheckConstraint("jsonb_typeof(phones) = 'array'", name="ck_mainsequence_crm__contact_3"),
        CheckConstraint(
            "jsonb_typeof(socials) = 'object'", name="ck_mainsequence_crm__contact_socials"
        ),
        CheckConstraint(
            "nullif(trim(coalesce(first_name,'')), '') IS NOT NULL OR nullif(trim(coalesce(last_name,'')), '') IS NOT NULL OR jsonb_array_length(emails) > 0",
            name="ck_mainsequence_crm__contact_4",
        ),
        Index("ix_mainsequence_crm__contact_1", "archived_at", "last_seen", "uid"),
        Index("ix_mainsequence_crm__contact_2", "company_uid"),
        Index("ix_mainsequence_crm__contact_3", "owner_uid"),
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

    first_name: Mapped[str | None] = mapped_column(
        String(255),
        primary_key=False,
        nullable=True,
        info={"label": "First Name", "description": "first name"},
    )

    last_name: Mapped[str | None] = mapped_column(
        String(255),
        primary_key=False,
        nullable=True,
        info={"label": "Last Name", "description": "last name"},
    )

    title: Mapped[str | None] = mapped_column(
        String(255),
        primary_key=False,
        nullable=True,
        info={"label": "Title", "description": "title"},
    )

    gender: Mapped[str | None] = mapped_column(
        String(100),
        primary_key=False,
        nullable=True,
        info={"label": "Gender", "description": "gender"},
    )

    background: Mapped[str | None] = mapped_column(
        Text(),
        primary_key=False,
        nullable=True,
        info={"label": "Background", "description": "background"},
    )

    avatar_ref: Mapped[Any | None] = mapped_column(
        JSONB(),
        primary_key=False,
        nullable=True,
        info={"label": "Avatar Ref", "description": "avatar ref"},
    )

    socials: Mapped[Any] = mapped_column(
        JSONB(),
        primary_key=False,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        info={
            "label": "Social profiles",
            "description": "Validated platform-keyed social profile URLs for this contact; absent keys have no profile.",
        },
    )

    emails: Mapped[Any] = mapped_column(
        JSONB(),
        primary_key=False,
        nullable=False,
        info={"label": "Emails", "description": "emails"},
    )

    phones: Mapped[Any] = mapped_column(
        JSONB(),
        primary_key=False,
        nullable=False,
        info={"label": "Phones", "description": "phones"},
    )

    first_seen: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        primary_key=False,
        nullable=True,
        info={"label": "First Seen", "description": "first seen"},
    )

    last_seen: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        primary_key=False,
        nullable=True,
        info={"label": "Last Seen", "description": "last seen"},
    )

    has_newsletter: Mapped[bool | None] = mapped_column(
        Boolean(),
        primary_key=False,
        nullable=True,
        info={
            "label": "Has Newsletter",
            "description": "Preserved source flag, not proof of consent or permission to send mail.",
        },
    )

    status_key: Mapped[str | None] = mapped_column(
        String(100),
        primary_key=False,
        nullable=True,
        info={"label": "Status Key", "description": "status key"},
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
