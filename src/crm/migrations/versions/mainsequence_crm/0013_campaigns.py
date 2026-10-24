"""Add the optional Campaigns module tables (ADR 0001) without touching existing rows."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

CAMPAIGN = "mainsequence_crm__campaign"
STEP = "mainsequence_crm__campaign_step"
TRANSITION = "mainsequence_crm__campaign_transition"
STEP_PROMPT = "mainsequence_crm__campaign_step_prompt"
PARTICIPANT = "mainsequence_crm__campaign_participant"
PROGRESS = "mainsequence_crm__campaign_progress"
ENTRY_FK = "fk_mainsequence_crm__campaign_entry_step"


def _versioned():
    return [
        sa.Column("uid", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_uid", sa.Uuid(), nullable=True),
        sa.Column("updated_by_uid", sa.Uuid(), nullable=True),
        sa.Column("version", sa.BigInteger(), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    ]


def upgrade() -> None:
    # The local SQLite runtime has no jsonb cast or functions; it gets portable
    # defaults and CHECK forms. PostgreSQL keeps the original SQL and the
    # circular entry-step foreign key, which SQLite cannot add after creation.
    sqlite = op.get_bind().dialect.name == "sqlite"
    jsonb = postgresql.JSONB(astext_type=sa.Text())
    empty_object = "'{}'" if sqlite else "'{}'::jsonb"
    empty_array = "'[]'" if sqlite else "'[]'::jsonb"
    json_type = "json_type" if sqlite else "jsonb_typeof"

    op.create_table(
        CAMPAIGN,
        *_versioned(),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("owner_uid", sa.Uuid(), nullable=False),
        sa.Column("context", jsonb, nullable=False, server_default=sa.text(empty_object)),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("entry_step_uid", sa.Uuid(), nullable=True),
        sa.CheckConstraint("version > 0", name="ck_mainsequence_crm__campaign_version"),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_mainsequence_crm__campaign_name"),
        sa.CheckConstraint(
            "status IN ('draft','active','paused','completed')",
            name="ck_mainsequence_crm__campaign_status",
        ),
    )
    op.create_index(
        "ix_mainsequence_crm__campaign_status", CAMPAIGN, ["archived_at", "status", "updated_at"]
    )
    op.create_table(
        STEP,
        *_versioned(),
        sa.Column("campaign_uid", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("task_text", sa.Text(), nullable=False),
        sa.Column("prompt_variants", jsonb, nullable=False),
        sa.Column("prompt_comparison", jsonb, nullable=True),
        sa.Column("completion_mode", sa.String(10), nullable=False, server_default=sa.text("'human'")),
        sa.Column("owner_uid", sa.Uuid(), nullable=True),
        sa.Column("task_type_key", sa.String(100), nullable=True),
        sa.Column("due_after_seconds", sa.BigInteger(), nullable=True),
        sa.Column("input_bindings", jsonb, nullable=False, server_default=sa.text(empty_object)),
        sa.Column("completion_criteria", sa.Text(), nullable=False),
        sa.Column("outcomes", jsonb, nullable=False),
        sa.Column("position", jsonb, nullable=True),
        sa.CheckConstraint("version > 0", name="ck_mainsequence_crm__campaign_step_version"),
        sa.CheckConstraint("length(trim(title)) > 0", name="ck_mainsequence_crm__campaign_step_title"),
        sa.CheckConstraint(
            "completion_mode IN ('human','agent')", name="ck_mainsequence_crm__campaign_step_mode"
        ),
        sa.CheckConstraint(
            f"{json_type}(prompt_variants) = 'array'",
            name="ck_mainsequence_crm__campaign_step_variants",
        ),
        sa.CheckConstraint(
            f"{json_type}(outcomes) = 'array'", name="ck_mainsequence_crm__campaign_step_outcomes"
        ),
        sa.ForeignKeyConstraint(
            ["campaign_uid"], [f"{CAMPAIGN}.uid"], ondelete="RESTRICT",
            name="fk_mainsequence_crm__campaign_step_campaign",
        ),
    )
    op.create_index(
        "ix_mainsequence_crm__campaign_step_campaign", STEP, ["campaign_uid", "archived_at"]
    )
    if not sqlite:
        op.create_foreign_key(
            ENTRY_FK, CAMPAIGN, STEP, ["entry_step_uid"], ["uid"], ondelete="RESTRICT"
        )
    op.create_table(
        TRANSITION,
        *_versioned(),
        sa.Column("campaign_uid", sa.Uuid(), nullable=False),
        sa.Column("from_step_uid", sa.Uuid(), nullable=False),
        sa.Column("outcome_key", sa.String(64), nullable=False),
        sa.Column("to_step_uid", sa.Uuid(), nullable=True),
        sa.Column("delay_seconds", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.CheckConstraint("version > 0", name="ck_mainsequence_crm__campaign_transition_version"),
        sa.CheckConstraint(
            "delay_seconds >= 0 AND (to_step_uid IS NOT NULL OR delay_seconds = 0)",
            name="ck_mainsequence_crm__campaign_transition_delay",
        ),
        sa.UniqueConstraint(
            "from_step_uid", "outcome_key", name="uq_mainsequence_crm__campaign_transition_route"
        ),
        sa.ForeignKeyConstraint(
            ["campaign_uid"], [f"{CAMPAIGN}.uid"], ondelete="RESTRICT",
            name="fk_mainsequence_crm__campaign_transition_campaign",
        ),
        sa.ForeignKeyConstraint(
            ["from_step_uid"], [f"{STEP}.uid"], ondelete="RESTRICT",
            name="fk_mainsequence_crm__campaign_transition_from",
        ),
        sa.ForeignKeyConstraint(
            ["to_step_uid"], [f"{STEP}.uid"], ondelete="RESTRICT",
            name="fk_mainsequence_crm__campaign_transition_to",
        ),
    )
    op.create_index(
        "ix_mainsequence_crm__campaign_transition_campaign", TRANSITION, ["campaign_uid"]
    )
    op.create_table(
        STEP_PROMPT,
        sa.Column("uid", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("inputs", jsonb, nullable=False, server_default=sa.text(empty_array)),
        sa.Column("result_fields", jsonb, nullable=False, server_default=sa.text(empty_array)),
        sa.CheckConstraint(
            f"{json_type}(inputs) = 'array' AND {json_type}(result_fields) = 'array'",
            name="ck_mainsequence_crm__campaign_step_prompt_fields",
        ),
        sa.ForeignKeyConstraint(
            ["uid"], ["mainsequence_crm__prompt.uid"], ondelete="RESTRICT",
            name="fk_mainsequence_crm__campaign_step_prompt_prompt",
        ),
    )
    op.create_table(
        PARTICIPANT,
        *_versioned(),
        sa.Column("campaign_uid", sa.Uuid(), nullable=False),
        sa.Column("contact_uid", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'active'")),
        sa.Column("context", jsonb, nullable=False, server_default=sa.text(empty_object)),
        sa.Column("next_step_uid", sa.Uuid(), nullable=True),
        sa.Column("eligible_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("version > 0", name="ck_mainsequence_crm__campaign_participant_version"),
        sa.CheckConstraint(
            "status IN ('active','paused','completed','withdrawn')",
            name="ck_mainsequence_crm__campaign_participant_status",
        ),
        sa.UniqueConstraint(
            "campaign_uid", "contact_uid", name="uq_mainsequence_crm__campaign_participant_contact"
        ),
        sa.ForeignKeyConstraint(
            ["campaign_uid"], [f"{CAMPAIGN}.uid"], ondelete="RESTRICT",
            name="fk_mainsequence_crm__campaign_participant_campaign",
        ),
        sa.ForeignKeyConstraint(
            ["contact_uid"], ["mainsequence_crm__contact.uid"], ondelete="RESTRICT",
            name="fk_mainsequence_crm__campaign_participant_contact",
        ),
        sa.ForeignKeyConstraint(
            ["next_step_uid"], [f"{STEP}.uid"], ondelete="RESTRICT",
            name="fk_mainsequence_crm__campaign_participant_next_step",
        ),
    )
    op.create_index(
        "ix_mainsequence_crm__campaign_participant_eligible",
        PARTICIPANT, ["campaign_uid", "status", "eligible_at"],
    )
    op.create_index(
        "ix_mainsequence_crm__campaign_participant_contact", PARTICIPANT, ["contact_uid"]
    )
    op.create_table(
        PROGRESS,
        sa.Column("uid", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("participant_uid", sa.Uuid(), nullable=False),
        sa.Column("step_uid", sa.Uuid(), nullable=False),
        sa.Column("task_uid", sa.Uuid(), nullable=False),
        sa.Column("prompt_assignment", jsonb, nullable=False),
        sa.Column("state", sa.String(20), nullable=False, server_default=sa.text("'open'")),
        sa.Column("outcome_key", sa.String(64), nullable=True),
        sa.Column("result", jsonb, nullable=False, server_default=sa.text(empty_object)),
        sa.Column("evidence", jsonb, nullable=False, server_default=sa.text(empty_array)),
        sa.Column("wake_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("blocked_reason", sa.String(500), nullable=True),
        sa.Column("prepared_with", jsonb, nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "state IN ('open','waiting','blocked','completed','cancelled')",
            name="ck_mainsequence_crm__campaign_progress_state",
        ),
        sa.UniqueConstraint(
            "participant_uid", "step_uid", name="uq_mainsequence_crm__campaign_progress_step"
        ),
        sa.UniqueConstraint("task_uid", name="uq_mainsequence_crm__campaign_progress_task"),
        sa.ForeignKeyConstraint(
            ["participant_uid"], [f"{PARTICIPANT}.uid"], ondelete="RESTRICT",
            name="fk_mainsequence_crm__campaign_progress_participant",
        ),
        sa.ForeignKeyConstraint(
            ["step_uid"], [f"{STEP}.uid"], ondelete="RESTRICT",
            name="fk_mainsequence_crm__campaign_progress_step",
        ),
        sa.ForeignKeyConstraint(
            ["task_uid"], ["mainsequence_crm__task.uid"], ondelete="RESTRICT",
            name="fk_mainsequence_crm__campaign_progress_task",
        ),
    )
    op.create_index("ix_mainsequence_crm__campaign_progress_wake", PROGRESS, ["state", "wake_at"])


def downgrade() -> None:
    sqlite = op.get_bind().dialect.name == "sqlite"
    op.drop_index("ix_mainsequence_crm__campaign_progress_wake", table_name=PROGRESS)
    op.drop_table(PROGRESS)
    op.drop_index("ix_mainsequence_crm__campaign_participant_contact", table_name=PARTICIPANT)
    op.drop_index("ix_mainsequence_crm__campaign_participant_eligible", table_name=PARTICIPANT)
    op.drop_table(PARTICIPANT)
    op.drop_table(STEP_PROMPT)
    op.drop_index("ix_mainsequence_crm__campaign_transition_campaign", table_name=TRANSITION)
    op.drop_table(TRANSITION)
    if not sqlite:
        op.drop_constraint(ENTRY_FK, CAMPAIGN, type_="foreignkey")
    op.drop_index("ix_mainsequence_crm__campaign_step_campaign", table_name=STEP)
    op.drop_table(STEP)
    op.drop_index("ix_mainsequence_crm__campaign_status", table_name=CAMPAIGN)
    op.drop_table(CAMPAIGN)
