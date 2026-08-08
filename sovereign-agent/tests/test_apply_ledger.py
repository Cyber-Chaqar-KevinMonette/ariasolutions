"""Tests for apply_ledger — the apply-system bookkeeping that prevents
re-applying the same thing twice unless it genuinely changed (newer
version / update / invariant). Kevin's reliability ask.
"""
from __future__ import annotations

from sovereign_agent.apply_ledger import (
    ApplyLedger,
    module_fingerprint,
    should_apply,
)


def _module(tmp_path, name="aria-thing", body="x = 1\n", apply="#!/bin/sh\necho hi\n"):
    m = tmp_path / name
    p = m / "payload" / "src" / "sovereign_agent" / "thing"
    p.mkdir(parents=True)
    (p / "__init__.py").write_text(body, encoding="utf-8")
    (m / "apply_thing.sh").write_text(apply, encoding="utf-8")
    return m


# ── fingerprint ──────────────────────────────────────────────────────────
def test_fingerprint_is_stable_for_identical_content(tmp_path):
    m1 = _module(tmp_path / "a", "aria-thing")
    m2 = _module(tmp_path / "b", "aria-thing")
    assert module_fingerprint(m1) == module_fingerprint(m2)


def test_fingerprint_changes_when_payload_changes(tmp_path):
    m = _module(tmp_path, "aria-thing", body="x = 1\n")
    fp1 = module_fingerprint(m)
    (m / "payload" / "src" / "sovereign_agent" / "thing" / "__init__.py").write_text(
        "x = 2  # updated\n", encoding="utf-8")
    assert module_fingerprint(m) != fp1


def test_fingerprint_changes_when_apply_script_changes(tmp_path):
    m = _module(tmp_path, "aria-thing")
    fp1 = module_fingerprint(m)
    (m / "apply_thing.sh").write_text("#!/bin/sh\necho DIFFERENT\n", encoding="utf-8")
    assert module_fingerprint(m) != fp1


# ── should_apply (pure decision) ─────────────────────────────────────────
def test_first_apply_proceeds():
    d = should_apply("aria-thing", "abc", prior=None)
    assert d.apply is True and d.reason == "first-apply"


def test_unchanged_is_skipped():
    d = should_apply("aria-thing", "abc", prior={"fingerprint": "abc"})
    assert d.apply is False and d.reason == "unchanged"


def test_changed_fingerprint_reapplies():
    d = should_apply("aria-thing", "NEW", prior={"fingerprint": "old"})
    assert d.apply is True and d.reason == "changed"


def test_force_always_applies_even_if_unchanged():
    d = should_apply("aria-thing", "abc", prior={"fingerprint": "abc"}, force=True)
    assert d.apply is True and d.reason == "forced"


# ── ApplyLedger (durable record) ─────────────────────────────────────────
def test_ledger_records_and_reads_back(tmp_path):
    led = ApplyLedger(tmp_path / "apply_ledger.json")
    assert led.last("aria-thing") is None
    led.record("aria-thing", "abc", version="0.1")
    e = led.last("aria-thing")
    assert e["fingerprint"] == "abc" and e["version"] == "0.1"


def test_ledger_decide_full_cycle(tmp_path):
    m = _module(tmp_path, "aria-thing")
    led = ApplyLedger(tmp_path / "led.json")
    fp = module_fingerprint(m)

    # first time → apply
    assert led.decide("aria-thing", fp).apply is True
    led.record("aria-thing", fp)

    # same content again → skip
    assert led.decide("aria-thing", fp).apply is False

    # content changes → apply again (newer version)
    (m / "apply_thing.sh").write_text("#!/bin/sh\necho v2\n", encoding="utf-8")
    fp2 = module_fingerprint(m)
    d = led.decide("aria-thing", fp2)
    assert d.apply is True and d.reason == "changed"


def test_corrupt_ledger_never_blocks_an_apply(tmp_path):
    p = tmp_path / "led.json"
    p.write_text("{ not valid json", encoding="utf-8")
    led = ApplyLedger(p)
    # a corrupt ledger degrades to 'no prior' → apply proceeds, never crashes
    assert led.last("aria-thing") is None
    assert led.decide("aria-thing", "abc").apply is True


def test_history_is_retained_per_module(tmp_path):
    led = ApplyLedger(tmp_path / "led.json")
    led.record("aria-a", "1")
    led.record("aria-b", "1")
    led.record("aria-a", "2")
    assert len(led.history("aria-a")) == 2
    assert led.last("aria-a")["fingerprint"] == "2"
