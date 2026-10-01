"""Regression checks for authored Alembic revisions."""

from __future__ import annotations

import importlib
from types import SimpleNamespace


def test_affiliation_backfill_has_no_accidental_sqlalchemy_bind_parameters(monkeypatch):
    revision = importlib.import_module(
        "src.crm.migrations.versions.mainsequence_crm.0002_add_contact_company_affiliations"
    )
    statements = []
    monkeypatch.setattr(
        revision,
        "op",
        SimpleNamespace(
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
