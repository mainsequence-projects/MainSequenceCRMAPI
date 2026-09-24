"""remove command receipts

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-23 20:36:27.046180

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: Union[str, Sequence[str], None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Remove the obsolete receipt table and its one legacy proof row."""
    op.drop_index(
        "ix_mainsequence_crm__command_receipt_1",
        table_name="mainsequence_crm__command_receipt",
    )
    op.drop_table("mainsequence_crm__command_receipt")


def downgrade() -> None:
    """Restore the table shape, but not deleted receipt data."""
    op.create_table(
        "mainsequence_crm__command_receipt",
        sa.Column("uid", sa.Uuid(), nullable=False),
        sa.Column("workspace_uid", sa.Uuid(), nullable=False),
        sa.Column("actor_uid", sa.Uuid(), nullable=False),
        sa.Column("operation_key", sa.String(length=255), nullable=False),
        sa.Column("key_hash", sa.CHAR(length=64), nullable=False),
        sa.Column("request_hash", sa.CHAR(length=64), nullable=False),
        sa.Column("http_status", sa.SmallInteger(), nullable=False),
        sa.Column("response_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "http_status >= 200 AND http_status < 300",
            name="ck_mainsequence_crm__command_receipt_1",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_uid"],
            ["mainsequence_crm__workspace.uid"],
            name="fk_mainsequence_crm__command_receipt_workspace_uid",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("uid"),
        sa.UniqueConstraint(
            "workspace_uid",
            "actor_uid",
            "operation_key",
            "key_hash",
            name="uq_mainsequence_crm__command_receipt_workspace_uid_actor_uid_op",
        ),
        sa.UniqueConstraint(
            "workspace_uid",
            "uid",
            name="uq_mainsequence_crm__command_receipt_workspace_uid_uid",
        ),
    )
    op.create_index(
        "ix_mainsequence_crm__command_receipt_1",
        "mainsequence_crm__command_receipt",
        ["expires_at"],
        unique=False,
    )
