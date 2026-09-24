"""Regression checks for migration and export wire-value invariants."""

from decimal import Decimal

import pytest

from src.crm.portability.normalization import (
    aware_timestamp,
    decimal_money,
    formula_safe_csv_cell,
    mapped_boolean,
    source_id,
    source_row_key,
)


def test_large_ids_and_decimal_money_never_use_binary_float():
    assert source_id(900719925474099312345) == "900719925474099312345"
    assert decimal_money(Decimal("0.0001")) == "0.0001"
    for value in (True, 1.2):
        with pytest.raises(ValueError):
            source_id(value)
        with pytest.raises(ValueError):
            decimal_money(value)


def test_boolean_false_time_and_row_identity():
    assert mapped_boolean("FALSE", {"false": False}) is False
    assert aware_timestamp("2026-09-22T10:00:00+02:00") == "2026-09-22T08:00:00Z"
    with pytest.raises(ValueError):
        aware_timestamp("2026-09-22T10:00:00")
    assert source_row_key("a" * 64, "/notes/0") != source_row_key("a" * 64, "/notes/1")


def test_csv_formula_escape_is_export_only():
    assert formula_safe_csv_cell(" =SUM(A1)") == "' =SUM(A1)"
    assert formula_safe_csv_cell("normal") == "normal"
