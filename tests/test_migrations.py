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
