"""
steward/health.py — invariant checks, conflict detection, hygiene scan.

The steward speaks in three voices:

  * ``audit_all`` — "is every channel internally consistent?"
  * ``find_conflicts`` — "are there contradictions I can see?"
  * ``find_stale_recalls`` / ``find_orphans`` — "what has aged?"

Everything is read-only. The steward never repairs; it only reports.
Repair is an operator-authorised action through specific channels.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field


@dataclass
class HealthCheck:
    """One named check with a pass/fail and optional detail.

    ``severity`` is one of: 'info' | 'notice' | 'warning' | 'critical'.
    The steward NEVER raises 'critical' on its own — that is reserved
    for invariant violations the operator must look at (e.g. duplicate
    principal, broken foreign key, corrupted chain).
    """
    name: str
    passed: bool
    severity: str
    detail: str = ""
    count: int = 0

    def render(self) -> str:
        mark = "✓" if self.passed else "✗"
        sev = self.severity.upper()
        head = f"{mark} {self.name:<32} [{sev}]"
        if self.count and not self.passed:
            head += f"  ({self.count} item(s))"
        if self.detail:
            return f"{head}\n    {self.detail.strip()}"
        return head


@dataclass
class StewardReport:
    """One pass of the steward across all channels and global invariants."""
    generated_at: str
    checks: list[HealthCheck] = field(default_factory=list)
    conflicts: list[dict] = field(default_factory=list)
    stale_recalls: list[str] = field(default_factory=list)
    orphans: list[dict] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(
            c.passed for c in self.checks if c.severity in ("warning", "critical")
        ) and not self.conflicts

    @property
    def health_score(self) -> float:
        """0-100. Critical fails dominate; warnings cost real points."""
        if not self.checks:
            return 0.0
        score = 100.0
        for c in self.checks:
            if c.passed:
                continue
            if c.severity == "critical":
                score -= 25.0
            elif c.severity == "warning":
                score -= 10.0
            elif c.severity == "notice":
                score -= 3.0
            # info: no penalty
        if self.conflicts:
            score -= min(20.0, 3.0 * len(self.conflicts))
        if self.stale_recalls:
            score -= min(10.0, 1.0 * len(self.stale_recalls))
        return max(0.0, min(100.0, score))

    def render(self) -> str:
        lines = [
            f"steward report · {self.generated_at[:19]} · "
            f"health {self.health_score:.1f}/100 · "
            f"{'OK' if self.ok else 'attention'}",
            "",
            "checks:",
        ]
        for c in self.checks:
            lines.append("  " + c.render())
        if self.conflicts:
            lines.append("")
            lines.append(f"conflicts ({len(self.conflicts)}):")
            for c in self.conflicts[:20]:
                lines.append(
                    f"  · {c.get('subject', '?')} :: {c.get('kind', '?')} "
                    f"= {c.get('values', [])}"
                )
            if len(self.conflicts) > 20:
                lines.append(f"  ... and {len(self.conflicts) - 20} more")
        if self.stale_recalls:
            lines.append("")
            lines.append(f"stale recalls ({len(self.stale_recalls)}):")
            for rid in self.stale_recalls[:20]:
                lines.append(f"  · {rid}")
        if self.orphans:
            lines.append("")
            lines.append(f"orphans ({len(self.orphans)}):")
            for o in self.orphans[:20]:
                lines.append(f"  · {o.get('kind', '?')} {o.get('id', '?')}: "
                             f"{o.get('reason', '')}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "generated_at": self.generated_at,
            "ok": self.ok,
            "health_score": round(self.health_score, 2),
            "checks": [
                {"name": c.name, "passed": c.passed, "severity": c.severity,
                 "detail": c.detail, "count": c.count}
                for c in self.checks
            ],
            "conflicts": self.conflicts,
            "stale_recalls": self.stale_recalls,
            "orphans": self.orphans,
        }


# ─── Audit runner ──────────────────────────────────────────────────────────


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?", (name,)
    ).fetchone()
    return row is not None


def _utc_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def audit_all(conn: sqlite3.Connection) -> StewardReport:
    """Run every available channel's ``audit()`` plus global invariants.

    Discovers channels dynamically from the registry — so adding a new
    channel with an audit() method automatically gets it picked up here.
    """
    report = StewardReport(generated_at=_utc_now())

    # ── Global atom invariants ────────────────────────────────────────
    if _table_exists(conn, "atoms"):
        # idempotency uniqueness inside a channel
        dup = conn.execute(
            """
            SELECT type, scope_tags, COUNT(*)
            FROM atoms
            WHERE scope_tags LIKE '%idempotency_id%'
            GROUP BY type, scope_tags
            HAVING COUNT(*) > 1
            """
        ).fetchall()
        report.checks.append(HealthCheck(
            name="atom.idempotency_unique",
            passed=len(dup) == 0,
            severity="critical",
            count=len(dup),
            detail="" if not dup else "duplicate idempotency_id within a channel",
        ))

        # broken supersedes chains (forward pointer to nonexistent atom)
        broken = conn.execute(
            """
            SELECT COUNT(*) FROM atoms a
            WHERE a.superseded_by IS NOT NULL
              AND NOT EXISTS (
                SELECT 1 FROM atoms b WHERE b.atom_id = a.superseded_by
              )
            """
        ).fetchone()[0]
        report.checks.append(HealthCheck(
            name="atom.chain_integrity",
            passed=broken == 0,
            severity="critical",
            count=broken,
            detail="" if broken == 0 else f"{broken} atoms point at a missing successor",
        ))

        total_atoms = conn.execute("SELECT COUNT(*) FROM atoms").fetchone()[0]
        report.checks.append(HealthCheck(
            name="atom.total",
            passed=True,
            severity="info",
            count=total_atoms,
            detail=f"{total_atoms} atom(s) currently in the library",
        ))

    # ── Per-channel audits ────────────────────────────────────────────
    try:
        from ..channels import list_channels, get_channel
        for spec in list_channels():
            ChannelClass = None
            try:
                ch = get_channel(spec.name, conn)
            except Exception as e:
                report.checks.append(HealthCheck(
                    name=f"channel.{spec.name}.construct",
                    passed=False, severity="warning",
                    detail=f"could not construct: {e}",
                ))
                continue
            audit_fn = getattr(ch, "audit", None)
            if audit_fn is None or not callable(audit_fn):
                # Not a failure — many channels are pure stores with no
                # invariants to verify. We note it so the operator can
                # see coverage growing over time.
                report.checks.append(HealthCheck(
                    name=f"channel.{spec.name}.audit_present",
                    passed=True, severity="info",
                    detail="no audit() method (channel has no declared invariants)",
                ))
                continue
            try:
                result = audit_fn()
            except Exception as e:
                report.checks.append(HealthCheck(
                    name=f"channel.{spec.name}.audit",
                    passed=False, severity="warning",
                    detail=f"audit raised: {type(e).__name__}: {e}",
                ))
                continue
            ok = bool(getattr(result, "ok", True))
            report.checks.append(HealthCheck(
                name=f"channel.{spec.name}.audit",
                passed=ok,
                severity="warning" if not ok else "info",
                detail="" if ok else f"channel reports unhealthy: {result!r}"[:200],
            ))
    except Exception as e:
        report.checks.append(HealthCheck(
            name="channel.discovery",
            passed=False, severity="warning",
            detail=f"could not iterate channels: {e}",
        ))

    # ── Cross-channel signals ─────────────────────────────────────────
    report.conflicts = find_conflicts(conn)
    report.stale_recalls = find_stale_recalls(conn)
    report.orphans = find_orphans(conn)

    return report


# ─── Conflict detection ────────────────────────────────────────────────────


def find_conflicts(conn: sqlite3.Connection) -> list[dict]:
    """Look for contradictions across channels.

    Currently scoped to ``people_facts``: same person + same fact kind +
    multiple confirmed values = conflict. Extensible: other channels with
    similar (subject, kind, value) shape can register their own pass.
    """
    out: list[dict] = []
    if not _table_exists(conn, "people_facts") or not _table_exists(conn, "people"):
        return out

    rows = conn.execute(
        """
        SELECT pf.person_id, p.canonical_name, pf.kind, pf.value
        FROM people_facts pf
        JOIN people p ON p.person_id = pf.person_id
        WHERE pf.status = 'confirmed'
          AND pf.retracted_at IS NULL
          AND p.redacted_at IS NULL
        """
    ).fetchall()
    by_key: dict[tuple, list[str]] = {}
    name_lookup: dict[tuple, str] = {}
    for person_id, canonical_name, kind, value in rows:
        key = (person_id, kind)
        by_key.setdefault(key, []).append(value)
        name_lookup[key] = canonical_name
    for (person_id, kind), values in by_key.items():
        uniq = sorted(set(values))
        if len(uniq) > 1:
            out.append({
                "channel": "people",
                "subject": name_lookup[(person_id, kind)],
                "subject_id": person_id,
                "kind": kind,
                "values": uniq,
            })
    return out


# ─── Hygiene surfaces ──────────────────────────────────────────────────────


def find_stale_recalls(conn: sqlite3.Connection) -> list[str]:
    """Return ids of currently-stale recalls. Does NOT mark them — read-only."""
    if not _table_exists(conn, "recalls"):
        return []
    rows = conn.execute(
        "SELECT recall_id FROM recalls WHERE status = 'stale' ORDER BY staled_at DESC"
    ).fetchall()
    return [r[0] for r in rows]


def find_orphans(conn: sqlite3.Connection) -> list[dict]:
    """Return rows that reference targets which no longer exist."""
    out: list[dict] = []

    # recall_sources pointing at missing recalls
    if _table_exists(conn, "recall_sources") and _table_exists(conn, "recalls"):
        rows = conn.execute(
            """
            SELECT rs.recall_source_id, rs.recall_id
            FROM recall_sources rs
            LEFT JOIN recalls r ON r.recall_id = rs.recall_id
            WHERE r.recall_id IS NULL
            """
        ).fetchall()
        for rs_id, recall_id in rows:
            out.append({
                "kind": "recall_source",
                "id": rs_id,
                "reason": f"references missing recall {recall_id}",
            })

    # people_facts pointing at redacted people (allowed but flagged)
    if _table_exists(conn, "people_facts") and _table_exists(conn, "people"):
        rows = conn.execute(
            """
            SELECT pf.fact_id, p.canonical_name
            FROM people_facts pf
            JOIN people p ON p.person_id = pf.person_id
            WHERE p.redacted_at IS NOT NULL
              AND pf.status = 'confirmed'
              AND pf.retracted_at IS NULL
            """
        ).fetchall()
        for fact_id, name in rows:
            out.append({
                "kind": "fact_under_redacted_person",
                "id": fact_id,
                "reason": f"confirmed fact still attached to redacted person ({name})",
            })

    return out
