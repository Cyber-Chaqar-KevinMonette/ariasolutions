"""Tests for income_ledger.py — Kevin, 2026-07-25: "make income earned a
real metric too, but only updates on verified income received." Verifies
the ledger only ever accepts a real charge id (never a bare amount) and
is idempotent by charge id (a re-poll of Stripe never double-counts)."""
from __future__ import annotations

import pytest

from sovereign_agent.income_ledger import (
    is_recorded,
    record_income,
    recent_events,
    total_income_cents,
)


def test_record_income_persists_and_totals(tmp_path):
    record_income("ch_1", 2500, data_dir=tmp_path)
    record_income("ch_2", 500, data_dir=tmp_path)
    assert total_income_cents(tmp_path) == 3000


def test_record_income_requires_a_real_charge_id(tmp_path):
    with pytest.raises(ValueError):
        record_income("", 2500, data_dir=tmp_path)


def test_record_income_requires_a_positive_amount(tmp_path):
    with pytest.raises(ValueError):
        record_income("ch_1", 0, data_dir=tmp_path)
    with pytest.raises(ValueError):
        record_income("ch_1", -500, data_dir=tmp_path)


def test_record_income_is_idempotent_by_charge_id(tmp_path):
    first = record_income("ch_dup", 1200, data_dir=tmp_path)
    second = record_income("ch_dup", 1200, data_dir=tmp_path)
    assert first is not None
    assert second is None  # already recorded — never double-counted
    assert total_income_cents(tmp_path) == 1200


def test_is_recorded(tmp_path):
    assert not is_recorded("ch_1", tmp_path)
    record_income("ch_1", 500, data_dir=tmp_path)
    assert is_recorded("ch_1", tmp_path)


def test_total_income_cents_is_zero_before_any_record(tmp_path):
    assert total_income_cents(tmp_path) == 0


def test_recent_events_newest_first(tmp_path):
    record_income("ch_1", 500, data_dir=tmp_path)
    record_income("ch_2", 1000, data_dir=tmp_path)
    recent = recent_events(n=5, data_dir=tmp_path)
    assert [e.charge_id for e in recent] == ["ch_2", "ch_1"]


def test_corrupt_line_never_breaks_the_read(tmp_path):
    record_income("ch_1", 500, data_dir=tmp_path)
    path = tmp_path / "income_ledger.ndjson"
    with path.open("a", encoding="utf-8") as fh:
        fh.write("not json{{{\n")
    assert total_income_cents(tmp_path) == 500  # the bad line is skipped
