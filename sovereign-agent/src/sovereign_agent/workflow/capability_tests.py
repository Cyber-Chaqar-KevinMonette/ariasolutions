"""capability_tests.py — a bounded, observable test of Aria's REAL capabilities.

capability-test-menu-d (Kevin, 2026-07-28): "make a test button... to test her
abilities, to do real work. Make images... search the web, make new trackers,
make new bots." Unlike workflow/demo.py (introspection-only, explicitly "no
subprocesses, no models, no network"), this module actually invokes real
tools — image generation (GPU/diffusers), web search (network), game-project
scaffolding, the marketing planner — with small, cheap, safe inputs, and
records what each produced (and where).

SAFETY (deliberately different from demo.py's promise, and said so plainly):
  • PRE-FLIGHT KILL-SWITCH GATE — same contract as demo.py: refuses to run at
    all if PROTOCOL-ZERO is tripped or a stop was already requested.
  • BOUNDED + HALT-ABLE + OBSERVABLE — time-boxed (default 300s, longer than
    demo.py's 120s since real GPU/network calls are slower), polls
    should_stop() between tests, emits a CapabilityEvent per test, writes
    journal.md + session.json.
  • DOES call real models/subprocesses/network — that's the point. Every test
    function is small, cheap, and safe by construction (tiny image sizes,
    a fixed benign search query, sandbox-scoped writes), never destructive.
  • The two Discord-adjacent tests (create.discord_tracker,
    create.discord_bot_command) are dry-run/introspection ONLY, by design,
    forever — they prove the real mechanism without ever calling Discord or
    the network, so clicking "test" repeatedly can never spam a live server.
  • GPU tools already self-serialize via vram_lock() (image_generate.py) —
    this module adds no locking of its own; it just calls the real execute().
  • Injectable clock/sleep so the runner's own timing logic is testable
    without waiting; the real tool calls in CAPABILITY_TEST_FNS are
    monkeypatched to cheap stand-ins in the main test suite (calling real
    GPU/network isn't safe or fast enough for CI) — see
    tests/test_workflow_capability_tests.py.
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
    "Bounded live capability test: calls REAL tools (image generation, web "
    "search, game-project scaffolding, the marketing planner) with small, "
    "cheap, safe inputs, and records what each produced. The two Discord "
    "tests are dry-run/introspection only — never a live network/Discord "
    "call. Honours the kill switch, is halt-able, time-boxed, and observable."
)

CapResultStatus = str  # "pass" | "fail" | "skip"


class CapTestSkipped(Exception):
    """Raise from a CAPABILITY_TEST_FNS entry to report an honest, non-failing
    skip (e.g. no internet reachable for create.web_search) — a third state
    alongside demo.py's plain return-or-raise pass/fail contract."""


@dataclass
class CapTestConfig:
    max_seconds: float = 300.0     # real tool calls are slower than demo.py's probes
    max_steps: int = 50
    cooldown_seconds: float = 0.0
    poll_seconds: float = 0.25


@dataclass
class CapTestContext:
    """What a capability test is handed. `sandbox` is a writable dir unique
    to this run — tests that need a safe write target (game-project
    scaffolding, the marketing planner) use it instead of the real data dir."""
    sandbox: Path


@dataclass
class CapabilityResult:
    wid: str
    title: str
    category: str
    status: CapResultStatus
    detail: str
    artifact_path: str | None = None
    elapsed_seconds: float = 0.0


@dataclass
class CapabilityEvent:
    kind: str                      # start|preflight|queued|running|step|done|refused|halt
    index: int
    elapsed: float
    message: str
    at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


@dataclass
class CapabilityReport:
    started_at: str
    ended_at: str
    ran: bool
    reason: str                    # completed | kill_switch | halted_preflight | error
    verdict: str
    queued: int
    passed: int
    failed: int
    skipped: int
    elapsed_seconds: float
    results: list[CapabilityResult] = field(default_factory=list)
    deferred: list[dict] = field(default_factory=list)   # gated capabilities, named
    journal_path: str | None = None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        d["results"] = [r.__dict__ for r in self.results]
        return d


# ─── the real capability tests — one per cap-testable workflow, keyed by wid ─
#
# Each returns (detail, artifact_path) and RAISES on failure (AssertionError
# for an honest failure, CapTestSkipped for an honest non-failing skip) — the
# same "return on success, raise on anything else" contract demo.py's CHECKS
# use, split into two exception types instead of one.


def _test_create_image(ctx: CapTestContext) -> tuple[str, str | None]:
    import asyncio
    from ..tools.image_generate import GenerateImageTool

    tool = GenerateImageTool()
    args = tool.Args(prompt="a small red cube on a plain white background",
                     model="sdxl-turbo", width=256, height=256, steps=2)
    result = asyncio.run(tool.execute(args, trace_id="captest-create.image"))
    if not result.ok:
        raise AssertionError(result.error or "generate_image failed")
    return "generated a real 256×256 PNG via GenerateImageTool", result.output


def _test_create_image_edit(ctx: CapTestContext) -> tuple[str, str | None]:
    import asyncio
    from ..tools.image_edit import EditImageTool
    from ..tools.image_generate import GenerateImageTool

    gen = GenerateImageTool()
    src = asyncio.run(gen.execute(
        gen.Args(prompt="a small blue sphere on a plain white background",
                 model="sdxl-turbo", width=256, height=256, steps=2),
        trace_id="captest-create.image_edit-source"))
    if not src.ok:
        raise AssertionError(f"couldn't generate a source image to edit: {src.error}")

    edit = EditImageTool()
    result = asyncio.run(edit.execute(
        edit.Args(path=src.output, prompt="the same sphere, but green",
                  model="sdxl-turbo", strength=0.5, steps=2),
        trace_id="captest-create.image_edit"))
    if not result.ok:
        raise AssertionError(result.error or "image edit failed")
    return "edited a freshly-generated real image via EditImageTool", result.output


def _test_create_web_search(ctx: CapTestContext) -> tuple[str, str | None]:
    import asyncio
    from ..tools.web_search import WebSearchTool

    tool = WebSearchTool()
    args = tool.Args(query="site:wikipedia.org python programming language", max_results=3)
    result = asyncio.run(tool.execute(args, trace_id="captest-create.web_search"))
    if not result.ok:
        err = (result.error or "").lower()
        if "disabled" in err or "unreachable" in err:
            raise CapTestSkipped("internet unavailable — the search never ran")
        raise AssertionError(result.error or "web_search failed")
    return f"found {len(result.output)} real result(s) via WebSearchTool", None


def _test_create_game_project(ctx: CapTestContext) -> tuple[str, str | None]:
    import asyncio
    from ..tools.define_game_project import DefineGameProjectTool

    tool = DefineGameProjectTool(data_dir=ctx.sandbox)
    args = tool.Args(project_name="Capability Test Game", genre="idle-incremental",
                     concept="a throwaway test project, never a real one")
    result = asyncio.run(tool.execute(args, trace_id="captest-create.game_project"))
    if not result.ok:
        raise AssertionError(result.error or "define_game_project failed")
    slug = (result.output or {}).get("slug", "?")
    return f"defined throwaway project {slug!r} in this run's own sandbox", str(ctx.sandbox)


def _test_create_scaffold_godot_project(ctx: CapTestContext) -> tuple[str, str | None]:
    import asyncio
    from unittest.mock import patch

    from ..game_projects import GameProject, game_workspace_dir, save
    from ..tools.scaffold_godot_project import ScaffoldGodotProjectTool

    save(GameProject(project_name="Capability Test Godot Project", dimension="2d"),
        ctx.sandbox)
    workspace = game_workspace_dir("capability-test-godot-project",
                                   sandbox_dir=ctx.sandbox)
    tool = ScaffoldGodotProjectTool(data_dir=ctx.sandbox)
    import sovereign_agent.tools.scaffold_godot_project as mod
    with patch.object(mod, "game_workspace_dir", return_value=workspace), \
         patch.object(mod, "check_write_path", side_effect=lambda p, mode: p):
        args = tool.Args(project_slug="capability-test-godot-project")
        result = asyncio.run(tool.execute(args, trace_id="captest-create.scaffold_godot_project"))
    if not result.ok:
        raise AssertionError(result.error or "scaffold_godot_project failed")
    project_godot = workspace / "project.godot"
    if not project_godot.is_file():
        raise AssertionError("project.godot was not written")
    return (f"scaffolded a real 2D Godot project (Node2D root) in this "
           f"run's own sandbox", str(workspace))


def _test_create_place_game_sprite(ctx: CapTestContext) -> tuple[str, str | None]:
    import asyncio
    from unittest.mock import patch

    from ..game_projects import GameProject, game_workspace_dir, save
    from ..tools.place_game_sprite import PlaceGameSpriteTool
    from ..tools.scaffold_godot_project import ScaffoldGodotProjectTool

    save(GameProject(project_name="Capability Test Sprite Project", dimension="2d"),
        ctx.sandbox)
    workspace = game_workspace_dir("capability-test-sprite-project", sandbox_dir=ctx.sandbox)

    scaffold_tool = ScaffoldGodotProjectTool(data_dir=ctx.sandbox)
    import sovereign_agent.tools.scaffold_godot_project as scaffold_mod
    with patch.object(scaffold_mod, "game_workspace_dir", return_value=workspace), \
         patch.object(scaffold_mod, "check_write_path", side_effect=lambda p, mode: p):
        scaffold_result = asyncio.run(scaffold_tool.execute(
            scaffold_tool.Args(project_slug="capability-test-sprite-project"),
            trace_id="captest-create.place_game_sprite-scaffold",
        ))
    if not scaffold_result.ok:
        raise AssertionError(scaffold_result.error or "scaffold_godot_project failed")

    sprite_tool = PlaceGameSpriteTool(data_dir=ctx.sandbox)
    import sovereign_agent.tools.place_game_sprite as sprite_mod
    with patch.object(sprite_mod, "game_workspace_dir", return_value=workspace), \
         patch.object(sprite_mod, "check_write_path", side_effect=lambda p, mode: p):
        result = asyncio.run(sprite_tool.execute(
            sprite_tool.Args(project_slug="capability-test-sprite-project",
                             prompt="a small red cube on a plain white background",
                             sprite_name="capability test cube",
                             model="sdxl-turbo", width=256, height=256, steps=2),
            trace_id="captest-create.place_game_sprite",
        ))
    if not result.ok:
        raise AssertionError(result.error or "place_game_sprite failed")
    sprite_path = Path(result.output["sprite_path"])
    if not sprite_path.is_file():
        raise AssertionError("sprite PNG was not written")
    scene_text = (workspace / "main.tscn").read_text()
    if "ext_resource" not in scene_text or result.output["node_name"] not in scene_text:
        raise AssertionError("main.tscn was not updated with the new sprite node")
    return (f"generated a real 256×256 PNG, imported it, and placed it as "
           f"{result.output['node_type']} {result.output['node_name']!r} in "
           f"this run's own sandbox", str(sprite_path))


def _test_create_game_design_brief(ctx: CapTestContext) -> tuple[str, str | None]:
    from ..game_projects import GameProject, save
    from ..planners.game_design_brief import SECTIONS, GameDesignBriefPlanner

    save(GameProject(project_name="Capability Test Design Project",
                     genre="platformer", dimension="2d",
                     concept="a throwaway test project, never a real one"),
        ctx.sandbox)

    planner = GameDesignBriefPlanner()
    out_path = ctx.sandbox / "design_brief.md"
    result = planner.plan(project_slug="capability-test-design-project",
                          output=str(out_path), data_dir=ctx.sandbox)
    expected = [name for name, _ in SECTIONS]
    got = [step.args.get("section") for step in result.steps]
    if got != expected:
        raise AssertionError(f"section order mismatch: expected {expected}, got {got}")

    rendered = planner.render_step(result.steps[3], {})  # scene-architecture — the Godot-specific one
    if "Node2D" not in rendered and "CharacterBody2D" not in rendered:
        raise AssertionError("doctrine engine guidance wasn't threaded into the rendered step")
    return (f"planned {len(result.steps)} real design-brief sections, in order, "
           "with Godot-specific doctrine guidance threaded in", None)


def _test_create_marketing_brief(ctx: CapTestContext) -> tuple[str, str | None]:
    from ..planners.marketing_brief import SECTIONS, MarketingBriefPlanner

    planner = MarketingBriefPlanner()
    out_path = ctx.sandbox / "brief.md"
    result = planner.plan(product="Capability Test Product", output=str(out_path))
    expected = [name for name, _ in SECTIONS]
    got = [step.args.get("section") for step in result.steps]
    if got != expected:
        raise AssertionError(f"section order mismatch: expected {expected}, got {got}")
    return (f"planned {len(result.steps)} real marketing sections, in order "
           f"(structure only — full copy needs the agentic loop)", None)


def _test_create_movie_project(ctx: CapTestContext) -> tuple[str, str | None]:
    import asyncio
    from ..tools.define_movie_project import DefineMovieProjectTool

    tool = DefineMovieProjectTool(data_dir=ctx.sandbox)
    args = tool.Args(title="Capability Test Film", genre="short-film",
                     logline="a throwaway test project, never a real one")
    result = asyncio.run(tool.execute(args, trace_id="captest-create.movie_project"))
    if not result.ok:
        raise AssertionError(result.error or "define_movie_project failed")
    return f"defined throwaway movie project {result.output['slug']!r} in this run's own sandbox", str(ctx.sandbox)


def _test_create_movie_pitch(ctx: CapTestContext) -> tuple[str, str | None]:
    from ..planners.movie_pitch import DEFAULT_PITCH_COUNT, MoviePitchPlanner

    planner = MoviePitchPlanner()
    out_path = ctx.sandbox / "pitches.md"
    result = planner.plan(theme="capability test theme", output=str(out_path))
    if len(result.steps) != DEFAULT_PITCH_COUNT:
        raise AssertionError(
            f"expected {DEFAULT_PITCH_COUNT} pitch steps, got {len(result.steps)}")
    indices = [s.args.get("pitch_index") for s in result.steps]
    if indices != list(range(1, DEFAULT_PITCH_COUNT + 1)):
        raise AssertionError(f"pitch steps out of order: {indices}")
    return (f"planned {len(result.steps)} real pitch steps, in order "
           f"(structure only — full pitch text needs the agentic loop)", None)


def _test_create_video(ctx: CapTestContext) -> tuple[str, str | None]:
    import asyncio
    from ..movie_projects import MovieProject, save, slugify
    from ..tools.generate_movie_clip import GenerateMovieClipTool

    proj = MovieProject(title="Capability Test Clip Project", genre="short-film")
    save(proj, ctx.sandbox)
    slug = slugify(proj.title)

    tool = GenerateMovieClipTool(data_dir=ctx.sandbox)
    args = tool.Args(project_slug=slug,
                     prompt="a small red cube on a plain white background",
                     width=256, height=256, num_frames=9, steps=8)
    result = asyncio.run(tool.execute(args, trace_id="captest-create.video"))
    if not result.ok:
        raise AssertionError(result.error or "generate_movie_clip failed")
    return ("generated a real local video clip via LTX-Video (FOSS, no cloud) "
           "— cheapest verified-safe combo, real but low quality", result.output["path"])


def _test_create_discord_tracker(ctx: CapTestContext) -> tuple[str, str | None]:
    from ..discord_admin.blueprint import shop_blueprint

    bp = shop_blueprint()
    if not bp.categories or not bp.channel_names():
        raise AssertionError("blueprint produced no categories/channels")
    return (f"planned {len(bp.categories)} real categories / "
           f"{len(bp.channel_names())} real channels through the same "
           f"blueprint a live setup uses — zero network/Discord calls", None)


def _test_create_discord_bot_command(ctx: CapTestContext) -> tuple[str, str | None]:
    from ..discord_admin.bot import COMMANDS, build_commands_embed

    if not COMMANDS:
        raise AssertionError("COMMANDS catalog is empty")
    for entry in COMMANDS:
        if len(entry) != 3:
            raise AssertionError(f"malformed COMMANDS entry: {entry!r}")
    embed = build_commands_embed("Capability Test", 0x000000, "owner")
    if embed is None:
        raise AssertionError("build_commands_embed returned None")
    return (f"{len(COMMANDS)} real commands render through the help-panel "
           f"builder — zero Discord client/network calls", None)


# wid → real capability test. Keys MUST equal the catalog's cap-testable
# workflow ids (a test asserts this lock-step, mirroring demo.py's CHECKS).
CAPABILITY_TEST_FNS: dict[str, Callable[[CapTestContext], tuple[str, str | None]]] = {
    "create.image": _test_create_image,
    "create.game_art": _test_create_image,  # alias: same tool, game-art guidance only
    "create.image_edit": _test_create_image_edit,
    "create.web_search": _test_create_web_search,
    "create.game_project": _test_create_game_project,
    "create.scaffold_godot_project": _test_create_scaffold_godot_project,
    "create.place_game_sprite": _test_create_place_game_sprite,
    "create.game_design_brief": _test_create_game_design_brief,
    "create.marketing_brief": _test_create_marketing_brief,
    "create.movie_project": _test_create_movie_project,
    "create.movie_pitch": _test_create_movie_pitch,
    "create.video": _test_create_video,
    "create.discord_tracker": _test_create_discord_tracker,
    "create.discord_bot_command": _test_create_discord_bot_command,
}


# ─── Runner ──────────────────────────────────────────────────────────────────


def _kill_switch_active() -> bool:
    """Best-effort read of PROTOCOL-ZERO via the charter kill switch. Never
    raises — if we can't tell, we do NOT block (should_stop is authoritative;
    this is an extra, explicit safety read). Duplicated from demo.py's own
    helper (6 lines) rather than imported, keeping the two engines decoupled."""
    try:
        from sovereign_agent import charter as ch
        return bool(ch.check_integrity().kill_switch_active)
    except Exception:  # noqa: BLE001
        return False


def run_capability_tests(
    selected_wids: list[str] | None = None,
    *,
    config: CapTestConfig | None = None,
    out_root: str | Path | None = None,
    should_stop: Callable[[], bool] | None = None,
    on_event: Callable[[CapabilityEvent], None] | None = None,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> CapabilityReport:
    """Run real capability tests. `selected_wids=None` runs every cap-testable
    workflow ("Test All"). Refuses cleanly if the kill switch is active or a
    stop is already requested. Writes a journal under `out_root/<ts>/`.
    `clock`/`sleep` are injectable so the runner's own timing is testable;
    real tool calls inside CAPABILITY_TEST_FNS are what actually take time."""
    cfg = config or CapTestConfig()
    stop = should_stop or (lambda: False)
    sink = on_event or (lambda _e: None)
    notes: list[str] = []
    journal: list[CapabilityEvent] = []

    start = clock()
    started_at = datetime.now().isoformat(timespec="seconds")

    def emit(kind: str, index: int, msg: str) -> None:
        ev = CapabilityEvent(kind=kind, index=index,
                             elapsed=round(clock() - start, 3), message=msg)
        journal.append(ev)
        try:
            sink(ev)
        except Exception as exc:  # noqa: BLE001 — a bad observer must not stop the run
            notes.append(f"on_event error: {exc!r}")

    ts = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    out_dir: Path | None = None
    if out_root is not None:
        out_dir = Path(out_root) / ts
    sandbox = (out_dir / "sandbox") if out_dir is not None \
        else Path(".sovereign-captest") / ts / "sandbox"
    ctx = CapTestContext(sandbox=sandbox)

    all_testable = _catalog.capability_testable_workflows()
    by_wid = {w.wid: w for w in all_testable}
    if selected_wids is None:
        targets = list(all_testable)
    else:
        targets = [by_wid[w] for w in selected_wids if w in by_wid]

    emit("start", 0, f"capability test run begins — {len(targets)} queued")

    if _kill_switch_active() or stop():
        reason = "kill_switch" if _kill_switch_active() else "halted_preflight"
        emit("refused", 0,
             "PROTOCOL-ZERO is active — the capability test run will not start "
             "while halted" if reason == "kill_switch" else
             "a stop was already requested — not running")
        report = CapabilityReport(
            started_at=started_at,
            ended_at=datetime.now().isoformat(timespec="seconds"),
            ran=False, reason=reason,
            verdict="REFUSED — capability tests honour the kill switch and did not run.",
            queued=len(targets), passed=0, failed=0, skipped=0,
            elapsed_seconds=round(clock() - start, 3),
            results=[], deferred=_deferred_list(), notes=notes,
        )
        if out_dir is not None:
            try:
                report.journal_path = str(_write_capability_journal(out_dir, report, journal))
            except Exception as exc:  # noqa: BLE001
                notes.append(f"journal failed: {exc!r}")
        emit("done", 0, report.verdict)
        return report

    emit("queued", 0, f"{len(targets)} test(s) queued: " + ", ".join(w.wid for w in targets))

    results: list[CapabilityResult] = []
    passed = failed = skipped = 0
    index = 0
    reason = "completed"

    for wf in targets:
        if stop():
            reason = "halt"
            emit("halt", index, "halt requested — stopping cleanly")
            break
        if (clock() - start) >= cfg.max_seconds:
            reason = "time"
            notes.append("time box reached before all tests ran")
            break
        if index >= cfg.max_steps:
            reason = "steps"
            break
        index += 1
        emit("running", index, f"running {wf.title}…")
        fn = CAPABILITY_TEST_FNS.get(wf.wid)
        t0 = clock()
        if fn is None:
            skipped += 1
            res = CapabilityResult(wf.wid, wf.title, wf.category, "skip",
                                   "no capability test wired for this workflow")
            results.append(res)
            emit("step", index, f"SKIP  {wf.title} — no test wired")
            continue
        try:
            detail, artifact = fn(ctx)
            elapsed = round(clock() - t0, 3)
            passed += 1
            res = CapabilityResult(wf.wid, wf.title, wf.category, "pass",
                                   detail, artifact, elapsed)
            emit("step", index, f"PASS  {wf.title} — {detail}")
        except CapTestSkipped as exc:
            elapsed = round(clock() - t0, 3)
            skipped += 1
            res = CapabilityResult(wf.wid, wf.title, wf.category, "skip",
                                   str(exc), None, elapsed)
            emit("step", index, f"SKIP  {wf.title} — {exc}")
        except Exception as exc:  # noqa: BLE001 — one test must never crash the run
            elapsed = round(clock() - t0, 3)
            failed += 1
            res = CapabilityResult(wf.wid, wf.title, wf.category, "fail",
                                   f"{type(exc).__name__}: {exc}", None, elapsed)
            notes.append(f"{wf.wid} traceback:\n{traceback.format_exc()}")
            emit("step", index, f"FAIL  {wf.title} — {type(exc).__name__}: {exc}")
        results.append(res)
        if cfg.cooldown_seconds > 0:
            _interruptible_rest(cfg.cooldown_seconds, should_stop=stop, clock=clock,
                                start=start, max_seconds=cfg.max_seconds, sleep=sleep,
                                poll=cfg.poll_seconds)

    total = passed + failed + skipped
    if failed == 0 and total > 0:
        verdict = (f"COMPLETE — {passed}/{total} capability tests passed live "
                  f"({len(_catalog.gated_workflows())} more are gated, awaiting "
                  f"a real capability first).")
    elif total == 0:
        verdict = "INCONCLUSIVE — no tests ran."
    else:
        verdict = (f"ATTENTION — {failed} of {total} tests failed; "
                  f"{passed} passed. See the journal.")

    report = CapabilityReport(
        started_at=started_at,
        ended_at=datetime.now().isoformat(timespec="seconds"),
        ran=True, reason=reason, verdict=verdict,
        queued=len(targets), passed=passed, failed=failed, skipped=skipped,
        elapsed_seconds=round(clock() - start, 3),
        results=results, deferred=_deferred_list(), notes=notes,
    )

    if out_dir is not None:
        try:
            report.journal_path = str(_write_capability_journal(out_dir, report, journal))
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
    Mirrors demo.py's own so HALT lands within one poll and we never oversleep."""
    if total <= 0:
        return
    poll = max(0.01, poll)
    end = clock() + total
    for _ in range(int(total / poll) + 2):
        now = clock()
        if now >= end or should_stop() or (now - start) >= max_seconds:
            return
        sleep(min(poll, max(0.0, end - now)))


def _write_capability_journal(out_dir: Path, report: CapabilityReport,
                              events: list[CapabilityEvent]) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Aria — capability test run",
        "",
        f"- **Started:** {report.started_at}",
        f"- **Ran:** {report.ran}  ·  **Reason:** {report.reason}",
        f"- **Verdict:** {report.verdict}",
        f"- **Queued / Passed / Failed / Skipped:** "
        f"{report.queued} / {report.passed} / {report.failed} / {report.skipped}",
        "",
        f"_{SAFETY_NOTE}_",
        "",
        "## Capabilities tested live",
        "",
        "| capability | category | result | detail | artifact |",
        "|---|---|---|---|---|",
    ]
    badge = {"pass": "✓ pass", "fail": "✗ FAIL", "skip": "· skip"}
    for r in report.results:
        det = r.detail.replace("|", "/").replace("\n", " ")
        art = (r.artifact_path or "—").replace("|", "/")
        lines.append(f"| {r.title} | {r.category} | {badge.get(r.status, r.status)} | "
                     f"{det} | `{art}` |")
    if report.deferred:
        lines += ["", "## Gated — a real, named future capability (honest boundary)", ""]
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
    "CapTestConfig", "CapTestContext", "CapTestSkipped", "CapabilityResult",
    "CapabilityEvent", "CapabilityReport", "CAPABILITY_TEST_FNS",
    "run_capability_tests", "SAFETY_NOTE",
]
