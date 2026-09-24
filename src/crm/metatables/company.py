"""SQLAlchemy MetaTable declaration for company records."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Index,
    SmallInteger,
    String,
    Text,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from mainsequence.meta_tables import PlatformManagedMetaTable, schema_table_name

from .base import Base


class Company(PlatformManagedMetaTable, Base):
    __tablename__ = schema_table_name("mainsequence_crm", "company")
    __metatable_namespace__ = "mainsequence-crm"
    __metatable_identifier__ = "mainsequence_crm__company"
    __metatable_description__ = "One organization being tracked."
    __metatable_labels__ = ["crm", "company"]
    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="ck_mainsequence_crm__company_1"),
        CheckConstraint(
            "size_category IS NULL OR size_category IN (1,10,50,250,500)",
            name="ck_mainsequence_crm__company_2",
        ),
        Index("ix_mainsequence_crm__company_1", "archived_at", "name", "uid"),
        Index("ix_mainsequence_crm__company_2", "owner_uid"),
        Index("ix_mainsequence_crm__company_3", "normalized_domain"),
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

    name: Mapped[str] = mapped_column(
        String(255),
        primary_key=False,
        nullable=False,
        info={"label": "Name", "description": "name"},
    )

    sector_key: Mapped[str | None] = mapped_column(
        String(100),
        primary_key=False,
        nullable=True,
        info={"label": "Sector Key", "description": "sector key"},
    )

    size_category: Mapped[int | None] = mapped_column(
        SmallInteger(),
        primary_key=False,
        nullable=True,
        info={"label": "Size Category", "description": "size category"},
    )

    linkedin_url: Mapped[str | None] = mapped_column(
        Text(),
        primary_key=False,
        nullable=True,
        info={"label": "Linkedin Url", "description": "linkedin url"},
    )

    website: Mapped[str | None] = mapped_column(
        Text(),
        primary_key=False,
        nullable=True,
        info={"label": "Website", "description": "website"},
    )

    normalized_domain: Mapped[str | None] = mapped_column(
        String(255),
        primary_key=False,
        nullable=True,
        info={
            "label": "Normalized Domain",
            "description": "Search/duplicate candidate only; never a unique identity.",
        },
    )

    phone_number: Mapped[str | None] = mapped_column(
        String(100),
        primary_key=False,
        nullable=True,
        info={"label": "Phone Number", "description": "phone number"},
    )

    address: Mapped[str | None] = mapped_column(
        Text(),
        primary_key=False,
        nullable=True,
        info={"label": "Address", "description": "address"},
    )

    zipcode: Mapped[str | None] = mapped_column(
        String(40),
        primary_key=False,
        nullable=True,
        info={"label": "Zipcode", "description": "zipcode"},
    )

    city: Mapped[str | None] = mapped_column(
        String(255),
        primary_key=False,
        nullable=True,
        info={"label": "City", "description": "city"},
    )

    state_abbr: Mapped[str | None] = mapped_column(
        String(100),
        primary_key=False,
        nullable=True,
        info={"label": "State Abbr", "description": "state abbr"},
    )

    country: Mapped[str | None] = mapped_column(
        String(255),
        primary_key=False,
        nullable=True,
        info={"label": "Country", "description": "country"},
    )

    description: Mapped[str | None] = mapped_column(
        Text(),
        primary_key=False,
        nullable=True,
        info={"label": "Description", "description": "description"},
    )

    revenue_text: Mapped[str | None] = mapped_column(
        Text(),
        primary_key=False,
        nullable=True,
        info={"label": "Revenue Text", "description": "revenue text"},
    )

    tax_identifier: Mapped[str | None] = mapped_column(
        String(255),
        primary_key=False,
        nullable=True,
        info={"label": "Tax Identifier", "description": "tax identifier"},
    )

    context_links: Mapped[Any] = mapped_column(
        JSONB(),
        primary_key=False,
        nullable=False,
        info={"label": "Context Links", "description": "context links"},
    )

    logo_ref: Mapped[Any | None] = mapped_column(
        JSONB(),
        primary_key=False,
        nullable=True,
        info={"label": "Logo Ref", "description": "logo ref"},
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
