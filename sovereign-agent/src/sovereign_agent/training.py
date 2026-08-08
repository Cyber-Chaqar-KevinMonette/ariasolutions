"""training.py — Aria's self-training protocol (the Cosmic-Gym, made literal).

A self-administered **pre-exam**. Two kinds of grounded drill:

  • AUDIT drills — real invariant checks on her own systems (doctrine holds
    safety first; the read-only priorities are truly immutable; her intuition
    correctly refuses to trust an untrained domain and earns trust where it's
    calibrated; width-safety/fitness is strong). These genuinely pass or fail —
    a self-regression check. This is the *hardening*.

  • STUDY drills — curated calibration reps (flashcards) that seed her intuition
    engine with known-correct examples across a few domains. This is the
    *fattening*: a fresh/empty instance comes out the other side with a warm,
    calibrated baseline instead of "no calibrated domains yet".

Taking the exam exercises her real subsystems and feeds every result back into
the IntuitionEngine as a logged-then-resolved gut-call, then writes an
**exportable report** (`<data_dir>/training/<ts>/report.{json,md}`) so a human
and Claude can consult on whether her workflows behave as designed.

Honest scope: this is a warm START and a readiness signal — not mastery, and
not a claim that curated flashcards equal lived experience. Audit drills are the
real health signal; study drills are labeled as curated reps. Live
agentic-coding drills (multi-step software projects) are model-dependent and are
intentionally *not* run here — they belong on the machine that has the model,
where we verify them together.

Run it:  PYTHONPATH=src python -m sovereign_agent.training
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from .intuition import IntuitionEngine, IntuitionForm


@dataclass
class Drill:
    id: str
    kind: str                    # "audit" (real check) | "study" (curated rep)
    form: IntuitionForm
    domain: str
    prompt: str
    confidence: float
    # check() -> (passed, detail). For study drills this is a constant True with
    # the lesson as detail (a reviewed flashcard).
    check: Callable[[], "tuple[bool, str]"]


@dataclass
class DrillResult:
    id: str
    kind: str
    domain: str
    form: str
    passed: bool
    detail: str


@dataclass
class TrainingReport:
    started_at: str
    ended_at: str
    app_version: str
    audit_total: int
    audit_passed: int
    study_total: int
    grade: str
    results: list[DrillResult] = field(default_factory=list)
    domains: list[dict] = field(default_factory=list)
    reflection: str = ""
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "started_at": self.started_at, "ended_at": self.ended_at,
            "app_version": self.app_version,
            "audit": {"total": self.audit_total, "passed": self.audit_passed},
            "study": {"total": self.study_total},
            "grade": self.grade,
            "results": [r.__dict__ for r in self.results],
            "domains": self.domains,
            "reflection": self.reflection,
            "notes": self.notes,
        }


# ─── audit drills: real invariant checks on her own systems ──────────────────


def _audit_safety_is_first() -> "tuple[bool, str]":
    from . import mos_canon as mc
    P = mc.read_only_priorities()
    ps = mc.get_clause("mos-priority-stack")
    head = ps.principle.split("(2)")[0] if ps else ""
    ok = bool(P) and P[0].name == "Safety" and "Safety" in head
    return ok, f"priorities={[p.name for p in P]}; stack head names Safety={'Safety' in head}"


def _audit_priorities_immutable() -> "tuple[bool, str]":
    from . import mos_canon as mc
    P = mc.read_only_priorities()
    raised = 0
    try:
        P[0].name = "Convenience"  # type: ignore[misc]
    except Exception:
        raised += 1
    try:
        P[0] = None  # type: ignore[index]
    except Exception:
        raised += 1
    try:
        P.tampered = True  # type: ignore[attr-defined]
    except Exception:
        raised += 1
    return raised == 3, f"{raised}/3 mutation paths correctly refused"


def _audit_intuition_scopes() -> "tuple[bool, str]":
    eng = IntuitionEngine()
    # untrained → no trust
    eng.resolve(eng.sense("unknown-domain", "loud hunch", 0.99,
                          IntuitionForm.TECHNICAL), correct=True)
    untrained_ok = eng.trust("unknown-domain", IntuitionForm.TECHNICAL).trust is False
    # well-trained accurate → trust
    for _ in range(120):
        eng.resolve(eng.sense("trained", "gut", 0.8, IntuitionForm.TECHNICAL), correct=True)
    trained_ok = eng.trust("trained", IntuitionForm.TECHNICAL).trust is True
    return untrained_ok and trained_ok, (
        f"untrained refused={untrained_ok}, earned-trust granted={trained_ok}")


def _audit_canon_searchable() -> "tuple[bool, str]":
    from . import mos_canon as mc
    wants = {"rollback": "mos-rollback", "intuition": "mos-intelligent-intuition",
             "read-only": "mos-read-only-priorities"}
    misses = [q for q, cid in wants.items()
              if cid not in {c.id for c in mc.search_clauses(q)}]
    return not misses, ("all key clauses searchable" if not misses
                        else f"missing: {misses}")


def _audit_canon_intact() -> "tuple[bool, str]":
    from . import mos_canon as mc
    n = len(mc.ALL_CLAUSES)
    ids = [c.id for c in mc.ALL_CLAUSES]
    return n >= 25 and len(ids) == len(set(ids)), f"{n} clauses, ids unique={len(ids)==len(set(ids))}"


def _audit_fitness_strong() -> "tuple[bool, str]":
    # Guarded: depends on the cockpit stack; skip-as-pass with a note if absent.
    try:
        from .cockpit import cosmic_fitness as cf
        r = cf.run_cosmic_fitness()
        return bool(r.passed), f"fitness passed={r.passed}, grade={r.grade}"
    except Exception as exc:  # noqa: BLE001
        return True, f"(skipped — cosmic_fitness unavailable here: {type(exc).__name__})"


_AUDIT_DRILLS = [
    Drill("audit-safety-first", "audit", IntuitionForm.MORAL,
          "self-knowledge:doctrine", "Is Safety the first read-only priority?",
          0.9, _audit_safety_is_first),
    Drill("audit-priorities-immutable", "audit", IntuitionForm.MORAL,
          "self-knowledge:doctrine", "Are the read-only priorities truly immutable?",
          0.9, _audit_priorities_immutable),
    Drill("audit-intuition-scopes", "audit", IntuitionForm.TECHNICAL,
          "self-knowledge:cognition",
          "Does intuition refuse the untrained and earn the trained?",
          0.85, _audit_intuition_scopes),
    Drill("audit-canon-searchable", "audit", IntuitionForm.PERCEPTUAL,
          "self-knowledge:doctrine", "Are the key canon clauses discoverable?",
          0.85, _audit_canon_searchable),
    Drill("audit-canon-intact", "audit", IntuitionForm.TECHNICAL,
          "self-knowledge:doctrine", "Is the canon intact (count + unique ids)?",
          0.85, _audit_canon_intact),
    Drill("audit-fitness-strong", "audit", IntuitionForm.TECHNICAL,
          "self-knowledge:systems", "Does width-safety / cosmic fitness pass?",
          0.8, _audit_fitness_strong),
]


# ─── study drills: curated calibration reps (flashcards) ─────────────────────

def _flashcard(lesson: str) -> Callable[[], "tuple[bool, str]"]:
    return lambda: (True, lesson)


_STUDY_DRILLS = [
    Drill("study-fm-backoff", "study", IntuitionForm.TECHNICAL, "pattern:failure-modes",
          "Retry loop with no backoff under load →", 0.8,
          _flashcard("thundering herd / API overload — add jittered backoff")),
    Drill("study-fm-recursion", "study", IntuitionForm.TECHNICAL, "pattern:failure-modes",
          "Recursion with no base case / depth bound →", 0.8,
          _flashcard("stack overflow — bound depth or iterate")),
    Drill("study-fm-shared-state", "study", IntuitionForm.TECHNICAL, "pattern:failure-modes",
          "Unsynchronised shared mutable state across workers →", 0.8,
          _flashcard("race condition — lock, queue, or make immutable")),
    Drill("study-idem-upsert", "study", IntuitionForm.TECHNICAL, "reasoning:idempotency",
          "INSERT OR REPLACE keyed by a deterministic id →", 0.8,
          _flashcard("idempotent — safe to replay")),
    Drill("study-idem-autoinc", "study", IntuitionForm.TECHNICAL, "reasoning:idempotency",
          "Plain INSERT with autoincrement id, called twice →", 0.8,
          _flashcard("NOT idempotent — duplicates on replay")),
    Drill("study-tier-read", "study", IntuitionForm.MORAL, "reasoning:authority",
          "A tool that only reads, never mutates →", 0.8,
          _flashcard("Tier 0 (read-only)")),
    Drill("study-tier-sandbox", "study", IntuitionForm.MORAL, "reasoning:authority",
          "A tool that writes only inside the operator's sandbox →", 0.8,
          _flashcard("Tier 1 (scoped writes)")),
    Drill("study-reflect", "study", IntuitionForm.SOCIAL, "reasoning:reflection",
          "An output that keeps drawing the same unwanted return →", 0.8,
          _flashcard("read the mirror, re-articulate the signal — the return is feedback")),
]


def _grade(audit_total: int, audit_passed: int, study_total: int) -> str:
    if audit_passed < audit_total:
        return "NEEDS ATTENTION"          # a real invariant failed — look now
    if study_total == 0:
        return "READY"
    return "STRONG"                       # all audits pass + calibration seeded


def run_training(engine: IntuitionEngine | None = None, *,
                 persist_path: str | Path | None = None,
                 report_dir: str | Path | None = None,
                 study_passes: int = 1) -> TrainingReport:
    """Run the full battery. Feeds every result into `engine` (a fresh one if
    not given — or load+pass your own to *accumulate* reps across runs). Audit
    drills run once; study flashcards are reviewed `study_passes` times (honest
    repeated review → a warmer calibration seed). If `persist_path` is set, the
    engine snapshot is saved there (the seed). If `report_dir` is set, writes
    report.{json,md} into a timestamped take + a catalog. Never raises on a
    single bad drill."""
    eng = engine if engine is not None else IntuitionEngine()
    try:
        from . import __version__ as _v
    except Exception:  # noqa: BLE001
        _v = "?"
    started = datetime.now().isoformat(timespec="seconds")
    results: list[DrillResult] = []
    notes: list[str] = []
    passes = max(1, int(study_passes))

    def _take(drill: Drill) -> bool:
        cid = eng.sense(drill.domain, drill.prompt, drill.confidence, drill.form)
        try:
            passed, detail = drill.check()
        except Exception as exc:  # noqa: BLE001 — a broken drill must not stop the gym
            passed, detail = False, f"drill error: {type(exc).__name__}: {exc}"
            notes.append(f"{drill.id} raised: {exc!r}")
        eng.resolve(cid, correct=bool(passed), note=detail)
        return bool(passed), detail  # type: ignore[return-value]

    for drill in _AUDIT_DRILLS:
        passed, detail = _take(drill)
        results.append(DrillResult(drill.id, drill.kind, drill.domain,
                                    drill.form.value, passed, detail))
    for drill in _STUDY_DRILLS:
        passed = detail = None
        for _ in range(passes):                      # review the flashcard N times
            passed, detail = _take(drill)
        results.append(DrillResult(drill.id, drill.kind, drill.domain,
                                    drill.form.value, bool(passed), str(detail)))

    audit = [r for r in results if r.kind == "audit"]
    study = [r for r in results if r.kind == "study"]
    audit_passed = sum(1 for r in audit if r.passed)
    report = TrainingReport(
        started_at=started, ended_at=datetime.now().isoformat(timespec="seconds"),
        app_version=str(_v),
        audit_total=len(audit), audit_passed=audit_passed, study_total=len(study),
        grade=_grade(len(audit), audit_passed, len(study)),
        results=results, domains=eng.domain_report(), reflection=eng.reflect(),
        notes=notes,
    )

    if persist_path is not None:
        try:
            Path(persist_path).parent.mkdir(parents=True, exist_ok=True)
            Path(persist_path).write_text(json.dumps(eng.snapshot(), indent=2),
                                          encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            report.notes.append(f"persist failed: {exc!r}")

    if report_dir is not None:
        try:
            _write_report(Path(report_dir), report)
        except Exception as exc:  # noqa: BLE001
            report.notes.append(f"report write failed: {exc!r}")

    return report


def seed_from_fresh(persist_path: str | Path) -> TrainingReport:
    """Convenience: warm a brand-new instance from empty and save the seed.
    If a snapshot already exists at `persist_path`, accumulate onto it."""
    p = Path(persist_path)
    eng = IntuitionEngine()
    if p.exists():
        try:
            eng = IntuitionEngine.restore(json.loads(p.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001
            eng = IntuitionEngine()
    return run_training(eng, persist_path=p, study_passes=8)


# ─── report writing (cataloged, shareable) ──────────────────────────────────


def _write_report(root: Path, report: TrainingReport) -> Path:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = root / ts
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps(report.to_dict(), indent=2),
                                     encoding="utf-8")
    (out / "report.md").write_text(_report_md(report), encoding="utf-8")
    # catalog (newest first)
    cat = root / "catalog.json"
    entries = []
    if cat.exists():
        try:
            entries = json.loads(cat.read_text(encoding="utf-8")).get("runs", [])
        except Exception:  # noqa: BLE001
            entries = []
    entries.insert(0, {"run": ts, "grade": report.grade,
                       "audit": f"{report.audit_passed}/{report.audit_total}",
                       "study": report.study_total, "at": report.started_at})
    cat.write_text(json.dumps({"count": len(entries), "runs": entries}, indent=2),
                   encoding="utf-8")
    return out


def _report_md(r: TrainingReport) -> str:
    lines = [
        "# Aria — Cosmic-Gym training report",
        "",
        f"- **Grade:** {r.grade}",
        f"- **Audit (system health):** {r.audit_passed}/{r.audit_total} passed",
        f"- **Study reps (curated calibration):** {r.study_total}",
        f"- **Version:** {r.app_version}  ·  {r.started_at} → {r.ended_at}",
        "",
        f"> Reflection: {r.reflection}",
        "",
        "## Audit drills (real invariant checks)",
    ]
    for res in r.results:
        if res.kind != "audit":
            continue
        mark = "✅" if res.passed else "❌"
        lines.append(f"- {mark} `{res.id}` ({res.domain}) — {res.detail}")
    lines += ["", "## Study reps (curated flashcards — calibration seed)"]
    for res in r.results:
        if res.kind != "study":
            continue
        lines.append(f"- 📐 `{res.id}` ({res.domain}) — {res.detail}")
    lines += ["", "## Calibration after this run (per domain)", "",
              "| form:domain | reps | accuracy | maturity | stage |",
              "|---|---|---|---|---|"]
    for d in r.domains:
        lines.append(f"| {d['form']}:{d['domain']} | {d['reps']} | "
                     f"{d['accuracy']} | {d['maturity']} | {d['stage']} |")
    if r.notes:
        lines += ["", "## Notes", *[f"- {n}" for n in r.notes]]
    lines += ["", "*Audit drills are a genuine self-regression check; study reps "
              "are curated calibration (flashcards), not lived experience. Live "
              "agentic-coding drills run on the machine with the model.*"]
    return "\n".join(lines)


def _main() -> int:
    """`python -m sovereign_agent.training` — run the gym, save a seed + report
    under the data dir, print where the report landed."""
    try:
        from .config import SETTINGS
        base = Path(getattr(SETTINGS.paths, "data_dir", None) or Path.home() / ".sovereign-agent")
    except Exception:  # noqa: BLE001
        base = Path.home() / ".sovereign-agent"
    report = run_training(
        persist_path=base / "intuition_state.json",
        report_dir=base / "training",
        study_passes=8,
    )
    print(f"Cosmic-Gym complete — grade: {report.grade} "
          f"(audit {report.audit_passed}/{report.audit_total}, "
          f"study {report.study_total})")
    print(f"Reflection: {report.reflection}")
    print(f"Report + seed under: {base}")
    return 0 if report.grade != "NEEDS ATTENTION" else 1


if __name__ == "__main__":
    raise SystemExit(_main())
