"""
╔══════════════════════════════════════════════════════════════════════════╗
║  channels/financial.py — Per-project investment & earnings ledger        ║
║  v0.2.14 · MOS Authority Tier 3                                           ║
║                                                                           ║
║  Financial memory is the most consequential channel. It records what     ║
║  was put into each project (in dollars or any other currency) and what   ║
║  came out, with per-project lifetime accounting and ROI ranking.         ║
║                                                                           ║
║  Default invested = $0 per project until explicitly set. The system     ║
║  refuses to guess. If there is no record, there is no investment.       ║
║                                                                           ║
║  WRITE PATH IS TIER 3 (canon §22):                                       ║
║    • Every write requires an idempotency_id (canon §16)                  ║
║    • Every write is append-only — no edits, no deletes                  ║
║    • Reverting an entry requires writing a counter-entry                ║
║    • CLI writes pass through explicit operator confirmation             ║
║                                                                           ║
║  READ PATH IS TIER 0:                                                    ║
║    • Project balances, ROI rankings, trend analysis are all free        ║
║                                                                           ║
║  STORAGE                                                                 ║
║                                                                           ║
║  A dedicated SQLite table ``financial_ledger`` lives in atoms.db. Each  ║
║  ledger row also writes an atom into the ``financial`` channel so that ║
║  semantic recall finds financial events ("when did we invest in        ║
║  genesis-seeds?") through the standard memory_search.                  ║
║                                                                           ║
║  THE GOAL                                                                ║
║                                                                           ║
║  Aria can answer:                                                        ║
║    • What's the lifetime ROI on each project?                            ║
║    • Which project earned the most per dollar invested?                  ║
║    • Which project earned the most per day of effort?                    ║
║    • Where should we invest more time given current trajectories?       ║
║                                                                           ║
║  These answers fund more research. They also keep the operator honest   ║
║  about where the energy actually went.                                   ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import json
import re
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterator, Literal

from ..channels import ChannelSpec, MemoryChannel, register_channel


LedgerKind = Literal["invest", "earn", "revert"]


# ─── Strict ISO 8601 UTC validator ──────────────────────────────────────────
#
# The ledger compares `occurred_at` strings lexicographically when ranking
# events. That comparison is only correct if every value uses the SAME
# format, in UTC, with consistent precision. We accept exactly the format
# we emit (microseconds, "Z" suffix) plus the common variant from
# fromisoformat-friendly parsers; everything else is rejected so the
# operator can't slip a TZ-naive or differently-formatted string in.

_ISO_UTC_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    r"(?:\.\d{1,6})?"             # optional fractional seconds, 1-6 digits
    r"(?:Z|\+00:00)$"             # UTC suffix, Z or +00:00
)


def _validate_iso_utc(value: str, *, field: str) -> str:
    """Reject anything that isn't strict ISO 8601 UTC. Returns the value unchanged."""
    if not isinstance(value, str) or not _ISO_UTC_RE.match(value):
        raise ValueError(
            f"{field} must be ISO 8601 UTC "
            f"(YYYY-MM-DDTHH:MM:SS[.ffffff]Z); got {value!r}"
        )
    return value


# ─── Errors ─────────────────────────────────────────────────────────────────


class CurrencyMismatchError(ValueError):
    """Raised when a write would mix currencies on a single project.

    The first ledger entry on a project pins its currency. Subsequent
    writes must match. To switch currencies, use a different project
    name (e.g. ``genesis-seeds-eur``) — the ledger refuses to silently
    fungible-add USD and EUR.
    """


# ─── Ledger table bootstrap ────────────────────────────────────────────────


_LEDGER_DDL = """
CREATE TABLE IF NOT EXISTS financial_ledger (
    entry_id        TEXT PRIMARY KEY,                 -- deterministic from idempotency_id
    project         TEXT NOT NULL,                    -- project name (memory_namespaces grammar)
    kind            TEXT NOT NULL CHECK (kind IN ('invest', 'earn', 'revert')),
    amount          REAL NOT NULL CHECK (amount >= 0),
    currency        TEXT NOT NULL DEFAULT 'USD',
    note            TEXT,
    occurred_at     TEXT NOT NULL,                    -- ISO 8601 UTC, validated
    recorded_at     TEXT NOT NULL,                    -- ISO 8601 UTC, validated
    idempotency_id  TEXT NOT NULL UNIQUE,             -- MOS §16 contract
    atom_id         TEXT,                             -- companion atom in atoms.financial
    reverts_entry_id TEXT REFERENCES financial_ledger(entry_id)
) STRICT;

CREATE INDEX IF NOT EXISTS idx_ledger_project    ON financial_ledger(project);
CREATE INDEX IF NOT EXISTS idx_ledger_kind       ON financial_ledger(kind);
CREATE INDEX IF NOT EXISTS idx_ledger_occurred   ON financial_ledger(occurred_at);
CREATE INDEX IF NOT EXISTS idx_ledger_proj_curr  ON financial_ledger(project, currency);
"""


def ensure_ledger_schema(conn: sqlite3.Connection) -> None:
    """Idempotent — safe to call on every open."""
    conn.executescript(_LEDGER_DDL)
    conn.commit()


# ─── Channel ────────────────────────────────────────────────────────────────


@register_channel
class FinancialChannel(MemoryChannel):
    """Per-project investment & earnings ledger.

    Tier 3 writes — operator must confirm at the CLI before any
    invest/earn/revert is committed.
    """

    spec = ChannelSpec(
        name="financial",
        description=(
            "Per-project investment & earnings ledger. Append-only. "
            "Records dollars in/out with idempotency. ROI ranking surface."
        ),
        authority_tier=3,
        default_confidence=0.99,        # ledger entries are facts, not estimates
        requires_idempotency=True,      # MOS canon §16 — payments-grade
        introduced_in="0.2.14",
        voice="Quiet, precise, never speculative. Numbers are sacred.",
    )

    def __init__(self, conn: sqlite3.Connection):
        super().__init__(conn)
        ensure_ledger_schema(conn)

    # ── Helpers ───────────────────────────────────────────────────────

    @contextmanager
    def _writer_tx(self) -> Iterator[None]:
        """BEGIN IMMEDIATE around a write so SELECT-then-INSERT is atomic.

        Without this, two concurrent record() calls with the same
        idempotency_id can both pass the existence check, write
        companion atoms, and then collide on the UNIQUE ledger insert —
        leaving an orphaned atom (regression test:
        ``test_v0214_hardening.py::TestRaceSafety``).

        Sets ``self._in_outer_tx`` so the base ``write_atom()`` skips
        its inner commit and the whole ``record()`` is one unit.
        """
        in_tx = self.conn.in_transaction
        if not in_tx:
            self.conn.execute("BEGIN IMMEDIATE")
        self._in_outer_tx = True
        try:
            yield
            if not in_tx:
                self.conn.commit()
        except Exception:
            if not in_tx:
                self.conn.rollback()
            raise
        finally:
            self._in_outer_tx = False

    def _project_currency(self, project: str) -> str | None:
        """The currency this project is locked to, or None if no entries yet."""
        row = self.conn.execute(
            "SELECT currency FROM financial_ledger WHERE project = ? LIMIT 1",
            (project,),
        ).fetchone()
        return row[0] if row else None

    # ── Core write API ────────────────────────────────────────────────

    def record(
        self,
        *,
        project: str,
        kind: LedgerKind,
        amount: float,
        idempotency_id: str,
        currency: str = "USD",
        note: str = "",
        occurred_at: str | None = None,
        reverts_entry_id: str | None = None,
    ) -> "LedgerEntry":
        """Record a ledger entry. Returns the LedgerEntry written.

        Idempotent on (project, idempotency_id). Re-recording the same
        idempotency_id returns the existing entry without modification.

        Currency-locked per project: the first entry pins the project's
        currency; subsequent writes that disagree raise
        ``CurrencyMismatchError``. To track the same effort in a
        different currency, use a different project name.

        Atomic: the existence check, companion atom write, and ledger
        insert all run under a single ``BEGIN IMMEDIATE`` transaction.

        Raises:
            ValueError: invalid amount, kind, currency, or occurred_at format.
            CurrencyMismatchError: currency mismatches the project's lock.
        """
        from ..memory_namespaces import normalize_project_name
        project = normalize_project_name(project)

        # ── Argument validation (no DB state touched) ─────────────────
        if kind not in ("invest", "earn", "revert"):
            raise ValueError(f"invalid kind: {kind!r}")
        if amount < 0:
            raise ValueError(f"amount must be ≥ 0; got {amount}")
        if kind == "revert" and not reverts_entry_id:
            raise ValueError("revert requires reverts_entry_id")
        if not isinstance(idempotency_id, str) or not idempotency_id.strip():
            raise ValueError("idempotency_id must be a non-empty string")
        if not isinstance(currency, str) or not currency.strip():
            raise ValueError("currency must be a non-empty string")
        currency = currency.strip().upper()
        if not re.match(r"^[A-Z]{3,10}$", currency):
            # ISO 4217 is 3 letters; we allow up to 10 to admit stablecoin
            # tickers (USDC, USDT) without locking out real tickers.
            raise ValueError(
                f"currency must be 3–10 uppercase letters; got {currency!r}"
            )

        recorded_at = _validate_iso_utc(_utc_now(), field="recorded_at")
        occurred_at = _validate_iso_utc(
            occurred_at or recorded_at, field="occurred_at",
        )

        with self._writer_tx():
            # ── Idempotency short-circuit (exact match) ───────────────
            existing_row = self.conn.execute(
                "SELECT entry_id FROM financial_ledger WHERE idempotency_id = ?",
                (idempotency_id,),
            ).fetchone()
            if existing_row:
                return self._load_entry(existing_row[0])

            # ── Currency lock ─────────────────────────────────────────
            project_currency = self._project_currency(project)
            if project_currency is not None and project_currency != currency:
                raise CurrencyMismatchError(
                    f"project {project!r} is locked to {project_currency!r}; "
                    f"refusing to record in {currency!r}. To track this in a "
                    f"different currency, use a separate project name."
                )

            # ── Mint deterministic entry_id from idempotency_id ───────
            import hashlib
            entry_id = (
                "le-" + hashlib.sha256(idempotency_id.encode("utf-8"))
                                  .hexdigest()[:20]
            )

            # ── Companion atom (semantic recall surface) ──────────────
            atom_summary = (
                f"{kind.upper()} {amount:.2f} {currency} on {project}"
                f"{' — ' + note if note else ''}"
            )
            atom_id = self.write_atom(
                summary=atom_summary,
                content={
                    "project": project, "kind": kind,
                    "amount": amount, "currency": currency,
                    "note": note, "occurred_at": occurred_at,
                    "reverts_entry_id": reverts_entry_id,
                },
                confidence=self.spec.default_confidence,
                idempotency_id=idempotency_id,
                extra_scope={"projects": [project]},
                actor="financial-ledger",
            )

            # ── Ledger row ────────────────────────────────────────────
            self.conn.execute(
                "INSERT INTO financial_ledger("
                "entry_id, project, kind, amount, currency, note, "
                "occurred_at, recorded_at, idempotency_id, atom_id, "
                "reverts_entry_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (entry_id, project, kind, amount, currency, note,
                 occurred_at, recorded_at, idempotency_id, atom_id,
                 reverts_entry_id),
            )

        # ── Observability event (outside the tx — best-effort) ────────
        try:
            from ..events import emit_event
            emit_event(
                f"finance-{kind}-d", plane="data",
                trace_id=f"finance:{project}:{entry_id}",
                payload={
                    "entry_id": entry_id, "project": project,
                    "kind": kind, "amount": amount, "currency": currency,
                    "idempotency_id": idempotency_id,
                },
            )
        except Exception as exc:  # noqa: BLE001
            _log_emit_failure("finance-event", exc)

        return LedgerEntry(
            entry_id=entry_id, project=project, kind=kind,
            amount=amount, currency=currency, note=note,
            occurred_at=occurred_at, recorded_at=recorded_at,
            idempotency_id=idempotency_id, atom_id=atom_id,
            reverts_entry_id=reverts_entry_id,
        )

    def _load_entry(self, entry_id: str) -> "LedgerEntry":
        row = self.conn.execute(
            "SELECT entry_id, project, kind, amount, currency, note, "
            "occurred_at, recorded_at, idempotency_id, atom_id, "
            "reverts_entry_id FROM financial_ledger WHERE entry_id = ?",
            (entry_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"no such ledger entry: {entry_id}")
        return LedgerEntry(*row)

    # ── Aggregations / queries ────────────────────────────────────────

    def project_balance(self, project: str) -> "ProjectBalance":
        """Lifetime totals for one project. Defaults: $0 invested, $0 earned."""
        from ..memory_namespaces import normalize_project_name
        project = normalize_project_name(project)
        rows = self.conn.execute(
            "SELECT kind, amount, currency, occurred_at FROM financial_ledger "
            "WHERE project = ? AND reverts_entry_id IS NULL",
            (project,),
        ).fetchall()

        invested = 0.0
        earned = 0.0
        currencies: set[str] = set()
        first_event: str | None = None
        last_event: str | None = None

        for kind, amount, currency, occurred_at in rows:
            currencies.add(currency)
            if kind == "invest":
                invested += float(amount)
            elif kind == "earn":
                earned += float(amount)
            if first_event is None or occurred_at < first_event:
                first_event = occurred_at
            if last_event is None or occurred_at > last_event:
                last_event = occurred_at

        # Apply reverts (negate matching kind).
        revert_rows = self.conn.execute(
            "SELECT a.kind, a.amount FROM financial_ledger a "
            "JOIN financial_ledger b ON b.reverts_entry_id = a.entry_id "
            "WHERE a.project = ?",
            (project,),
        ).fetchall()
        for kind, amount in revert_rows:
            if kind == "invest":
                invested -= float(amount)
            elif kind == "earn":
                earned -= float(amount)

        return ProjectBalance(
            project=project,
            invested=invested, earned=earned,
            net=earned - invested,
            roi_ratio=(earned / invested) if invested > 0 else None,
            currency=", ".join(sorted(currencies)) if currencies else "USD",
            first_event=first_event, last_event=last_event,
            entry_count=len(rows),
        )

    def list_projects(self) -> list[str]:
        """All projects with at least one ledger entry."""
        rows = self.conn.execute(
            "SELECT DISTINCT project FROM financial_ledger ORDER BY project"
        ).fetchall()
        return [r[0] for r in rows]

    def ranking(self, *, by: Literal["roi", "net", "earned", "velocity"] = "roi") -> list["ProjectBalance"]:
        """All projects ranked by chosen metric.

        - 'roi': earnings / investment (None at 0 invested → sorted last)
        - 'net': earnings − investment
        - 'earned': lifetime earnings (raw)
        - 'velocity': earnings per day-since-first-event
        """
        balances = [self.project_balance(p) for p in self.list_projects()]

        def _key(pb: ProjectBalance) -> tuple[int, float]:
            # Primary key returns (priority, score) where -1 priority for None/0 cases
            # so they sort last.
            if by == "roi":
                if pb.roi_ratio is None:
                    return (1, 0.0)
                return (0, -pb.roi_ratio)  # negative for descending
            if by == "net":
                return (0, -pb.net)
            if by == "earned":
                return (0, -pb.earned)
            if by == "velocity":
                v = pb.velocity_per_day()
                if v is None:
                    return (1, 0.0)
                return (0, -v)
            return (0, 0.0)

        balances.sort(key=_key)
        return balances

    def hydrate(self, atom_id: str) -> dict[str, Any]:
        """Attach the corresponding ledger entry to a recall hit."""
        base = super().hydrate(atom_id)
        row = self.conn.execute(
            "SELECT entry_id, project, kind, amount, currency, "
            "occurred_at FROM financial_ledger WHERE atom_id = ?",
            (atom_id,),
        ).fetchone()
        if row:
            base["ledger_entry"] = {
                "entry_id": row[0], "project": row[1], "kind": row[2],
                "amount": row[3], "currency": row[4],
                "occurred_at": row[5],
            }
        return base

    # ── Audit / reconciliation ────────────────────────────────────────

    def audit(self) -> "LedgerAudit":
        """Verify ledger integrity. Returns a LedgerAudit report.

        Checks performed:
          1. Every ledger row has a companion atom in the ``financial`` channel.
          2. Every revert row points at an existing entry_id.
          3. No project mixes currencies (currency-lock invariant).
          4. Every entry_id is a deterministic SHA hash of its idempotency_id.
          5. occurred_at and recorded_at are valid ISO 8601 UTC.

        A clean audit returns ``LedgerAudit(ok=True, ...)``. Any
        violation populates ``violations`` and sets ``ok=False``. The
        audit is read-only — it never mutates the ledger.
        """
        violations: list[str] = []
        orphaned_atoms: list[str] = []
        orphaned_reverts: list[str] = []
        currency_mixed: list[str] = []
        bad_entry_ids: list[str] = []
        bad_timestamps: list[str] = []

        # 1. Every ledger row has a companion atom.
        rows = self.conn.execute(
            "SELECT entry_id, atom_id FROM financial_ledger"
        ).fetchall()
        for entry_id, atom_id in rows:
            if not atom_id:
                violations.append(f"entry {entry_id}: missing atom_id")
                orphaned_atoms.append(entry_id)
                continue
            atom_row = self.conn.execute(
                "SELECT 1 FROM atoms WHERE atom_id = ? AND type = 'financial'",
                (atom_id,),
            ).fetchone()
            if not atom_row:
                violations.append(
                    f"entry {entry_id}: companion atom {atom_id} missing"
                )
                orphaned_atoms.append(entry_id)

        # 2. Reverts point at existing entries.
        revert_rows = self.conn.execute(
            "SELECT entry_id, reverts_entry_id FROM financial_ledger "
            "WHERE reverts_entry_id IS NOT NULL"
        ).fetchall()
        for entry_id, target_id in revert_rows:
            target = self.conn.execute(
                "SELECT 1 FROM financial_ledger WHERE entry_id = ?",
                (target_id,),
            ).fetchone()
            if not target:
                violations.append(
                    f"revert {entry_id}: target {target_id} does not exist"
                )
                orphaned_reverts.append(entry_id)

        # 3. Per-project currency uniqueness.
        proj_rows = self.conn.execute(
            "SELECT project, COUNT(DISTINCT currency) AS n "
            "FROM financial_ledger GROUP BY project HAVING n > 1"
        ).fetchall()
        for project, n in proj_rows:
            violations.append(
                f"project {project!r}: {n} currencies present "
                f"(currency-lock invariant violated)"
            )
            currency_mixed.append(project)

        # 4. entry_id matches deterministic mint of idempotency_id.
        import hashlib
        id_rows = self.conn.execute(
            "SELECT entry_id, idempotency_id FROM financial_ledger"
        ).fetchall()
        for entry_id, idem_id in id_rows:
            expected = "le-" + hashlib.sha256(
                idem_id.encode("utf-8")
            ).hexdigest()[:20]
            if entry_id != expected:
                violations.append(
                    f"entry {entry_id}: id does not match SHA-256 of "
                    f"idempotency_id {idem_id!r} (expected {expected})"
                )
                bad_entry_ids.append(entry_id)

        # 5. Timestamp formats.
        ts_rows = self.conn.execute(
            "SELECT entry_id, occurred_at, recorded_at FROM financial_ledger"
        ).fetchall()
        for entry_id, occ, rec in ts_rows:
            for label, val in (("occurred_at", occ), ("recorded_at", rec)):
                if not _ISO_UTC_RE.match(val or ""):
                    violations.append(
                        f"entry {entry_id}: {label}={val!r} not ISO 8601 UTC"
                    )
                    bad_timestamps.append(entry_id)

        return LedgerAudit(
            ok=not violations,
            ledger_rows=len(rows),
            violations=violations,
            orphaned_atoms=orphaned_atoms,
            orphaned_reverts=orphaned_reverts,
            currency_mixed_projects=currency_mixed,
            bad_entry_ids=bad_entry_ids,
            bad_timestamps=bad_timestamps,
        )


# ─── Data classes ───────────────────────────────────────────────────────────


@dataclass
class LedgerEntry:
    """One row of the financial ledger."""
    entry_id: str
    project: str
    kind: str
    amount: float
    currency: str
    note: str
    occurred_at: str
    recorded_at: str
    idempotency_id: str
    atom_id: str | None
    reverts_entry_id: str | None


@dataclass
class ProjectBalance:
    """Lifetime balance for one project."""
    project: str
    invested: float          # default 0.0 — MOS-aligned: no record → no claim
    earned: float
    net: float
    roi_ratio: float | None  # None when invested == 0 (undefined ROI)
    currency: str
    first_event: str | None
    last_event: str | None
    entry_count: int

    def velocity_per_day(self) -> float | None:
        """Earned dollars per day since first event. None if uncomputable."""
        if self.first_event is None or self.earned == 0:
            return None
        try:
            first = datetime.strptime(
                self.first_event, "%Y-%m-%dT%H:%M:%S.%fZ",
            ).replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            return None
        delta = datetime.now(timezone.utc) - first
        days = max(delta.total_seconds() / 86400.0, 1.0)  # floor at 1 day
        return self.earned / days


@dataclass
class LedgerAudit:
    """Result of FinancialChannel.audit() — the integrity report."""
    ok: bool
    ledger_rows: int
    violations: list[str]
    orphaned_atoms: list[str]
    orphaned_reverts: list[str]
    currency_mixed_projects: list[str]
    bad_entry_ids: list[str]
    bad_timestamps: list[str]

    def render(self) -> str:
        """Human-readable audit report."""
        if self.ok:
            return (
                f"✓ ledger audit clean — {self.ledger_rows} rows, "
                f"no integrity violations"
            )
        lines = [
            f"✗ ledger audit FAILED — {len(self.violations)} violation(s) "
            f"across {self.ledger_rows} rows",
            "",
        ]
        for v in self.violations:
            lines.append(f"  - {v}")
        return "\n".join(lines)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _log_emit_failure(stage: str, exc: BaseException) -> None:
    """Best-effort observability for failed event emission.

    The financial path must not crash if the events plane is
    unavailable, but silent failure hides operational drift. We attempt
    to emit a meta-event; if THAT fails too, we fall back to stderr so
    at least the operator sees something.
    """
    try:
        from ..events import emit_event
        emit_event(
            "channel-error-d", plane="control",
            trace_id=f"channel-error:{stage}",
            payload={"stage": stage, "error": repr(exc)[:500]},
        )
    except Exception:  # noqa: BLE001
        import sys
        print(
            f"[financial] event emit failure at {stage}: {exc!r}",
            file=sys.stderr,
        )


__all__ = [
    "CurrencyMismatchError",
    "FinancialChannel",
    "LedgerAudit",
    "LedgerEntry",
    "LedgerKind",
    "ProjectBalance",
    "ensure_ledger_schema",
]
