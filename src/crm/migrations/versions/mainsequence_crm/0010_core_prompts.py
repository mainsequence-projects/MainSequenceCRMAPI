"""Add the core fixed-Markdown prompt library without altering existing templates."""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    content_bytes = (
        "length(CAST(content_markdown AS BLOB))"
        if op.get_bind().dialect.name == "sqlite"
        else "octet_length(content_markdown)"
    )
    op.create_table(
        "mainsequence_crm__prompt",
        sa.Column("uid", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_uid", sa.Uuid(), nullable=True),
        sa.Column("updated_by_uid", sa.Uuid(), nullable=True),
        sa.Column("version", sa.BigInteger(), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("content_markdown", sa.Text(), nullable=False),
        sa.CheckConstraint("version > 0", name="ck_mainsequence_crm__prompt_version"),
        sa.CheckConstraint(
            "length(trim(name)) BETWEEN 1 AND 255", name="ck_mainsequence_crm__prompt_name"
        ),
        sa.CheckConstraint(
            "description IS NULL OR length(description) <= 2000",
            name="ck_mainsequence_crm__prompt_description",
        ),
        sa.CheckConstraint(
            f"{content_bytes} BETWEEN 1 AND 65536", name="ck_mainsequence_crm__prompt_content"
        ),
    )
    op.create_index(
        "ix_mainsequence_crm__prompt_updated",
        "mainsequence_crm__prompt",
        ["archived_at", "updated_at", "uid"],
    )


def downgrade() -> None:
    op.drop_index("ix_mainsequence_crm__prompt_updated", table_name="mainsequence_crm__prompt")
    op.drop_table("mainsequence_crm__prompt")
