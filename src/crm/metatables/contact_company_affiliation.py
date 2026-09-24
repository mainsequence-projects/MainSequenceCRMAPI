"""Dated contact-company affiliation records."""

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
    String,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from mainsequence.meta_tables import PlatformManagedMetaTable, schema_table_name

from .base import Base


class ContactCompanyAffiliation(PlatformManagedMetaTable, Base):
    __tablename__ = schema_table_name("mainsequence_crm", "contact_company_affiliation")
    __metatable_namespace__ = "mainsequence-crm"
    __metatable_identifier__ = "mainsequence_crm__contact_company_affiliation"
    __metatable_description__ = (
        "One dated or undated period in which a tracked contact was affiliated "
        "with a company; multiple periods and concurrent current affiliations are allowed."
    )
    __metatable_labels__ = ["crm", "contact", "company", "affiliation"]
    __table_args__ = (
        ForeignKeyConstraint(
            ["contact_uid"],
            ["mainsequence_crm__contact.uid"],
            ondelete="RESTRICT",
            name="fk_mainsequence_crm__affiliation_contact",
        ),
        ForeignKeyConstraint(
            ["company_uid"],
            ["mainsequence_crm__company.uid"],
            ondelete="RESTRICT",
            name="fk_mainsequence_crm__affiliation_company",
        ),
        CheckConstraint("version > 0", name="ck_mainsequence_crm__affiliation_version"),
        CheckConstraint(
            "status IN ('current','former','unknown')",
            name="ck_mainsequence_crm__affiliation_status",
        ),
        CheckConstraint(
            "NOT is_primary OR (status='current' AND archived_at IS NULL)",
            name="ck_mainsequence_crm__affiliation_primary",
        ),
        CheckConstraint(
            "ended_period IS NULL OR status='former'",
            name="ck_mainsequence_crm__affiliation_end_status",
        ),
        CheckConstraint(
            "started_period IS NULL OR started_period ~ '^[0-9]{4}(-[0-9]{2}(-[0-9]{2})?)?$'",
            name="ck_mainsequence_crm__affiliation_start_shape",
        ),
        CheckConstraint(
            "ended_period IS NULL OR ended_period ~ '^[0-9]{4}(-[0-9]{2}(-[0-9]{2})?)?$'",
            name="ck_mainsequence_crm__affiliation_end_shape",
        ),
        Index(
            "ix_mainsequence_crm__affiliation_contact_timeline",
            "contact_uid",
            "started_period",
            "uid",
        ),
        Index(
            "ix_mainsequence_crm__affiliation_company_status",
            "company_uid",
            "status",
            "contact_uid",
        ),
        Index(
            "uq_mainsequence_crm__affiliation_primary_current",
            "contact_uid",
            unique=True,
            postgresql_where=text("is_primary AND archived_at IS NULL"),
        ),
    )

    uid: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        info={
            "label": "Affiliation UID",
            "description": "Stable identity of one contact-company period.",
        },
    )

    contact_uid: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        nullable=False,
        info={
            "label": "Contact UID",
            "description": "Person whose company history includes this period.",
        },
    )
    company_uid: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        nullable=False,
        info={
            "label": "Company UID",
            "description": "Organization associated with the contact during this period.",
        },
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        info={
            "label": "Created at",
            "description": "Time this relationship record was created in the CRM.",
        },
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        info={
            "label": "Updated at",
            "description": "Time this relationship record was last changed in the CRM.",
        },
    )
    created_by_uid: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        nullable=True,
        info={
            "label": "Created by",
            "description": "Existing platform principal that recorded this relationship.",
        },
    )
    updated_by_uid: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        nullable=True,
        info={
            "label": "Updated by",
            "description": "Existing platform principal that last changed this relationship.",
        },
    )
    version: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        info={"label": "Version", "description": "Optimistic version of this relationship period."},
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        info={
            "label": "Archived at",
            "description": "Correction/removal marker; not an employment end date.",
        },
    )
    status: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        info={
            "label": "Status",
            "description": "Current, former, or unknown affiliation status independent of date precision.",
        },
    )
    is_primary: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        info={
            "label": "Primary",
            "description": "Whether this current period supplies the contact's compatibility company projection.",
        },
    )
    started_period: Mapped[str | None] = mapped_column(
        String(10),
        nullable=True,
        info={
            "label": "Start period",
            "description": "Known employment start at year, month, or day precision; null means unknown.",
        },
    )
    ended_period: Mapped[str | None] = mapped_column(
        String(10),
        nullable=True,
        info={
            "label": "End period",
            "description": "Known employment end at year, month, or day precision; null does not imply current.",
        },
    )
    job_title: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        info={
            "label": "Job title",
            "description": "Role at this particular company during this period.",
        },
    )
