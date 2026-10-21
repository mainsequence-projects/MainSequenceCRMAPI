"""Add optional note titles without rewriting existing notes or their versions."""

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

TABLE = "mainsequence_crm__note"
CONSTRAINT = "ck_mainsequence_crm__note_title"
CHECK = "title IS NULL OR (length(trim(title)) > 0 AND length(title) <= 255)"


def upgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        # Native ADD preserves every existing check, index and parent FK.
        op.execute(sa.text(
            f"ALTER TABLE {TABLE} ADD COLUMN title VARCHAR(255) "
            f"CONSTRAINT {CONSTRAINT} CHECK ({CHECK})"
        ))
        return
    op.add_column(TABLE, sa.Column("title", sa.String(255), nullable=True))
    op.create_check_constraint(CONSTRAINT, TABLE, CHECK)


def downgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        op.execute(sa.text(f"ALTER TABLE {TABLE} DROP COLUMN title"))
        return
    op.drop_constraint(CONSTRAINT, TABLE, type_="check")
    op.drop_column(TABLE, "title")
