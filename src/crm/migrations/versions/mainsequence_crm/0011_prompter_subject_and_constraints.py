"""Add optional subjects and draft constraints without changing existing templates."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

TABLE = "mainsequence_crm__solution_selling_prompter"


def upgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        # Native additive DDL preserves the unnamed checks authored in 0006;
        # recreating the table through batch reflection would drop them.
        op.execute(sa.text(f"ALTER TABLE {TABLE} ADD COLUMN subject_template TEXT"))
        op.execute(
            sa.text(f"ALTER TABLE {TABLE} ADD COLUMN constraints JSON NOT NULL DEFAULT '{{}}'")
        )
        return
    op.add_column(TABLE, sa.Column("subject_template", sa.Text(), nullable=True))
    op.add_column(
        TABLE, sa.Column("constraints", JSONB(), nullable=False, server_default=sa.text("'{}'"))
    )


def downgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        op.execute(sa.text(f"ALTER TABLE {TABLE} DROP COLUMN constraints"))
        op.execute(sa.text(f"ALTER TABLE {TABLE} DROP COLUMN subject_template"))
        return
    op.drop_column(TABLE, "constraints")
    op.drop_column(TABLE, "subject_template")
