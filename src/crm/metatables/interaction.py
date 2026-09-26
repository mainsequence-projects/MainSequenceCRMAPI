"""Core CRM Interaction MetaTable, independent of sales methodology."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKeyConstraint, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from mainsequence.meta_tables import PlatformManagedMetaTable, schema_table_name

from .base import Base, VersionedRecord
from .base import column_info as _info


class Interaction(VersionedRecord, PlatformManagedMetaTable, Base):
    __tablename__ = schema_table_name("mainsequence_crm", "interaction")
    __metatable_namespace__ = "mainsequence-crm"
    __metatable_identifier__ = "mainsequence_crm__interaction"
    __metatable_description__ = (
        "A planned or completed CRM conversation, independent of methodology."
    )
    __metatable_labels__ = ["crm", "interaction"]
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_uid"], ["mainsequence_crm__company.uid"], ondelete="RESTRICT"
        ),
        ForeignKeyConstraint(
            ["contact_uid"], ["mainsequence_crm__contact.uid"], ondelete="RESTRICT"
        ),
        ForeignKeyConstraint(
            ["deal_uid", "company_uid"],
            ["mainsequence_crm__deal.uid", "mainsequence_crm__deal.company_uid"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("version > 0"),
        CheckConstraint("length(trim(subject)) > 0"),
        CheckConstraint("kind IN ('call','meeting','workshop','email')"),
        CheckConstraint("status IN ('planned','completed','cancelled')"),
        Index("ix_mainsequence_crm__interaction_company", "company_uid", "scheduled_at"),
        Index("ix_mainsequence_crm__interaction_deal", "deal_uid"),
        Index("ix_mainsequence_crm__interaction_contact", "contact_uid"),
    )

    company_uid: Mapped[uuid.UUID] = mapped_column(
        Uuid(), nullable=False, info=_info("Company", "Customer Company FK.")
    )
    contact_uid: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(), info=_info("Primary contact", "Optional Contact FK.")
    )
    deal_uid: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(), info=_info("Deal", "Optional Deal FK; must belong to Company.")
    )
    subject: Mapped[str] = mapped_column(
        String(255), nullable=False, info=_info("Subject", "Conversation subject.")
    )
    kind: Mapped[str] = mapped_column(
        String(20), nullable=False, info=_info("Kind", "Call, meeting, workshop or email.")
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, info=_info("Status", "Planned, completed or cancelled.")
    )
    scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), info=_info("Scheduled at", "Planned instant.")
    )
    occurred_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), info=_info("Occurred at", "Actual instant.")
    )
    objective: Mapped[str | None] = mapped_column(
        Text(), info=_info("Objective", "Intended outcome.")
    )
    research_notes: Mapped[str | None] = mapped_column(
        Text(), info=_info("Research notes", "Known context and assumptions.")
    )
    discussion_plan: Mapped[str | None] = mapped_column(
        Text(), info=_info("Discussion plan", "Topics and planned questions.")
    )
    outcome_notes: Mapped[str | None] = mapped_column(
        Text(), info=_info("Outcome notes", "What was learned.")
    )
    next_steps: Mapped[str | None] = mapped_column(
        Text(), info=_info("Next steps", "Agreed follow-up.")
    )
