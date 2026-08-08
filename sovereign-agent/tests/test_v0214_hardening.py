"""
test_v0214_hardening.py — Adversarial regression tests for the v0.2.14 patches.

Each test class corresponds to a specific bug found during the v0.2.14
post-release audit. The tests exist so the bug cannot silently come back.

Audit findings:
  RED-1   Multi-currency math silently fungible (financial.py)
  RED-2   _find_by_idempotency LIKE wildcard injection (channels.py)
  YELLOW-1  Race window between idempotency SELECT and ledger INSERT
  YELLOW-2  Bare except: pass swallowed event-emit failures
  YELLOW-3  protocol_zero.is_armed() called with stale arg signature
  GREEN-1   Atom-id microsecond clock could collide under burst writes

Test isolation comes from the autouse ``isolated_paths`` fixture in
``tests/conftest.py`` — we don't override it here.
"""
from __future__ import annotations

import sqlite3

import pytest


def _open_conn():
    """Open a fresh atoms DB. The conftest fixture ensures a unique path per test."""
    from sovereign_agent.db import open_atoms_db
    return open_atoms_db()


# ─── RED-2: idempotency exactness ───────────────────────────────────────────


class TestIdempotencyExactness:
    """The LIKE-on-JSON-string idempotency lookup matched SQL wildcards.

    A string like ``probe_2026`` would falsely match ``probeX2026``
    because ``_`` is the LIKE single-char wildcard. Equivalent for ``%``.
    Fix: use json_extract for exact-match equality.
    """

    def test_underscore_does_not_wildcard(self):
        from sovereign_agent.mem_channels.lessons import LessonsChannel
        from sovereign_agent.channels import _find_by_idempotency

        conn = _open_conn()
        ch = LessonsChannel(conn)
        a1 = ch.write_atom(summary="A", idempotency_id="lesson-2026-05-10")

        # _ in SQL LIKE matches any single char; an exact-match impl returns None.
        result = _find_by_idempotency(conn, "lessons", "lesson-2026_05_10")
        assert result is None, (
            "underscore should not behave as a SQL LIKE wildcard "
            f"(got false-positive match on {a1!r})"
        )

    def test_percent_does_not_wildcard(self):
        from sovereign_agent.mem_channels.lessons import LessonsChannel
        from sovereign_agent.channels import _find_by_idempotency

        conn = _open_conn()
        ch = LessonsChannel(conn)
        ch.write_atom(summary="C", idempotency_id="lesson-2026-special")

        # Even more aggressive: % matches any string of chars.
        result = _find_by_idempotency(
            conn, "lessons", "lesson-%-special",
        )
        assert result is None, (
            "percent should not behave as a SQL LIKE wildcard"
        )

    def test_exact_match_still_works(self):
        from sovereign_agent.mem_channels.lessons import LessonsChannel
        from sovereign_agent.channels import _find_by_idempotency

        conn = _open_conn()
        ch = LessonsChannel(conn)
        a = ch.write_atom(summary="X", idempotency_id="exact-id-001")

        # Exact match returns the existing atom (idempotency contract).
        result = _find_by_idempotency(conn, "lessons", "exact-id-001")
        assert result == a

    def test_idempotent_retry_returns_same_atom(self):
        """The whole point of idempotency: retry → same id."""
        from sovereign_agent.mem_channels.lessons import LessonsChannel
        conn = _open_conn()
        ch = LessonsChannel(conn)
        a1 = ch.write_atom(summary="L", idempotency_id="retry-test")
        a2 = ch.write_atom(summary="L (retry)", idempotency_id="retry-test")
        assert a1 == a2


# ─── RED-1: currency lock ───────────────────────────────────────────────────


class TestCurrencyLock:
    """The ledger silently summed USD and EUR. Fix: lock currency per project."""

    def test_first_entry_pins_currency(self):
        from sovereign_agent.mem_channels.financial import FinancialChannel
        conn = _open_conn()
        fc = FinancialChannel(conn)
        fc.record(project="probe-cur-1", kind="invest", amount=100.0,
                  currency="USD", idempotency_id="cur-1")
        bal = fc.project_balance("probe-cur-1")
        assert bal.currency == "USD"

    def test_mismatched_currency_raises(self):
        from sovereign_agent.mem_channels.financial import (
            FinancialChannel, CurrencyMismatchError,
        )
        conn = _open_conn()
        fc = FinancialChannel(conn)
        fc.record(project="probe-cur-2", kind="invest", amount=100.0,
                  currency="USD", idempotency_id="cur-2a")
        with pytest.raises(CurrencyMismatchError) as info:
            fc.record(project="probe-cur-2", kind="earn", amount=50.0,
                      currency="EUR", idempotency_id="cur-2b")
        msg = str(info.value)
        assert "USD" in msg and "EUR" in msg

    def test_same_currency_ok_after_lock(self):
        from sovereign_agent.mem_channels.financial import FinancialChannel
        conn = _open_conn()
        fc = FinancialChannel(conn)
        fc.record(project="probe-cur-3", kind="invest", amount=100.0,
                  currency="USD", idempotency_id="cur-3a")
        fc.record(project="probe-cur-3", kind="earn", amount=200.0,
                  currency="USD", idempotency_id="cur-3b")
        bal = fc.project_balance("probe-cur-3")
        assert bal.invested == 100.0
        assert bal.earned == 200.0
        assert bal.roi_ratio == 2.0
        assert bal.currency == "USD"

    def test_currency_normalization(self):
        """Lower-case 'usd' and ' USD ' both store as 'USD'."""
        from sovereign_agent.mem_channels.financial import FinancialChannel
        conn = _open_conn()
        fc = FinancialChannel(conn)
        fc.record(project="probe-cur-4", kind="invest", amount=10.0,
                  currency="usd", idempotency_id="cur-4a")
        # Re-using the same project with a case-different but equivalent
        # ticker should NOT raise — it normalises to USD.
        fc.record(project="probe-cur-4", kind="earn", amount=5.0,
                  currency=" USD ", idempotency_id="cur-4b")
        bal = fc.project_balance("probe-cur-4")
        assert bal.currency == "USD"

    def test_invalid_currency_format_rejected(self):
        from sovereign_agent.mem_channels.financial import FinancialChannel
        conn = _open_conn()
        fc = FinancialChannel(conn)
        for bad in ("US", "TOOLONGCURRENCY", "us1", "", "  "):
            with pytest.raises(ValueError):
                fc.record(project="probe-cur-5", kind="invest", amount=1.0,
                          currency=bad,
                          idempotency_id=f"cur-5-{bad!r}")


# ─── YELLOW-1: race safety / transactional record ──────────────────────────


class TestRaceSafety:
    """record() must be atomic: SELECT-then-INSERT runs under BEGIN IMMEDIATE."""

    def test_record_runs_in_transaction(self):
        """If the ledger INSERT fails after the companion atom is written,
        the rollback must remove the orphaned companion atom too.

        We use SQLite's set_authorizer hook to deny the financial_ledger
        INSERT at SQL-prepare time — this is more robust than
        monkeypatching the read-only Connection.execute attribute.
        """
        from sovereign_agent.mem_channels.financial import FinancialChannel
        conn = _open_conn()
        fc = FinancialChannel(conn)

        def deny_ledger_insert(action, arg1, arg2, db_name, source):
            if action == sqlite3.SQLITE_INSERT and arg1 == "financial_ledger":
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        conn.set_authorizer(deny_ledger_insert)
        try:
            with pytest.raises(sqlite3.DatabaseError):
                fc.record(project="probe-race", kind="invest", amount=1.0,
                          idempotency_id="race-1")
        finally:
            conn.set_authorizer(None)

        # Verify NO atom was orphaned — the rollback must cascade.
        atoms = conn.execute(
            "SELECT COUNT(*) FROM atoms WHERE type = 'financial' "
            "AND json_extract(scope_tags, '$.idempotency_id') = ?",
            ("race-1",),
        ).fetchone()[0]
        assert atoms == 0, "rolled-back transaction left an orphaned atom"

    def test_idempotent_replay_after_partial_failure(self):
        """A retry with the same idempotency_id after a successful write
        must return the existing entry — no second atom, no second ledger row."""
        from sovereign_agent.mem_channels.financial import FinancialChannel
        conn = _open_conn()
        fc = FinancialChannel(conn)

        e1 = fc.record(project="probe-replay", kind="invest", amount=42.0,
                       idempotency_id="replay-1")
        e2 = fc.record(project="probe-replay", kind="invest", amount=42.0,
                       idempotency_id="replay-1")
        assert e1.entry_id == e2.entry_id
        assert e1.atom_id == e2.atom_id

        n_atoms = conn.execute(
            "SELECT COUNT(*) FROM atoms WHERE type = 'financial' "
            "AND json_extract(scope_tags, '$.idempotency_id') = ?",
            ("replay-1",),
        ).fetchone()[0]
        n_rows = conn.execute(
            "SELECT COUNT(*) FROM financial_ledger WHERE idempotency_id = ?",
            ("replay-1",),
        ).fetchone()[0]
        assert n_atoms == 1
        assert n_rows == 1


# ─── ISO timestamp validation ───────────────────────────────────────────────


class TestTimestampValidation:
    """occurred_at strings are compared lexicographically. Format drift
    would break every ranking."""

    def test_default_occurred_at_valid(self):
        from sovereign_agent.mem_channels.financial import FinancialChannel
        conn = _open_conn()
        fc = FinancialChannel(conn)
        e = fc.record(project="probe-ts-1", kind="invest", amount=1.0,
                      idempotency_id="ts-1")
        # Must round-trip through the validator.
        assert e.occurred_at.endswith("Z")

    def test_naive_timestamp_rejected(self):
        from sovereign_agent.mem_channels.financial import FinancialChannel
        conn = _open_conn()
        fc = FinancialChannel(conn)
        with pytest.raises(ValueError):
            fc.record(project="probe-ts-2", kind="invest", amount=1.0,
                      idempotency_id="ts-2",
                      occurred_at="2026-05-10 10:00:00")  # no T, no Z

    def test_non_utc_offset_rejected(self):
        from sovereign_agent.mem_channels.financial import FinancialChannel
        conn = _open_conn()
        fc = FinancialChannel(conn)
        with pytest.raises(ValueError):
            fc.record(project="probe-ts-3", kind="invest", amount=1.0,
                      idempotency_id="ts-3",
                      occurred_at="2026-05-10T10:00:00-05:00")

    def test_plus_zero_zero_offset_accepted(self):
        from sovereign_agent.mem_channels.financial import FinancialChannel
        conn = _open_conn()
        fc = FinancialChannel(conn)
        e = fc.record(project="probe-ts-4", kind="invest", amount=1.0,
                      idempotency_id="ts-4",
                      occurred_at="2026-05-10T10:00:00+00:00")
        assert "+00:00" in e.occurred_at


# ─── Audit / reconciliation ─────────────────────────────────────────────────


class TestLedgerAudit:
    """The audit() method is the operator's integrity guarantor."""

    def test_clean_ledger_audits_clean(self):
        from sovereign_agent.mem_channels.financial import FinancialChannel
        conn = _open_conn()
        fc = FinancialChannel(conn)
        fc.record(project="audit-clean", kind="invest", amount=100.0,
                  idempotency_id="audit-1")
        fc.record(project="audit-clean", kind="earn", amount=150.0,
                  idempotency_id="audit-2")
        result = fc.audit()
        assert result.ok
        assert result.ledger_rows == 2
        assert result.violations == []

    def test_audit_detects_orphaned_atom(self):
        from sovereign_agent.mem_channels.financial import FinancialChannel
        conn = _open_conn()
        fc = FinancialChannel(conn)
        fc.record(project="audit-orphan", kind="invest", amount=10.0,
                  idempotency_id="orphan-1")

        # Manually delete the companion atom to simulate corruption.
        conn.execute("DELETE FROM atoms WHERE type = 'financial'")
        conn.commit()

        result = fc.audit()
        assert not result.ok
        assert any("companion atom" in v for v in result.violations)
        assert len(result.orphaned_atoms) == 1

    def test_audit_detects_dangling_revert(self):
        from sovereign_agent.mem_channels.financial import FinancialChannel
        conn = _open_conn()
        fc = FinancialChannel(conn)

        # Hand-craft a revert pointing at a non-existent entry. We must
        # disable FK enforcement to inject the corruption — the audit is
        # the second line of defence, in case data was migrated from a
        # version that didn't enforce FKs or a FK-off restore happens.
        conn.execute("PRAGMA foreign_keys = OFF")
        try:
            conn.execute(
                "INSERT INTO financial_ledger("
                "entry_id, project, kind, amount, currency, "
                "occurred_at, recorded_at, idempotency_id, "
                "reverts_entry_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                ("le-fake", "audit-revert", "revert", 5.0, "USD",
                 "2026-05-10T00:00:00.000000Z", "2026-05-10T00:00:00.000000Z",
                 "fake-revert", "le-does-not-exist"),
            )
            conn.commit()
        finally:
            conn.execute("PRAGMA foreign_keys = ON")

        result = fc.audit()
        assert not result.ok
        assert any("does not exist" in v for v in result.violations)

    def test_audit_detects_currency_mix_via_backdoor(self):
        """If a future bug allowed mixed-currency rows past the lock, the
        audit must still flag it."""
        from sovereign_agent.mem_channels.financial import FinancialChannel
        conn = _open_conn()
        fc = FinancialChannel(conn)

        # Backdoor: write directly to the table to simulate a corrupted state.
        for i, cur in enumerate(("USD", "EUR")):
            conn.execute(
                "INSERT INTO financial_ledger("
                "entry_id, project, kind, amount, currency, "
                "occurred_at, recorded_at, idempotency_id) VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?)",
                (f"le-mix-{i}", "audit-mix", "invest", 10.0, cur,
                 "2026-05-10T00:00:00.000000Z",
                 "2026-05-10T00:00:00.000000Z", f"mix-{i}"),
            )
        conn.commit()

        result = fc.audit()
        assert not result.ok
        assert "audit-mix" in result.currency_mixed_projects


# ─── protocol_zero call-site signature ──────────────────────────────────────


class TestProtocolZeroSignature:
    """is_armed() takes no arguments. Calling it with one is a runtime crash
    waiting to happen during a halt scenario — the WORST time to find a bug."""

    def test_is_armed_no_args(self):
        from sovereign_agent import protocol_zero
        # Call with zero args; must not raise.
        assert isinstance(protocol_zero.is_armed(), bool)

    def test_is_armed_with_arg_raises(self):
        from sovereign_agent import protocol_zero
        with pytest.raises(TypeError):
            protocol_zero.is_armed("not-a-valid-arg")  # type: ignore[call-arg]


# ─── Atom-id collision safety ───────────────────────────────────────────────


class TestAtomIdCollisionSafety:
    """Non-idempotent atoms previously used summary+microsecond as seed.
    Two writes in the same microsecond would collide under INSERT OR IGNORE."""

    def test_burst_writes_dont_collide(self):
        """Write 100 atoms with the same summary as fast as possible. All
        should land. With the old microsecond-seeded fallback, some would
        be silently dropped."""
        from sovereign_agent.mem_channels.lessons import LessonsChannel
        conn = _open_conn()
        ch = LessonsChannel(conn)
        ids = set()
        for _ in range(100):
            atom_id = ch.write_atom(summary="duplicate summary text")
            ids.add(atom_id)
        assert len(ids) == 100, (
            f"only {len(ids)} of 100 burst writes survived — "
            "atom_id collision under INSERT OR IGNORE"
        )

        n_rows = conn.execute(
            "SELECT COUNT(*) FROM atoms WHERE type = 'lessons'"
        ).fetchone()[0]
        assert n_rows == 100


# ─── Audit clean against a freshly-built ledger of every shape ──────────────


class TestEndToEndIntegrity:
    """A real workload should audit clean."""

    def test_realistic_workload_audits_clean(self):
        from sovereign_agent.mem_channels.financial import FinancialChannel
        conn = _open_conn()
        fc = FinancialChannel(conn)

        # Two projects, USD only, with reverts.
        fc.record(project="alpha", kind="invest", amount=500.0,
                  idempotency_id="alpha-i1", note="initial seed")
        fc.record(project="alpha", kind="earn", amount=200.0,
                  idempotency_id="alpha-e1", note="contract a")
        e_bad = fc.record(project="alpha", kind="earn", amount=999.0,
                          idempotency_id="alpha-e-typo", note="oops")
        fc.record(project="alpha", kind="revert", amount=999.0,
                  idempotency_id="alpha-e-typo-revert",
                  reverts_entry_id=e_bad.entry_id, note="undo typo")

        fc.record(project="beta", kind="invest", amount=1000.0,
                  idempotency_id="beta-i1")

        # Sanity check the math.
        alpha = fc.project_balance("alpha")
        assert alpha.invested == 500.0
        assert alpha.earned == 200.0  # 999 was reverted
        assert alpha.net == -300.0
        assert alpha.roi_ratio == pytest.approx(0.4)

        # Audit should pass.
        result = fc.audit()
        assert result.ok, result.render()
