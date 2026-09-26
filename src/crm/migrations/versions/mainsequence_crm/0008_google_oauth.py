"""Add private Google OAuth attempt and connection tables.

Revision ID: 0008
Revises: 0007
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mainsequence_crm__google_oauth_attempt",
        sa.Column("uid", sa.Uuid(), primary_key=True),
        sa.Column("state_hash", sa.String(64), nullable=False),
        sa.Column("actor_uid", sa.Uuid(), nullable=False),
        sa.Column("connection_uid", sa.Uuid(), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("verifier_ciphertext", sa.Text(), nullable=False),
        sa.Column("nonce", sa.String(128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("completion_hash", sa.String(64)),
        sa.Column("pending_ciphertext", sa.Text()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('started','redeeming','exchanged','completed')", name="ck_mainsequence_crm__google_attempt_status"),
    )
    op.create_index("ix_mainsequence_crm__google_oauth_attempt_state", "mainsequence_crm__google_oauth_attempt", ["state_hash"], unique=True)
    op.create_index("ix_mainsequence_crm__google_oauth_attempt_handle", "mainsequence_crm__google_oauth_attempt", ["completion_hash"], unique=True)
    op.create_index("ix_mainsequence_crm__google_oauth_attempt_expiry", "mainsequence_crm__google_oauth_attempt", ["expires_at"])
    op.create_table(
        "mainsequence_crm__google_oauth_connection",
        sa.Column("uid", sa.Uuid(), primary_key=True),
        sa.Column("actor_uid", sa.Uuid(), nullable=False),
        sa.Column("source_connection_uid", sa.Uuid(), nullable=False),
        sa.Column("google_sub", sa.String(255), nullable=False),
        sa.Column("display_email", sa.String(320), nullable=False),
        sa.Column("granted_scopes", postgresql.JSONB(), nullable=False),
        sa.Column("refresh_ciphertext", sa.Text()),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("version", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('connected','reauthorization_required','disconnected')", name="ck_mainsequence_crm__google_connection_status"),
        sa.CheckConstraint("version > 0", name="ck_mainsequence_crm__google_connection_version"),
    )
    op.create_index("uq_mainsequence_crm__google_connection_actor", "mainsequence_crm__google_oauth_connection", ["actor_uid"], unique=True)
    op.create_index("uq_mainsequence_crm__google_connection_sub_active", "mainsequence_crm__google_oauth_connection", ["google_sub"], unique=True, postgresql_where=sa.text("status <> 'disconnected'"))


def downgrade() -> None:
    op.drop_index("uq_mainsequence_crm__google_connection_sub_active", table_name="mainsequence_crm__google_oauth_connection")
    op.drop_index("uq_mainsequence_crm__google_connection_actor", table_name="mainsequence_crm__google_oauth_connection")
    op.drop_table("mainsequence_crm__google_oauth_connection")
    op.drop_index("ix_mainsequence_crm__google_oauth_attempt_expiry", table_name="mainsequence_crm__google_oauth_attempt")
    op.drop_index("ix_mainsequence_crm__google_oauth_attempt_handle", table_name="mainsequence_crm__google_oauth_attempt")
    op.drop_index("ix_mainsequence_crm__google_oauth_attempt_state", table_name="mainsequence_crm__google_oauth_attempt")
    op.drop_table("mainsequence_crm__google_oauth_attempt")
