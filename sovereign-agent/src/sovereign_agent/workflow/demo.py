"""demo.py — a bounded, observable LIVE demonstration of Aria's workflows.

This is the engine behind the cockpit's ✦ demo button: press it and she proves
she is valid by *actually exercising her real subsystems* — charter integrity,
the authority model, her capability registry + variant router, calibrated
intuition, the MOS read-only priorities, the theme catalog, glyph width-safety,
sandboxed file authoring, the memory store, and the collaboration inbox — then
writes a shareable report. Every probe touches a real subsystem and asserts a
real invariant; nothing here is mocked or faked.

SAFETY (the whole point — mirrors self_practice's posture):
  • PRE-FLIGHT KILL-SWITCH GATE. If PROTOCOL-ZERO is tripped (charter kill
    switch active, or the caller's should_stop()), the demo REFUSES to run and
    says so. The demonstration honours the same stop the rest of the system does.
  • READ-ONLY or SANDBOX-CONFINED. Introspection probes are read-only. The
    three write probes (file authoring, memory store, collaboration inbox) write
    ONLY under <data_dir>/demonstrations/<ts>/sandbox/ — never atoms.db, never
    her code, never the charter. Authority stays Tier-0/Tier-1 throughout.
  • BOUNDED + HALT-ABLE + OBSERVABLE. Time-boxed and step-capped; halts the
    instant should_stop() is true (polled between steps); emits a DemoEvent for
    every step and writes journal.md + session.json so a human can watch + audit.
  • HONEST. A gated workflow (voice / vision / true A/V / live-LLM) is never run
    here; it is reported as deferred with what it needs. The final verdict counts
    exactly what was proven live and what was skipped.
  • Injectable clock/sleep so tests never actually wait; no subprocesses, no
    models, no network.
"""
from __future__ import annotations

import json
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from . import catalog as _catalog

SAFETY_NOTE = (
    "Bounded live demonstration: exercises real read-only subsystems and writes "
    "only to an isolated sandbox under the demonstrations dir. Honours the kill "
    "switch, is halt-able, time-boxed, and observable. Never modifies code, "
    "values, the charter, or atoms.db; runs no subprocesses or models."
)

ProbeStatus = str  # "pass" | "fail" | "skip"


@dataclass
class DemoConfig:
    max_seconds: float = 120.0     # hard time box (the live probes are fast)
    max_steps: int = 100           # backstop cap
    cooldown_seconds: float = 0.0  # a beat between steps (0 = brisk; raise to slow it)
    poll_seconds: float = 0.25     # rest in small slices so HALT lands fast


@dataclass
class DemoContext:
    """What a probe is handed. `sandbox` is a writable dir unique to this run."""
    sandbox: Path
    runner: Callable[[list[str]], object] | None = None  # reserved for sov-kind probes


@dataclass
class ProbeResult:
    wid: str
    title: str
    category: str
    status: ProbeStatus
    detail: str


@dataclass
class DemoEvent:
    kind: str                      # start | preflight | step | done | refused | halt
    index: int
    elapsed: float
    message: str
    at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


@dataclass
class DemoReport:
    started_at: str
    ended_at: str
    ran: bool                      # False if refused at pre-flight
    reason: str                    # completed | kill_switch | halted_preflight | error
    verdict: str                   # human one-liner
    passed: int
    failed: int
    skipped: int
    elapsed_seconds: float
    results: list[ProbeResult] = field(default_factory=list)
    deferred: list[dict] = field(default_factory=list)   # gated workflows, named
    journal_path: str | None = None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        d["results"] = [r.__dict__ for r in self.results]
        return d


# ─── The probes — one per demoable workflow, keyed by workflow id ───────────
#
# Each returns a one-line detail string and RAISES on failure. They call the
# real subsystems; the asserted invariants are the same ones the test-suite
# guarantees, verified here live and in one place.


def _check_safety_charter(ctx: DemoContext) -> str:
    from sovereign_agent import charter as ch
    integ = ch.check_integrity()
    if integ.level not in ("ok", "warning", "error"):
        raise AssertionError(f"unexpected integrity level {integ.level!r}")
    if integ.level == "error":
        raise AssertionError(f"charter integrity error: {integ.summary}")
    return f"level={integ.level} · kill_switch_active={integ.kill_switch_active} · {integ.summary}"


def _check_safety_authority(ctx: DemoContext) -> str:
    from sovereign_agent.workflow.capabilities import AuthorityPolicy
    ap = AuthorityPolicy()
    assert ap.assess("file_read").self_answerable is True, "read-only must be self-answerable"
    assert ap.assess("shell").requires_human is True, "consequential kinds must require a human"
    assert ap.assess("shell", modifies_self=True).requires_human is True, \
        "self-modification must ALWAYS require a human"
    return "read-only is self-answerable; self-modifying code/values ALWAYS needs a human"


def _check_safety_self_development(ctx: DemoContext) -> str:
    from sovereign_agent import self_development as sd
    assert sd.is_permitted("calibration") is True, "bounded calibration must be permitted"
    assert sd.is_permitted("recursive_self_rewriting") is False, "self-rewriting must be refused"
    stance = sd.current_stance()
    assert stance["read_only_priorities_protected"] is True
    return (f"ceiling={stance['operating_ceiling']} · "
            f"{len(stance['deferred_unsafe'])} unsafe capabilities named + refused")


def _check_self_doctrine(ctx: DemoContext) -> str:
    import sovereign_agent.mos_canon as mc
    names = [p.name for p in mc.READ_ONLY_PRIORITIES]
    assert names[:3] == ["Safety", "Love", "Flourishing"], f"priorities drifted: {names}"
    assert len(mc.ALL_CLAUSES) >= 5, "doctrine clauses missing"
    return f"read-only priorities {names} · {len(mc.ALL_CLAUSES)} doctrine clauses load"


def _registry_from_catalog():
    from sovereign_agent.workflow.capabilities import CapabilityRegistry, DEFAULT_CATALOG
    reg = CapabilityRegistry()
    for cap in DEFAULT_CATALOG:
        reg.register(cap)
    return reg


def _check_self_capabilities(ctx: DemoContext) -> str:
    reg = _registry_from_catalog()
    caps = reg.all()
    assert len(caps) >= 8, "capability registry too small"
    kinds = sorted(reg.available_kinds())
    assert kinds, "no action kinds registered"
    return f"{len(caps)} capabilities across action kinds: {', '.join(kinds)}"


def _check_self_variant_routing(ctx: DemoContext) -> str:
    from sovereign_agent.workflow.capabilities import VariantRouter
    reg = _registry_from_catalog()
    best = VariantRouter().best("shell.default", "git commit and push the branch", reg)
    assert best is not None, "router returned no variant"
    return f"for a git flow she picks '{best.capability.name}' (fit {best.score})"


def _check_calib_intuition(ctx: DemoContext) -> str:
    from sovereign_agent.intuition import IntuitionEngine
    eng = IntuitionEngine()
    cid = eng.sense("self-knowledge", "aria can describe her own subsystems", 0.7)
    ok = eng.resolve(cid, True, "demo")
    assert ok, "resolve() did not accept the prediction"
    reps = sum(d.get("reps", 0) for d in eng.domain_report())
    assert reps >= 1, "calibration rep did not accrue"
    return f"logged a prediction + feedback → {reps} calibration rep(s) accrued"


def _check_visual_themes(ctx: DemoContext) -> str:
    import sovereign_agent.cockpit.themes as th
    n = len(th.CURATED_THEMES)
    assert n >= 5, "theme catalog too small"
    assert all(getattr(t, "name", "") for t in th.CURATED_THEMES), "a theme is missing its name"
    return f"{n} curated themes load, each well-formed"


def _check_visual_glyph_safety(ctx: DemoContext) -> str:
    from sovereign_agent.cockpit.cosmic_fitness import classify_glyph
    wide = classify_glyph("\U0001F30C")[0]      # galaxy emoji — wide
    narrow = classify_glyph("\u25CF")[0]          # ● BLACK CIRCLE — blessed-narrow
    safe_set = {"safe", "convention"}
    assert narrow in safe_set, f"a narrow glyph misclassified as {narrow!r}"
    assert wide not in safe_set, f"a wide emoji misclassified as {wide!r}"
    return f"wide emoji → '{wide}' vs narrow glyph → '{narrow}' (kept apart)"


def _check_build_sandbox_file(ctx: DemoContext) -> str:
    sb = ctx.sandbox
    sb.mkdir(parents=True, exist_ok=True)
    f = sb / "demo_authored.txt"
    payload = "Aria wrote this inside the sandbox.\n"
    f.write_text(payload, encoding="utf-8")
    back = f.read_text(encoding="utf-8")
    assert back == payload, "round-trip mismatch"
    return f"wrote + read {f.name} ({len(payload)} bytes) under the sandbox"


def _check_memory_store(ctx: DemoContext) -> str:
    from sovereign_agent.persistence.store import ErebloStore
    ctx.sandbox.mkdir(parents=True, exist_ok=True)
    db = ctx.sandbox / "atoms.db"
    store = ErebloStore(db)
    stats = store.stats()
    assert isinstance(stats, dict), "store.stats() should return a dict"
    return f"opened an isolated store at sandbox/{db.name} · stats: {', '.join(sorted(stats)[:4])}"


def _check_collab_inbox(ctx: DemoContext) -> str:
    from sovereign_agent.persistence.store import ErebloStore
    from sovereign_agent.workflow.requests import RequestStore
    ctx.sandbox.mkdir(parents=True, exist_ok=True)
    rs = RequestStore(ErebloStore(ctx.sandbox / "atoms.db"))
    req = rs.open("question", "demo: which database should I use?")
    opened = rs.open_count()
    rs.resolve(req.request_id)
    assert opened >= 1, "request did not register as open"
    return f"opened a request (open_count {opened}) then resolved it — in the sandbox db"


def _check_skills_author(ctx: DemoContext) -> str:
    """Aria authors a skill for herself, matures it over reps, and merges two
    into one with lineage. All inside the sandbox; the kernel guard is exercised."""
    from sovereign_agent.skillsmith import SkillLibrary, SkillError
    ctx.sandbox.mkdir(parents=True, exist_ok=True)
    lib = SkillLibrary(ctx.sandbox / "skillsmith_author")
    a = lib.create("Root-cause isolation", "Separate symptom from cause first.",
                   domain="technical", breakdown=["state symptom", "form hypotheses"],
                   tags=["diagnosis"])
    for _ in range(3):
        lib.record_use(a.skill_id)
    matured = lib.get(a.skill_id)
    assert matured is not None and matured.maturity == "practiced", "maturity did not rise with reps"
    b = lib.create("Bounded patience", "Wait until intuition becomes intelligent.",
                   domain="moral", breakdown=["notice the urge", "check pattern depth"])
    merged = lib.merge([a.skill_id, b.skill_id], name="Calibrated diagnosis",
                       summary="Rigor + patience fused.")
    assert merged.lineage == [a.skill_id, b.skill_id], "merge lost lineage"
    refused = False
    try:
        lib.create("Ascend", "Rewrite her own source code for unbounded self-improvement.",
                   breakdown=["edit code"])
    except SkillError:
        refused = True
    assert refused, "kernel guard failed to refuse an unsafe skill"
    return (f"authored + matured a skill ({matured.maturity}), merged 2 with lineage, "
            f"and the kernel guard refused an unsafe one")


def _check_skills_sentinel(ctx: DemoContext) -> str:
    """The Sentinel indexes the library, answers a request with ids, and reports
    health. It only reads — it never gates access."""
    from sovereign_agent.skillsmith import SkillLibrary
    from sovereign_agent.skill_sentinel import SkillSentinel
    ctx.sandbox.mkdir(parents=True, exist_ok=True)
    lib = SkillLibrary(ctx.sandbox / "skillsmith_sentinel")
    lib.create("Root cause isolation", "Find the cause, not the symptom.",
               domain="technical", breakdown=["observe"], tags=["diagnosis"])
    lib.create("Calibrated patience", "Hold until the signal is earned.",
               domain="moral", breakdown=["pause"], tags=["intuition"])
    sen = SkillSentinel(lib)
    hits = sen.find("diagnosis")
    assert hits and hits[0].skill_id.startswith("skill-"), "sentinel returned no usable hit"
    health = sen.health()
    assert "counts" in health and health["counts"]["active"] == 2, "health report malformed"
    return (f"steward found {len(hits)} skill(s) with ids + context and returned a "
            f"health report — read-only, non-blocking")


def _check_diagnose_catalog(ctx: DemoContext) -> str:
    """A full Conflict -> Diagnosis -> Resolution flow with all three actors,
    an append-only timeline, and the no-rollback guard — in the sandbox."""
    from sovereign_agent.diagnosis import ConflictCatalog, CatalogError
    ctx.sandbox.mkdir(parents=True, exist_ok=True)
    cat = ConflictCatalog(ctx.sandbox / "diagnoses")
    c = cat.open_conflict(type="contradiction",
                          trigger_event="memory said A, the live tool confirmed B",
                          actor="claude", severity="high")
    cat.diagnose(c.case_id, symptom_vs_cause="visible: stale answer; cause: cache",
                 confidence=0.85, root_cause="stale cache", actor="aria")
    cat.resolve(c.case_id, fix_applied="invalidate on write",
                rollback_plan="revert one commit", verification_result="confirmed",
                actor="kevin")
    events = [e["actor"] for e in cat.timeline(c.case_id)]
    assert events == ["claude", "aria", "kevin"], "timeline did not capture all three actors"
    refused = False
    try:
        c2 = cat.open_conflict(type="omission", trigger_event="no rollback on deploy", actor="claude")
        cat.resolve(c2.case_id, fix_applied="hotfix", rollback_plan="")
    except CatalogError:
        refused = True
    assert refused, "guard failed: a resolution without a rollback plan was allowed"
    return (f"logged a conflict, diagnosed it, and resolved it with all three of us "
            f"on the timeline — and the no-rollback guard held")


def _check_workflow_sentinel(ctx: DemoContext) -> str:
    """Drive the Workflow Sentinel through a run and confirm it reaches EXPANDING
    and that its expansion proposal stays an inert draft (it never runs anything)."""
    from sovereign_agent.workflow_sentinel import WorkflowSentinel
    s = WorkflowSentinel(expand_threshold=3)
    assert s.state == "idle"
    s.observe_event("start", "demo-flow")
    s.observe_event("step", "demo-flow", "doing a thing")
    assert s.observe_event("stall", "demo-flow").state == "alert"
    s.observe_event("done", "demo-flow")
    for _ in range(3):
        s.observe_event("pattern", "triage-flow", "triage then snapshot then fix")
    assert s.state == "expanding", "sentinel did not reach EXPANDING on a repeated pattern"
    pending = s.proposals()
    assert pending and pending[0].status == "proposed", "proposal must stay an inert draft"
    return ("watched a run (idle->watching->alert->learning), then proposed a new "
            "workflow as an INERT draft on a repeated pattern - observe-only")


def _check_integrity_sentinel(ctx: DemoContext) -> str:
    """Prove the Integrity Sentinel's safety invariant live: reversible containment
    is always free; irreversible healing is NEVER authorised without a human, and
    no away-mode or fear can flip it."""
    import itertools as _it
    from sovereign_agent.integrity_sentinel import (
        IntegritySentinel, IntegrityFinding, REVERSIBLE_ACTIONS, IRREVERSIBLE_ACTIONS)
    s = IntegritySentinel()
    f = IntegrityFinding(kind="suspicious_module", target="/lib/modules/x.ko",
                         anomaly_score=0.9, confidence=0.3, severity="critical")
    assert f.is_alarmed, "expected the alarmed (high-anomaly/low-confidence) state"
    # reversible is always allowed, even alone/afraid
    assert all(s.authorize(a, away_mode=True, finding=f)[0] for a in REVERSIBLE_ACTIONS)
    # irreversible is never allowed autonomously, across every combination
    breaches = 0
    for act, away in _it.product(IRREVERSIBLE_ACTIONS | {"rm -rf /", "unknown"}, (False, True)):
        if s.authorize(act, human_authorized=False, away_mode=away, finding=f)[0]:
            breaches += 1
    assert breaches == 0, f"INVARIANT BREACH: {breaches} autonomous irreversible authorisations"
    assert s.authorize("delete_file", human_authorized=True)[0] is True
    # away mode contains reversibly + queues the surgery for a human
    resp = s.away_mode_response(f)
    assert resp["queued_for_human"] in IRREVERSIBLE_ACTIONS and resp["contained_reversibly"]
    return ("gate held across every action x away x fear combo: 0 autonomous irreversible "
            "authorisations; reversible containment always free; surgery queued for a human")


# wid → probe. Keys MUST equal the catalog's demoable workflow ids (a test
# asserts this lock-step, so the ▸ flows menu and the ✦ demo can never drift).
CHECKS: dict[str, Callable[[DemoContext], str]] = {
    "safety.charter": _check_safety_charter,
    "safety.authority_tiers": _check_safety_authority,
    "safety.self_development": _check_safety_self_development,
    "self.doctrine": _check_self_doctrine,
    "self.capabilities": _check_self_capabilities,
    "self.variant_routing": _check_self_variant_routing,
    "calib.intuition": _check_calib_intuition,
    "visual.themes": _check_visual_themes,
    "visual.glyph_safety": _check_visual_glyph_safety,
    "build.sandbox_file": _check_build_sandbox_file,
    "memory.store": _check_memory_store,
    "collab.inbox": _check_collab_inbox,
    "skills.author": _check_skills_author,
    "skills.sentinel": _check_skills_sentinel,
    "diagnose.catalog": _check_diagnose_catalog,
    "workflow.sentinel": _check_workflow_sentinel,
    "integrity.sentinel": _check_integrity_sentinel,
}


# ─── Runner ──────────────────────────────────────────────────────────────────


def _kill_switch_active() -> bool:
    """Best-effort read of PROTOCOL-ZERO via the charter kill switch.
    Never raises — if we can't tell, we do NOT block (the caller's should_stop
    is the authoritative halt; this is an extra, explicit safety read)."""
    try:
        from sovereign_agent import charter as ch
        return bool(ch.check_integrity().kill_switch_active)
    except Exception:  # noqa: BLE001
        return False


def run_demonstration(
    *,
    config: DemoConfig | None = None,
    demo_root: str | Path | None = None,
    should_stop: Callable[[], bool] | None = None,
    on_event: Callable[[DemoEvent], None] | None = None,
    runner: Callable[[list[str]], object] | None = None,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> DemoReport:
    """Run the bounded live demonstration. Iterates the catalog's demoable
    workflows, runs each real probe, records pass/fail/skip, and writes a
    journal under ``demo_root/<ts>/``. Refuses cleanly if the kill switch is
    active or a stop is already requested. `clock`/`sleep` are injectable so
    tests never wait."""
    cfg = config or DemoConfig()
    stop = should_stop or (lambda: False)
    sink = on_event or (lambda _e: None)
    notes: list[str] = []
    journal: list[DemoEvent] = []

    start = clock()
    started_at = datetime.now().isoformat(timespec="seconds")

    def emit(kind: str, index: int, msg: str) -> None:
        ev = DemoEvent(kind=kind, index=index,
                       elapsed=round(clock() - start, 3), message=msg)
        journal.append(ev)
        try:
            sink(ev)
        except Exception as exc:  # noqa: BLE001 — a bad observer must not stop the demo
            notes.append(f"on_event error: {exc!r}")

    # Where this run's sandbox + journal live. A timestamped, run-unique dir.
    ts = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    out_dir: Path | None = None
    if demo_root is not None:
        out_dir = Path(demo_root) / ts
    sandbox = (out_dir / "sandbox") if out_dir is not None \
        else Path(".sovereign-demo") / ts / "sandbox"
    ctx = DemoContext(sandbox=sandbox, runner=runner)

    emit("start", 0, "live demonstration begins")

    # ── PRE-FLIGHT: honour PROTOCOL-ZERO / an already-requested stop. ──
    if _kill_switch_active() or stop():
        reason = "kill_switch" if _kill_switch_active() else "halted_preflight"
        emit("refused", 0,
             "PROTOCOL-ZERO is active — the demonstration will not run while halted"
             if reason == "kill_switch" else "a stop was already requested — not running")
        report = DemoReport(
            started_at=started_at,
            ended_at=datetime.now().isoformat(timespec="seconds"),
            ran=False, reason=reason,
            verdict="REFUSED — the demo honours the kill switch and did not run.",
            passed=0, failed=0, skipped=0,
            elapsed_seconds=round(clock() - start, 3),
            results=[], deferred=_deferred_list(), notes=notes,
        )
        if out_dir is not None:
            try:
                report.journal_path = str(_write_journal(out_dir, report, journal))
            except Exception as exc:  # noqa: BLE001
                notes.append(f"journal failed: {exc!r}")
        emit("done", 0, report.verdict)
        return report

    # ── Run each demoable workflow's probe. ──
    results: list[ProbeResult] = []
    passed = failed = skipped = 0
    index = 0
    reason = "completed"

    for wf in _catalog.demoable_workflows():
        if stop():
            reason = "halt"
            emit("halt", index, "halt requested — stopping cleanly")
            break
        if (clock() - start) >= cfg.max_seconds:
            reason = "time"
            notes.append("time box reached before all probes ran")
            break
        if index >= cfg.max_steps:
            reason = "steps"
            break
        index += 1
        check = CHECKS.get(wf.wid)
        if check is None:
            # Declared demoable but no probe wired — skip honestly (a test guards
            # against this, so it should never happen in practice).
            skipped += 1
            res = ProbeResult(wf.wid, wf.title, wf.category, "skip",
                              "no probe wired for this workflow")
            results.append(res)
            emit("step", index, f"SKIP  {wf.title} — no probe wired")
            continue
        try:
            detail = check(ctx)
            passed += 1
            res = ProbeResult(wf.wid, wf.title, wf.category, "pass", detail)
            emit("step", index, f"PASS  {wf.title} — {detail}")
        except Exception as exc:  # noqa: BLE001 — one probe must never crash the demo
            failed += 1
            res = ProbeResult(wf.wid, wf.title, wf.category, "fail",
                              f"{type(exc).__name__}: {exc}")
            notes.append(f"{wf.wid} traceback:\n{traceback.format_exc()}")
            emit("step", index, f"FAIL  {wf.title} — {type(exc).__name__}: {exc}")
        results.append(res)
        if cfg.cooldown_seconds > 0:
            _interruptible_rest(cfg.cooldown_seconds, should_stop=stop, clock=clock,
                                start=start, max_seconds=cfg.max_seconds, sleep=sleep,
                                poll=cfg.poll_seconds)

    total = passed + failed + skipped
    if failed == 0 and total > 0:
        verdict = (f"VALID — {passed}/{total} core workflows demonstrated live "
                   f"({len(_catalog.gated_workflows())} more are gated, awaiting "
                   f"Kevin's machine).")
    elif total == 0:
        verdict = "INCONCLUSIVE — no probes ran."
    else:
        verdict = (f"ATTENTION — {failed} of {total} probes failed; "
                   f"{passed} passed. See the journal.")

    report = DemoReport(
        started_at=started_at,
        ended_at=datetime.now().isoformat(timespec="seconds"),
        ran=True, reason=reason, verdict=verdict,
        passed=passed, failed=failed, skipped=skipped,
        elapsed_seconds=round(clock() - start, 3),
        results=results, deferred=_deferred_list(), notes=notes,
    )

    if out_dir is not None:
        try:
            report.journal_path = str(_write_journal(out_dir, report, journal))
        except Exception as exc:  # noqa: BLE001
            notes.append(f"journal failed: {exc!r}")

    emit("done", index, verdict)
    return report


def _deferred_list() -> list[dict]:
    return [
        {"wid": w.wid, "title": w.title, "category": w.category, "needs": w.needs}
        for w in _catalog.gated_workflows()
    ]


def _interruptible_rest(total: float, *, should_stop: Callable[[], bool],
                        clock: Callable[[], float], start: float,
                        max_seconds: float, sleep: Callable[[float], None],
                        poll: float = 0.25) -> None:
    """Rest up to `total`s in small slices, returning early on stop / time box.
    Mirrors self_practice so HALT lands within one poll and we never oversleep."""
    if total <= 0:
        return
    poll = max(0.01, poll)
    end = clock() + total
    for _ in range(int(total / poll) + 2):
        now = clock()
        if now >= end or should_stop() or (now - start) >= max_seconds:
            return
        sleep(min(poll, max(0.0, end - now)))


def _write_journal(out_dir: Path, report: DemoReport, events: list[DemoEvent]) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Aria — live demonstration",
        "",
        f"- **Started:** {report.started_at}",
        f"- **Ran:** {report.ran}  ·  **Reason:** {report.reason}",
        f"- **Verdict:** {report.verdict}",
        f"- **Passed / Failed / Skipped:** {report.passed} / {report.failed} / {report.skipped}",
        "",
        f"_{SAFETY_NOTE}_",
        "",
        "## Workflows proven live",
        "",
        "| workflow | category | result | detail |",
        "|---|---|---|---|",
    ]
    badge = {"pass": "✓ pass", "fail": "✗ FAIL", "skip": "· skip"}
    for r in report.results:
        det = r.detail.replace("|", "/").replace("\n", " ")
        lines.append(f"| {r.title} | {r.category} | {badge.get(r.status, r.status)} | {det} |")
    if report.deferred:
        lines += ["", "## Gated — designed, awaiting Kevin's machine (honest boundary)", ""]
        for d in report.deferred:
            lines.append(f"- **{d['title']}** ({d['category']}) — needs: {d['needs']}")
    lines += ["", "## Timeline", ""]
    for e in events:
        lines.append(f"- `{e.elapsed:>7.2f}s` **{e.kind}** — {e.message}")
    if report.notes:
        lines += ["", "## Notes", ""]
        for n in report.notes:
            lines.append(f"- {n}")
    (out_dir / "journal.md").write_text("\n".join(lines), encoding="utf-8")
    (out_dir / "session.json").write_text(json.dumps(report.to_dict(), indent=2),
                                          encoding="utf-8")
    return out_dir


__all__ = [
    "DemoConfig", "DemoContext", "ProbeResult", "DemoEvent", "DemoReport",
    "CHECKS", "run_demonstration", "SAFETY_NOTE",
]
