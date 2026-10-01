"""Make people the Interaction relationship and Company optional context.

Revision ID: 0009
Revises: 0008
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

TABLE = "mainsequence_crm__interaction"


def upgrade() -> None:
    op.add_column(TABLE, sa.Column("participants", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.execute(sa.text(
        f"UPDATE {TABLE} SET participants=jsonb_build_array(jsonb_build_object("
        "'contact_uid', contact_uid::text, 'email', NULL, 'display_name', NULL, 'role', 'attendee')) "
        "WHERE contact_uid IS NOT NULL"
    ))
    op.create_check_constraint("ck_mainsequence_crm__interaction_participants_array", TABLE, "jsonb_typeof(participants) = 'array'")
    op.create_check_constraint("ck_mainsequence_crm__interaction_deal_company", TABLE, "deal_uid IS NULL OR company_uid IS NOT NULL")
    op.drop_index("ix_mainsequence_crm__interaction_contact", table_name=TABLE)
    op.drop_constraint("mainsequence_crm__interaction_contact_uid_fkey", TABLE, type_="foreignkey")
    op.drop_column(TABLE, "contact_uid")
    op.alter_column(TABLE, "company_uid", existing_type=sa.Uuid(), nullable=True)


def downgrade() -> None:
    connection = op.get_bind()
    if connection.execute(sa.text(f"SELECT 1 FROM {TABLE} WHERE company_uid IS NULL LIMIT 1")).scalar():
        raise RuntimeError("Cannot restore required Company while companyless Interactions exist")
    if connection.execute(sa.text(
        f"SELECT 1 FROM {TABLE} WHERE jsonb_array_length(participants)>1 LIMIT 1"
    )).scalar():
        raise RuntimeError("Cannot restore single Contact while multi-person Interactions exist")
    if connection.execute(sa.text(
        f"SELECT 1 FROM {TABLE} WHERE jsonb_array_length(participants)=1 "
        "AND participants->0->>'contact_uid' IS NULL LIMIT 1"
    )).scalar():
        raise RuntimeError("Cannot restore single Contact while unlinked people exist")
    op.add_column(TABLE, sa.Column("contact_uid", sa.Uuid(), nullable=True))
    op.execute(sa.text(
        f"UPDATE {TABLE} SET contact_uid=(participants->0->>'contact_uid')::uuid "
        "WHERE jsonb_array_length(participants)=1 AND participants->0->>'contact_uid' IS NOT NULL"
    ))
    op.create_foreign_key("mainsequence_crm__interaction_contact_uid_fkey", TABLE, "mainsequence_crm__contact", ["contact_uid"], ["uid"], ondelete="RESTRICT")
    op.create_index("ix_mainsequence_crm__interaction_contact", TABLE, ["contact_uid"])
    op.alter_column(TABLE, "company_uid", existing_type=sa.Uuid(), nullable=False)
    op.drop_constraint("ck_mainsequence_crm__interaction_participants_array", TABLE, type_="check")
    op.drop_constraint("ck_mainsequence_crm__interaction_deal_company", TABLE, type_="check")
    op.drop_column(TABLE, "participants")
