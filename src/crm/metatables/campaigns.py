"""SQLAlchemy-authored MetaTables for the optional Campaigns module."""

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
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from metatables import PlatformManagedMetaTable, schema_table_name

from .base import Base, VersionedRecord
from .base import column_info as _info


class Campaign(VersionedRecord, PlatformManagedMetaTable, Base):
    __tablename__ = schema_table_name("mainsequence_crm", "campaign")
    __metatable_namespace__ = "mainsequence-crm"
    __metatable_identifier__ = "mainsequence_crm__campaign"
    __metatable_description__ = "One live campaign graph of prompted task definitions."
    __metatable_labels__ = ["crm", "campaigns"]
    __table_args__ = (
        ForeignKeyConstraint(
            ["entry_step_uid"],
            ["mainsequence_crm__campaign_step.uid"],
            ondelete="RESTRICT",
            use_alter=True,
            name="fk_mainsequence_crm__campaign_entry_step",
        ),
        CheckConstraint("version > 0", name="ck_mainsequence_crm__campaign_version"),
        CheckConstraint("length(trim(name)) > 0", name="ck_mainsequence_crm__campaign_name"),
        CheckConstraint(
            "status IN ('draft','active','paused','completed')",
            name="ck_mainsequence_crm__campaign_status",
        ),
        Index("ix_mainsequence_crm__campaign_status", "archived_at", "status", "updated_at"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False, info=_info("Name", "Display name."))
    objective: Mapped[str] = mapped_column(
        Text(), nullable=False, info=_info("Objective", "Intended outcome and success criteria.")
    )
    owner_uid: Mapped[uuid.UUID] = mapped_column(
        Uuid(), nullable=False, info=_info("Owner", "Responsible platform user; default Task owner.")
    )
    context: Mapped[Any] = mapped_column(
        JSONB(), nullable=False, server_default=text("'{}'::jsonb"),
        info=_info("Context", "Bounded shared business values supplied by the user."),
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'draft'"),
        info=_info("Status", "Whether participants may begin or advance."),
    )
    entry_step_uid: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(), info=_info("Entry step", "Starting task definition of this campaign.")
    )


class CampaignStep(VersionedRecord, PlatformManagedMetaTable, Base):
    __tablename__ = schema_table_name("mainsequence_crm", "campaign_step")
    __metatable_namespace__ = "mainsequence-crm"
    __metatable_identifier__ = "mainsequence_crm__campaign_step"
    __metatable_description__ = "Reusable task definition inside one campaign graph."
    __metatable_labels__ = ["crm", "campaigns"]
    __table_args__ = (
        ForeignKeyConstraint(
            ["campaign_uid"], ["mainsequence_crm__campaign.uid"], ondelete="RESTRICT",
            name="fk_mainsequence_crm__campaign_step_campaign",
        ),
        CheckConstraint("version > 0", name="ck_mainsequence_crm__campaign_step_version"),
        CheckConstraint("length(trim(title)) > 0", name="ck_mainsequence_crm__campaign_step_title"),
        CheckConstraint(
            "completion_mode IN ('human','agent')", name="ck_mainsequence_crm__campaign_step_mode"
        ),
        CheckConstraint(
            "jsonb_typeof(prompt_variants) = 'array'",
            name="ck_mainsequence_crm__campaign_step_variants",
        ).ddl_if(dialect="postgresql"),
        CheckConstraint(
            "jsonb_typeof(outcomes) = 'array'", name="ck_mainsequence_crm__campaign_step_outcomes"
        ).ddl_if(dialect="postgresql"),
        Index("ix_mainsequence_crm__campaign_step_campaign", "campaign_uid", "archived_at"),
    )

    campaign_uid: Mapped[uuid.UUID] = mapped_column(
        Uuid(), nullable=False, info=_info("Campaign", "Owning graph; immutable.")
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False, info=_info("Title", "Card label."))
    task_text: Mapped[str] = mapped_column(
        Text(), nullable=False, info=_info("Task text", "Markdown work instructions.")
    )
    prompt_variants: Mapped[Any] = mapped_column(
        JSONB(), nullable=False, info=_info("Prompt variants", "One prompt or two A/B alternatives.")
    )
    prompt_comparison: Mapped[Any | None] = mapped_column(
        JSONB(), info=_info("Prompt comparison", "A/B metric, window and control variant.")
    )
    completion_mode: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default=text("'human'"),
        info=_info("Completion mode", "Who supplies the result."),
    )
    owner_uid: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(), info=_info("Owner", "Task owner override.")
    )
    task_type_key: Mapped[str | None] = mapped_column(
        String(100), info=_info("Task type", "Existing CRM task type key.")
    )
    due_after_seconds: Mapped[int | None] = mapped_column(
        BigInteger(), info=_info("Due after", "Due-time offset from Task creation.")
    )
    input_bindings: Mapped[Any] = mapped_column(
        JSONB(), nullable=False, server_default=text("'{}'::jsonb"),
        info=_info("Input bindings", "Prompt input name to documented context path."),
    )
    completion_criteria: Mapped[str] = mapped_column(
        Text(), nullable=False, info=_info("Completion criteria", "Evidence needed to finish.")
    )
    outcomes: Mapped[Any] = mapped_column(
        JSONB(), nullable=False, info=_info("Outcomes", "Allowed terminal business outcomes.")
    )
    position: Mapped[Any | None] = mapped_column(
        JSONB(), info=_info("Position", "Designer layout only.")
    )


class CampaignTransition(VersionedRecord, PlatformManagedMetaTable, Base):
    __tablename__ = schema_table_name("mainsequence_crm", "campaign_transition")
    __metatable_namespace__ = "mainsequence-crm"
    __metatable_identifier__ = "mainsequence_crm__campaign_transition"
    __metatable_description__ = "Outcome connection from one step to the next step or finish."
    __metatable_labels__ = ["crm", "campaigns"]
    __table_args__ = (
        ForeignKeyConstraint(
            ["campaign_uid"], ["mainsequence_crm__campaign.uid"], ondelete="RESTRICT",
            name="fk_mainsequence_crm__campaign_transition_campaign",
        ),
        ForeignKeyConstraint(
            ["from_step_uid"], ["mainsequence_crm__campaign_step.uid"], ondelete="RESTRICT",
            name="fk_mainsequence_crm__campaign_transition_from",
        ),
        ForeignKeyConstraint(
            ["to_step_uid"], ["mainsequence_crm__campaign_step.uid"], ondelete="RESTRICT",
            name="fk_mainsequence_crm__campaign_transition_to",
        ),
        UniqueConstraint(
            "from_step_uid", "outcome_key", name="uq_mainsequence_crm__campaign_transition_route"
        ),
        CheckConstraint("version > 0", name="ck_mainsequence_crm__campaign_transition_version"),
        CheckConstraint(
            "delay_seconds >= 0 AND (to_step_uid IS NOT NULL OR delay_seconds = 0)",
            name="ck_mainsequence_crm__campaign_transition_delay",
        ),
        Index("ix_mainsequence_crm__campaign_transition_campaign", "campaign_uid"),
    )

    campaign_uid: Mapped[uuid.UUID] = mapped_column(Uuid(), nullable=False, info=_info("Campaign", "Owning graph."))
    from_step_uid: Mapped[uuid.UUID] = mapped_column(
        Uuid(), nullable=False, info=_info("From step", "Task definition whose result is evaluated.")
    )
    outcome_key: Mapped[str] = mapped_column(
        String(64), nullable=False, info=_info("Outcome", "Source step outcome key.")
    )
    to_step_uid: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(), info=_info("To step", "Next definition; null finishes the participant.")
    )
    delay_seconds: Mapped[int] = mapped_column(
        BigInteger(), nullable=False, server_default=text("0"),
        info=_info("Delay", "Seconds before the next task becomes eligible."),
    )


class CampaignStepPrompt(PlatformManagedMetaTable, Base):
    """One-to-one extension sharing the core Prompt's UID, version and audit."""

    __tablename__ = schema_table_name("mainsequence_crm", "campaign_step_prompt")
    __metatable_namespace__ = "mainsequence-crm"
    __metatable_identifier__ = "mainsequence_crm__campaign_step_prompt"
    __metatable_description__ = "Declared inputs and result fields of a campaign step prompt."
    __metatable_labels__ = ["crm", "campaigns", "prompts"]
    __table_args__ = (
        ForeignKeyConstraint(
            ["uid"], ["mainsequence_crm__prompt.uid"], ondelete="RESTRICT",
            name="fk_mainsequence_crm__campaign_step_prompt_prompt",
        ),
        CheckConstraint(
            "jsonb_typeof(inputs) = 'array' AND jsonb_typeof(result_fields) = 'array'",
            name="ck_mainsequence_crm__campaign_step_prompt_fields",
        ).ddl_if(dialect="postgresql"),
    )

    uid: Mapped[uuid.UUID] = mapped_column(
        Uuid(), primary_key=True, info=_info("Prompt UID", "Shared with the core Prompt.")
    )
    inputs: Mapped[Any] = mapped_column(
        JSONB(), nullable=False, server_default=text("'[]'::jsonb"),
        info=_info("Inputs", "Named context values the prompt expects."),
    )
    result_fields: Mapped[Any] = mapped_column(
        JSONB(), nullable=False, server_default=text("'[]'::jsonb"),
        info=_info("Result fields", "Business fields expected in the structured result."),
    )


class CampaignParticipant(VersionedRecord, PlatformManagedMetaTable, Base):
    __tablename__ = schema_table_name("mainsequence_crm", "campaign_participant")
    __metatable_namespace__ = "mainsequence-crm"
    __metatable_identifier__ = "mainsequence_crm__campaign_participant"
    __metatable_description__ = "One Contact's enrollment in one campaign."
    __metatable_labels__ = ["crm", "campaigns"]
    __table_args__ = (
        ForeignKeyConstraint(
            ["campaign_uid"], ["mainsequence_crm__campaign.uid"], ondelete="RESTRICT",
            name="fk_mainsequence_crm__campaign_participant_campaign",
        ),
        ForeignKeyConstraint(
            ["contact_uid"], ["mainsequence_crm__contact.uid"], ondelete="RESTRICT",
            name="fk_mainsequence_crm__campaign_participant_contact",
        ),
        ForeignKeyConstraint(
            ["next_step_uid"], ["mainsequence_crm__campaign_step.uid"], ondelete="RESTRICT",
            name="fk_mainsequence_crm__campaign_participant_next_step",
        ),
        UniqueConstraint(
            "campaign_uid", "contact_uid", name="uq_mainsequence_crm__campaign_participant_contact"
        ),
        CheckConstraint("version > 0", name="ck_mainsequence_crm__campaign_participant_version"),
        CheckConstraint(
            "status IN ('active','paused','completed','withdrawn')",
            name="ck_mainsequence_crm__campaign_participant_status",
        ),
        Index(
            "ix_mainsequence_crm__campaign_participant_eligible",
            "campaign_uid", "status", "eligible_at",
        ),
        Index("ix_mainsequence_crm__campaign_participant_contact", "contact_uid"),
    )

    campaign_uid: Mapped[uuid.UUID] = mapped_column(Uuid(), nullable=False, info=_info("Campaign", "Campaign being followed."))
    contact_uid: Mapped[uuid.UUID] = mapped_column(
        Uuid(), nullable=False, info=_info("Contact", "Enrolled person; immutable.")
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'active'"),
        info=_info("Status", "Participant lifecycle."),
    )
    context: Mapped[Any] = mapped_column(
        JSONB(), nullable=False, server_default=text("'{}'::jsonb"),
        info=_info("Context", "Participant-specific campaign values."),
    )
    next_step_uid: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(), info=_info("Next step", "Service-owned next eligible definition.")
    )
    eligible_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), info=_info("Eligible at", "Earliest next-task creation time.")
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), info=_info("Finished at", "Completion or withdrawal time.")
    )


class CampaignProgress(PlatformManagedMetaTable, Base):
    """Internal association from a participant/step to its actual CRM Task.

    Embedded in ``Participant.progress``; it has no API identity of its own.
    """

    __tablename__ = schema_table_name("mainsequence_crm", "campaign_progress")
    __metatable_namespace__ = "mainsequence-crm"
    __metatable_identifier__ = "mainsequence_crm__campaign_progress"
    __metatable_description__ = "Task instance, prompt assignment and result for one participant step."
    __metatable_labels__ = ["crm", "campaigns"]
    __table_args__ = (
        ForeignKeyConstraint(
            ["participant_uid"], ["mainsequence_crm__campaign_participant.uid"], ondelete="RESTRICT",
            name="fk_mainsequence_crm__campaign_progress_participant",
        ),
        ForeignKeyConstraint(
            ["step_uid"], ["mainsequence_crm__campaign_step.uid"], ondelete="RESTRICT",
            name="fk_mainsequence_crm__campaign_progress_step",
        ),
        ForeignKeyConstraint(
            ["task_uid"], ["mainsequence_crm__task.uid"], ondelete="RESTRICT",
            name="fk_mainsequence_crm__campaign_progress_task",
        ),
        UniqueConstraint(
            "participant_uid", "step_uid", name="uq_mainsequence_crm__campaign_progress_step"
        ),
        UniqueConstraint("task_uid", name="uq_mainsequence_crm__campaign_progress_task"),
        CheckConstraint(
            "state IN ('open','waiting','blocked','completed','cancelled')",
            name="ck_mainsequence_crm__campaign_progress_state",
        ),
        Index("ix_mainsequence_crm__campaign_progress_wake", "state", "wake_at"),
    )

    uid: Mapped[uuid.UUID] = mapped_column(
        Uuid(), primary_key=True, info=_info("UID", "Derived from participant and step.")
    )
    participant_uid: Mapped[uuid.UUID] = mapped_column(Uuid(), nullable=False, info=_info("Participant", "Enrollment."))
    step_uid: Mapped[uuid.UUID] = mapped_column(Uuid(), nullable=False, info=_info("Step", "Definition identity."))
    task_uid: Mapped[uuid.UUID] = mapped_column(Uuid(), nullable=False, info=_info("Task", "Concrete CRM Task instance."))
    prompt_assignment: Mapped[Any] = mapped_column(
        JSONB(), nullable=False, info=_info("Prompt assignment", "Immutable variant selection facts.")
    )
    state: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'open'"),
        info=_info("State", "Campaign progression state."),
    )
    outcome_key: Mapped[str | None] = mapped_column(String(64), info=_info("Outcome", "Validated outcome once completed."))
    result: Mapped[Any] = mapped_column(
        JSONB(), nullable=False, server_default=text("'{}'::jsonb"),
        info=_info("Result", "Actual business outputs."),
    )
    evidence: Mapped[Any] = mapped_column(
        JSONB(), nullable=False, server_default=text("'[]'::jsonb"),
        info=_info("Evidence", "Observed or reported facts."),
    )
    wake_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), info=_info("Wake at", "Next consideration time."))
    blocked_reason: Mapped[str | None] = mapped_column(String(500), info=_info("Blocked reason", "Actionable block explanation."))
    prepared_with: Mapped[Any | None] = mapped_column(
        JSONB(), info=_info("Prepared with", "Definition provenance submitted with the last result.")
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), info=_info("Completed at", "Settled time."))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, info=_info("Created at", "Task creation instant."))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, info=_info("Updated at", "Last progress edit."))
