"""SQLAlchemy-authored MetaTables for the optional Solution Selling module."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from mainsequence.meta_tables import PlatformManagedMetaTable, schema_table_name

from .base import Base, VersionedRecord
from .base import column_info as _info


class SolutionSelling(VersionedRecord, PlatformManagedMetaTable, Base):
    __tablename__ = schema_table_name("mainsequence_crm", "solution_selling")
    __metatable_namespace__ = "mainsequence-crm"
    __metatable_identifier__ = "mainsequence_crm__solution_selling"
    __metatable_description__ = "Maintained Solution Selling assessment of one Deal."
    __metatable_labels__ = ["crm", "solution-selling"]
    __table_args__ = (
        ForeignKeyConstraint(
            ["deal_uid", "company_uid"],
            ["mainsequence_crm__deal.uid", "mainsequence_crm__deal.company_uid"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_uid"], ["mainsequence_crm__company.uid"], ondelete="RESTRICT"
        ),
        ForeignKeyConstraint(
            ["pain_contact_uid"], ["mainsequence_crm__contact.uid"], ondelete="RESTRICT"
        ),
        ForeignKeyConstraint(
            ["power_contact_uid"], ["mainsequence_crm__contact.uid"], ondelete="RESTRICT"
        ),
        ForeignKeyConstraint(
            ["sponsor_contact_uid"], ["mainsequence_crm__contact.uid"], ondelete="RESTRICT"
        ),
        UniqueConstraint("deal_uid"),
        CheckConstraint("version > 0"),
        CheckConstraint("jsonb_typeof(key_players) = 'array'"),
        CheckConstraint("jsonb_typeof(pain_chain) = 'array'"),
        Index("ix_mainsequence_crm__solution_selling_company", "company_uid"),
    )

    deal_uid: Mapped[uuid.UUID] = mapped_column(
        Uuid(), nullable=False, info=_info("Deal", "One-to-one Deal FK.")
    )
    company_uid: Mapped[uuid.UUID] = mapped_column(
        Uuid(), nullable=False, info=_info("Company", "Direct customer Company FK matching Deal.")
    )
    pain_summary: Mapped[str | None] = mapped_column(
        Text(), info=_info("Pain summary", "Current problem understanding.")
    )
    pain_contact_uid: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(), info=_info("Pain contact", "Main affected Contact FK.")
    )
    power_summary: Mapped[str | None] = mapped_column(
        Text(), info=_info("Power summary", "Purchasing authority understanding.")
    )
    power_contact_uid: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(), info=_info("Power contact", "Principal authority Contact FK.")
    )
    sponsor_contact_uid: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(), info=_info("Sponsor contact", "Principal sponsor Contact FK.")
    )
    vision_summary: Mapped[str | None] = mapped_column(
        Text(), info=_info("Vision summary", "Buyer-desired capabilities.")
    )
    value_summary: Mapped[str | None] = mapped_column(
        Text(), info=_info("Value summary", "Expected business improvement.")
    )
    control_summary: Mapped[str | None] = mapped_column(
        Text(), info=_info("Control summary", "Decision process and commitments.")
    )
    key_players: Mapped[Any] = mapped_column(
        JSONB(),
        nullable=False,
        server_default=text("'[]'::jsonb"),
        info=_info("Key players", "Typed embedded Contact pain statements."),
    )
    pain_chain: Mapped[Any] = mapped_column(
        JSONB(),
        nullable=False,
        server_default=text("'[]'::jsonb"),
        info=_info("Pain chain", "Typed embedded directed links between key players."),
    )
    evaluation_plan: Mapped[str | None] = mapped_column(
        Text(), info=_info("Evaluation plan", "Evaluation, criteria and commitments.")
    )


class SolutionSellingProspectingProfile(VersionedRecord, PlatformManagedMetaTable, Base):
    __tablename__ = schema_table_name("mainsequence_crm", "solution_selling_prospecting_profile")
    __metatable_namespace__ = "mainsequence-crm"
    __metatable_identifier__ = "mainsequence_crm__solution_selling_prospecting_profile"
    __metatable_description__ = "Reusable role and potential-pain hypothesis, not a Contact."
    __metatable_labels__ = ["crm", "solution-selling", "prospecting"]
    __table_args__ = (
        CheckConstraint("version > 0"),
        CheckConstraint("length(trim(name)) > 0"),
        CheckConstraint("jsonb_typeof(likely_reasons) = 'array'"),
        CheckConstraint("jsonb_typeof(likely_impacts) = 'array'"),
        CheckConstraint(
            "diagnosis_template IS NULL OR jsonb_typeof(diagnosis_template) = 'object'"
        ),
        Index("ix_mainsequence_crm__ss_profile_context", "market_context", "role"),
    )

    name: Mapped[str] = mapped_column(
        String(255), nullable=False, info=_info("Name", "Profile name.")
    )
    market_context: Mapped[str] = mapped_column(
        String(255), nullable=False, info=_info("Market context", "Reusable market context.")
    )
    role: Mapped[str] = mapped_column(
        String(255), nullable=False, info=_info("Role", "Target role.")
    )
    potential_pain: Mapped[str] = mapped_column(
        Text(),
        nullable=False,
        info=_info("Potential pain", "Unverified role-based pain hypothesis."),
    )
    likely_reasons: Mapped[Any] = mapped_column(
        JSONB(),
        nullable=False,
        server_default=text("'[]'::jsonb"),
        info=_info("Likely reasons", "Typed list of hypothesized reasons."),
    )
    likely_impacts: Mapped[Any] = mapped_column(
        JSONB(),
        nullable=False,
        server_default=text("'[]'::jsonb"),
        info=_info("Likely impacts", "Typed list of hypothesized impacts."),
    )
    research_guidance: Mapped[str | None] = mapped_column(
        Text(), info=_info("Research guidance", "How to prepare.")
    )
    opening_message: Mapped[str | None] = mapped_column(
        Text(), info=_info("Opening message", "Suggested opening.")
    )
    suggested_next_commitment: Mapped[str | None] = mapped_column(
        Text(), info=_info("Next commitment", "Suggested next commitment.")
    )
    diagnosis_template: Mapped[Any | None] = mapped_column(
        JSONB(), info=_info("Diagnosis template", "Unanswered nine-cell question matrix.")
    )


class SolutionSellingLead(VersionedRecord, PlatformManagedMetaTable, Base):
    __tablename__ = schema_table_name("mainsequence_crm", "solution_selling_lead")
    __metatable_namespace__ = "mainsequence-crm"
    __metatable_identifier__ = "mainsequence_crm__solution_selling_lead"
    __metatable_description__ = "Prospecting effort for an existing Contact."
    __metatable_labels__ = ["crm", "solution-selling", "lead"]
    __table_args__ = (
        ForeignKeyConstraint(
            ["contact_uid"], ["mainsequence_crm__contact.uid"], ondelete="RESTRICT"
        ),
        ForeignKeyConstraint(
            ["profile_uid"],
            ["mainsequence_crm__solution_selling_prospecting_profile.uid"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["next_task_uid"], ["mainsequence_crm__task.uid"], ondelete="RESTRICT"
        ),
        UniqueConstraint("contact_uid"),
        CheckConstraint("version > 0"),
        CheckConstraint(
            "status IN ('to_contact','contacted','qualified','nurture','disqualified')"
        ),
        Index("ix_mainsequence_crm__ss_lead_status", "status", "owner_uid"),
    )

    contact_uid: Mapped[uuid.UUID] = mapped_column(
        Uuid(), nullable=False, info=_info("Contact", "Existing Contact being pursued.")
    )
    profile_uid: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(), info=_info("Profile", "Optional prospecting hypothesis FK.")
    )
    owner_uid: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(), info=_info("Owner", "Existing platform user UID.")
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, info=_info("Status", "Prospecting progress.")
    )
    next_task_uid: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(), info=_info("Next task", "Current next-action Task FK.")
    )
    notes: Mapped[str | None] = mapped_column(Text(), info=_info("Notes", "Prospecting context."))


class SolutionSellingDiagnosis(VersionedRecord, PlatformManagedMetaTable, Base):
    __tablename__ = schema_table_name("mainsequence_crm", "solution_selling_diagnosis")
    __metatable_namespace__ = "mainsequence-crm"
    __metatable_identifier__ = "mainsequence_crm__solution_selling_diagnosis"
    __metatable_description__ = "Nine-cell diagnosis tied to an Interaction and Contact."
    __metatable_labels__ = ["crm", "solution-selling", "diagnosis"]
    __table_args__ = (
        ForeignKeyConstraint(
            ["interaction_uid"], ["mainsequence_crm__interaction.uid"], ondelete="RESTRICT"
        ),
        ForeignKeyConstraint(
            ["contact_uid"], ["mainsequence_crm__contact.uid"], ondelete="RESTRICT"
        ),
        ForeignKeyConstraint(
            ["solution_selling_uid"],
            ["mainsequence_crm__solution_selling.uid"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("version > 0"),
        CheckConstraint("length(trim(business_issue)) > 0"),
        CheckConstraint("jsonb_typeof(matrix) = 'object'"),
        Index("ix_mainsequence_crm__ss_diagnosis_interaction", "interaction_uid"),
        Index("ix_mainsequence_crm__ss_diagnosis_assessment", "solution_selling_uid"),
    )

    interaction_uid: Mapped[uuid.UUID] = mapped_column(
        Uuid(), nullable=False, info=_info("Interaction", "Source conversation FK.")
    )
    contact_uid: Mapped[uuid.UUID] = mapped_column(
        Uuid(), nullable=False, info=_info("Contact", "Diagnosed Contact FK.")
    )
    solution_selling_uid: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(), info=_info("Assessment", "Optional maintained SolutionSelling FK.")
    )
    business_issue: Mapped[str] = mapped_column(
        Text(), nullable=False, info=_info("Business issue", "Context for the matrix.")
    )
    matrix: Mapped[Any] = mapped_column(
        JSONB(), nullable=False, info=_info("Diagnosis matrix", "Typed nine-cell matrix.")
    )
    conclusion: Mapped[str | None] = mapped_column(
        Text(), info=_info("Conclusion", "What diagnosis established.")
    )


class SolutionSellingPrompter(VersionedRecord, PlatformManagedMetaTable, Base):
    __tablename__ = schema_table_name("mainsequence_crm", "solution_selling_prompter")
    __metatable_namespace__ = "mainsequence-crm"
    __metatable_identifier__ = "mainsequence_crm__solution_selling_prompter"
    __metatable_description__ = "Reusable content template rendered only on demand."
    __metatable_labels__ = ["crm", "solution-selling", "prompter"]
    __table_args__ = (
        CheckConstraint("version > 0"),
        CheckConstraint("length(trim(name)) > 0"),
        CheckConstraint("length(template) > 0"),
        Index("ix_mainsequence_crm__ss_prompter_kind", "kind"),
    )

    name: Mapped[str] = mapped_column(
        String(255), nullable=False, info=_info("Name", "Template name.")
    )
    kind: Mapped[str] = mapped_column(
        String(100), nullable=False, info=_info("Kind", "Purpose of generated draft.")
    )
    description: Mapped[str | None] = mapped_column(
        Text(), info=_info("Description", "Usage notes.")
    )
    template: Mapped[str] = mapped_column(
        Text(),
        nullable=False,
        info=_info("Template", "Sandboxed Jinja text, not executable Python."),
    )
