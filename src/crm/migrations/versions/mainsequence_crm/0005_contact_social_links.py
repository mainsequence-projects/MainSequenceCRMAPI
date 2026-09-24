"""Replace the contact-only LinkedIn column with typed social links.

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-24 09:48:50.182480

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pydantic import HttpUrl, TypeAdapter, ValidationError
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: Union[str, Sequence[str], None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CONTACT = "mainsequence_crm__contact"


def upgrade() -> None:
    """Backfill every legacy LinkedIn URL before dropping its old column."""
    connection = op.get_bind()
    url_adapter = TypeAdapter(HttpUrl)
    for (raw_url,) in connection.execute(
        sa.text(f'SELECT DISTINCT linkedin_url FROM "{CONTACT}" WHERE linkedin_url IS NOT NULL')
    ):
        try:
            url_adapter.validate_python(raw_url)
        except ValidationError as exc:
            raise RuntimeError(
                "A contact has an invalid legacy LinkedIn URL; correct it before upgrading"
            ) from exc

    op.add_column(
        CONTACT,
        sa.Column(
            "socials", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
    )
    connection.execute(
        sa.text(
            f"UPDATE \"{CONTACT}\" SET socials=jsonb_build_object('linkedin', linkedin_url) "
            "WHERE linkedin_url IS NOT NULL"
        )
    )
    op.create_check_constraint(
        "ck_mainsequence_crm__contact_socials", CONTACT, "jsonb_typeof(socials) = 'object'"
    )
    op.drop_column(CONTACT, "linkedin_url")


def downgrade() -> None:
    """Refuse to discard any profile the old schema cannot represent."""
    connection = op.get_bind()
    has_other_profiles = connection.execute(
        sa.text(
            f"SELECT EXISTS(SELECT 1 FROM \"{CONTACT}\" WHERE socials - 'linkedin' <> '{{}}'::jsonb)"
        )
    ).scalar_one()
    if has_other_profiles:
        raise RuntimeError("Cannot downgrade contacts with non-LinkedIn social profiles")
    op.add_column(CONTACT, sa.Column("linkedin_url", sa.Text(), nullable=True))
    connection.execute(sa.text(f"UPDATE \"{CONTACT}\" SET linkedin_url=socials->>'linkedin'"))
    op.drop_constraint("ck_mainsequence_crm__contact_socials", CONTACT, type_="check")
    op.drop_column(CONTACT, "socials")
