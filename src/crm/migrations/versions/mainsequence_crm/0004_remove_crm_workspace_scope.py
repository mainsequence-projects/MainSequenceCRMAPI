"""remove CRM workspace scope

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-23 20:58:54.276206

"""

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: Union[str, Sequence[str], None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLES = (
    "activity_event",
    "company",
    "contact",
    "contact_company_affiliation",
    "contact_tag",
    "deal",
    "deal_contact",
    "entity_redirect",
    "note",
    "pipeline",
    "source_connection",
    "source_identity",
    "stage",
    "tag",
    "task",
    "transfer_job",
    "transfer_row",
)
PREFIX = "mainsequence_crm__"

FOREIGN_KEYS = {
    "contact": [("contact_company_uid", ("company_uid",), "company", ("uid",))],
    "contact_company_affiliation": [
        ("affiliation_contact", ("contact_uid",), "contact", ("uid",)),
        ("affiliation_company", ("company_uid",), "company", ("uid",)),
    ],
    "contact_tag": [
        ("contact_tag_contact_uid", ("contact_uid",), "contact", ("uid",)),
        ("contact_tag_tag_uid", ("tag_uid",), "tag", ("uid",)),
    ],
    "deal": [
        ("deal_company_uid", ("company_uid",), "company", ("uid",)),
        ("deal_pipeline_uid", ("pipeline_uid",), "pipeline", ("uid",)),
        (
            "deal_pipeline_uid_stage_uid",
            ("pipeline_uid", "stage_uid"),
            "stage",
            ("pipeline_uid", "uid"),
        ),
    ],
    "deal_contact": [
        ("deal_contact_deal_uid", ("deal_uid",), "deal", ("uid",)),
        ("deal_contact_contact_uid", ("contact_uid",), "contact", ("uid",)),
    ],
    "note": [
        ("note_contact_uid", ("contact_uid",), "contact", ("uid",)),
        ("note_deal_uid", ("deal_uid",), "deal", ("uid",)),
    ],
    "source_identity": [
        ("source_identity_source_conne", ("source_connection_uid",), "source_connection", ("uid",)),
    ],
    "stage": [("stage_pipeline_uid", ("pipeline_uid",), "pipeline", ("uid",))],
    "task": [("task_contact_uid", ("contact_uid",), "contact", ("uid",))],
    "transfer_job": [
        ("transfer_job_source_connecti", ("source_connection_uid",), "source_connection", ("uid",)),
    ],
    "transfer_row": [("transfer_row_job_uid", ("job_uid",), "transfer_job", ("uid",))],
}

UNIQUES = {
    "activity_event": [
        ("activity_event_command_uid_e", ("command_uid", "entity_type", "entity_uid", "kind"))
    ],
    "contact_tag": [("contact_tag_contact_uid_tag_", ("contact_uid", "tag_uid"))],
    "deal_contact": [("deal_contact_deal_uid_contac", ("deal_uid", "contact_uid"))],
    "entity_redirect": [("entity_redirect_entity_type_", ("entity_type", "from_uid"))],
    "source_connection": [("source_connection_adapter_id", ("adapter_id", "source_account_key"))],
    "source_identity": [
        ("source_identity_source_conne", ("source_connection_uid", "entity_type", "external_id"))
    ],
    "stage": [
        ("stage_pipeline_uid_key", ("pipeline_uid", "key")),
        ("stage_pipeline_uid_uid", ("pipeline_uid", "uid")),
    ],
    "tag": [("tag_normalized_name", ("normalized_name",))],
    "transfer_row": [("transfer_row_job_uid_entity_", ("job_uid", "entity_type", "ordinal"))],
}

INDEXES = {
    "activity_event": [
        ("activity_event_1", ("occurred_at", "uid")),
        ("activity_event_2", ("entity_type", "entity_uid", "occurred_at", "uid")),
    ],
    "company": [
        ("company_1", ("archived_at", "name", "uid")),
        ("company_2", ("owner_uid",)),
        ("company_3", ("normalized_domain",)),
    ],
    "contact": [
        ("contact_1", ("archived_at", "last_seen", "uid")),
        ("contact_2", ("company_uid",)),
        ("contact_3", ("owner_uid",)),
    ],
    "contact_company_affiliation": [
        ("affiliation_company_status", ("company_uid", "status", "contact_uid")),
        ("affiliation_contact_timeline", ("contact_uid", "started_period", "uid")),
        ("affiliation_primary_current", ("contact_uid",), "is_primary AND archived_at IS NULL"),
    ],
    "contact_tag": [("contact_tag_1", ("tag_uid", "contact_uid"))],
    "deal": [
        ("deal_1", ("pipeline_uid", "stage_uid", "archived_at", "position", "uid")),
        ("deal_2", ("company_uid",)),
        ("deal_3", ("owner_uid", "expected_closing_date")),
    ],
    "deal_contact": [("deal_contact_1", ("contact_uid", "deal_uid"))],
    "entity_redirect": [("entity_redirect_1", ("entity_type", "to_uid"))],
    "note": [
        ("note_1", ("contact_uid", "occurred_at", "uid")),
        ("note_2", ("deal_uid", "occurred_at", "uid")),
    ],
    "pipeline": [("pipeline_default", ("is_default",), "is_default = true")],
    "source_identity": [("source_identity_1", ("entity_type", "target_uid"))],
    "stage": [("stage_1", ("pipeline_uid", "position", "uid"))],
    "task": [
        ("task_1", ("contact_uid",)),
        (
            "task_open_due",
            ("owner_uid", "due_at", "uid"),
            "completed_at IS NULL AND archived_at IS NULL",
        ),
    ],
    "transfer_job": [("transfer_job_1", ("status", "created_at", "uid"))],
    "transfer_row": [("transfer_row_1", ("job_uid", "state", "ordinal", "uid"))],
}


def upgrade() -> None:
    """Replace CRM-only workspace scoping with ordinary application settings."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    names = set(inspector.get_table_names())
    expected = {PREFIX + name for name in TABLES} | {PREFIX + "workspace"}
    if not expected <= names:
        raise RuntimeError("CRM workspace migration requires the 0003 schema")
    for table_name in names:
        for fk in inspector.get_foreign_keys(table_name):
            if fk.get("referred_table") == PREFIX + "workspace" and table_name not in expected:
                raise RuntimeError("A non-CRM table references the CRM workspace")
    for logical in TABLES:
        table = PREFIX + logical
        if "workspace_uid" not in {column["name"] for column in inspector.get_columns(table)}:
            raise RuntimeError(f"{table} is missing the expected workspace column")
    count = bind.execute(sa.text(f'SELECT count(*) FROM "{PREFIX}workspace"')).scalar_one()
    if count > 1:
        raise RuntimeError("Cannot merge multiple CRM workspace settings rows")

    op.create_table(
        PREFIX + "settings",
        sa.Column("uid", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("key", sa.String(32), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("default_currency", sa.CHAR(3), nullable=False),
        sa.Column("timezone", sa.String(100), nullable=False),
        sa.Column("configuration", postgresql.JSONB(), nullable=False),
        sa.Column("configuration_version", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("key = 'default'", name="ck_mainsequence_crm__settings_key"),
        sa.CheckConstraint(
            "default_currency ~ '^[A-Z]{3}$'", name="ck_mainsequence_crm__settings_currency"
        ),
        sa.CheckConstraint(
            "configuration_version > 0", name="ck_mainsequence_crm__settings_version"
        ),
        sa.UniqueConstraint("key", name="uq_mainsequence_crm__settings_key"),
    )
    if count:
        bind.execute(
            sa.text(
                f'INSERT INTO "{PREFIX}settings" (uid,key,name,default_currency,timezone,configuration,configuration_version,created_at,updated_at) '
                f"SELECT :uid,'default',name,default_currency,timezone,configuration,configuration_version,created_at,updated_at FROM \"{PREFIX}workspace\""
            ),
            {"uid": uuid.uuid4()},
        )
    else:
        bind.execute(
            sa.text(
                f'INSERT INTO "{PREFIX}settings" (uid,key,name,default_currency,timezone,configuration,configuration_version,created_at,updated_at) '
                "VALUES (:uid,'default','Main Sequence CRM','USD','UTC',CAST(:configuration AS jsonb),1,NOW(),NOW())"
            ),
            {
                "uid": uuid.uuid4(),
                "configuration": '{"company_sectors":[],"contact_statuses":[],"deal_categories":[],"task_types":[]}',
            },
        )

    # All old constraints are provider-owned and explicitly contain workspace_uid.
    # Drop the incoming composite FKs first, then indexes/uniques and columns.
    for logical in TABLES:
        table = PREFIX + logical
        for fk in inspector.get_foreign_keys(table):
            if "workspace_uid" in fk.get("constrained_columns", ()):
                name = fk.get("name")
                if not name or not name.startswith("fk_mainsequence_crm__"):
                    raise RuntimeError(f"Unexpected FK on {table}")
                op.drop_constraint(name, table, type_="foreignkey")
    for logical in TABLES:
        table = PREFIX + logical
        for item in inspector.get_unique_constraints(table):
            if "workspace_uid" in item.get("column_names", ()):
                name = item.get("name")
                if not name or not name.startswith("uq_mainsequence_crm__"):
                    raise RuntimeError(f"Unexpected unique constraint on {table}")
                op.drop_constraint(name, table, type_="unique")
        for item in inspector.get_indexes(table):
            if "workspace_uid" in item.get("column_names", ()):
                if item.get("duplicates_constraint"):
                    continue
                name = item.get("name")
                if not name or not name.startswith(
                    ("ix_mainsequence_crm__", "uq_mainsequence_crm__")
                ):
                    raise RuntimeError(f"Unexpected index on {table}")
                op.drop_index(name, table_name=table)
        op.drop_column(table, "workspace_uid")

    for logical, specs in UNIQUES.items():
        for suffix, columns in specs:
            op.create_unique_constraint(
                "uq_mainsequence_crm__" + suffix, PREFIX + logical, list(columns)
            )
    for logical, specs in FOREIGN_KEYS.items():
        for suffix, columns, target, target_columns in specs:
            op.create_foreign_key(
                "fk_mainsequence_crm__" + suffix,
                PREFIX + logical,
                PREFIX + target,
                list(columns),
                list(target_columns),
                ondelete="RESTRICT",
            )
    for logical, specs in INDEXES.items():
        for spec in specs:
            suffix, columns = spec[:2]
            predicate = spec[2] if len(spec) == 3 else None
            name = (
                ("uq_" if suffix == "affiliation_primary_current" else "ix_")
                + "mainsequence_crm__"
                + suffix
            )
            op.create_index(
                name,
                PREFIX + logical,
                list(columns),
                unique=suffix in {"affiliation_primary_current", "pipeline_default"},
                **({"postgresql_where": sa.text(predicate)} if predicate else {}),
            )
    op.drop_table(PREFIX + "workspace")
    if not count:
        pipeline_uid = uuid.uuid4()
        bind.execute(
            sa.text(
                f'INSERT INTO "{PREFIX}pipeline" '
                "(uid,created_at,updated_at,created_by_uid,updated_by_uid,version,name,is_default,board_version) "
                "VALUES (:uid,NOW(),NOW(),NULL,NULL,1,'Sales',TRUE,1)"
            ),
            {"uid": pipeline_uid},
        )
        for position, (key, label, outcome) in enumerate(
            (
                ("new", "New", "open"),
                ("qualified", "Qualified", "open"),
                ("proposal", "Proposal", "open"),
                ("negotiation", "Negotiation", "open"),
                ("won", "Won", "won"),
                ("lost", "Lost", "lost"),
            )
        ):
            bind.execute(
                sa.text(
                    f'INSERT INTO "{PREFIX}stage" '
                    "(uid,created_at,updated_at,created_by_uid,updated_by_uid,version,pipeline_uid,key,label,position,outcome,is_active) "
                    "VALUES (:uid,NOW(),NOW(),NULL,NULL,1,:pipeline_uid,:key,:label,:position,:outcome,TRUE)"
                ),
                {
                    "uid": uuid.uuid4(),
                    "pipeline_uid": pipeline_uid,
                    "key": key,
                    "label": label,
                    "position": position,
                    "outcome": outcome,
                },
            )


def downgrade() -> None:
    """The removed application tenant cannot be reconstructed safely."""
    raise RuntimeError("CRM workspace-scope removal is intentionally irreversible")
