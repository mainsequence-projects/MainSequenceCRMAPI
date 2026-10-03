"""Regression checks for authored Alembic revisions."""

from __future__ import annotations

import hashlib
import importlib
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from alembic import command

from metatables.migrations import alembic_config_for_provider
from metatables.migrations.connection import migration_engine
from src.crm.migrations import migration


def _postgresql_bind():
    return SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))


def test_affiliation_backfill_has_no_accidental_sqlalchemy_bind_parameters(monkeypatch):
    revision = importlib.import_module(
        "src.crm.migrations.versions.mainsequence_crm.0002_add_contact_company_affiliations"
    )
    statements = []
    monkeypatch.setattr(
        revision,
        "op",
        SimpleNamespace(
            get_bind=_postgresql_bind,
            create_table=lambda *args, **kwargs: None,
            create_index=lambda *args, **kwargs: None,
            execute=statements.append,
        ),
    )
    revision.upgrade()
    assert len(statements) == 1
    assert not statements[0]._bindparams
    assert "-initial-company-affiliation" in statements[0].text


def test_receipt_removal_revision_drops_only_obsolete_table(monkeypatch):
    revision = importlib.import_module(
        "src.crm.migrations.versions.mainsequence_crm.0003_remove_command_receipts"
    )
    operations = []
    monkeypatch.setattr(
        revision,
        "op",
        SimpleNamespace(
            drop_index=lambda *args, **kwargs: operations.append(("index", args, kwargs)),
            drop_table=lambda *args, **kwargs: operations.append(("table", args, kwargs)),
        ),
    )
    revision.upgrade()
    assert operations == [
        (
            "index",
            ("ix_mainsequence_crm__command_receipt_1",),
            {"table_name": "mainsequence_crm__command_receipt"},
        ),
        ("table", ("mainsequence_crm__command_receipt",), {}),
    ]


def test_interaction_participant_migration_backfills_before_removing_primary_contact(monkeypatch):
    revision = importlib.import_module(
        "src.crm.migrations.versions.mainsequence_crm.0009_interaction_participants"
    )
    operations = []
    monkeypatch.setattr(revision, "op", SimpleNamespace(
        get_bind=_postgresql_bind,
        add_column=lambda *a, **k: operations.append(("add_column", a, k)),
        execute=lambda statement: operations.append(("execute", statement.text)),
        create_check_constraint=lambda *a, **k: operations.append(("check", a, k)),
        drop_index=lambda *a, **k: operations.append(("drop_index", a, k)),
        drop_constraint=lambda *a, **k: operations.append(("drop_constraint", a, k)),
        drop_column=lambda *a, **k: operations.append(("drop_column", a, k)),
        alter_column=lambda *a, **k: operations.append(("alter_column", a, k)),
    ))
    revision.upgrade()
    assert [step[0] for step in operations] == [
        "add_column", "execute", "check", "check", "drop_index",
        "drop_constraint", "drop_column", "alter_column",
    ]
    assert "jsonb_build_array" in operations[1][1]
    assert "contact_uid" in operations[1][1]
    assert operations[-1][2]["nullable"] is True


WORKSPACE = uuid.UUID("11111111-1111-4111-8111-111111111111")
COMPANY = uuid.UUID("22222222-2222-4222-8222-222222222222")
CONTACT = uuid.UUID("33333333-3333-4333-8333-333333333333")
INTERACTION = uuid.UUID("55555555-5555-4555-8555-555555555555")
LINKEDIN = "https://www.linkedin.com/in/ada"


def _table(name, /, **columns):
    return sa.table(name, *(sa.column(key, kind) for key, kind in columns.items()))


@pytest.mark.filterwarnings("error::UserWarning")  # A batch rebuild that drops a CHECK warns.
def test_revisions_upgrade_and_downgrade_on_the_local_sqlite_runtime(tmp_path):
    """Run the whole history through MetaTables' Alembic env and SQLite rules.

    Legacy rows seeded at 0001 and 0008 exercise every data backfill.
    """
    when = datetime(2026, 9, 1, 12, tzinfo=timezone.utc)
    U, T, J, S, I = sa.Uuid(), sa.DateTime(timezone=True), sa.JSON(), sa.String(), sa.BigInteger()
    config = alembic_config_for_provider(
        migration, sqlalchemy_url=f"sqlite:///{tmp_path / 'crm.sqlite'}"
    )
    with migration_engine(config) as engine, engine.connect() as connection:
        config.attributes["connection"] = connection

        def migrate(operation, target):
            getattr(command, operation)(config, target)
            if connection.in_transaction():
                connection.commit()

        def one(statement):
            row = connection.execute(statement).one()
            connection.rollback()
            return row

        migrate("upgrade", "0001")
        connection.execute(_table(
            "mainsequence_crm__workspace", uid=U, name=S, default_currency=S, timezone=S,
            configuration=J, configuration_version=I, mutation_epoch=I, created_at=T,
            updated_at=T,
        ).insert().values(
            uid=WORKSPACE, name="Legacy", default_currency="EUR", timezone="UTC",
            configuration={"company_sectors": []}, configuration_version=3, mutation_epoch=0,
            created_at=when, updated_at=when,
        ))
        connection.execute(_table(
            "mainsequence_crm__company", uid=U, workspace_uid=U, created_at=T, updated_at=T,
            version=I, name=S, context_links=J,
        ).insert().values(
            uid=COMPANY, workspace_uid=WORKSPACE, created_at=when, updated_at=when, version=1,
            name="Acme", context_links=[],
        ))
        connection.execute(_table(
            "mainsequence_crm__contact", uid=U, workspace_uid=U, created_at=T, updated_at=T,
            version=I, company_uid=U, first_name=S, linkedin_url=S, emails=J, phones=J,
        ).insert().values(
            uid=CONTACT, workspace_uid=WORKSPACE, created_at=when, updated_at=when, version=1,
            company_uid=COMPANY, first_name="Ada", linkedin_url=LINKEDIN, emails=[], phones=[],
        ))
        connection.commit()
        migrate("upgrade", "0008")
        interaction = _table(
            "mainsequence_crm__interaction", uid=U, company_uid=U, contact_uid=U, subject=S,
            kind=S, status=S, created_at=T, updated_at=T, version=I, participants=J,
        )
        connection.execute(interaction.insert().values(
            uid=INTERACTION, company_uid=COMPANY, contact_uid=CONTACT, subject="Intro",
            kind="call", status="planned", created_at=when, updated_at=when, version=1,
        ))
        connection.commit()
        migrate("upgrade", "head")

        version = sa.text("SELECT version_num FROM mainsequence_crm__alembic_version")
        assert one(version).version_num == "0009"
        settings = _table("mainsequence_crm__settings", name=S, default_currency=S)
        assert tuple(one(sa.select(settings))) == ("Legacy", "EUR")
        affiliation = _table("mainsequence_crm__contact_company_affiliation", uid=U)
        assert one(sa.select(affiliation)).uid == uuid.UUID(
            hashlib.md5(f"{CONTACT}-initial-company-affiliation".encode()).hexdigest()
        )
        contact = _table("mainsequence_crm__contact", socials=J)
        assert one(sa.select(contact)).socials == {"linkedin": LINKEDIN}
        assert one(sa.select(interaction.c.participants)).participants == [
            {"contact_uid": str(CONTACT), "email": None, "display_name": None, "role": "attendee"}
        ]
        # The portable CHECK forms are enforced, including the ones 0009 rebuilt.
        for statement in (
            "UPDATE mainsequence_crm__settings SET default_currency='eur'",
            "UPDATE mainsequence_crm__interaction SET kind='letter'",
            "UPDATE mainsequence_crm__interaction SET participants='{}'",
        ):
            with pytest.raises(sa.exc.IntegrityError):
                connection.execute(sa.text(statement))
            connection.rollback()

        migrate("downgrade", "0008")
        assert one(sa.select(interaction.c.contact_uid)).contact_uid == CONTACT
        migrate("downgrade", "0004")
        legacy_contact = _table("mainsequence_crm__contact", linkedin_url=S)
        assert one(sa.select(legacy_contact)).linkedin_url == LINKEDIN
        migrate("upgrade", "head")
        assert one(version).version_num == "0009"
        assert one(sa.select(contact)).socials == {"linkedin": LINKEDIN}
