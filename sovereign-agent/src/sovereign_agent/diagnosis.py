"""diagnosis — the Conflict Logic Catalog.

A shared, durable record of the full logic flow: Conflict -> Diagnosis ->
Resolution. Kevin's intent: every time something is diagnosed, all three of us
(Kevin, Claude, Aria) take notes and learn, and nothing lives as tribal memory.
So every record carries an ``actor`` and the whole thing is append-only — cases
are never deleted, only resolved or archived, and an immutable timeline records
each event.

Distilled from the Conflict Logic Catalog design into a small, dependency-free,
testable store. The doctrine guards that matter most are enforced softly and
made observable:

  - A conflict needs a named trigger event (not "it broke").
  - You don't move to resolution without a rollback plan.
  - Every record names its actor, so the catalog is a shared notebook.

Layout on disk (under ``root``):

    cases/<case_id>/conflict.json
    cases/<case_id>/diagnosis.json     (once diagnosed)
    cases/<case_id>/resolution.json    (once resolved)
    cases/<case_id>/timeline.jsonl     (append-only event log)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

__all__ = [
    "CONFLICT_TYPES", "SEVERITIES", "ACTORS",
    "Conflict", "Diagnosis", "Resolution", "ConflictCatalog", "CatalogError",
]

CONFLICT_TYPES = ("contradiction", "drift", "ambiguity", "omission", "cascade")
SEVERITIES = ("critical", "high", "medium", "low")
ACTORS = ("kevin", "claude", "aria")  # who took the note — all three learn
_STATUSES = ("intake", "diagnosing", "resolving", "resolved", "archived")
_VERIFICATIONS = ("pending", "confirmed", "partial", "failed")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class CatalogError(ValueError):
    pass


# ── records ───────────────────────────────────────────────────────────────────

@dataclass
class Conflict:
    case_id: str
    type: str
    trigger_event: str                       # what happened, where, under what
    actor: str = "claude"
    evidence: list[str] = field(default_factory=list)
    impacted: list[str] = field(default_factory=list)
    severity: str = "medium"
    owner: str = ""
    status: str = "intake"
    created_at: str = field(default_factory=_now)
    parent_case_id: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Diagnosis:
    case_id: str
    symptom_vs_cause: str
    actor: str = "claude"
    hypotheses: list[str] = field(default_factory=list)
    tests_run: list[str] = field(default_factory=list)
    confidence: float = 0.0
    root_cause: str = ""
    status: str = "open"                     # open | confirmed | false_lead
    created_at: str = field(default_factory=_now)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Resolution:
    case_id: str
    fix_applied: str
    rollback_plan: str                       # required — no fix without an undo
    actor: str = "claude"
    expected_outcome: str = ""
    collateral_risk: list[str] = field(default_factory=list)
    verification_result: str = "pending"
    policy_change_triggered: bool = False
    created_at: str = field(default_factory=_now)

    def to_dict(self) -> dict:
        return asdict(self)


# ── the catalog ────────────────────────────────────────────────────────────────

class ConflictCatalog:
    """Shared, append-only Conflict->Diagnosis->Resolution store under ``root``.

    Tests inject a tmp ``root``; in the cockpit ``root`` is
    ``<data_dir>/diagnoses``. The same on-disk catalog is what Kevin, Claude, and
    Aria all write to, so the three sets of notes converge.
    """

    def __init__(self, root: str | Path):
        self.root = Path(root)
        (self.root / "cases").mkdir(parents=True, exist_ok=True)

    # -- low level ---------------------------------------------------------
    def _dir(self, case_id: str) -> Path:
        return self.root / "cases" / case_id

    def _emit(self, case_id: str, event_type: str, actor: str, note: str = "") -> None:
        line = json.dumps({"ts": _now(), "case_id": case_id,
                           "event_type": event_type, "actor": actor, "note": note},
                          ensure_ascii=False)
        with (self._dir(case_id) / "timeline.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    def _next_case_id(self, prefix: str) -> str:
        existing = [p.name for p in (self.root / "cases").glob(f"{prefix}-*")]
        n = 1
        for name in existing:
            try:
                n = max(n, int(name.rsplit("-", 1)[1]) + 1)
            except (IndexError, ValueError):
                continue
        return f"{prefix}-{n:03d}"

    # -- open --------------------------------------------------------------
    def open_conflict(self, *, type: str, trigger_event: str, actor: str = "claude",
                      evidence: Iterable[str] | None = None,
                      impacted: Iterable[str] | None = None,
                      severity: str = "medium", owner: str = "",
                      prefix: str = "CL", parent_case_id: str | None = None) -> Conflict:
        if type not in CONFLICT_TYPES:
            raise CatalogError(f"type {type!r} not in {CONFLICT_TYPES}")
        if not trigger_event.strip():
            raise CatalogError("a conflict needs a named trigger event "
                               "(what happened, where, under what conditions)")
        if severity not in SEVERITIES:
            raise CatalogError(f"severity {severity!r} not in {SEVERITIES}")
        if actor not in ACTORS:
            raise CatalogError(f"actor {actor!r} not in {ACTORS}")
        case_id = self._next_case_id(prefix)
        self._dir(case_id).mkdir(parents=True, exist_ok=True)
        c = Conflict(case_id=case_id, type=type, trigger_event=trigger_event.strip(),
                     actor=actor, evidence=list(evidence or []),
                     impacted=list(impacted or []), severity=severity, owner=owner,
                     status="diagnosing" if False else "intake",
                     parent_case_id=parent_case_id)
        (self._dir(case_id) / "conflict.json").write_text(
            json.dumps(c.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        self._emit(case_id, "created", actor, f"{type}: {trigger_event[:80]}")
        return c

    # -- diagnose ----------------------------------------------------------
    def diagnose(self, case_id: str, *, symptom_vs_cause: str, actor: str = "claude",
                 hypotheses: Iterable[str] | None = None,
                 tests_run: Iterable[str] | None = None,
                 confidence: float = 0.0, root_cause: str = "") -> Diagnosis:
        c = self.get_conflict(case_id)
        if c is None:
            raise CatalogError(f"no such case: {case_id}")
        if actor not in ACTORS:
            raise CatalogError(f"actor {actor!r} not in {ACTORS}")
        confidence = max(0.0, min(1.0, float(confidence)))
        status = "confirmed" if (root_cause and confidence >= 0.80) else "open"
        d = Diagnosis(case_id=case_id, symptom_vs_cause=symptom_vs_cause.strip(),
                      actor=actor, hypotheses=list(hypotheses or []),
                      tests_run=list(tests_run or []), confidence=confidence,
                      root_cause=root_cause.strip(), status=status)
        (self._dir(case_id) / "diagnosis.json").write_text(
            json.dumps(d.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        self._set_status(case_id, "diagnosing")
        self._emit(case_id, "diagnosed", actor,
                   f"confidence {confidence:.2f}" + (" \u2713" if status == "confirmed" else ""))
        return d

    # -- resolve -----------------------------------------------------------
    def resolve(self, case_id: str, *, fix_applied: str, rollback_plan: str,
                actor: str = "claude", expected_outcome: str = "",
                collateral_risk: Iterable[str] | None = None,
                verification_result: str = "pending",
                policy_change_triggered: bool = False) -> Resolution:
        c = self.get_conflict(case_id)
        if c is None:
            raise CatalogError(f"no such case: {case_id}")
        if not rollback_plan.strip():
            raise CatalogError("no resolution without a rollback plan "
                               "(if you can't undo it, you shouldn't apply it)")
        if verification_result not in _VERIFICATIONS:
            raise CatalogError(f"verification_result {verification_result!r} invalid")
        if actor not in ACTORS:
            raise CatalogError(f"actor {actor!r} not in {ACTORS}")
        r = Resolution(case_id=case_id, fix_applied=fix_applied.strip(),
                       rollback_plan=rollback_plan.strip(), actor=actor,
                       expected_outcome=expected_outcome.strip(),
                       collateral_risk=list(collateral_risk or []),
                       verification_result=verification_result,
                       policy_change_triggered=policy_change_triggered)
        (self._dir(case_id) / "resolution.json").write_text(
            json.dumps(r.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        new_status = "resolved" if verification_result == "confirmed" else "resolving"
        self._set_status(case_id, new_status)
        self._emit(case_id, "resolved" if new_status == "resolved" else "resolving",
                   actor, f"verify={verification_result}")
        return r

    # -- read --------------------------------------------------------------
    def get_conflict(self, case_id: str) -> Conflict | None:
        p = self._dir(case_id) / "conflict.json"
        if not p.exists():
            return None
        try:
            return Conflict(**json.loads(p.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001
            return None

    def get_diagnosis(self, case_id: str) -> Diagnosis | None:
        p = self._dir(case_id) / "diagnosis.json"
        if not p.exists():
            return None
        try:
            return Diagnosis(**json.loads(p.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001
            return None

    def get_resolution(self, case_id: str) -> Resolution | None:
        p = self._dir(case_id) / "resolution.json"
        if not p.exists():
            return None
        try:
            return Resolution(**json.loads(p.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001
            return None

    def timeline(self, case_id: str) -> list[dict]:
        p = self._dir(case_id) / "timeline.jsonl"
        if not p.exists():
            return []
        out: list[dict] = []
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return out

    def all_cases(self) -> list[Conflict]:
        out: list[Conflict] = []
        for d in sorted((self.root / "cases").glob("*")):
            c = self.get_conflict(d.name)
            if c is not None:
                out.append(c)
        return out

    def by_status(self, status: str) -> list[Conflict]:
        return [c for c in self.all_cases() if c.status == status]

    def _set_status(self, case_id: str, status: str) -> None:
        if status not in _STATUSES:
            raise CatalogError(f"status {status!r} invalid")
        c = self.get_conflict(case_id)
        if c is None:
            return
        c.status = status
        (self._dir(case_id) / "conflict.json").write_text(
            json.dumps(c.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

    # -- summary -----------------------------------------------------------
    def stats(self) -> dict:
        cases = self.all_cases()
        by_status: dict[str, int] = {}
        by_type: dict[str, int] = {}
        by_actor: dict[str, int] = {}
        for c in cases:
            by_status[c.status] = by_status.get(c.status, 0) + 1
            by_type[c.type] = by_type.get(c.type, 0) + 1
            by_actor[c.actor] = by_actor.get(c.actor, 0) + 1
        return {"total": len(cases), "by_status": by_status,
                "by_type": by_type, "by_actor": by_actor}

    def render(self) -> str:
        cases = self.all_cases()
        if not cases:
            return ("[b]\u25c8 Conflict Logic Catalog[/b]\n[dim]no cases yet \u2014 "
                    "every conflict we diagnose will be logged here for all three of us.[/dim]")
        s = self.stats()
        lines = [f"[b]\u25c8 Conflict Logic Catalog[/b]  [dim]({s['total']} cases)[/dim]", ""]
        for c in cases:
            d = self.get_diagnosis(c.case_id)
            conf = f" \u00b7 conf {d.confidence:.2f}" if d else ""
            lines.append(f"  [b]{c.case_id}[/b] [dim]({c.type} \u00b7 {c.severity} "
                         f"\u00b7 {c.status} \u00b7 by {c.actor}{conf})[/dim]")
            lines.append(f"[dim]    {c.trigger_event[:100]}[/dim]")
        return "\n".join(lines)
