"""
╔══════════════════════════════════════════════════════════════════════════╗
║  cli.py — Operator surface (v0.2.5)                                      ║
║  Architecture §5 + §7a + §8a + §11 + §13                                 ║
╚══════════════════════════════════════════════════════════════════════════╝

The CLI is how YOU (the operator) talk to the agent. The agent doesn't
use it. Commands are grouped by purpose:

    Setup:        init       — bootstrap config dirs, secret key, DBs
                  doctor     — diagnose config + ollama reachability + models
                  config     — show resolved configuration
    Run:          run        — single ONESHOT task
                  busy       — drain backlog forever (or once / N times)
                  until      — drain until predicate
    Re-trigger:   plan       — pre-decompose a large task into atomic steps
                  continue   — execute ONE pending step from a continuation
                  continuations — list / show / delete continuation files
    Backlog:      backlog    — list / add / remove / show / requeue / clear
    Approvals:    approvals  — list pending Tier 3 requests
                  approve    — grant a request
                  deny       — refuse a request
    Safety:       halt       — trip PROTOCOL-ZERO
                  disarm     — clear PROTOCOL-ZERO (after review)
    Audit:        tail       — ingest events.jsonl into events.db
                  seal       — compute yesterday's Merkle root
                  verify     — verify a past seal still matches its events
                  events     — show recent events (with --follow)
                  lessons    — show recent distilled lessons

Exit codes are stable and documented:
    0  success
    1  generic runtime error
    2  usage error
    3  PROTOCOL-ZERO armed (refused start)
    4  not initialized (run `sovereign init`)
    5  ollama unreachable
    6  approval not found / already resolved
    7  budget exhausted (when applicable)
    8  continuation drained (used by `continue` and the loop driver)
    9  continuation locked by another process

Top-level flags (apply to every command):
    --version
    --json / -j         emit JSON for read commands
    --quiet / -q        suppress non-essential output
    --verbose / -v      log INFO / DEBUG to stderr
    --no-color          disable Rich color (implied when not a TTY)
    --config-dir PATH   override XDG config dir
    --data-dir PATH     override XDG data dir
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import structlog
import typer
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from . import __version__, protocol_zero
from .config import SETTINGS, Paths
from .events import init_events_db, tail_to_sqlite
from .modes import Mode, RunBudget


# ─── Exit codes (single source of truth) ────────────────────────────────────


class ExitCode:
    OK = 0
    ERROR = 1
    USAGE = 2
    HALTED = 3
    NOT_INITIALIZED = 4
    OLLAMA_UNREACHABLE = 5
    APPROVAL_NOT_FOUND = 6
    BUDGET = 7
    DRAINED = 8
    LOCKED = 9


# ─── Global state set by the top-level callback ─────────────────────────────


class _CliState:
    json_out: bool = False
    quiet: bool = False
    verbose: bool = False
    no_color: bool = False


STATE = _CliState()
console = Console()


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(level=level, stream=sys.stderr, format="%(message)s")
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(colors=not STATE.no_color),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
    )


def _override_paths(*, config_dir: Path | None, data_dir: Path | None) -> None:
    """Mutate SETTINGS.paths in place. Same trick as conftest."""
    if config_dir is None and data_dir is None:
        return
    new_paths = Paths(
        config_dir=config_dir or SETTINGS.paths.config_dir,
        data_dir=data_dir or SETTINGS.paths.data_dir,
    )
    object.__setattr__(SETTINGS, "paths", new_paths)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"sovereign-agent {__version__}")
        raise typer.Exit(ExitCode.OK)


app = typer.Typer(
    no_args_is_help=True,
    add_completion=True,
    rich_markup_mode="rich",
    help="◊ sovereign-agent — your local 24/7 agent",
    pretty_exceptions_show_locals=False,
)


@app.callback()
def _global_options(
    ctx: typer.Context,
    version: bool = typer.Option(
        False, "--version", callback=_version_callback, is_eager=True,
        help="Show version and exit.",
    ),
    json_out: bool = typer.Option(False, "--json", "-j", help="Emit JSON for read commands."),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress non-essential output."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Log INFO/DEBUG to stderr."),
    no_color: bool = typer.Option(False, "--no-color", help="Disable color output."),
    config_dir: Path | None = typer.Option(None, "--config-dir", help="Override XDG config dir."),
    data_dir: Path | None = typer.Option(None, "--data-dir", help="Override XDG data dir."),
) -> None:
    """Global options. Apply to every subcommand."""
    STATE.json_out = json_out
    STATE.quiet = quiet
    STATE.verbose = verbose
    STATE.no_color = no_color or not sys.stdout.isatty()
    if STATE.no_color:
        global console
        console = Console(no_color=True, force_terminal=False)
    _override_paths(config_dir=config_dir, data_dir=data_dir)
    _setup_logging(verbose)

    # ── Article V kill switch ─────────────────────────────────────────────
    # If the charter file is present but its integrity is violated, refuse
    # to dispatch anything except `sov doctor` and `sov charter`. Absence
    # of the charter (pre-charter operators) emits a doctor warning but
    # does NOT trigger the kill switch — operators upgrading must not be
    # stranded by it.
    invoked = ctx.invoked_subcommand
    if invoked in (None, "doctor", "charter"):
        return
    try:
        from . import charter as _charter
        verdict = _charter.check_integrity()
    except Exception:
        # Charter machinery itself broken — fall through. The doctor will
        # surface this on the next `sov doctor` invocation.
        return
    if verdict.kill_switch_active:
        sys.stderr.write(
            "\n╔══════════════════════════════════════════════════════════════════════╗\n"
            "║  [!] CHARTER VIOLATION -- kill switch active                         ║\n"
            "║                                                                      ║\n"
            f"║  {verdict.summary[:66].ljust(66)}  ║\n"
            "║                                                                      ║\n"
            "║  Per Article V, no command runs except `sov doctor` and              ║\n"
            "║  `sov charter` until charter integrity is restored.                  ║\n"
            "║                                                                      ║\n"
            "║  Repair paths:                                                       ║\n"
            "║    sov doctor                  # see the full diagnostic             ║\n"
            "║    sov charter status          # inspect the violation               ║\n"
            "║    sov charter amend --help    # ratify or amend                     ║\n"
            "╚══════════════════════════════════════════════════════════════════════╝\n"
        )
        raise typer.Exit(code=78)  # 78 = configuration error (sysexits.h)


# ─── Output helpers ─────────────────────────────────────────────────────────


def _print(*args: Any, **kwargs: Any) -> None:
    if STATE.quiet:
        return
    console.print(*args, **kwargs)


def _emit_json(payload: Any) -> None:
    typer.echo(json.dumps(payload, default=str, indent=2 if sys.stdout.isatty() else None))


def _die(code: int, message: str, *, hint: str | None = None) -> None:
    if STATE.json_out:
        payload = {"ok": False, "code": code, "error": message}
        if hint:
            payload["hint"] = hint
        _emit_json(payload)
    else:
        console.print(f"[red]✗ {message}[/red]")
        if hint:
            console.print(f"[dim]hint: {hint}[/dim]")
    raise typer.Exit(code)


# ─── Pre-flight checks ──────────────────────────────────────────────────────


def _preflight_initialized() -> None:
    if not SETTINGS.paths.secret_key_file.exists():
        _die(ExitCode.NOT_INITIALIZED, "agent is not initialized",
             hint="run `sovereign init` first")


def _preflight_not_halted() -> None:
    if SETTINGS.paths.halt_flag.exists() or protocol_zero.is_armed():
        _die(ExitCode.HALTED, "PROTOCOL-ZERO is armed",
             hint="review HALT file, then `sovereign disarm`")


def _preflight_ollama_reachable(*, fatal: bool = True) -> bool:
    import socket
    from urllib.parse import urlparse

    parsed = urlparse(SETTINGS.ollama_host)
    host = parsed.hostname or "localhost"
    port = parsed.port or 11434
    try:
        with socket.create_connection((host, port), timeout=3):
            return True
    except (OSError, socket.timeout) as e:
        if fatal:
            _die(ExitCode.OLLAMA_UNREACHABLE,
                 f"ollama unreachable at {host}:{port}: {e}",
                 hint="start ollama, or set OLLAMA_HOST")
        return False


# ─── Banner ─────────────────────────────────────────────────────────────────


BANNER = """[bold cyan]
╔══════════════════════════════════════════════════════════════════════╗
║                                                                      ║
║              ◊  S O V E R E I G N   A G E N T  ◊                     ║
║                                                                      ║
║       local · authority-tiered · audited · recoverable · yours       ║
║                                                                      ║
╚══════════════════════════════════════════════════════════════════════╝
[/bold cyan]"""


def _build_tools_for_mode(mode: Mode) -> dict:
    from .tools import (
        CopyFileTool, EditFileTool, EmbedQueryTool, ImageCaptionTool,
        ImpactScoreTool, ListDirTool, MemorySearchTool, MemoryWriteTool,
        PalaceSearchTool, ProposalWriteTool, ReadFileTool, SearchTextTool,
        WebFetchTool, WebSearchTool, WriteFileTool, internet_available,
    )
    tools = {
        "read_file": ReadFileTool(),
        "list_dir": ListDirTool(),
        "search_text": SearchTextTool(),
        "embed_query": EmbedQueryTool(),
        "image_caption": ImageCaptionTool(),
        "web_fetch": WebFetchTool(),
        "memory_search": MemorySearchTool(),
        "memory_write": MemoryWriteTool(),
        "palace_search": PalaceSearchTool(),
        "proposal_write": ProposalWriteTool(),
        "impact_score": ImpactScoreTool(),
        "write_file": WriteFileTool(mode=mode),
        "edit_file": EditFileTool(mode=mode),
        "copy_file": CopyFileTool(mode=mode),
    }
    if internet_available():
        tools["web_search"] = WebSearchTool()
    return tools


# ═══════════════════════════════════════════════════════════════════════════
#  SETUP
# ═══════════════════════════════════════════════════════════════════════════


@app.command()
def init() -> None:
    """Bootstrap config dirs, generate secret key, initialize DBs."""
    if not STATE.json_out:
        _print(BANNER)
        _print("[bold]Initializing sovereign-agent...[/bold]\n")

    SETTINGS.paths.ensure()
    from .approval import _load_or_create_secret  # noqa: WPS437
    _load_or_create_secret()

    conn_e = init_events_db()
    conn_e.close()
    from .db import open_atoms_db
    conn_a = open_atoms_db()
    conn_a.close()

    if STATE.json_out:
        _emit_json({
            "ok": True,
            "config_dir": str(SETTINGS.paths.config_dir),
            "data_dir": str(SETTINGS.paths.data_dir),
            "sandbox": str(SETTINGS.paths.sandbox_dir),
            "events": str(SETTINGS.paths.events_dir),
            "atoms_db": str(SETTINGS.paths.atoms_db),
            "continuations": str(SETTINGS.paths.continuations_dir),
            "palace_db": str(SETTINGS.paths.palace_db),
            "proposals_dir": str(SETTINGS.paths.proposals_dir),
        })
        return

    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column(style="dim")
    table.add_column()
    table.add_row("config dir", str(SETTINGS.paths.config_dir))
    table.add_row("data dir", str(SETTINGS.paths.data_dir))
    table.add_row("sandbox", str(SETTINGS.paths.sandbox_dir))
    table.add_row("events", str(SETTINGS.paths.events_dir))
    table.add_row("atoms.db", str(SETTINGS.paths.atoms_db))
    table.add_row("continuations", str(SETTINGS.paths.continuations_dir))
    table.add_row("palace.db", str(SETTINGS.paths.palace_db))
    table.add_row("proposals", str(SETTINGS.paths.proposals_dir))
    table.add_row("secret key", "[green]created[/green] (mode 0600)")
    _print(Panel(table, title="◊ initialized", border_style="green"))


@app.command()
def doctor() -> None:
    """Diagnose the agent's environment: paths, models, Ollama, VRAM, locks."""
    import shutil
    import socket
    from urllib.parse import urlparse

    if not STATE.json_out:
        _print(BANNER)
        _print("[bold]Running diagnostics...[/bold]\n")

    rows: list[dict[str, str]] = []

    def add(name: str, status: str, detail: str = "") -> None:
        rows.append({"check": name, "status": status, "detail": detail})

    for label, path in [
        ("config_dir", SETTINGS.paths.config_dir),
        ("data_dir", SETTINGS.paths.data_dir),
        ("sandbox_dir", SETTINGS.paths.sandbox_dir),
        ("events_dir", SETTINGS.paths.events_dir),
        ("atoms.db", SETTINGS.paths.atoms_db),
        ("secret.key", SETTINGS.paths.secret_key_file),
        ("continuations", SETTINGS.paths.continuations_dir),
    ]:
        add(label, "PASS" if path.exists() else "WARN",
            str(path) if path.exists() else f"{path} (run `sovereign init`)")

    if SETTINGS.paths.secret_key_file.exists():
        mode = SETTINGS.paths.secret_key_file.stat().st_mode & 0o777
        if mode == 0o600:
            add("secret mode", "PASS", "0600 (owner read-only)")
        else:
            add("secret mode", "FAIL", f"mode {oct(mode)} — should be 0600")

    add("orchestrator", "PASS", SETTINGS.orchestrator_model)
    add("coder", "PASS", SETTINGS.coder_model)
    add("embedder", "PASS", SETTINGS.embed_model)
    add("reflector", "PASS", SETTINGS.reflector_model)

    parsed = urlparse(SETTINGS.ollama_host)
    host = parsed.hostname or "localhost"
    port = parsed.port or 11434
    ollama_up = False
    try:
        with socket.create_connection((host, port), timeout=2):
            add("ollama tcp", "PASS", f"{host}:{port}")
            ollama_up = True
    except (OSError, socket.timeout) as e:
        add("ollama tcp", "FAIL", f"{host}:{port} unreachable: {e}")

    if ollama_up:
        try:
            import httpx
            r = httpx.get(f"{SETTINGS.ollama_host}/api/tags", timeout=5)
            r.raise_for_status()
            installed = {m["name"] for m in r.json().get("models", [])}
            for label, name in [
                ("orchestrator model", SETTINGS.orchestrator_model),
                ("embedder model", SETTINGS.embed_model),
                ("reflector model", SETTINGS.reflector_model),
            ]:
                if name in installed or any(n.startswith(name + ":") for n in installed):
                    add(label, "PASS", "found")
                else:
                    add(label, "FAIL", f"{name!r} not installed (try `ollama pull {name}`)")

            try:
                from .ollama_client import OllamaClient

                async def _probe():
                    cli = OllamaClient()
                    return {
                        "orchestrator": await cli.supports_thinking(SETTINGS.orchestrator_model),
                        "reflector": await cli.supports_thinking(SETTINGS.reflector_model),
                    }
                caps = asyncio.run(_probe())
                for label, key in [("orch thinking", "orchestrator"), ("reflector thinking", "reflector")]:
                    add(label, "PASS" if caps[key] else "WARN",
                        "supported" if caps[key] else "NOT supported (auto-disabled)")
            except Exception as e:  # noqa: BLE001
                add("capabilities", "WARN", f"could not probe: {e}")
        except Exception as e:  # noqa: BLE001
            add("ollama models", "WARN", f"could not query: {e}")

    if shutil.which("bwrap"):
        add("bubblewrap", "PASS", shutil.which("bwrap"))
    else:
        add("bubblewrap", "FAIL", "not installed — `apt install bubblewrap`")

    if SETTINGS.paths.halt_flag.exists():
        add("protocol-zero", "WARN", "ARMED — `sovereign disarm`")
    else:
        add("protocol-zero", "PASS", "clear")

    # Internet (v0.2.7+) — informational; not a failure when off.
    from .tools import internet_available, reset_internet_cache
    reset_internet_cache()  # fresh probe each doctor run
    setting = os.environ.get("AGENT_INTERNET", "auto").lower()
    if internet_available():
        add("internet", "PASS", f"available (AGENT_INTERNET={setting})")
    else:
        add("internet", "WARN",
            f"unavailable (AGENT_INTERNET={setting}) — web_search disabled")

    try:
        from .vram import read_vram
        snap = read_vram()
        add("vram", "PASS", f"{snap.free_mb} MB free / {snap.total_mb} MB total ({snap.source})")
    except Exception as e:  # noqa: BLE001
        add("vram", "WARN", f"could not read: {e}")

    if STATE.json_out:
        n_fail = sum(1 for r in rows if r["status"] == "FAIL")
        _emit_json({"ok": n_fail == 0, "checks": rows, "fail_count": n_fail})
        return

    table = Table(title="◊ doctor", show_header=True, header_style="bold cyan")
    table.add_column("check", style="dim", width=22)
    table.add_column("status", width=8)
    table.add_column("detail", overflow="fold")
    for r in rows:
        color = {"PASS": "green", "WARN": "yellow", "FAIL": "red"}.get(r["status"], "white")
        table.add_row(r["check"], f"[{color}]{r['status']}[/{color}]", r["detail"])
    _print(table)


@app.command(name="config")
def show_config() -> None:
    """Print the resolved configuration with effective values."""
    payload = {
        "version": __version__,
        "paths": {
            "config_dir": str(SETTINGS.paths.config_dir),
            "data_dir": str(SETTINGS.paths.data_dir),
            "sandbox_dir": str(SETTINGS.paths.sandbox_dir),
            "events_dir": str(SETTINGS.paths.events_dir),
            "atoms_db": str(SETTINGS.paths.atoms_db),
            "continuations_dir": str(SETTINGS.paths.continuations_dir),
            "palace_db": str(SETTINGS.paths.palace_db),
            "proposals_dir": str(SETTINGS.paths.proposals_dir),
            "backlog_yaml": str(SETTINGS.paths.backlog_yaml),
        },
        "models": {
            "orchestrator": SETTINGS.orchestrator_model,
            "coder": SETTINGS.coder_model,
            "embedder": SETTINGS.embed_model,
            "reflector": SETTINGS.reflector_model,
            "fast": SETTINGS.fast_model,
        },
        "ollama_host": SETTINGS.ollama_host,
        "think_mode": SETTINGS.think_mode,
        "num_ctx": SETTINGS.num_ctx,
        "approval_default_expiry_seconds": SETTINGS.approval_default_expiry_seconds,
        "env_overrides": {
            k: os.environ.get(k) for k in (
                "OLLAMA_HOST", "AGENT_ORCHESTRATOR_MODEL", "AGENT_CODER_MODEL",
                "AGENT_EMBED_MODEL", "AGENT_REFLECTOR_MODEL", "AGENT_FAST_MODEL",
                "AGENT_THINK",
            ) if os.environ.get(k) is not None
        },
    }

    if STATE.json_out:
        _emit_json(payload)
        return

    table = Table(title="◊ config", show_header=False, box=None, padding=(0, 1))
    table.add_column(style="dim")
    table.add_column()
    table.add_row("version", payload["version"])
    table.add_row("ollama_host", payload["ollama_host"])
    table.add_row("think_mode", payload["think_mode"])
    table.add_row("num_ctx", str(payload["num_ctx"]))
    table.add_row("orchestrator", payload["models"]["orchestrator"])
    table.add_row("coder", payload["models"]["coder"])
    table.add_row("embedder", payload["models"]["embedder"])
    table.add_row("reflector", payload["models"]["reflector"])
    table.add_row("fast", payload["models"]["fast"])
    for k, v in payload["paths"].items():
        table.add_row(f"path.{k}", v)
    if payload["env_overrides"]:
        for k, v in payload["env_overrides"].items():
            table.add_row(f"env.{k}", v)
    _print(table)


# ═══════════════════════════════════════════════════════════════════════════
#  RUN
# ═══════════════════════════════════════════════════════════════════════════


@app.command()
def run(
    goal: str = typer.Argument(..., help="What you want the agent to accomplish"),
    mode: Mode = typer.Option(Mode.ONESHOT, "--mode"),
    max_iterations: int = typer.Option(25, "--max-iter"),
    max_wall_seconds: int = typer.Option(1800, "--max-wall"),
    max_tokens: int = typer.Option(200_000, "--max-tokens"),
    dry_run: bool = typer.Option(False, "--dry-run",
        help="Show resolved tools, mode, and budget without invoking the model."),
) -> None:
    """Run a single task through the agent loop."""
    _preflight_initialized()
    if not dry_run:
        _preflight_not_halted()
        _preflight_ollama_reachable()

    from .loop import agent_loop

    protocol_zero.install_signal_handlers()
    tools = _build_tools_for_mode(mode)
    budget = RunBudget(max_iterations=max_iterations,
                      max_wall_seconds=max_wall_seconds, max_tokens=max_tokens)

    if dry_run:
        from .authority import tools_available_in_mode
        from .modes import MODE_TIER_CEILING
        available = sorted(m.name for m in tools_available_in_mode(mode))
        payload = {
            "ok": True, "dry_run": True, "goal": goal, "mode": mode.value,
            "tier_ceiling": MODE_TIER_CEILING[mode],
            "available_tools": available,
            "budget": {
                "max_iterations": budget.max_iterations,
                "max_wall_seconds": budget.max_wall_seconds,
                "max_tokens": budget.max_tokens,
            },
        }
        if STATE.json_out:
            _emit_json(payload)
        else:
            table = Table(title=f"◊ dry-run · {mode.value}")
            table.add_column("field", style="dim")
            table.add_column("value", overflow="fold")
            table.add_row("goal", goal)
            table.add_row("mode", mode.value)
            table.add_row("tier_ceiling", str(payload["tier_ceiling"]))
            table.add_row("tools", ", ".join(available))
            table.add_row("budget.iter", str(budget.max_iterations))
            table.add_row("budget.wall", f"{budget.max_wall_seconds}s")
            table.add_row("budget.tokens", str(budget.max_tokens))
            _print(table)
        raise typer.Exit(ExitCode.OK)

    _print(f"\n◊ [bold]{mode.value}[/bold] · {goal[:80]}\n")
    result = asyncio.run(agent_loop(goal=goal, mode=mode, budget=budget, tools=tools))

    if STATE.json_out:
        _emit_json({
            "ok": result.ok, "reason": result.reason,
            "iterations": result.iterations, "tokens": result.tokens_used,
            "lesson_id": result.lesson_id, "final_message": result.final_message,
        })
    else:
        color = "green" if result.ok else "yellow"
        _print(Panel(
            f"[bold]{result.reason}[/bold]\n"
            f"iterations: {result.iterations}  ·  tokens: {result.tokens_used}\n"
            f"lesson: {result.lesson_id or '(none)'}",
            title="◊ result", border_style=color,
        ))
        if result.final_message:
            _print("\n" + result.final_message)
    raise typer.Exit(ExitCode.OK if result.ok else ExitCode.ERROR)


@app.command()
def busy(
    cooldown: float = typer.Option(5.0, "--cooldown", help="Seconds between tasks"),
    empty_sleep: float = typer.Option(30.0, "--empty-sleep", help="Sleep when backlog empty"),
    max_iter_per_task: int = typer.Option(25, "--max-iter"),
    max_wall_per_task: int = typer.Option(1800, "--max-wall"),
    once: bool = typer.Option(False, "--once", help="Drain one task then exit (cron-friendly)."),
    max_tasks: int = typer.Option(0, "--max-tasks", help="At most N tasks then exit (0=unbounded)."),
) -> None:
    """Drain the backlog. PROTOCOL-ZERO is the only stop signal in unbounded mode."""
    _preflight_initialized()
    _preflight_not_halted()
    _preflight_ollama_reachable()

    from .mode_controller import ControllerSettings, ModeController

    _print(BANNER)
    _print(Panel(
        "[bold yellow]BUSY mode[/bold yellow] — Tier 0 + Tier 1 only.\n"
        "Tier 2 and Tier 3 are not in the agent's tool list.\n"
        "Stop with: [cyan]sovereign halt[/cyan]  or  [cyan]echo > ~/.config/sovereign-agent/HALT[/cyan]",
        border_style="yellow",
    ))

    tools = _build_tools_for_mode(Mode.BUSY)
    settings = ControllerSettings(
        cooldown_seconds=cooldown, empty_backlog_sleep=empty_sleep,
        per_task_budget=RunBudget(max_iterations=max_iter_per_task,
                                  max_wall_seconds=max_wall_per_task),
    )
    controller = ModeController(tools=tools, settings=settings)
    try:
        if once:
            asyncio.run(controller._drain_iteration())
        elif max_tasks > 0:
            async def _bounded() -> None:
                count = 0
                while count < max_tasks and not protocol_zero.is_armed():
                    ran = await controller._drain_iteration()
                    if ran:
                        count += 1
                        await asyncio.sleep(cooldown)
                    else:
                        await asyncio.sleep(empty_sleep)
            asyncio.run(_bounded())
        else:
            asyncio.run(controller.run_busy())
    except KeyboardInterrupt:
        _print("\n[yellow]interrupted[/yellow]")
    _print("[green]busy mode stopped[/green]")


@app.command()
def until(
    minutes: int = typer.Option(..., "--minutes", help="Stop after this many minutes"),
    mode: Mode = typer.Option(Mode.ONESHOT, "--mode"),
) -> None:
    """Drain backlog until a time limit is reached."""
    _preflight_initialized()
    _preflight_not_halted()
    _preflight_ollama_reachable()

    from .mode_controller import ModeController

    end_ts = time.time() + minutes * 60
    tools = _build_tools_for_mode(mode)
    controller = ModeController(tools=tools)

    def _done() -> bool:
        return time.time() >= end_ts

    _print(f"\n◊ [bold]until[/bold] · stopping in {minutes} minutes\n")
    asyncio.run(controller.run_until(_done))


# ═══════════════════════════════════════════════════════════════════════════
#  RE-TRIGGER ARCHITECTURE — plan / continue / continuations
# ═══════════════════════════════════════════════════════════════════════════


plan_app = typer.Typer(help="◊ pre-decompose a large task into atomic continuation steps")


@app.command(name="plan")
def plan_cmd(
    planner: str | None = typer.Argument(None, help="Planner name (omit to list)."),
    root: Path | None = typer.Option(None, "--root", help="Root path the planner walks."),
    output: Path | None = typer.Option(None, "--output", help="Aggregation output."),
    pattern: list[str] = typer.Option([], "--pattern", help="Glob pattern. Repeatable."),
    exclude: list[str] = typer.Option(
        [], "--exclude",
        help="Glob pattern to exclude files (matched against full path). Repeatable. (v0.2.6)",
    ),
    include: list[str] = typer.Option(
        [], "--include",
        help="Glob pattern whitelist (image-inventory only). Repeatable. (v0.2.6)",
    ),
    include_no_ext: bool = typer.Option(
        False, "--include-no-extension",
        help="Also include files with no extension (LICENSE, transcripts). (v0.2.6)",
    ),
    max_files: int = typer.Option(0, "--max-files", help="Cap step count (0=unbounded)."),
    no_recursive: bool = typer.Option(False, "--no-recursive", help="Don't walk subdirs."),
    tag: str | None = typer.Option(None, "--tag", help="Tag (read-files planner)."),
    max_extract_chars: int = typer.Option(
        40_000, "--max-extract-chars",
        help="Per-file extraction cap (pdf-inventory). (v0.2.6)",
    ),
    max_file_size: int = typer.Option(
        0, "--max-file-size",
        help="Skip files larger than N bytes (0=use planner default). (v0.2.6)",
    ),
    room_id: str | None = typer.Option(
        None, "--room-id",
        help="Palace room id (palace-mine planner). (v0.2.8)",
    ),
    room_name: str | None = typer.Option(
        None, "--room-name",
        help="Palace room display name (palace-mine planner). (v0.2.8)",
    ),
    atom_type: str | None = typer.Option(
        None, "--atom-type",
        help="Filter atoms by type (palace-mine planner). (v0.2.8)",
    ),
    task_id: str | None = typer.Option(None, "--task-id", help="Override generated ULID."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show the plan, don't write."),
) -> None:
    """Run a planner. With no planner name, lists available planners."""
    from .planners import REGISTRY, get_planner
    from .planners.base import PlannerError, PlannerNotFound
    from .continuation import ContinuationStore

    if planner is None:
        if STATE.json_out:
            _emit_json({"planners": [
                {"name": p.name, "description": p.description,
                 "required_args": list(p.required_args())}
                for p in REGISTRY.values()
            ]})
            return
        table = Table(title="◊ planners", show_header=True, header_style="bold cyan")
        table.add_column("name", style="cyan")
        table.add_column("required args", style="magenta")
        table.add_column("description")
        for p in REGISTRY.values():
            table.add_row(p.name, ", ".join(p.required_args()) or "—", p.description)
        _print(table)
        _print("\n[dim]Run a planner: [/dim][cyan]sovereign plan inventory --root <dir> --output <file>[/cyan]")
        return

    try:
        planner_obj = get_planner(planner)
    except PlannerNotFound as e:
        _die(ExitCode.USAGE, str(e), hint="run `sovereign plan` to list planners")

    args = {
        "root": str(root) if root else None,
        "output": str(output) if output else None,
        "patterns": pattern or None,
        "exclude": exclude or None,
        "include": include or None,
        "include_no_extension": include_no_ext if include_no_ext else None,
        "max_files": max_files,
        "recursive": not no_recursive,
        "tag": tag,
        "max_extract_chars": max_extract_chars if max_extract_chars != 40_000 else None,
        "max_file_size_bytes": max_file_size if max_file_size > 0 else None,
        "room_id": room_id,
        "room_name": room_name,
        "atom_type": atom_type,
    }
    args = {k: v for k, v in args.items() if v is not None}

    try:
        result = planner_obj.plan(**args)
    except PlannerError as e:
        _die(ExitCode.USAGE, f"plan failed: {e}")

    if dry_run:
        payload = {
            "ok": True, "dry_run": True, "planner": planner,
            "goal": result.goal, "step_count": len(result.steps),
            "output_path": result.output_path,
            "first_steps": [{"id": s.id, "kind": s.kind, "args": s.args}
                           for s in result.steps[:5]],
        }
        if STATE.json_out:
            _emit_json(payload)
        else:
            _print(Panel(
                f"[bold]{result.goal}[/bold]\n"
                f"steps: {len(result.steps)}\n"
                f"output: {result.output_path or '(none)'}\n"
                f"notes: {result.notes}",
                title=f"◊ plan (dry-run) · {planner}", border_style="cyan",
            ))
            if result.steps:
                t = Table(title="first 5 steps", show_header=True)
                t.add_column("id", style="dim")
                t.add_column("kind")
                t.add_column("args", overflow="fold")
                for s in result.steps[:5]:
                    t.add_row(str(s.id), s.kind, json.dumps(s.args, default=str)[:120])
                _print(t)
        return

    _preflight_initialized()
    store = ContinuationStore(SETTINGS.paths.continuations_dir)
    cont = store.create(
        goal=result.goal, planner=planner, planner_args=args,
        steps=result.steps, output_path=result.output_path,
        task_id=task_id, notes=result.notes,
    )

    if STATE.json_out:
        _emit_json({"ok": True, "task_id": cont.task_id,
                    "step_count": len(cont.steps), "goal": cont.goal,
                    "output_path": cont.output_path})
    else:
        _print(Panel(
            f"[bold]{cont.goal}[/bold]\n"
            f"task_id: [cyan]{cont.task_id}[/cyan]\n"
            f"steps: {len(cont.steps)}\n"
            f"output: {cont.output_path or '(none)'}\n\n"
            f"[dim]drive it:[/dim] [cyan]sovereign continue {cont.task_id}[/cyan]\n"
            f"[dim]or loop:[/dim]  [cyan]scripts/sovereign-continue-loop.sh {cont.task_id}[/cyan]",
            title="◊ continuation created", border_style="green",
        ))


@app.command(name="continue")
def continue_(
    task_id: str = typer.Argument(..., help="Continuation ID from `sovereign plan`"),
    max_iter: int = typer.Option(5, "--max-iter", help="Per-step iteration cap."),
    max_wall: int = typer.Option(120, "--max-wall", help="Per-step wall-time cap (seconds)."),
    max_tokens: int = typer.Option(20_000, "--max-tokens", help="Per-step token cap."),
    model_filter: str | None = typer.Option(
        None, "--model-filter",
        help="Only run steps requiring this model (orchestrator/coder/vision/none). (v0.2.6)",
    ),
) -> None:
    """Execute exactly ONE pending step from a continuation, then exit.

    Exit codes: 0 step OK · 1 step poison · 3 halted · 8 drained · 9 locked

    With ``--model-filter X``, only run a step whose ``required_model == X``.
    Other steps stay pending. Use this to batch by model affinity:

        sovereign continue <id> --model-filter orchestrator
        sovereign continue <id> --model-filter vision

    Or use the higher-level ``sovereign drain-by-model <id>`` which sequences
    phases automatically.
    """
    _preflight_initialized()
    _preflight_not_halted()

    # Pre-flight Ollama only if this continuation has steps that need a model.
    # palace-mine and metadata-inventory continuations are pure-Python; they
    # shouldn't refuse to start just because Ollama is down. v0.2.8.
    from .continuation import ContinuationStore
    store = ContinuationStore(SETTINGS.paths.continuations_dir)
    needs_model = False
    try:
        cont_preview = store.get(task_id)
        models = cont_preview.models_needed()
        # If model_filter is set and it's 'none', or all pending models are
        # 'none', skip the Ollama check.
        if model_filter == "none":
            needs_model = False
        elif model_filter is not None:
            needs_model = model_filter != "none"
        else:
            needs_model = any(m != "none" for m in models)
    except Exception:  # noqa: BLE001
        # If we can't read the continuation, fall through to the normal path.
        needs_model = True

    if needs_model:
        _preflight_ollama_reachable()

    from .continue_runner import run_one_step
    tools = _build_tools_for_mode(Mode.ONESHOT)
    budget = RunBudget(max_iterations=max_iter, max_wall_seconds=max_wall,
                      max_tokens=max_tokens, consecutive_fail_limit=2)

    protocol_zero.install_signal_handlers()
    result = asyncio.run(run_one_step(
        task_id=task_id, tools=tools, store=store, budget=budget,
        mode=Mode.ONESHOT, model_filter=model_filter,
    ))

    payload = {
        "task_id": result.task_id, "step_id": result.step_id,
        "step_kind": result.step_kind, "outcome": result.outcome,
        "iterations": result.iterations, "tokens": result.tokens,
        "elapsed_seconds": result.elapsed_seconds,
        "required_model": result.required_model,
        "cont_status": result.cont_status, "progress": list(result.progress),
        "final_message": result.final_message,
        "model_filter": model_filter,
    }

    if result.outcome == "locked":
        if STATE.json_out:
            _emit_json({"ok": False, "code": ExitCode.LOCKED, **payload})
        else:
            _print(f"[yellow]locked[/yellow] · {task_id} held by another runner")
        raise typer.Exit(ExitCode.LOCKED)

    if result.outcome == "filtered":
        # No work for this model right now, but other models still have steps.
        # Use a distinct exit code so drain-by-model knows to advance phase.
        if STATE.json_out:
            _emit_json({"ok": True, "code": ExitCode.DRAINED, **payload})
        else:
            done, total = result.progress
            _print(
                f"[dim]filtered[/dim] · no '{model_filter}' steps · "
                f"{done}/{total} · status={result.cont_status}"
            )
        raise typer.Exit(ExitCode.DRAINED)

    if result.outcome in ("drained", "no_step"):
        if STATE.json_out:
            _emit_json({"ok": True, "code": ExitCode.DRAINED, **payload})
        else:
            done, total = result.progress
            _print(f"[green]drained[/green] · {done}/{total} · status={result.cont_status}")
        raise typer.Exit(ExitCode.DRAINED)

    if STATE.json_out:
        ok = result.outcome == "complete"
        # Surface VRAM in JSON too — operators using --json for monitoring
        # benefit from per-step VRAM data.
        payload["vram_before_mb"] = result.vram_before_mb
        payload["vram_peak_mb"] = result.vram_peak_mb
        payload["vram_after_mb"] = result.vram_after_mb
        _emit_json({"ok": ok, "code": ExitCode.OK if ok else ExitCode.ERROR, **payload})
    else:
        from .continuation import format_elapsed

        # Build VRAM suffix. Empty string when no GPU data — keeps the line
        # uncluttered on no-GPU systems and on pure-Python steps. v0.2.11+.
        vram_suffix = ""
        if result.vram_before_mb is not None and result.vram_peak_mb is not None:
            delta = result.vram_peak_mb - result.vram_before_mb
            sign = "+" if delta >= 0 else ""
            vram_suffix = (
                f" · vram={result.vram_before_mb}→{result.vram_peak_mb}MB "
                f"Δ{sign}{delta}"
            )

        done, total = result.progress
        if result.outcome == "complete":
            _print(f"[green]✓ step {result.step_id}[/green] ({result.step_kind}) · "
                  f"{done}/{total} · iter={result.iterations} tokens={result.tokens} · "
                  f"elapsed={format_elapsed(result.elapsed_seconds)}{vram_suffix}")
        else:
            _print(f"[red]✗ step {result.step_id}[/red] ({result.step_kind}) · "
                  f"{result.outcome} · {done}/{total} · "
                  f"elapsed={format_elapsed(result.elapsed_seconds)}{vram_suffix}")
    raise typer.Exit(ExitCode.OK if result.outcome == "complete" else ExitCode.ERROR)


@app.command(name="drain-by-model")
def drain_by_model_cmd(
    task_id: str = typer.Argument(..., help="Continuation ID to drain"),
    max_iter: int = typer.Option(5, "--max-iter", help="Per-step iteration cap."),
    max_wall: int = typer.Option(120, "--max-wall", help="Per-step wall-time cap (s)."),
    max_tokens: int = typer.Option(20_000, "--max-tokens", help="Per-step token cap."),
    cooldown: float = typer.Option(2.0, "--cooldown", help="Sleep between steps (s)."),
) -> None:
    """Drain a continuation in model-affinity phases. v0.2.6.

    Inspects the continuation's pending steps, groups by ``required_model``,
    and runs each model's batch contiguously. Each model loads exactly once
    instead of swapping in and out per step.

    Phase order: ``orchestrator`` first (most common, fastest to load), then
    other models alphabetically. ``required_model='none'`` steps run without
    invoking any model.

    Stops cleanly on PROTOCOL-ZERO. Halt-and-resume safe — all state is in
    the continuation file. Re-running picks up exactly where it left off.

    Exit codes: 0 fully drained · 3 halted · other = error.
    """
    _preflight_initialized()
    _preflight_not_halted()

    from .continuation import ContinuationStore
    from .continue_runner import run_one_step

    store = ContinuationStore(SETTINGS.paths.continuations_dir)
    cont = store.get(task_id)

    # Pre-flight Ollama only if any pending phase actually needs a model. v0.2.8.
    if any(m != "none" for m in cont.models_needed()):
        _preflight_ollama_reachable()

    if cont.is_drained():
        if STATE.json_out:
            _emit_json({"ok": True, "drained": True, "task_id": task_id})
        else:
            _print(f"[green]already drained[/green] · {task_id}")
        return

    phases = cont.models_needed()
    if not phases:
        if STATE.json_out:
            _emit_json({"ok": True, "drained": True, "task_id": task_id})
        else:
            _print(f"[green]nothing pending[/green] · {task_id}")
        return

    if not STATE.json_out:
        _print(Panel(
            f"[bold]{cont.goal}[/bold]\n"
            f"phases: {' → '.join(phases)}\n"
            f"total pending: {sum(len([s for s in cont.steps if s.status == 'pending' and s.required_model == m]) for m in phases)}",
            title=f"◊ drain-by-model · {task_id}",
            border_style="cyan",
        ))

    tools = _build_tools_for_mode(Mode.ONESHOT)
    budget = RunBudget(
        max_iterations=max_iter, max_wall_seconds=max_wall,
        max_tokens=max_tokens, consecutive_fail_limit=2,
    )

    protocol_zero.install_signal_handlers()

    overall_start = time.monotonic()
    phase_results = []

    for phase_idx, model in enumerate(phases, start=1):
        if protocol_zero.is_armed():
            if not STATE.json_out:
                _print("[red]HALT armed · stopping[/red]")
            raise typer.Exit(ExitCode.HALTED)

        if not STATE.json_out:
            _print(f"\n[bold cyan]◊ phase {phase_idx}/{len(phases)}: {model}[/bold cyan]")

        phase_start = time.monotonic()
        phase_steps = 0
        phase_complete = 0
        phase_poison = 0

        while True:
            if protocol_zero.is_armed():
                break

            result = asyncio.run(run_one_step(
                task_id=task_id, tools=tools, store=store, budget=budget,
                mode=Mode.ONESHOT, model_filter=model,
            ))

            if result.outcome == "locked":
                if not STATE.json_out:
                    _print(f"[yellow]locked, waiting…[/yellow]")
                time.sleep(5.0)
                continue

            if result.outcome in ("filtered", "drained", "no_step"):
                # No more steps in this phase (or continuation drained).
                break

            phase_steps += 1
            if result.outcome == "complete":
                phase_complete += 1
                if not STATE.json_out:
                    done, total = result.progress
                    vram_suffix = ""
                    if result.vram_before_mb is not None and result.vram_peak_mb is not None:
                        delta = result.vram_peak_mb - result.vram_before_mb
                        sign = "+" if delta >= 0 else ""
                        vram_suffix = (
                            f" · vram={result.vram_before_mb}→{result.vram_peak_mb}MB "
                            f"Δ{sign}{delta}"
                        )
                    _print(
                        f"  [green]✓ step {result.step_id}[/green] "
                        f"({result.step_kind}) · {done}/{total} · "
                        f"iter={result.iterations} tokens={result.tokens}{vram_suffix}"
                    )
            else:
                phase_poison += 1
                if not STATE.json_out:
                    _print(
                        f"  [red]✗ step {result.step_id}[/red] "
                        f"({result.step_kind}) · {result.outcome}"
                    )

            time.sleep(cooldown)

        phase_elapsed = time.monotonic() - phase_start
        phase_results.append({
            "model": model,
            "steps_attempted": phase_steps,
            "complete": phase_complete,
            "poison": phase_poison,
            "elapsed_seconds": round(phase_elapsed, 1),
        })

        if not STATE.json_out:
            _print(
                f"[dim]phase {phase_idx} done · {phase_complete} complete, "
                f"{phase_poison} poison, {phase_elapsed:.1f}s[/dim]"
            )

    overall_elapsed = time.monotonic() - overall_start
    final = store.get(task_id)
    done, total = final.progress

    if STATE.json_out:
        _emit_json({
            "ok": True, "task_id": task_id,
            "phases": phase_results, "final_status": final.status,
            "progress": [done, total],
            "elapsed_seconds": round(overall_elapsed, 1),
        })
    else:
        _print(Panel(
            f"final status: [bold]{final.status}[/bold]\n"
            f"progress: {done}/{total}\n"
            f"total elapsed: {overall_elapsed:.1f}s",
            title="◊ drain-by-model · complete",
            border_style="green" if final.status == "done" else "yellow",
        ))


cont_app = typer.Typer(help="◊ inspect / manage continuation files")
app.add_typer(cont_app, name="continuations")


@cont_app.command("list")
def cont_list(status: str | None = typer.Option(None, "--status")) -> None:
    """List all continuation files with progress."""
    from .continuation import ContinuationStore

    store = ContinuationStore(SETTINGS.paths.continuations_dir)
    conts = store.list_all(status=status)

    if STATE.json_out:
        _emit_json({"continuations": [
            {"task_id": c.task_id, "status": c.status, "planner": c.planner,
             "goal": c.goal, "progress": list(c.progress),
             "updated_at": c.updated_at, "output_path": c.output_path}
            for c in conts
        ]})
        return

    if not conts:
        _print("[dim](no continuations)[/dim]")
        return

    table = Table(title="◊ continuations")
    table.add_column("task_id", style="cyan")
    table.add_column("status")
    table.add_column("planner", style="magenta")
    table.add_column("progress", justify="right")
    table.add_column("goal", overflow="fold")
    for c in conts:
        done, total = c.progress
        color = {"planned": "yellow", "in_progress": "cyan", "done": "green",
                 "poisoned": "red", "halted": "red"}.get(c.status, "white")
        table.add_row(c.task_id, f"[{color}]{c.status}[/{color}]",
                     c.planner, f"{done}/{total}", c.goal[:80])
    _print(table)


@cont_app.command("show")
def cont_show(task_id: str) -> None:
    """Show a continuation in detail, including all steps."""
    from .continuation import ContinuationNotFound, ContinuationStore

    store = ContinuationStore(SETTINGS.paths.continuations_dir)
    try:
        cont = store.get(task_id)
    except ContinuationNotFound:
        _die(ExitCode.USAGE, f"continuation not found: {task_id}")

    if STATE.json_out:
        from dataclasses import asdict
        _emit_json({
            "task_id": cont.task_id, "goal": cont.goal,
            "planner": cont.planner, "planner_args": cont.planner_args,
            "status": cont.status, "progress": list(cont.progress),
            "output_path": cont.output_path, "notes": cont.notes,
            "created_at": cont.created_at, "updated_at": cont.updated_at,
            "steps": [asdict(s) for s in cont.steps],
        })
        return

    done, total = cont.progress
    by_model = cont.progress_by_model()
    elapsed_by_model = cont.elapsed_by_model()
    progress_lines = [f"status: {cont.status} · progress: {done}/{total}"]
    if len(by_model) > 1:
        per = "  ".join(f"{m}={d}/{t}" for m, (d, t) in sorted(by_model.items()))
        progress_lines.append(f"by model: {per}")
    if cont.total_elapsed_seconds > 0:
        from .continuation import format_elapsed
        progress_lines.append(f"total elapsed: {format_elapsed(cont.total_elapsed_seconds)}")
        if len(elapsed_by_model) > 1:
            per_elapsed = "  ".join(
                f"{m}={format_elapsed(s)}"
                for m, s in sorted(elapsed_by_model.items())
            )
            progress_lines.append(f"elapsed by model: {per_elapsed}")
    _print(Panel(
        f"[bold]{cont.goal}[/bold]\n"
        f"planner: {cont.planner}\n"
        + "\n".join(progress_lines) + "\n"
        f"output: {cont.output_path or '(none)'}\n"
        f"created: {cont.created_at}\n"
        f"updated: {cont.updated_at}",
        title=f"◊ {cont.task_id}", border_style="cyan",
    ))

    from .continuation import format_elapsed as _fmt_elapsed
    table = Table(title="steps", show_header=True)
    table.add_column("id", style="dim", width=4)
    table.add_column("kind", style="magenta")
    table.add_column("model", style="cyan")
    table.add_column("status")
    table.add_column("iter", justify="right")
    table.add_column("tokens", justify="right")
    table.add_column("elapsed", justify="right")
    table.add_column("args", overflow="fold")
    for s in cont.steps:
        color = {"pending": "yellow", "done": "green",
                 "poisoned": "red", "skipped": "dim"}.get(s.status, "white")
        table.add_row(str(s.id), s.kind, s.required_model,
                     f"[{color}]{s.status}[/{color}]",
                     str(s.iterations), str(s.tokens),
                     _fmt_elapsed(s.elapsed_seconds),
                     json.dumps(s.args, default=str)[:80])
    _print(table)


@cont_app.command("delete")
def cont_delete(task_id: str) -> None:
    """Delete a continuation. Refuses if a runner holds the lock."""
    from .continuation import ContinuationLocked, ContinuationStore

    store = ContinuationStore(SETTINGS.paths.continuations_dir)
    try:
        existed = store.delete(task_id)
    except ContinuationLocked:
        _die(ExitCode.LOCKED, f"continuation {task_id} is locked by a runner")

    if STATE.json_out:
        _emit_json({"ok": existed, "task_id": task_id, "deleted": existed})
    elif existed:
        _print(f"[green]deleted[/green] {task_id}")
    else:
        _print(f"[yellow]not found[/yellow] {task_id}")


# ═══════════════════════════════════════════════════════════════════════════
#  BACKLOG
# ═══════════════════════════════════════════════════════════════════════════


backlog_app = typer.Typer(help="◊ manage the task backlog")
app.add_typer(backlog_app, name="backlog")


@backlog_app.command("list")
def backlog_list(status: str | None = typer.Option(None, "--status")) -> None:
    """Show the current backlog."""
    from .mode_controller import read_backlog

    tasks = read_backlog()
    if status:
        tasks = [t for t in tasks if t.status == status]

    if STATE.json_out:
        _emit_json({"tasks": [
            {"id": t.id, "priority": t.priority, "mode": t.mode,
             "status": t.status, "goal": t.goal, "notes": t.notes}
            for t in tasks
        ]})
        return

    if not tasks:
        _print("[dim](backlog empty)[/dim]")
        return

    table = Table(title="◊ backlog")
    table.add_column("id", style="cyan")
    table.add_column("priority", style="magenta")
    table.add_column("mode")
    table.add_column("status")
    table.add_column("goal", overflow="fold")
    for t in tasks:
        status_color = {"pending": "yellow", "running": "cyan", "done": "green",
                       "poison": "red", "budget": "yellow", "halted": "red"}.get(t.status, "white")
        table.add_row(t.id[:18], t.priority, t.mode,
                     f"[{status_color}]{t.status}[/{status_color}]", t.goal[:80])
    _print(table)


@backlog_app.command("add")
def backlog_add(
    goal: str = typer.Argument(...),
    priority: str = typer.Option("medium", "--priority"),
    mode: str = typer.Option("oneshot", "--mode"),
) -> None:
    """Add a task to the backlog."""
    from .mode_controller import add_task
    task = add_task(goal=goal, priority=priority, mode=mode)
    if STATE.json_out:
        _emit_json({"ok": True, "id": task.id})
    else:
        _print(f"[green]added[/green] {task.id}")


@backlog_app.command("remove")
def backlog_remove(task_id: str) -> None:
    """Remove a task from the backlog by id."""
    from .mode_controller import remove_task
    if remove_task(task_id):
        if STATE.json_out:
            _emit_json({"ok": True, "id": task_id})
        else:
            _print(f"[green]removed[/green] {task_id}")
    else:
        if STATE.json_out:
            _emit_json({"ok": False, "id": task_id})
        else:
            _print(f"[yellow]not found[/yellow] {task_id}")


@backlog_app.command("show")
def backlog_show(task_id: str) -> None:
    """Show one task in detail."""
    from .mode_controller import read_backlog
    task = next((t for t in read_backlog() if t.id == task_id or t.id.startswith(task_id)), None)
    if task is None:
        _die(ExitCode.USAGE, f"task not found: {task_id}")

    if STATE.json_out:
        _emit_json({"id": task.id, "goal": task.goal, "priority": task.priority,
                   "mode": task.mode, "status": task.status, "notes": task.notes})
        return

    _print(Panel(
        f"[bold]{task.goal}[/bold]\n"
        f"id: {task.id}\n"
        f"priority: {task.priority}\n"
        f"mode: {task.mode}\n"
        f"status: {task.status}\n"
        f"notes: {task.notes or '(none)'}",
        title=f"◊ {task.id[:18]}",
    ))


@backlog_app.command("requeue")
def backlog_requeue(task_id: str) -> None:
    """Reset a task to 'pending' so it'll be picked up again."""
    from .mode_controller import read_backlog, write_backlog
    tasks = read_backlog()
    target = next((t for t in tasks if t.id == task_id), None)
    if target is None:
        _die(ExitCode.USAGE, f"task not found: {task_id}")
    target.status = "pending"
    target.notes = "requeued by operator"
    write_backlog(tasks)
    if STATE.json_out:
        _emit_json({"ok": True, "id": task_id})
    else:
        _print(f"[green]requeued[/green] {task_id}")


@backlog_app.command("priority")
def backlog_priority(
    task_id: str,
    priority: str = typer.Argument(..., help="critical | high | medium | low"),
) -> None:
    """Change a task's priority."""
    valid = {"critical", "high", "medium", "low"}
    if priority not in valid:
        _die(ExitCode.USAGE, f"priority must be one of {sorted(valid)}")

    from .mode_controller import read_backlog, write_backlog
    tasks = read_backlog()
    target = next((t for t in tasks if t.id == task_id), None)
    if target is None:
        _die(ExitCode.USAGE, f"task not found: {task_id}")
    target.priority = priority
    write_backlog(tasks)
    if STATE.json_out:
        _emit_json({"ok": True, "id": task_id, "priority": priority})
    else:
        _print(f"[green]priority={priority}[/green] {task_id}")


@backlog_app.command("clear")
def backlog_clear(
    status: str = typer.Option(..., "--status", help="Clear tasks with this status."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
) -> None:
    """Remove all tasks with the given status."""
    from .mode_controller import read_backlog, write_backlog

    tasks = read_backlog()
    keep = [t for t in tasks if t.status != status]
    removed = len(tasks) - len(keep)
    if removed == 0:
        _print(f"[dim]no tasks with status={status!r}[/dim]")
        return
    if not yes and not STATE.json_out:
        if not typer.confirm(f"Remove {removed} task(s) with status={status!r}?"):
            _print("[dim]cancelled[/dim]")
            return
    write_backlog(keep)
    if STATE.json_out:
        _emit_json({"ok": True, "removed": removed, "status": status})
    else:
        _print(f"[green]cleared[/green] {removed} task(s) with status={status!r}")


# ═══════════════════════════════════════════════════════════════════════════
#  APPROVALS
# ═══════════════════════════════════════════════════════════════════════════


def _parse_expiry(expiry_ts: str) -> datetime | None:
    """RFC3339-ish expiry parser. Tolerates whole-second AND fractional forms.

    The v0.2.4 implementation hard-coded ``%Y-%m-%dT%H:%M:%S.%f%z`` which
    silently fails on whole-second timestamps. Falls back to fromisoformat
    which Python 3.11 accepts both forms of.
    """
    if not expiry_ts:
        return None
    s = expiry_ts.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _scan_pending_approval_requests() -> list[dict]:
    """Find approval-needed-d events that haven't been resolved."""
    from .events import init_events_db, tail_to_sqlite

    conn = init_events_db()
    tail_to_sqlite(conn)
    rows = conn.execute(
        "SELECT event_id, ts, payload FROM events "
        "WHERE flag = 'approval-needed-d' ORDER BY ts ASC"
    ).fetchall()

    pending: list[dict] = []
    for ev_id, ts, payload_json in rows:
        try:
            payload = json.loads(payload_json)
        except json.JSONDecodeError:
            continue

        resolved = conn.execute(
            "SELECT 1 FROM events "
            "WHERE flag IN ('approval-d', 'approval-x', 'approval-denied-d') "
            "AND json_extract(payload, '$.event_id') = ? LIMIT 1",
            (ev_id,),
        ).fetchone()
        if resolved:
            continue

        expiry = _parse_expiry(payload.get("expiry_ts", ""))
        if expiry and datetime.now(timezone.utc) >= expiry:
            continue

        pending.append({
            "event_id": ev_id, "requested_at": ts,
            "tool_name": payload.get("tool_name"),
            "args_hash": payload.get("args_hash"),
            "args_preview": payload.get("args_preview"),
            "justification": payload.get("justification"),
            "expiry_ts": payload.get("expiry_ts"),
            "expiry_dt": expiry,
        })

    conn.close()
    return pending


def _format_ttl(expiry: datetime | None) -> str:
    if expiry is None:
        return "(unknown)"
    delta = expiry - datetime.now(timezone.utc)
    secs = int(delta.total_seconds())
    if secs <= 0:
        return "expired"
    if secs < 60:
        return f"{secs}s"
    if secs < 3600:
        return f"{secs // 60}m {secs % 60}s"
    return f"{secs // 3600}h {(secs % 3600) // 60}m"


@app.command()
def approvals() -> None:
    """List pending Tier 3 approval requests."""
    pending = _scan_pending_approval_requests()

    if STATE.json_out:
        _emit_json({"pending": [
            {**{k: v for k, v in p.items() if k != "expiry_dt"},
             "ttl": _format_ttl(p.get("expiry_dt"))}
            for p in pending
        ]})
        return

    if not pending:
        _print("[dim](no pending approvals)[/dim]")
        return

    for req in pending:
        ttl = _format_ttl(req.get("expiry_dt"))
        body = (
            f"[bold]tool:[/bold]      {req['tool_name']}\n"
            f"[bold]requested:[/bold] {req['requested_at']}\n"
            f"[bold]expires in:[/bold] {ttl}\n"
            f"[bold]args:[/bold]      {req['args_preview']}\n"
            f"[bold]reason:[/bold]    {req['justification']}\n\n"
            f"[dim]grant:  sovereign approve {req['event_id']}\n"
            f"deny:   sovereign deny {req['event_id']}[/dim]"
        )
        _print(Panel(body, title=f"◊ {req['event_id']}", border_style="yellow"))


@app.command()
def approve(
    event_id: str,
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
) -> None:
    """Grant a Tier 3 approval. The agent picks it up on next dispatch."""
    pending = _scan_pending_approval_requests()
    match = next((p for p in pending if p["event_id"] == event_id), None)
    if match is None:
        _die(ExitCode.APPROVAL_NOT_FOUND, f"not found or already resolved: {event_id}")

    if not yes and not STATE.json_out:
        body = (
            f"tool:      {match['tool_name']}\n"
            f"args:      {match['args_preview']}\n"
            f"reason:    {match['justification']}\n"
            f"expires:   {match['expiry_ts']}"
        )
        _print(Panel(body, title=f"◊ approve {event_id}?", border_style="yellow"))
        if not typer.confirm("Grant this approval?"):
            _print("[dim]cancelled[/dim]")
            raise typer.Exit(ExitCode.OK)

    from .approval import ApprovalRequest, write_grant
    req = ApprovalRequest(
        event_id=event_id, tool_name=match["tool_name"], args={},
        args_hash=match["args_hash"], justification=match["justification"] or "",
        expiry_ts=match["expiry_ts"],
    )
    write_grant(req)
    if STATE.json_out:
        _emit_json({"ok": True, "granted": event_id})
    else:
        _print(f"[green]✓ granted[/green] {event_id}")


@app.command()
def deny(event_id: str, reason: str = typer.Option("operator denied", "--reason")) -> None:
    """Refuse a Tier 3 approval."""
    from .approval import write_denial
    write_denial(event_id, trace_id="cli-deny", reason=reason)
    if STATE.json_out:
        _emit_json({"ok": True, "denied": event_id, "reason": reason})
    else:
        _print(f"[red]✗ denied[/red] {event_id}")


# ═══════════════════════════════════════════════════════════════════════════
#  SAFETY
# ═══════════════════════════════════════════════════════════════════════════


@app.command()
def halt(reason: str = typer.Option("operator", "--reason")) -> None:
    """Trip PROTOCOL-ZERO. The agent halts at the next iteration boundary."""
    protocol_zero.arm(reason)
    if STATE.json_out:
        _emit_json({"ok": True, "halted": True, "reason": reason})
    else:
        _print(Panel(
            f"[red]PROTOCOL-ZERO armed[/red]\nreason: {reason}\n\n"
            f"[dim]clear with: sovereign disarm[/dim]",
            border_style="red",
        ))


@app.command()
def disarm() -> None:
    """Clear PROTOCOL-ZERO. Manual ack required after operator review."""
    protocol_zero.disarm()
    if STATE.json_out:
        _emit_json({"ok": True, "disarmed": True})
    else:
        _print("[green]✓ disarmed[/green]")


# ═══════════════════════════════════════════════════════════════════════════
#  AUDIT
# ═══════════════════════════════════════════════════════════════════════════


@app.command()
def tail() -> None:
    """Ingest events.jsonl into the SQLite events projection."""
    conn = init_events_db()
    inserted = tail_to_sqlite(conn)
    conn.close()
    if STATE.json_out:
        _emit_json({"ok": True, "inserted": inserted})
    else:
        _print(f"[green]ingested[/green] {inserted} events")


@app.command()
def seal() -> None:
    """Compute yesterday's Merkle seal over events.jsonl."""
    from .seal import seal_yesterday
    root = seal_yesterday()
    if STATE.json_out:
        _emit_json({"ok": True, "root": root})
        return
    if root:
        _print(f"[green]✓ sealed[/green] yesterday: [cyan]{root}[/cyan]")
    else:
        _print("[dim]no events to seal[/dim]")


@app.command()
def verify(target_date: str = typer.Argument(..., help="YYYY-MM-DD")) -> None:
    """Verify a past seal still matches its events file."""
    from .seal import verify_seal
    try:
        d = date.fromisoformat(target_date)
    except ValueError:
        _die(ExitCode.USAGE, f"invalid date: {target_date}")

    matches, msg = verify_seal(d)
    if STATE.json_out:
        _emit_json({"ok": matches, "message": msg, "date": target_date})
    else:
        style = "green" if matches else "red"
        _print(f"[{style}]{msg}[/{style}]")
    raise typer.Exit(ExitCode.OK if matches else ExitCode.ERROR)


@app.command()
def events(
    n: int = typer.Option(20, "-n", help="How many recent events to show"),
    flag: str | None = typer.Option(None, "--flag", help="Filter by flag (e.g., 'tool-x')"),
    follow: bool = typer.Option(False, "--follow", "-f", help="tail -f mode (Ctrl-C to stop)"),
    interval: float = typer.Option(1.0, "--interval", help="Poll interval for --follow."),
) -> None:
    """Show recent events from the SQLite projection.

    With ``--follow``, polls for new events forever (Ctrl-C to stop).
    """
    if follow:
        _follow_events(flag=flag, interval=interval)
        return

    conn = init_events_db()
    tail_to_sqlite(conn)
    if flag:
        rows = conn.execute(
            "SELECT ts, flag, trace_id, payload FROM events "
            "WHERE flag = ? ORDER BY ts DESC LIMIT ?",
            (flag, n),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT ts, flag, trace_id, payload FROM events "
            "ORDER BY ts DESC LIMIT ?", (n,),
        ).fetchall()
    conn.close()

    if STATE.json_out:
        _emit_json({"events": [
            {"ts": ts, "flag": fl, "trace_id": tid, "payload": pl}
            for ts, fl, tid, pl in rows
        ]})
        return

    table = Table(title="◊ recent events" + (f" (flag={flag})" if flag else ""))
    table.add_column("ts", style="dim")
    table.add_column("flag", style="cyan")
    table.add_column("trace", style="dim")
    table.add_column("payload", overflow="fold")
    for ts, fl, tid, pl in rows:
        table.add_row(ts.split("T")[1][:12], fl, tid[:8], pl[:80])
    _print(table)


def _follow_events(*, flag: str | None, interval: float) -> None:
    """tail -f over the events table."""
    conn = init_events_db()
    tail_to_sqlite(conn)
    last_ts = ""
    row = conn.execute("SELECT MAX(ts) FROM events").fetchone()
    if row and row[0]:
        last_ts = row[0]
    if not STATE.json_out:
        _print(f"[dim]following events (interval={interval}s, Ctrl-C to stop)…[/dim]")
    try:
        while True:
            tail_to_sqlite(conn)
            if flag:
                rows = conn.execute(
                    "SELECT ts, flag, trace_id, payload FROM events "
                    "WHERE flag = ? AND ts > ? ORDER BY ts ASC LIMIT 100",
                    (flag, last_ts),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT ts, flag, trace_id, payload FROM events "
                    "WHERE ts > ? ORDER BY ts ASC LIMIT 100", (last_ts,),
                ).fetchall()
            for ts, fl, tid, pl in rows:
                if STATE.json_out:
                    _emit_json({"ts": ts, "flag": fl, "trace_id": tid, "payload": pl})
                else:
                    _print(f"[dim]{ts.split('T')[1][:12]}[/dim] [cyan]{fl}[/cyan] {tid[:8]} {pl[:120]}")
                last_ts = ts
            time.sleep(interval)
    except KeyboardInterrupt:
        if not STATE.json_out:
            _print("\n[dim]stopped[/dim]")
    finally:
        conn.close()


@app.command()
def lessons(n: int = typer.Option(10, "-n")) -> None:
    """Show recent distilled lessons from the Reflector."""
    from .db import open_atoms_db
    conn = open_atoms_db()
    rows = conn.execute(
        "SELECT ts, trigger, rule, confidence FROM lessons "
        "ORDER BY ts DESC LIMIT ?", (n,),
    ).fetchall()
    conn.close()

    if STATE.json_out:
        _emit_json({"lessons": [
            {"ts": ts, "trigger": trigger, "rule": rule, "confidence": conf}
            for ts, trigger, rule, conf in rows
        ]})
        return

    if not rows:
        _print("[dim](no lessons yet)[/dim]")
        return

    table = Table(title="◊ lessons")
    table.add_column("when", style="dim")
    table.add_column("trigger", style="yellow")
    table.add_column("confidence", justify="right")
    table.add_column("rule")
    for ts, trigger, rule, conf in rows:
        table.add_row(ts.split("T")[0], trigger[:30], f"{conf:.2f}", rule)
    _print(table)


# ═══════════════════════════════════════════════════════════════════════════
#  PALACE — Structured layer over atoms.db (v0.2.7+)
# ═══════════════════════════════════════════════════════════════════════════


palace_app = typer.Typer(help="◊ structured memory: rooms, closets, triples")
app.add_typer(palace_app, name="palace")


@palace_app.command("stats")
def palace_stats() -> None:
    """Counts of rooms, closets, entities, triples in the palace."""
    from .palace import open_palace
    p = open_palace()
    try:
        stats = p.stats()
    finally:
        p.close()

    if STATE.json_out:
        _emit_json({"ok": True, **stats})
        return

    table = Table(title="◊ palace · stats", show_header=False, box=None, padding=(0, 1))
    table.add_column(style="dim")
    table.add_column(justify="right")
    for k, v in stats.items():
        table.add_row(k, str(v))
    _print(table)


@palace_app.command("rooms")
def palace_rooms() -> None:
    """List all rooms in the palace."""
    from .palace import open_palace
    p = open_palace()
    try:
        rooms = p.list_rooms()
    finally:
        p.close()

    if STATE.json_out:
        _emit_json({"rooms": [
            {"id": r.id, "name": r.name, "description": r.description,
             "created_at": r.created_at}
            for r in rooms
        ]})
        return

    if not rooms:
        _print("[dim](no rooms)[/dim]")
        return

    table = Table(title="◊ palace · rooms")
    table.add_column("id", style="cyan")
    table.add_column("name")
    table.add_column("description", overflow="fold")
    table.add_column("created", style="dim")
    for r in rooms:
        table.add_row(r.id, r.name, r.description[:60], r.created_at.split("T")[0])
    _print(table)


@palace_app.command("create-room")
def palace_create_room(
    room_id: str = typer.Argument(..., help="Stable room id, e.g. room-research"),
    name: str = typer.Argument(..., help="Human-readable name"),
    description: str = typer.Option("", "--description"),
) -> None:
    """Create a new room in the palace."""
    from .palace import open_palace
    p = open_palace()
    try:
        room = p.create_room(room_id=room_id, name=name, description=description)
    except Exception as e:  # noqa: BLE001
        p.close()
        _die(ExitCode.ERROR, f"create-room failed: {e}")
    finally:
        p.close()

    if STATE.json_out:
        _emit_json({"ok": True, "id": room.id, "name": room.name})
    else:
        _print(f"[green]created[/green] {room.id} · {room.name}")


@palace_app.command("closets")
def palace_closets(
    room_id: str | None = typer.Option(None, "--room", help="Filter by room"),
    limit: int = typer.Option(20, "-n"),
) -> None:
    """List recent closets, optionally filtered by room."""
    from .palace import open_palace
    p = open_palace()
    try:
        closets = p.list_closets(room_id=room_id)[:limit]
    finally:
        p.close()

    if STATE.json_out:
        _emit_json({"closets": [
            {"id": c.id, "room_id": c.room_id, "topic": c.topic,
             "entities": c.entities, "atom_ids": c.atom_ids,
             "source_file": c.source_file, "created_at": c.created_at}
            for c in closets
        ]})
        return

    if not closets:
        _print("[dim](no closets)[/dim]")
        return

    table = Table(title=f"◊ palace · closets" + (f" ({room_id})" if room_id else ""))
    table.add_column("id", style="cyan", overflow="ellipsis", max_width=24)
    table.add_column("topic", overflow="fold")
    table.add_column("entities", style="magenta", overflow="fold")
    table.add_column("atoms", justify="right")
    table.add_column("source", style="dim", overflow="ellipsis", max_width=30)
    for c in closets:
        table.add_row(
            c.id, c.topic[:80],
            "; ".join(c.entities[:3]) + ("…" if len(c.entities) > 3 else ""),
            str(len(c.atom_ids)),
            c.source_file or "",
        )
    _print(table)


@palace_app.command("search")
def palace_search(
    query: str = typer.Argument(..., help="Substring search over closet topics + entities"),
    room_id: str | None = typer.Option(None, "--room"),
    limit: int = typer.Option(10, "-n"),
) -> None:
    """Keyword search over the closet index. v0.2.7 first cut.

    For semantic search, use ``sovereign palace search-semantic`` (requires
    embed_query tool). Hybrid BM25+cosine is roadmap for v0.2.8.
    """
    from .palace import open_palace
    p = open_palace()
    try:
        results = p.search_closets_keyword(query, limit=limit, room_id=room_id)
    finally:
        p.close()

    if STATE.json_out:
        _emit_json({"results": [
            {"id": c.id, "topic": c.topic, "entities": c.entities,
             "atom_ids": c.atom_ids, "room_id": c.room_id}
            for c in results
        ]})
        return

    if not results:
        _print(f"[dim](no closets matched {query!r})[/dim]")
        return

    table = Table(title=f"◊ palace · search · {query!r}")
    table.add_column("id", style="cyan", overflow="ellipsis", max_width=20)
    table.add_column("topic", overflow="fold")
    table.add_column("entities", style="magenta")
    table.add_column("atoms", justify="right")
    for c in results:
        table.add_row(c.id, c.topic[:80], "; ".join(c.entities[:3]), str(len(c.atom_ids)))
    _print(table)


@palace_app.command("subject")
def palace_subject(
    entity_id: str = typer.Argument(..., help="Entity id to query"),
    as_of: str | None = typer.Option(None, "--as-of",
        help="Point-in-time filter (RFC3339 / ISO date)"),
) -> None:
    """Show all triples about this subject. Optional point-in-time filter."""
    from .palace import open_palace
    p = open_palace()
    try:
        triples = p.query_subject(entity_id, as_of=as_of)
        ent = p.get_entity(entity_id)
    finally:
        p.close()

    if STATE.json_out:
        _emit_json({
            "entity": {
                "id": ent.id, "name": ent.name, "type": ent.type,
            } if ent else None,
            "triples": [
                {"id": t.id, "subject": t.subject_id,
                 "predicate": t.predicate, "object_id": t.object_id,
                 "object_literal": t.object_literal,
                 "valid_from": t.valid_from, "valid_to": t.valid_to,
                 "confidence": t.confidence}
                for t in triples
            ],
        })
        return

    if ent:
        _print(Panel(
            f"[bold]{ent.name}[/bold]  ({ent.type})\n"
            f"id: {ent.id}\n"
            f"first seen: {ent.first_seen.split('T')[0]}\n"
            f"last seen:  {ent.last_seen.split('T')[0]}",
            title="◊ entity", border_style="cyan",
        ))

    if not triples:
        _print(f"[dim](no triples for {entity_id})[/dim]")
        return

    table = Table(title=f"◊ triples about {entity_id}")
    table.add_column("predicate", style="magenta")
    table.add_column("object")
    table.add_column("from", style="dim")
    table.add_column("to", style="dim")
    table.add_column("conf", justify="right")
    for t in triples:
        obj = t.object_id or t.object_literal or "?"
        table.add_row(
            t.predicate, obj[:40],
            (t.valid_from or "—").split("T")[0],
            (t.valid_to or "—").split("T")[0],
            f"{t.confidence:.2f}",
        )
    _print(table)


# ═══════════════════════════════════════════════════════════════════════════
#  PALACE UNDERSTANDING + PROPOSALS — Self-reflection loop (v0.2.9+)
# ═══════════════════════════════════════════════════════════════════════════


@palace_app.command("understanding")
def palace_understanding(
    output: Path | None = typer.Option(
        None, "--output", help="Write markdown report to this file."
    ),
) -> None:
    """Scan the palace, print or write a structured understanding report.

    Read-only. No mutations. Used to drive palace-reflect and palace-clean.
    """
    from .palace import open_palace
    from .palace_scan import (
        render_understanding_markdown,
        scan_palace,
        understanding_to_dict,
    )

    p = open_palace()
    try:
        understanding = scan_palace(p)
    finally:
        p.close()

    if STATE.json_out:
        _emit_json({"ok": True, "understanding": understanding_to_dict(understanding)})
        return

    md = render_understanding_markdown(understanding)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(md, encoding="utf-8")
        _print(f"[green]wrote[/green] {output}")
    else:
        _print(md)


@palace_app.command("lineage")
def palace_lineage(
    target_id: str = typer.Argument(..., help="atom_id (forward) or closet_id (reverse)"),
    reverse: bool = typer.Option(
        False, "--reverse", "-r",
        help="Walk back from a closet to its source atoms + files. Default: forward from atom.",
    ),
    output: Path | None = typer.Option(
        None, "--output",
        help="Write markdown report to this file. Default: print to stdout.",
    ),
) -> None:
    """Walk the lineage chain for an atom or closet. Read-only.

    Forward (default): atom → parents, closets, triples, child atoms.
    Reverse (--reverse): closet → contributing atoms → source files.

    Use this to trace where any piece of structured memory came from. The
    chain is built from the breadcrumbs already stored in the system —
    atom.parents, closet.atom_ids, triple.source_atom_ids, etc.

    v0.2.11+
    """
    from .lineage import (
        lineage_forward, lineage_reverse, lineage_to_dict,
        render_forward_markdown, render_reverse_markdown,
    )

    if reverse:
        result = lineage_reverse(target_id)
        if result.closet is None:
            _die(ExitCode.APPROVAL_NOT_FOUND, f"closet not found: {target_id}")
        md = render_reverse_markdown(result)
    else:
        result = lineage_forward(target_id)
        if result.atom is None:
            _die(ExitCode.APPROVAL_NOT_FOUND,
                 f"atom not found: {target_id}\n"
                 f"  Hint: did you mean --reverse for a closet_id?")
        md = render_forward_markdown(result)

    if STATE.json_out:
        _emit_json({"ok": True, "lineage": lineage_to_dict(result)})
        return

    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(md, encoding="utf-8")
        _print(f"[green]wrote[/green] {output}")
    else:
        _print(md)


proposals_app = typer.Typer(help="◊ self-reflection proposals (v0.2.9)")
app.add_typer(proposals_app, name="proposals")


@proposals_app.command("list")
def proposals_list(
    status: str | None = typer.Option(None, "--status",
        help="Filter: pending / approved / rejected / applied / failed"),
    kind: str | None = typer.Option(None, "--kind",
        help="Filter: clean / reorganize / insight / enhancement"),
) -> None:
    """List proposals, optionally filtered by status or kind."""
    from .proposals import open_store

    store = open_store()
    items = store.list_all(status=status, kind=kind)

    if STATE.json_out:
        _emit_json({"proposals": [
            {"id": p.id, "kind": p.kind, "title": p.title,
             "status": p.status, "source": p.source,
             "created_at": p.created_at,
             "approved_at": p.approved_at,
             "applied_at": p.applied_at}
            for p in items
        ]})
        return

    if not items:
        suffix = ""
        if status:
            suffix = f" with status={status}"
        if kind:
            suffix += f" kind={kind}"
        _print(f"[dim](no proposals{suffix})[/dim]")
        return

    table = Table(title="◊ proposals")
    table.add_column("id", style="cyan", overflow="ellipsis", max_width=24)
    table.add_column("kind", style="magenta")
    table.add_column("status")
    table.add_column("title", overflow="fold")
    table.add_column("created", style="dim")
    for p in items:
        color = {"pending": "yellow", "approved": "green",
                 "rejected": "dim", "applied": "blue", "failed": "red"}.get(p.status, "white")
        table.add_row(p.id, p.kind, f"[{color}]{p.status}[/{color}]",
                     p.title[:60], p.created_at.split("T")[0])
    _print(table)


@proposals_app.command("show")
def proposals_show(
    proposal_id: str = typer.Argument(..., help="Proposal id"),
) -> None:
    """Show full detail for one proposal."""
    from .proposals import ProposalNotFound, open_store

    store = open_store()
    try:
        p = store.get(proposal_id)
    except ProposalNotFound:
        _die(ExitCode.APPROVAL_NOT_FOUND, f"proposal not found: {proposal_id}")

    if STATE.json_out:
        from dataclasses import asdict
        _emit_json({"proposal": asdict(p)})
        return

    _print(Panel(
        f"[bold]{p.title}[/bold]\n"
        f"id: {p.id}\n"
        f"kind: {p.kind} · status: {p.status}\n"
        f"source: {p.source}\n"
        f"created: {p.created_at}\n"
        + (f"approved: {p.approved_at} by {p.approved_by}\n" if p.approved_at else "")
        + (f"applied: {p.applied_at}\n" if p.applied_at else "")
        + f"\n[bold]rationale:[/bold]\n{p.rationale or '(none)'}\n"
        + f"\n[bold]action:[/bold]\n{json.dumps(p.action, indent=2)}\n"
        + (f"\n[bold]notes:[/bold]\n{p.notes}\n" if p.notes else "")
        + (f"\n[bold]result:[/bold]\n{p.result}\n" if p.result else "")
        + (f"\n[bold]rollback:[/bold]\n{json.dumps(p.rollback, indent=2)}\n"
           if p.rollback else ""),
        title=f"◊ proposal {p.id}", border_style="cyan",
    ))


@proposals_app.command("approve")
def proposals_approve(
    proposal_id: str = typer.Argument(..., help="Proposal id to approve"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
) -> None:
    """Approve a proposal so palace-apply can execute it."""
    from .approval import _load_or_create_secret
    from .proposals import (
        ProposalNotApprovable, ProposalNotFound, open_store,
    )

    store = open_store()
    try:
        p = store.get(proposal_id)
    except ProposalNotFound:
        _die(ExitCode.APPROVAL_NOT_FOUND, f"proposal not found: {proposal_id}")

    if not yes:
        _print(Panel(
            f"[bold]{p.title}[/bold]\n"
            f"kind: {p.kind}\n\n"
            f"[bold]rationale:[/bold] {p.rationale}\n\n"
            f"[bold]action:[/bold]\n{json.dumps(p.action, indent=2)}",
            title="◊ approve proposal?", border_style="yellow",
        ))
        if not typer.confirm("Approve this proposal?"):
            _print("[dim]aborted[/dim]")
            raise typer.Exit(ExitCode.OK)

    secret = _load_or_create_secret()
    try:
        approved = store.approve(proposal_id, secret=secret)
    except ProposalNotApprovable as e:
        _die(ExitCode.APPROVAL_NOT_FOUND, str(e))

    if STATE.json_out:
        _emit_json({"ok": True, "id": approved.id, "status": approved.status})
    else:
        _print(f"[green]approved[/green] {approved.id}")
        _print(f"  apply with: [bold]sovereign plan palace-apply[/bold]")


@proposals_app.command("reject")
def proposals_reject(
    proposal_id: str = typer.Argument(..., help="Proposal id to reject"),
    reason: str = typer.Option("operator rejected", "--reason"),
) -> None:
    """Reject a proposal. Cannot be undone."""
    from .proposals import (
        ProposalNotApprovable, ProposalNotFound, open_store,
    )

    store = open_store()
    try:
        p = store.reject(proposal_id, reason=reason)
    except ProposalNotFound:
        _die(ExitCode.APPROVAL_NOT_FOUND, f"proposal not found: {proposal_id}")
    except ProposalNotApprovable as e:
        _die(ExitCode.APPROVAL_NOT_FOUND, str(e))

    if STATE.json_out:
        _emit_json({"ok": True, "id": p.id, "status": p.status})
    else:
        _print(f"[dim]rejected[/dim] {p.id} ({reason})")


impact_app = typer.Typer(help="◊ multi-scale impact measurement (MSIMS, v0.2.10)")
app.add_typer(impact_app, name="impact")


@impact_app.command("score")
def impact_score_cmd(
    action_label: str = typer.Argument(..., help="One-line summary of the action."),
    description: str = typer.Option("", "--description", "-d",
        help="Longer description for the model to score against."),
    context: str = typer.Option("", "--context", "-c",
        help="Additional context (atoms it'll affect, who's involved, etc.)."),
    drive: bool = typer.Option(True, "--drive/--no-drive",
        help="Plan + drive the continuation in one shot (default: yes)."),
) -> None:
    """Score a 3×4 Impact Vector for an action. Stores as a Knowledge Atom.

    Convenience wrapper around `sov plan impact-score` + drive loop. The
    model emits a 3×4 matrix with confidence per cell, written as an atom
    in atoms.db. Operator reviews via `sov impact show <atom-id>`.

    The scoring is JUDGMENT, not measurement. Confidence is surfaced
    prominently. The IV is information for the operator — the system
    never auto-rejects based on it.
    """
    from .planners import REGISTRY
    planner = REGISTRY["impact-score"]

    args = {
        "action_label": action_label,
        "action_description": description or action_label,
        "context": context,
    }
    try:
        plan_result = planner.plan(**args)
    except Exception as e:  # noqa: BLE001
        _die(ExitCode.USAGE, f"plan failed: {e}")

    # Persist the continuation
    from .continuation import Continuation, ContinuationStore
    from ulid import ULID
    task_id = f"cont-{ULID()}"
    cont = Continuation(
        task_id=task_id, planner=planner.name, planner_args=args,
        steps=plan_result.steps, output_path=plan_result.output_path,
        notes=plan_result.notes, goal=plan_result.goal,
    )
    store = ContinuationStore(SETTINGS.paths.continuations_dir)
    store.put(cont)

    if STATE.json_out:
        _emit_json({
            "ok": True, "task_id": task_id,
            "step_count": len(plan_result.steps),
            "drove": drive,
        })
        if not drive:
            return
    else:
        _print(f"◊ planned · {task_id} · {len(plan_result.steps)} step(s)")
        if not drive:
            _print(f"  drive with: sov continue {task_id}")
            return

    # Drive
    from .continue_runner import run_one_step
    while True:
        try:
            result = run_one_step(task_id)
        except Exception as e:  # noqa: BLE001
            _die(ExitCode.GENERIC, f"continue failed: {e}")
        if result.outcome == "drained":
            break
        if result.outcome == "halted":
            _die(ExitCode.HALTED, "PROTOCOL-ZERO armed")
        # complete or poison: keep going

    # Find the resulting atom_id by scanning the events log for the impact_score tool result
    # Simplest: read the continuation's last event log entry — but the tool result
    # lands in events.jsonl. For now, point the operator at recent atoms.
    if STATE.json_out:
        _emit_json({"ok": True, "task_id": task_id, "drained": True,
                    "next": "find atom_id via `sov memory_search 'impact'` or check recent events"})
    else:
        _print(f"[green]done[/green] · IV emitted as atom (type=decision)")
        _print(f"  find it: `sov events --flag tool-d -n 5` then `sov impact show <atom-id>`")


@impact_app.command("show")
def impact_show_cmd(
    atom_id: str = typer.Argument(..., help="atom_id of an Impact Vector atom"),
) -> None:
    """Render an Impact Vector atom as a 3×4 matrix with confidence per cell."""
    from .impact import ImpactVector, render_iv_matrix_dict, render_iv_matrix_text
    from .db import open_atoms_db
    import json as _json

    conn = open_atoms_db()
    try:
        row = conn.execute(
            "SELECT atom_id, type, summary, content_ref, claims FROM atoms "
            "WHERE atom_id = ?",
            (atom_id,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        _die(ExitCode.APPROVAL_NOT_FOUND, f"atom not found: {atom_id}")
    atom_id_, atype, summary, content_ref_json, claims_json = row[0], row[1], row[2], row[3], row[4]
    if atype != "decision":
        _print(f"[yellow]warning:[/yellow] atom is type={atype!r}, expected 'decision' for IVs")

    try:
        content_ref = _json.loads(content_ref_json) if content_ref_json else {}
        claims = _json.loads(claims_json) if claims_json else []
    except _json.JSONDecodeError as e:
        _die(ExitCode.GENERIC, f"corrupt atom: {e}")

    # The IV metadata is stored in content_ref.data
    metadata = content_ref.get("data", {}) if isinstance(content_ref, dict) else {}
    atom_dict = {
        "summary": summary,
        "claims": claims,
        "metadata": metadata,
        "framing": metadata.get("framing", ""),
    }
    iv = ImpactVector.from_atom_dict(atom_dict)

    if STATE.json_out:
        _emit_json({"atom_id": atom_id_, "iv": render_iv_matrix_dict(iv)})
    else:
        _print(render_iv_matrix_text(iv))


@proposals_app.command("delete")
def proposals_delete(
    proposal_id: str = typer.Argument(..., help="Proposal id to delete"),
    yes: bool = typer.Option(False, "--yes", "-y"),
) -> None:
    """Hard-delete a proposal. Use sparingly; reject preserves audit better."""
    from .proposals import open_store
    if not yes:
        if not typer.confirm(f"Hard-delete proposal {proposal_id}? (Use 'reject' to preserve audit)"):
            _print("[dim]aborted[/dim]")
            raise typer.Exit(ExitCode.OK)
    store = open_store()
    deleted = store.delete(proposal_id)
    if STATE.json_out:
        _emit_json({"ok": True, "deleted": deleted})
    else:
        if deleted:
            _print(f"[red]deleted[/red] {proposal_id}")
        else:
            _print(f"[dim]not found[/dim] {proposal_id}")


@proposals_app.command("stage")
def proposals_stage(
    proposal_id: str = typer.Argument(..., help="code_update proposal id"),
    timeout: int = typer.Option(600, "--timeout",
        help="pytest timeout in seconds"),
) -> None:
    """Stage a code_update proposal: copy proposed file → run tests → record result.

    Required for code_update proposals before they can be approved + applied.
    The proposal's action must contain {source_path, target_relpath}.

    The pipeline:
      1. Read proposal action (source_path, target_relpath)
      2. Copy source_path into <data_dir>/staging/<proposal_id>/
      3. Temporarily apply proposed file to target, run pytest, restore original
      4. Persist test_result.json in staging dir
      5. Update proposal notes with the test summary

    Operator then reviews via `sov proposals show`. If tests passed AND the
    operator is satisfied, they `sov proposals approve <id>` and the
    palace-apply pipeline picks it up. archive_and_swap will refuse if
    test_result.ok is not True.
    """
    from .code_update import (
        StagingError, run_tests_against_staging, stage_proposal,
    )
    from .proposals import (
        ProposalNotApprovable, ProposalNotFound, open_store,
    )

    store = open_store()
    try:
        p = store.get(proposal_id)
    except ProposalNotFound:
        _die(ExitCode.APPROVAL_NOT_FOUND, f"proposal not found: {proposal_id}")

    if p.kind != "code_update":
        _die(ExitCode.USAGE,
             f"proposal {proposal_id} is kind={p.kind!r}, not 'code_update'. "
             f"Only code_update proposals can be staged.")
    if p.status != "pending":
        _die(ExitCode.USAGE,
             f"proposal {proposal_id} is in state {p.status!r}; "
             f"only pending proposals can be staged.")

    src = p.action.get("source_path")
    rel = p.action.get("target_relpath")
    if not src or not rel:
        _die(ExitCode.USAGE,
             f"proposal {proposal_id} action missing source_path or target_relpath")

    if not STATE.json_out:
        _print(f"◊ staging {proposal_id}")
        _print(f"  source: {src}")
        _print(f"  target: {rel}")
    try:
        from pathlib import Path as _Path
        stage_proposal(
            proposal_id=proposal_id,
            source_path=_Path(src),
            target_relpath=str(rel),
            data_dir=SETTINGS.paths.data_dir,
        )
    except StagingError as e:
        _die(ExitCode.GENERIC, f"stage failed: {e}")

    if not STATE.json_out:
        _print(f"  running tests (timeout {timeout}s)…")
    result = run_tests_against_staging(
        proposal_id=proposal_id,
        data_dir=SETTINGS.paths.data_dir,
        timeout=timeout,
    )

    # Append result summary to proposal notes (so `proposals show` surfaces it)
    p_again = store.get(proposal_id)
    summary_line = (
        f"STAGE {result['ran_at']}: "
        f"ok={result['ok']} "
        f"summary={result['summary']!r} "
        f"duration={result['duration_seconds']:.1f}s"
    )
    p_again.notes = (p_again.notes + "\n" if p_again.notes else "") + summary_line
    from .proposals import _atomic_write_yaml, _to_yaml_dict
    _atomic_write_yaml(store._path(proposal_id), _to_yaml_dict(p_again))

    if STATE.json_out:
        _emit_json({"ok": result["ok"], "result": result})
    else:
        if result["ok"]:
            _print(f"  [green]✓ tests passed[/green] · {result['summary']}")
            _print(f"  next: review via `sov proposals show {proposal_id}` then approve")
        else:
            _print(f"  [red]✗ tests failed[/red] · {result['summary']}")
            _print(f"  staged file is in {SETTINGS.paths.data_dir}/staging/{proposal_id}/")
            _print(f"  the swap will REFUSE while tests are failing.")
            raise typer.Exit(ExitCode.GENERIC)


@proposals_app.command("rollback")
def proposals_rollback(
    proposal_id: str = typer.Argument(..., help="Applied proposal id to roll back"),
    yes: bool = typer.Option(False, "--yes", "-y"),
) -> None:
    """Roll back an applied proposal using its recorded rollback descriptor.

    The proposal must be in status='applied' AND have a rollback descriptor
    that we know how to execute. Currently supported:
      - code_rollback: restore the archived file
      - restore_triple: re-mark a triple as valid (currently no-op; soft-delete via valid_to is its own contract)
      - restore_closet: re-add a removed closet
      - remove_closet: delete an additive closet (insights/enhancements)
    """
    from .events import emit_event
    from .proposals import (
        ProposalNotApprovable, ProposalNotFound, open_store,
    )

    store = open_store()
    try:
        p = store.get(proposal_id)
    except ProposalNotFound:
        _die(ExitCode.APPROVAL_NOT_FOUND, f"proposal not found: {proposal_id}")

    if p.status != "applied":
        _die(ExitCode.USAGE,
             f"proposal {proposal_id} is in state {p.status!r}, "
             f"only 'applied' proposals can be rolled back.")
    if not p.rollback:
        _die(ExitCode.USAGE,
             f"proposal {proposal_id} has no rollback descriptor; "
             f"cannot be auto-rolled-back.")

    rb_type = p.rollback.get("type")

    if not yes:
        _print(Panel(
            f"[bold]{p.title}[/bold]\n"
            f"applied at: {p.applied_at}\n"
            f"rollback type: {rb_type}\n"
            f"rollback details: {json.dumps(p.rollback, indent=2)}",
            title="◊ rollback applied proposal?", border_style="yellow",
        ))
        if not typer.confirm("Proceed with rollback?"):
            _print("[dim]aborted[/dim]")
            raise typer.Exit(ExitCode.OK)

    # Dispatch on rollback type
    result_msg: str = ""
    try:
        if rb_type == "code_rollback":
            from .code_update import rollback_from_archive
            from pathlib import Path as _Path
            r = rollback_from_archive(
                archive_dir=_Path(p.rollback["archive_dir"]),
                target_relpath=p.rollback["target_relpath"],
            )
            result_msg = f"restored {r['restored_to']} from {r['from_archive']}"
        elif rb_type == "remove_closet":
            from .palace import open_palace
            palace = open_palace()
            try:
                with palace._connect() as c:
                    c.execute("DELETE FROM closets WHERE id = ?",
                              (p.rollback["closet_id"],))
            finally:
                palace.close()
            result_msg = f"removed closet {p.rollback['closet_id']}"
        elif rb_type == "restore_closet":
            from .palace import Closet, open_palace
            palace = open_palace()
            try:
                cd = p.rollback["closet"]
                palace.add_closet(Closet(
                    id=cd["id"], room_id=cd["room_id"],
                    topic=cd["topic"], entities=cd["entities"],
                    atom_ids=cd["atom_ids"],
                    embedding=cd.get("embedding"),
                    source_file=cd.get("source_file"),
                    created_at=cd.get("created_at"),
                ))
            finally:
                palace.close()
            result_msg = f"restored closet {cd['id']}"
        elif rb_type == "restore_triple":
            # Re-validate the triple (clear valid_to). Use direct SQL since
            # palace.py doesn't expose this — invalidating is the supported op,
            # and unwinding it requires this raw access for now.
            from .palace import open_palace
            palace = open_palace()
            try:
                with palace._connect() as c:
                    c.execute("UPDATE triples SET valid_to = NULL WHERE id = ?",
                              (p.rollback["triple_id"],))
            finally:
                palace.close()
            result_msg = f"re-validated triple {p.rollback['triple_id']}"
        elif rb_type == "restore_entities":
            from .palace import open_palace
            palace = open_palace()
            try:
                with palace._connect() as c:
                    # Re-insert the entities
                    for ent in p.rollback.get("entities", []):
                        c.execute(
                            "INSERT OR REPLACE INTO entities(id, name, type, "
                            "properties_json, first_seen, last_seen) "
                            "VALUES (?,?,?,?,?,?)",
                            (ent["id"], ent["name"], ent["type"],
                             ent["properties_json"], ent["first_seen"], ent["last_seen"]),
                        )
                    # Reverse the triple remaps
                    for remap in p.rollback.get("triple_remaps", []):
                        c.execute(
                            "UPDATE triples SET subject_id = ? "
                            "WHERE id = ? AND subject_id = ?",
                            (remap["to_id"], remap["triple_id"], remap["from_id"]),
                        )
                        c.execute(
                            "UPDATE triples SET object_id = ? "
                            "WHERE id = ? AND object_id = ?",
                            (remap["to_id"], remap["triple_id"], remap["from_id"]),
                        )
            finally:
                palace.close()
            result_msg = f"unmerged {len(p.rollback.get('entities', []))} entities"
        else:
            _die(ExitCode.USAGE,
                 f"unsupported rollback type: {rb_type!r}")
    except Exception as e:  # noqa: BLE001
        _die(ExitCode.GENERIC, f"rollback failed: {type(e).__name__}: {e}")

    # Audit event — proposal stays 'applied' for trail; we add a rollback note.
    p_again = store.get(proposal_id)
    p_again.notes = (p_again.notes + "\n" if p_again.notes else "") + \
                    f"ROLLED BACK {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}: {result_msg}"
    from .proposals import _atomic_write_yaml as _w, _to_yaml_dict as _d
    _w(store._path(proposal_id), _d(p_again))
    emit_event(
        "proposal-rolled-back-d",
        plane="control",
        trace_id=f"prop:{proposal_id}",
        payload={"proposal_id": proposal_id, "rollback_type": rb_type, "result": result_msg[:200]},
    )

    if STATE.json_out:
        _emit_json({"ok": True, "result": result_msg})
    else:
        _print(f"[green]rolled back[/green] · {result_msg}")


# ════════════════════════════════════════════════════════════════════════════
#  v0.2.12 — pause/resume, dream, projects, do (plain English)
# ════════════════════════════════════════════════════════════════════════════


# ─── pause / resume primitives (continuations) ──────────────────────────────


@app.command(name="pause")
def pause_cmd(
    task_id: str = typer.Argument(
        ..., help="Continuation ID (cont-... or cycle-...)"
    ),
    reason: str = typer.Option(
        "operator pause", "--reason",
        help="Free text persisted on the continuation's notes field.",
    ),
) -> None:
    """Pause a continuation. The runner refuses to advance until ``sov resume``.

    Idempotent: pausing an already-paused continuation succeeds with no change.
    Drained continuations cannot be paused (refused with USAGE exit code).

    v0.2.12+
    """
    _preflight_initialized()
    from .continuation import (
        ContinuationLocked, ContinuationNotFound, ContinuationStore,
    )
    store = ContinuationStore(SETTINGS.paths.continuations_dir)
    try:
        with store.lock(task_id, blocking=True, timeout_seconds=5.0) as cont:
            if cont.is_drained():
                _die(ExitCode.USAGE,
                     f"continuation {task_id} is already drained "
                     f"(status={cont.status}); pause is a no-op")
            if cont.status != "paused":
                cont.status = "paused"
                cont.notes = (cont.notes + "\n" if cont.notes else "") + \
                             f"PAUSED {_utc_now_str()}: {reason}"
    except ContinuationNotFound:
        _die(ExitCode.USAGE, f"continuation not found: {task_id}")
    except ContinuationLocked:
        _die(ExitCode.LOCKED,
             f"continuation {task_id} is held by a running step; try again")

    if STATE.json_out:
        _emit_json({"ok": True, "task_id": task_id, "status": "paused"})
    else:
        _print(f"[yellow]paused[/yellow] · {task_id} (reason: {reason})")
        _print(f"[dim]resume with:[/dim] [cyan]sov resume {task_id}[/cyan]")


@app.command(name="resume")
def resume_cmd(
    task_id: str = typer.Argument(..., help="Continuation ID to resume"),
    drive: bool = typer.Option(
        False, "--drive",
        help="After resuming, drive the continuation to completion.",
    ),
) -> None:
    """Resume a paused continuation. Optionally drive it to completion.

    Without --drive: just flips status from paused → in_progress / planned and
    returns. The operator (or an existing loop driver) picks it up.

    With --drive: invokes scripts/sovereign-continue-loop.sh inline.

    v0.2.12+
    """
    _preflight_initialized()
    from .continuation import (
        ContinuationLocked, ContinuationNotFound, ContinuationStore,
    )
    store = ContinuationStore(SETTINGS.paths.continuations_dir)
    try:
        with store.lock(task_id, blocking=True, timeout_seconds=5.0) as cont:
            if cont.is_drained():
                _die(ExitCode.USAGE,
                     f"continuation {task_id} is already drained "
                     f"(status={cont.status}); cannot resume")
            if cont.status == "paused":
                # Recompute from steps — landing on planned / in_progress / etc.
                # update_status_from_steps preserves "paused", so we clear the
                # field first and let the recompute set the right value.
                cont.status = "in_progress"
                cont.update_status_from_steps()
                cont.notes = (cont.notes + "\n" if cont.notes else "") + \
                             f"RESUMED {_utc_now_str()}"
    except ContinuationNotFound:
        _die(ExitCode.USAGE, f"continuation not found: {task_id}")
    except ContinuationLocked:
        _die(ExitCode.LOCKED,
             f"continuation {task_id} is held by a running step; try again")

    if STATE.json_out:
        _emit_json({"ok": True, "task_id": task_id, "status": "resumed",
                    "drive": drive})
    else:
        _print(f"[green]resumed[/green] · {task_id}")
        if not drive:
            _print(f"[dim]drive it:[/dim] [cyan]sov continue {task_id}[/cyan]")

    if drive:
        # Inline driver — same shape as sov-drive but starting from an
        # already-existing continuation.
        import subprocess
        scripts = Path(__file__).resolve().parent.parent.parent / "scripts" / \
                  "sovereign-continue-loop.sh"
        if scripts.exists():
            subprocess.call([str(scripts), task_id])
        else:
            _print("[yellow]warning[/yellow] no continue-loop script found; "
                   "drive manually with `sov continue`")


def _utc_now_str() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ─── dream subcommand ───────────────────────────────────────────────────────


dream_app = typer.Typer(
    help="◊ infinite trillion-dollar software builder (v0.2.12)"
)
app.add_typer(dream_app, name="dream")


@dream_app.command("start")
def dream_start(
    goal: str = typer.Argument(
        "Build trillion-dollar software cycles, ideate→build→document, "
        "until paused.",
        help="Free-text description of what the dream is for.",
    ),
    max_files: int = typer.Option(
        2000, "--max-files",
        help="Stop after this many files have been written. 0 = unbounded.",
    ),
    max_cycles: int = typer.Option(
        0, "--max-cycles",
        help="Stop after this many cycles complete. 0 = unbounded.",
    ),
    max_seconds: int = typer.Option(
        0, "--max-seconds",
        help="Stop after this many wall-clock seconds. 0 = unbounded.",
    ),
    project: list[str] = typer.Option(
        [], "--project",
        help="Register a project the dream should be aware of. Repeatable.",
    ),
    drive: bool = typer.Option(
        False, "--drive",
        help="After creating the session, drive it (loop until paused/exhausted).",
    ),
) -> None:
    """Start a new infinite trillion-dollar builder dream session.

    Each cycle does: ideate → architect → build → document → atomize.
    Cycles run until ``--max-files`` is reached, ``--max-cycles`` is
    reached, ``--max-seconds`` is reached, or you ``sov dream pause``.
    The session has a stable ID so you can resume across sessions.

    Examples:
        sov dream start                              # 2000-file default cap
        sov dream start --max-files 0 --drive        # forever, drive immediately
        sov dream start --project genesis-seeds      # tie to a tracked project

    v0.2.12+
    """
    _preflight_initialized()
    from .dream import DreamCaps, DreamStore, ProjectRef
    store = DreamStore(SETTINGS.paths.dream_sessions_dir,
                       SETTINGS.paths.dreams_work_dir)
    caps = DreamCaps(
        max_files=max_files if max_files > 0 else (0 if max_files == 0 else 2000),
        max_cycles=max_cycles if max_cycles > 0 else None,
        max_seconds=float(max_seconds) if max_seconds > 0 else None,
    )
    # Special-case: explicit --max-files 0 means unbounded → store as None
    if max_files == 0:
        caps.max_files = None

    dream = store.create(goal=goal, caps=caps)
    for proj_name in project:
        dream.projects.append(ProjectRef(name=proj_name, root=""))
    if project:
        store.save(dream)

    if STATE.json_out:
        _emit_json({"ok": True, "dream_id": dream.dream_id,
                    "work_dir": dream.work_dir,
                    "max_files": dream.caps.max_files,
                    "max_cycles": dream.caps.max_cycles,
                    "max_seconds": dream.caps.max_seconds})
    else:
        cap_line = (
            f"max_files={dream.caps.max_files or '∞'}"
            f"  max_cycles={dream.caps.max_cycles or '∞'}"
            f"  max_seconds={dream.caps.max_seconds or '∞'}"
        )
        _print(Panel(
            f"[bold]{dream.goal}[/bold]\n"
            f"dream_id: [cyan]{dream.dream_id}[/cyan]\n"
            f"work_dir: {dream.work_dir}\n"
            f"caps: {cap_line}\n\n"
            f"[dim]advance one step:[/dim] "
            f"[cyan]sov dream advance {dream.dream_id}[/cyan]\n"
            f"[dim]drive in a loop:[/dim] "
            f"[cyan]scripts/sovereign-dream-loop.sh {dream.dream_id}[/cyan]\n"
            f"[dim]pause anytime:[/dim] "
            f"[cyan]sov dream pause {dream.dream_id}[/cyan]",
            title="◊ dream session created", border_style="green",
        ))

    if drive:
        _drive_dream_inline(dream.dream_id)


@dream_app.command("advance")
def dream_advance_cmd(
    dream_id: str = typer.Argument(..., help="Dream ID (dream-...)"),
    max_iter: int = typer.Option(5, "--max-iter"),
    max_wall: int = typer.Option(120, "--max-wall"),
    max_tokens: int = typer.Option(20_000, "--max-tokens"),
) -> None:
    """Advance a dream by exactly ONE step. Exit codes match `continue`.

    The shell driver re-invokes us until status terminal.
    """
    _preflight_initialized()
    _preflight_not_halted()

    from .dream import DreamStore
    from .dream_runner import advance_dream
    store = DreamStore(SETTINGS.paths.dream_sessions_dir,
                       SETTINGS.paths.dreams_work_dir)
    try:
        dream = store.get(dream_id)
    except Exception as e:  # noqa: BLE001
        _die(ExitCode.USAGE, f"dream not found: {e}")

    # Ollama only required for non-pure-Python steps.
    # We don't know which step yet, but the cycle runner will skip Ollama
    # checks for required_model='none' steps. Be lenient at this layer.
    needs_model = (dream.status not in ("paused", "exhausted", "halted", "completed"))
    if needs_model:
        _preflight_ollama_reachable(fatal=False)

    tools = _build_tools_for_mode(Mode.ONESHOT)
    budget = RunBudget(max_iterations=max_iter, max_wall_seconds=max_wall,
                      max_tokens=max_tokens, consecutive_fail_limit=2)

    protocol_zero.install_signal_handlers()
    result = advance_dream(
        dream_id=dream_id, tools=tools, store=store,
        budget=budget, mode=Mode.ONESHOT,
    )

    payload = {
        "dream_id": result.dream_id, "dream_status": result.dream_status,
        "cycle_number": result.cycle_number,
        "step_outcome": result.step_outcome, "step_id": result.step_id,
        "step_kind": result.step_kind, "iterations": result.iterations,
        "tokens": result.tokens, "elapsed_seconds": result.elapsed_seconds,
        "files_written_total": result.files_written_total,
        "cycles_completed": result.cycles_completed,
        "reason": result.reason,
    }

    # Map dream-level outcomes to exit codes.
    if result.step_outcome in ("dream_paused", "dream_exhausted",
                                "dream_completed", "dream_halted"):
        if STATE.json_out:
            _emit_json({"ok": True, "code": ExitCode.DRAINED, **payload})
        else:
            _print(f"[green]{result.step_outcome}[/green] · "
                   f"{result.dream_status} · {result.cycles_completed} cycles · "
                   f"{result.files_written_total} files · {result.reason}")
        raise typer.Exit(ExitCode.DRAINED)

    if result.step_outcome == "locked":
        if STATE.json_out:
            _emit_json({"ok": False, "code": ExitCode.LOCKED, **payload})
        else:
            _print(f"[yellow]locked[/yellow] · cycle held by another runner")
        raise typer.Exit(ExitCode.LOCKED)

    if result.step_outcome == "paused":
        if STATE.json_out:
            _emit_json({"ok": False, "code": ExitCode.DRAINED, **payload})
        else:
            _print(f"[yellow]cycle paused[/yellow] · {result.dream_id}")
        raise typer.Exit(ExitCode.DRAINED)

    if STATE.json_out:
        ok = result.step_outcome in ("complete", "new_cycle", "drained")
        _emit_json({"ok": ok, "code": ExitCode.OK if ok else ExitCode.ERROR, **payload})
    else:
        _print(f"[cyan]✓ dream step[/cyan] · cycle={result.cycle_number} · "
               f"{result.step_kind or '(no step)'} · "
               f"outcome={result.step_outcome} · "
               f"files={result.files_written_total}")
    raise typer.Exit(
        ExitCode.OK if result.step_outcome in ("complete", "new_cycle", "drained")
        else ExitCode.ERROR
    )


@dream_app.command("list")
def dream_list_cmd(
    status_filter: str | None = typer.Option(
        None, "--status", help="Filter by status (active/paused/exhausted/...)"
    ),
) -> None:
    """List all dream sessions."""
    _preflight_initialized()
    from .dream import DreamStore
    store = DreamStore(SETTINGS.paths.dream_sessions_dir,
                       SETTINGS.paths.dreams_work_dir)
    dreams = store.list_all(status=status_filter)

    if STATE.json_out:
        _emit_json({"dreams": [
            {"dream_id": d.dream_id, "status": d.status, "goal": d.goal,
             "cycles_completed": d.cycles_completed,
             "files_written": d.files_written,
             "max_files": d.caps.max_files,
             "created_at": d.created_at, "updated_at": d.updated_at}
            for d in dreams
        ]})
        return

    if not dreams:
        _print("[dim](no dreams yet — `sov dream start` to begin)[/dim]")
        return

    table = Table(title="◊ dream sessions", show_header=True, header_style="bold cyan")
    table.add_column("dream_id", style="cyan", no_wrap=True)
    table.add_column("status")
    table.add_column("cycles", justify="right")
    table.add_column("files", justify="right")
    table.add_column("cap")
    table.add_column("goal", overflow="fold")
    for d in dreams:
        cap_str = str(d.caps.max_files) if d.caps.max_files else "∞"
        table.add_row(
            d.dream_id, d.status,
            str(d.cycles_completed), str(d.files_written),
            cap_str, d.goal[:80],
        )
    _print(table)


@dream_app.command("show")
def dream_show_cmd(dream_id: str = typer.Argument(...)) -> None:
    """Show full state for one dream session."""
    _preflight_initialized()
    from .dream import DreamStore
    store = DreamStore(SETTINGS.paths.dream_sessions_dir,
                       SETTINGS.paths.dreams_work_dir)
    try:
        d = store.get(dream_id)
    except Exception as e:  # noqa: BLE001
        _die(ExitCode.USAGE, f"dream not found: {e}")

    if STATE.json_out:
        from .dream import _to_yaml
        _emit_json({"dream": _to_yaml(d)})
        return

    cap_line = (
        f"max_files={d.caps.max_files or '∞'}  "
        f"max_cycles={d.caps.max_cycles or '∞'}  "
        f"max_seconds={d.caps.max_seconds or '∞'}"
    )
    _print(Panel(
        f"[bold]{d.goal}[/bold]\n"
        f"status: [cyan]{d.status}[/cyan]\n"
        f"created: {d.created_at}\n"
        f"updated: {d.updated_at}\n"
        f"work_dir: {d.work_dir}\n"
        f"caps: {cap_line}\n"
        f"progress: {d.progress_summary()}\n"
        f"current cycle task: {d.current_cycle_task_id or '(none)'}",
        title=f"◊ dream {d.dream_id}", border_style="cyan",
    ))
    if d.cycles:
        t = Table(title="cycles", show_header=True, header_style="bold")
        t.add_column("#", justify="right")
        t.add_column("status")
        t.add_column("files", justify="right")
        t.add_column("title", overflow="fold")
        t.add_column("task_id", style="dim")
        for c in d.cycles[-20:]:  # last 20
            t.add_row(str(c.cycle_number), c.status, str(c.files_written),
                      c.title[:60], c.task_id)
        _print(t)


@dream_app.command("pause")
def dream_pause_cmd(dream_id: str = typer.Argument(...)) -> None:
    """Pause a dream session. The advance loop returns dream_paused next call."""
    _preflight_initialized()
    from .dream import DreamStore
    store = DreamStore(SETTINGS.paths.dream_sessions_dir,
                       SETTINGS.paths.dreams_work_dir)
    try:
        d = store.get(dream_id)
    except Exception as e:  # noqa: BLE001
        _die(ExitCode.USAGE, f"dream not found: {e}")

    if d.is_terminal():
        _die(ExitCode.USAGE,
             f"dream is already {d.status}; pause is a no-op")

    d.status = "paused"
    d.notes = (d.notes + "\n" if d.notes else "") + f"PAUSED {_utc_now_str()}"
    store.save(d)

    # Also pause the underlying current cycle if any, so a parallel
    # advance call can't sneak through.
    if d.current_cycle_task_id:
        from .continuation import (
            ContinuationLocked, ContinuationNotFound, ContinuationStore,
        )
        cstore = ContinuationStore(SETTINGS.paths.continuations_dir)
        try:
            with cstore.lock(d.current_cycle_task_id, blocking=True,
                              timeout_seconds=5.0) as cont:
                if not cont.is_drained() and cont.status != "paused":
                    cont.status = "paused"
        except (ContinuationNotFound, ContinuationLocked):
            pass

    if STATE.json_out:
        _emit_json({"ok": True, "dream_id": dream_id, "status": "paused"})
    else:
        _print(f"[yellow]paused[/yellow] · dream {dream_id}")
        _print(f"[dim]resume:[/dim] [cyan]sov dream resume {dream_id}[/cyan]")


@dream_app.command("resume")
def dream_resume_cmd(
    dream_id: str = typer.Argument(...),
    drive: bool = typer.Option(False, "--drive",
                               help="Drive in a loop after resuming."),
) -> None:
    """Resume a paused dream. With --drive, run the loop until paused/exhausted."""
    _preflight_initialized()
    from .dream import DreamStore
    store = DreamStore(SETTINGS.paths.dream_sessions_dir,
                       SETTINGS.paths.dreams_work_dir)
    try:
        d = store.get(dream_id)
    except Exception as e:  # noqa: BLE001
        _die(ExitCode.USAGE, f"dream not found: {e}")

    if d.status not in ("paused",):
        _die(ExitCode.USAGE,
             f"dream is {d.status}, not paused; nothing to resume")

    d.status = "active"
    d.notes = (d.notes + "\n" if d.notes else "") + f"RESUMED {_utc_now_str()}"
    store.save(d)

    # Wake the current cycle too.
    if d.current_cycle_task_id:
        from .continuation import (
            ContinuationLocked, ContinuationNotFound, ContinuationStore,
        )
        cstore = ContinuationStore(SETTINGS.paths.continuations_dir)
        try:
            with cstore.lock(d.current_cycle_task_id, blocking=True,
                              timeout_seconds=5.0) as cont:
                if cont.status == "paused" and not cont.is_drained():
                    cont.status = "in_progress"
                    cont.update_status_from_steps()
        except (ContinuationNotFound, ContinuationLocked):
            pass

    if STATE.json_out:
        _emit_json({"ok": True, "dream_id": dream_id, "status": "resumed",
                    "drive": drive})
    else:
        _print(f"[green]resumed[/green] · dream {dream_id}")

    if drive:
        _drive_dream_inline(dream_id)


@dream_app.command("stop")
def dream_stop_cmd(
    dream_id: str = typer.Argument(...),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Mark a dream completed. Permanent. Files on disk are preserved."""
    _preflight_initialized()
    from .dream import DreamStore
    store = DreamStore(SETTINGS.paths.dream_sessions_dir,
                       SETTINGS.paths.dreams_work_dir)
    try:
        d = store.get(dream_id)
    except Exception as e:  # noqa: BLE001
        _die(ExitCode.USAGE, f"dream not found: {e}")

    if not yes and not STATE.json_out:
        confirm = typer.confirm(
            f"Stop dream {dream_id}? "
            f"({d.cycles_completed} cycles, {d.files_written} files preserved on disk.)"
        )
        if not confirm:
            raise typer.Abort()

    d.status = "completed"
    d.notes = (d.notes + "\n" if d.notes else "") + f"STOPPED {_utc_now_str()}"
    store.save(d)

    if STATE.json_out:
        _emit_json({"ok": True, "dream_id": dream_id, "status": "completed"})
    else:
        _print(f"[green]stopped[/green] · dream {dream_id} (work_dir preserved)")


def _drive_dream_inline(dream_id: str) -> None:
    """Inline driver loop: keep calling advance until terminal.

    Lighter than the shell script but does the same thing. Emits a single
    line per advance, exits cleanly when the dream is terminal.
    """
    from .dream import DreamStore
    from .dream_runner import advance_dream
    store = DreamStore(SETTINGS.paths.dream_sessions_dir,
                       SETTINGS.paths.dreams_work_dir)
    tools = _build_tools_for_mode(Mode.ONESHOT)
    budget = RunBudget(max_iterations=5, max_wall_seconds=120,
                      max_tokens=20_000, consecutive_fail_limit=2)
    protocol_zero.install_signal_handlers()

    _print(f"[cyan]◊ driving dream {dream_id} · Ctrl-C to stop[/cyan]")
    while True:
        result = advance_dream(
            dream_id=dream_id, tools=tools, store=store,
            budget=budget, mode=Mode.ONESHOT,
        )
        if result.step_outcome in ("dream_paused", "dream_exhausted",
                                    "dream_completed", "dream_halted"):
            _print(f"[green]◊ {result.step_outcome}[/green] · "
                   f"{result.cycles_completed} cycles · "
                   f"{result.files_written_total} files · {result.reason}")
            return
        if result.step_outcome == "locked":
            time.sleep(5)
            continue
        # Brief cooldown so a fast loop on poison errors doesn't cook the CPU.
        if result.step_outcome in ("poison", "budget"):
            time.sleep(2)
        if protocol_zero.is_armed():
            _print("[red]◊ HALT armed · stopping[/red]")
            return


# ─── projects subcommand ────────────────────────────────────────────────────


projects_app = typer.Typer(help="◊ named project tracking + change detection (v0.2.12)")
app.add_typer(projects_app, name="projects")


@projects_app.command("scan")
def projects_scan_cmd(
    name: str = typer.Argument(..., help="Project name (alphanum / -_.)"),
    root: Path = typer.Argument(..., help="Directory to scan"),
    exclude: list[str] = typer.Option(
        [], "--exclude",
        help="Extra glob patterns to exclude (added to defaults). Repeatable.",
    ),
    follow_symlinks: bool = typer.Option(False, "--follow-symlinks"),
    max_files: int = typer.Option(0, "--max-files",
                                  help="Cap (0=unbounded)."),
) -> None:
    """Scan a directory and save its snapshot under <name>.

    Idempotent on the file content: re-scanning an unchanged tree replaces
    the snapshot with byte-identical data. Use ``sov projects update``
    afterwards to compute diffs against the saved snapshot.

    v0.2.12+
    """
    _preflight_initialized()
    from .projects import (
        DEFAULT_EXCLUDES, ProjectError, ProjectSnapshot, ProjectStore,
        scan_directory,
    )
    store = ProjectStore(SETTINGS.paths.projects_dir)

    root_resolved = root.expanduser().resolve()
    if not root_resolved.is_dir():
        _die(ExitCode.USAGE, f"not a directory: {root_resolved}")

    excludes = list(DEFAULT_EXCLUDES) + list(exclude)
    try:
        files = scan_directory(
            root_resolved, excludes=excludes,
            follow_symlinks=follow_symlinks, max_files=max_files,
        )
    except ProjectError as e:
        _die(ExitCode.ERROR, str(e))

    snap = ProjectSnapshot(
        name=name, root=str(root_resolved),
        excludes=excludes, files=files,
    )
    store.save(snap)

    if STATE.json_out:
        _emit_json({"ok": True, "name": name,
                    "file_count": snap.file_count,
                    "total_bytes": snap.total_bytes,
                    "root": snap.root})
    else:
        _print(Panel(
            f"name: [cyan]{name}[/cyan]\n"
            f"root: {snap.root}\n"
            f"files: {snap.file_count}\n"
            f"bytes: {snap.total_bytes:,}\n"
            f"excludes: {len(excludes)} patterns",
            title="◊ project scanned", border_style="green",
        ))


@projects_app.command("list")
def projects_list_cmd() -> None:
    """List tracked projects."""
    _preflight_initialized()
    from .projects import ProjectStore
    store = ProjectStore(SETTINGS.paths.projects_dir)
    names = store.list_names()

    if STATE.json_out:
        out = []
        for n in names:
            try:
                s = store.get(n)
                out.append({"name": n, "root": s.root,
                            "file_count": s.file_count,
                            "updated_at": s.updated_at})
            except Exception:  # noqa: BLE001
                out.append({"name": n, "error": "corrupt"})
        _emit_json({"projects": out})
        return

    if not names:
        _print("[dim](no tracked projects — `sov projects scan <name> <root>`)[/dim]")
        return

    table = Table(title="◊ projects", show_header=True, header_style="bold cyan")
    table.add_column("name", style="cyan")
    table.add_column("files", justify="right")
    table.add_column("updated_at")
    table.add_column("root")
    for n in names:
        try:
            s = store.get(n)
            table.add_row(n, str(s.file_count), s.updated_at, s.root)
        except Exception:  # noqa: BLE001
            table.add_row(n, "?", "?", "(corrupt)")
    _print(table)


@projects_app.command("show")
def projects_show_cmd(name: str = typer.Argument(...)) -> None:
    """Show snapshot summary for one project."""
    _preflight_initialized()
    from .projects import ProjectNotFound, ProjectStore
    store = ProjectStore(SETTINGS.paths.projects_dir)
    try:
        s = store.get(name)
    except ProjectNotFound:
        _die(ExitCode.USAGE, f"project not found: {name}")

    if STATE.json_out:
        _emit_json({"name": s.name, "root": s.root,
                    "file_count": s.file_count, "total_bytes": s.total_bytes,
                    "created_at": s.created_at, "updated_at": s.updated_at,
                    "excludes": s.excludes,
                    "first_files": [f.path for f in s.files[:50]]})
        return

    _print(Panel(
        f"name: [cyan]{s.name}[/cyan]\n"
        f"root: {s.root}\n"
        f"files: {s.file_count}\n"
        f"bytes: {s.total_bytes:,}\n"
        f"created: {s.created_at}\n"
        f"updated: {s.updated_at}\n"
        f"excludes: {len(s.excludes)} patterns",
        title=f"◊ project {s.name}", border_style="cyan",
    ))


@projects_app.command("update")
def projects_update_cmd(
    name: str = typer.Argument(...),
    atomize: bool = typer.Option(
        True, "--atomize/--no-atomize",
        help="Write atoms to atoms.db for added/modified/removed files. (default: on)",
    ),
    keep_old: bool = typer.Option(
        False, "--keep-old",
        help="Don't overwrite the snapshot — just report the diff.",
    ),
) -> None:
    """Re-scan a tracked project and report what changed.

    By default, also writes one atom per changed file to atoms.db so the
    dream-runner / palace-mine can see the change. With ``--no-atomize``
    just the diff is reported. With ``--keep-old`` the snapshot stays at
    the prior scan (useful for dry-runs).

    v0.2.12+
    """
    _preflight_initialized()
    from .projects import (
        ProjectNotFound, ProjectSnapshot, ProjectStore,
        atomize_diff, diff_snapshots, scan_directory,
    )
    store = ProjectStore(SETTINGS.paths.projects_dir)
    try:
        old = store.get(name)
    except ProjectNotFound:
        _die(ExitCode.USAGE,
             f"project not found: {name}\n"
             f"  Hint: run `sov projects scan {name} <root>` first.")

    root = Path(old.root)
    if not root.is_dir():
        _die(ExitCode.ERROR,
             f"project root no longer a directory: {root}")

    new_files = scan_directory(
        root, excludes=list(old.excludes),
        follow_symlinks=False, max_files=0,
    )
    new = ProjectSnapshot(
        name=name, root=str(root),
        excludes=list(old.excludes), files=new_files,
        created_at=old.created_at,
    )
    diff = diff_snapshots(old, new)

    written = 0
    if atomize and not diff.is_empty:
        try:
            written = atomize_diff(name, diff, new)
        except Exception as e:  # noqa: BLE001
            _print(f"[yellow]warn[/yellow] atomize failed: {e}")
            written = 0

    if not keep_old:
        store.save(new)

    payload = {
        "name": name, "added": diff.added, "modified": diff.modified,
        "removed": diff.removed, "unchanged_count": diff.unchanged_count,
        "atoms_written": written, "kept_old": keep_old,
    }
    if STATE.json_out:
        _emit_json({"ok": True, **payload})
        return

    _print(Panel(
        f"[bold]{diff.summary()}[/bold]\n"
        f"atoms written: {written}\n"
        f"snapshot: {'preserved (--keep-old)' if keep_old else 'replaced'}",
        title=f"◊ project update · {name}",
        border_style="green" if not diff.is_empty else "dim",
    ))
    if diff.added or diff.modified or diff.removed:
        t = Table(title="changes", show_header=True)
        t.add_column("change", style="cyan")
        t.add_column("path", overflow="fold")
        for p in diff.added[:50]:
            t.add_row("added", p)
        for p in diff.modified[:50]:
            t.add_row("modified", p)
        for p in diff.removed[:50]:
            t.add_row("removed", p)
        _print(t)


@projects_app.command("delete")
def projects_delete_cmd(
    name: str = typer.Argument(...),
    yes: bool = typer.Option(False, "--yes", "-y"),
) -> None:
    """Remove a project's snapshot. Files on disk untouched."""
    _preflight_initialized()
    from .projects import ProjectStore
    store = ProjectStore(SETTINGS.paths.projects_dir)
    if not store.exists(name):
        _die(ExitCode.USAGE, f"project not found: {name}")
    if not yes and not STATE.json_out:
        if not typer.confirm(f"Delete project snapshot '{name}'?"):
            raise typer.Abort()
    store.delete(name)
    if STATE.json_out:
        _emit_json({"ok": True, "deleted": name})
    else:
        _print(f"[green]deleted[/green] · project {name}")


# ─── plain-English `sov do` ─────────────────────────────────────────────────


@app.command(name="do")
def do_cmd(
    directive: str = typer.Argument(..., help="Plain-English directive"),
    yes: bool = typer.Option(
        False, "--yes", "-y",
        help="Skip the confirm prompt before dispatch.",
    ),
) -> None:
    """Plain-English entry point. Tell the agent what to do in a sentence.

    Examples:
        sov do "Build trillion-dollar software, max 2000 files"
        sov do "Pause my dream"
        sov do "I updated genesis-seeds"
        sov do "Inventory ~/AA-Erebo/Genesis-Seeds for markdown files"
        sov do "Show me what's happening"

    The parser is deterministic and keyword-based — see directives.py.
    Missing arguments turn into interactive prompts.

    v0.2.12+
    """
    from .directives import (
        Directive, parse_directive, render_directive_summary,
    )
    d: Directive = parse_directive(directive)

    if d.intent == "unknown":
        _die(ExitCode.USAGE,
             d.confidence_message,
             hint="Try: 'build trillion dollar software', 'pause my dream', "
                  "'inventory ~/AA-Erebo for markdown', 'show status'")

    # ── Interactive: ask any missing-data questions ─────────────────────
    if d.questions:
        _print(f"[cyan]◊ understanding directive:[/cyan] {render_directive_summary(d)}")
        if yes:
            # Non-interactive: take defaults; abort if any required Q lacks one.
            for q in d.questions:
                if q.default is not None:
                    d.kwargs[q.field] = q.default
                elif q.required:
                    _die(ExitCode.USAGE,
                         f"directive missing required field: {q.field} "
                         f"(no default; cannot continue with --yes)",
                         hint=q.prompt)
        else:
            _print(f"[dim]I need a few details — answer 'cancel' to abort.[/dim]\n")
            for q in d.questions:
                answered = _ask_question(q)
                if answered is None:
                    _print("[yellow]aborted[/yellow]")
                    raise typer.Exit(ExitCode.USAGE)
                d.kwargs[q.field] = answered
            _print()

    # ── Confirm before dispatch ─────────────────────────────────────────
    summary = render_directive_summary(d)
    if not yes and not STATE.json_out:
        _print(f"[bold]ready:[/bold] {summary}")
        if not typer.confirm("proceed?"):
            _print("[yellow]aborted[/yellow]")
            raise typer.Abort()

    _dispatch_directive(d)


def _ask_question(q) -> str | None:
    """Prompt for one piece of missing data. Returns None if operator cancels.

    Suggestions are shown inline. If a default is provided, an empty answer
    accepts it.
    """
    suggest_str = ""
    if q.suggestions:
        suggest_str = f" [dim]examples:[/dim] {', '.join(q.suggestions)}"
    default_str = f" [dim]\\[default: {q.default}][/dim]" if q.default else ""
    while True:
        _print(f"  {q.prompt}{default_str}{suggest_str}")
        try:
            answer = input("  > ").strip()
        except (EOFError, KeyboardInterrupt):
            return None
        if answer.lower() in ("cancel", "q", "quit", "abort"):
            return None
        if not answer:
            if q.default is not None:
                return q.default
            if not q.required:
                return ""
            _print("  [yellow](required — please answer or type 'cancel')[/yellow]")
            continue
        return answer


def _dispatch_directive(d) -> None:
    """Take a fully-resolved directive and run it via existing CLI entry points.

    Each branch translates the directive's kwargs into the right call. We
    re-enter the Typer commands by calling them as functions. This keeps a
    single source of truth for the command logic — `sov do` is a UX layer,
    not a parallel dispatcher.
    """
    intent = d.intent
    kw = d.kwargs

    if intent == "dream":
        max_files = int(kw.get("max_files", 2000) or 0)
        max_cycles = int(kw.get("max_cycles", 0) or 0)
        return dream_start(
            goal=kw.get("goal", "trillion-dollar dream"),
            max_files=max_files, max_cycles=max_cycles,
            max_seconds=0, project=[], drive=False,
        )
    if intent == "dream_control":
        action = kw.get("action", "")
        dream_id = kw.get("dream_id", "")
        if dream_id == "latest":
            from .dream import DreamStore
            store = DreamStore(SETTINGS.paths.dream_sessions_dir,
                               SETTINGS.paths.dreams_work_dir)
            actives = store.list_all(status="active")
            if not actives:
                _die(ExitCode.USAGE,
                     "no active dreams found; specify a dream-id explicitly")
            dream_id = actives[-1].dream_id
        if action == "pause":
            return dream_pause_cmd(dream_id=dream_id)
        if action == "resume":
            return dream_resume_cmd(dream_id=dream_id, drive=False)
        if action == "stop":
            return dream_stop_cmd(dream_id=dream_id, yes=True)
    if intent == "continue_cont":
        return resume_cmd(task_id=kw["task_id"], drive=False)
    if intent == "pause_cont":
        return pause_cmd(task_id=kw["task_id"], reason="via sov do")
    if intent == "inventory":
        return plan_cmd(
            planner="inventory",
            root=Path(kw["root"]),
            output=Path(kw["output"]),
            pattern=list(kw.get("patterns") or []),
            exclude=[], include=[], include_no_ext=False,
            max_files=0, no_recursive=False,
            tag=None, max_extract_chars=40_000, max_file_size=0,
            room_id=None, room_name=None, atom_type=None,
            task_id=None, dry_run=False,
        )
    if intent == "projects":
        action = kw.get("action", "list")
        if action == "list":
            return projects_list_cmd()
        if action == "scan":
            return projects_scan_cmd(
                name=kw["name"], root=Path(kw["root"]),
                exclude=[], follow_symlinks=False, max_files=0,
            )
        if action == "update":
            return projects_update_cmd(
                name=kw["name"], atomize=True, keep_old=False,
            )
    if intent == "status":
        # Render a one-screen summary similar to `sov-status` shell alias,
        # but in-process so it works from `sov do "status"`.
        _render_status()
        return
    if intent == "list":
        what = kw.get("what", "all")
        if what in ("dreams", "all"):
            dream_list_cmd(status_filter=None)
        if what in ("continuations", "all"):
            cont_list(status=None)
        if what in ("projects", "all"):
            projects_list_cmd()
        if what in ("planners", "all"):
            plan_cmd(
                planner=None, root=None, output=None, pattern=[],
                exclude=[], include=[], include_no_ext=False,
                max_files=0, no_recursive=False, tag=None,
                max_extract_chars=40_000, max_file_size=0,
                room_id=None, room_name=None, atom_type=None,
                task_id=None, dry_run=False,
            )
        return
    if intent == "help":
        _print(Panel(
            "[bold]sov do[/bold] — plain-English entry\n\n"
            "Try things like:\n"
            "  • 'Build trillion-dollar software, max 2000 files'\n"
            "  • 'Build trillion-dollar software forever'\n"
            "  • 'Pause my dream'\n"
            "  • 'Resume dream-01J...'\n"
            "  • 'I updated genesis-seeds'\n"
            "  • 'Scan ~/AA-Erebo/Genesis-Seeds for markdown'\n"
            "  • 'Show status'\n"
            "  • 'List dreams'\n",
            title="◊ help · sov do", border_style="cyan",
        ))
        return

    _die(ExitCode.USAGE, f"unhandled intent: {intent}")


def _render_status() -> None:
    """One-screen status summary."""
    from .continuation import ContinuationStore
    from .dream import DreamStore
    from .projects import ProjectStore
    cstore = ContinuationStore(SETTINGS.paths.continuations_dir)
    dstore = DreamStore(SETTINGS.paths.dream_sessions_dir,
                       SETTINGS.paths.dreams_work_dir)
    pstore = ProjectStore(SETTINGS.paths.projects_dir)

    conts = cstore.list_all()
    dreams = dstore.list_all()
    projects = pstore.list_names()

    active_conts = [c for c in conts if c.status in ("planned", "in_progress")]
    paused_conts = [c for c in conts if c.status == "paused"]
    active_dreams = [d for d in dreams if d.status == "active"]
    paused_dreams = [d for d in dreams if d.status == "paused"]

    if STATE.json_out:
        _emit_json({
            "continuations": {
                "total": len(conts),
                "active": len(active_conts),
                "paused": len(paused_conts),
            },
            "dreams": {
                "total": len(dreams),
                "active": len(active_dreams),
                "paused": len(paused_dreams),
            },
            "projects": {"total": len(projects), "names": projects},
        })
        return

    _print(Panel(
        f"continuations: total={len(conts)} active={len(active_conts)} paused={len(paused_conts)}\n"
        f"dreams: total={len(dreams)} active={len(active_dreams)} paused={len(paused_dreams)}\n"
        f"projects: {len(projects)}",
        title="◊ status", border_style="cyan",
    ))
    if active_dreams:
        _print(f"[cyan]active dreams:[/cyan]")
        for d in active_dreams:
            _print(f"  {d.dream_id} · {d.progress_summary()}")
    if active_conts:
        _print(f"[cyan]active continuations:[/cyan]")
        for c in active_conts[:5]:
            done, total = c.progress
            _print(f"  {c.task_id} · {done}/{total} · {c.planner}")


# ─── sov ask — natural-language entry point (v0.2.30.0) ────────────────────


@app.command(name="ask")
def ask_cmd(
    message: list[str] = typer.Argument(
        ...,
        help="What you want to say to Aria. Plain English.",
    ),
    json_only: bool = typer.Option(
        False, "--json-only",
        help="Suppress the rendered turn and print only the JSON Intent.",
    ),
    no_route: bool = typer.Option(
        False, "--no-route",
        help="Interpret only; do not route the intent. Useful for debugging.",
    ),
    no_llm: bool = typer.Option(
        False, "--no-llm",
        help="Force the offline minimal-fallback interpreter "
             "(no Ollama call). Honest when the model is unavailable.",
    ),
    timeout: float = typer.Option(
        30.0, "--timeout",
        help="LLM call timeout in seconds. Default 30.",
    ),
) -> None:
    """Talk to Aria. She reads what you say, decides what to do, and tells you.

    This is the *natural-language* doorway — the LLM-backed sibling of ``sov do``
    (which is deterministic keyword parsing). ``sov ask`` routes your message
    through ``interpret()`` → ``Router.route()`` and shows you:

    \b
      • her one-sentence *understanding* of what you meant
      • the channels she chose to save the message to (if any)
      • the commands she proposes (if any — Tier ≤ 2 only)
      • her own response, in her voice
      • her *reasoning* and any *uncertain_about* note

    Examples:

    \b
        sov ask "my back is killing me today"
        sov ask "what do I have on rollbacks?"
        sov ask "pause my dream"
        sov ask "remind me what we decided about the seal cadence"

    Honest degradation:

    \b
      • If Ollama is unreachable, she falls back to the minimal-honest path —
        the message is saved to ``context`` with a note that the interpreter
        was offline. She does not pretend to understand.
      • Tier-3 actions are *never* executed by ``sov ask``. If she proposes a
        Tier-3 command (financial writes, irreversible deletes), it is shown
        but not run — you must invoke it explicitly. The chat surface
        (``sov chat`` cockpit) is where Tier-3 confirmation lives.

    Provenance:

    \b
      The router writes channel content via the default channel writer
      (``<data_dir>/channels/*.log``) and the conversation-events trail
      (``<data_dir>/conversation-events.ndjson``). Both are append-only.
      ``--no-route`` skips that side effect entirely.

    v0.2.30.0+
    """
    text = " ".join(message).strip()
    if not text:
        _die(ExitCode.USAGE, "empty message", hint="sov ask 'what's the work?'")

    from .conversation import (
        Turn,
        converse,
        make_default_channel_writer,
        make_default_event_sink,
    )
    from .interpreter import interpret
    from .intents import (
        Ambiguous,
        Conversation,
        Intent,
        Recall,
        Slash,
        Work,
    )

    # Build an Ollama client if available (best-effort; the interpreter is
    # written to degrade honestly when it isn't).
    ollama_client = None
    if not no_llm:
        try:
            from .ollama_client import OllamaClient
            ollama_client = OllamaClient()
        except Exception as exc:  # noqa: BLE001
            logger.debug("ollama client unavailable: %r", exc)

    # ── --no-route: pure interpretation, no side effects ──────────────────
    if no_route:
        intent = asyncio.run(interpret(
            text,
            ollama_client=ollama_client,
            allow_llm=not no_llm,
            llm_timeout_seconds=timeout,
        ))
        payload = _intent_to_dict(intent)
        if STATE.json_out or json_only:
            _emit_json(payload)
            return
        _render_intent_card(payload, text)
        return

    # ── Full converse path ────────────────────────────────────────────────
    channel_writer = make_default_channel_writer()
    event_sink = make_default_event_sink()

    try:
        turn: Turn = asyncio.run(converse(
            text,
            ollama_client=ollama_client,
            channel_writer=channel_writer,
            event_sink=event_sink,
            surface="cli",
            allow_llm=not no_llm,
        ))
    except Exception as exc:  # noqa: BLE001
        logger.exception("converse failed")
        _die(ExitCode.GENERIC,
             f"conversation failed: {type(exc).__name__}: {exc}",
             hint="run `sov doctor` to verify your install")

    payload = _turn_to_dict(turn)
    if STATE.json_out or json_only:
        _emit_json(payload)
        return
    _render_turn_card(turn)


def _intent_to_dict(intent: Any) -> dict[str, Any]:
    """Best-effort JSON-friendly view of an Intent for ``sov ask --no-route``.

    Lives next to ``ask_cmd`` so the renderer can stay shape-stable as
    the Intent algebra in ``intents.py`` evolves.
    """
    base = {"kind": getattr(intent, "kind", "unknown")}
    for field_name in (
        "text", "save_to", "reply_voice", "reply_hint",
        "summary", "commands", "authority_tier",
        "project_hint", "rationale",
        "query", "scope",
        "verb", "arg",
        "question", "options", "timeout_seconds",
    ):
        if hasattr(intent, field_name):
            base[field_name] = getattr(intent, field_name)
    return base


def _turn_to_dict(turn: Any) -> dict[str, Any]:
    """JSON-friendly Turn for ``sov ask --json``."""
    return {
        "text": turn.text,
        "intent": _intent_to_dict(turn.intent),
        "result": {
            "kind": turn.result.kind,
            "messages": list(turn.result.messages),
            "has_pending": turn.has_pending,
        },
    }


def _render_intent_card(payload: dict[str, Any], text: str) -> None:
    """Pretty-print an interpretation result (no routing happened)."""
    kind = payload.get("kind", "unknown")
    _print(Panel(
        f"[dim]you said:[/dim] {text}",
        title=f"◊ aria interpreted · kind={kind}",
        border_style="cyan",
    ))
    for k, v in payload.items():
        if k in ("kind",) or not v:
            continue
        if isinstance(v, list):
            v = ", ".join(str(x) for x in v) if v else "(empty)"
        _print(f"  [cyan]{k}:[/cyan] {v}")


def _render_turn_card(turn: Any) -> None:
    """Render Aria's reply alongside the interpretation, in her voice."""
    intent = turn.intent
    kind = getattr(intent, "kind", "unknown")

    # Lead with her response (warmest signal to the operator)
    response_hint = getattr(intent, "reply_hint", "") or ""
    if response_hint:
        _print(Panel(response_hint, title="◊ aria", border_style="cyan"))

    # Show the interpretation
    _print(f"[dim]◊ kind={kind}[/dim]")
    summary = getattr(intent, "summary", "") or getattr(intent, "query", "")
    rationale = getattr(intent, "rationale", "") or getattr(intent, "reply_hint", "")
    save_to = getattr(intent, "save_to", []) or []
    commands = getattr(intent, "commands", []) or []
    tier = getattr(intent, "authority_tier", None)

    if summary:
        _print(f"  [cyan]understanding:[/cyan] {summary}")
    if save_to:
        _print(f"  [cyan]saved to:[/cyan] {', '.join(save_to)}")
    if commands:
        tier_str = f" (tier {tier})" if tier is not None else ""
        _print(f"  [cyan]proposed commands{tier_str}:[/cyan]")
        for cmd in commands:
            _print(f"    $ {cmd}")
    if rationale and rationale != response_hint:
        _print(f"  [dim]reasoning:[/dim] {rationale}")

    # Surface routing messages (one per line, dim)
    for msg in turn.messages:
        _print(f"  [dim]· {msg}[/dim]")

    if turn.has_pending:
        _print("  [yellow]⚠ this turn has a pending action — "
               "use `sov chat` to confirm Tier-3 work[/yellow]")


# ─── continuation aliases (light-touch) ─────────────────────────────────────


@cont_app.command("alias")
def cont_alias_cmd(
    task_id: str = typer.Argument(..., help="Existing continuation ID"),
    alias: str = typer.Argument(..., help="Short friendly name (alphanum/-_.)"),
) -> None:
    """Attach a friendly name to a continuation. Look it up by alias later.

    Aliases are stored in `<config_dir>/continuation-aliases.yaml`. Resolved
    everywhere a task_id is accepted via `sov do` (continue/pause/resume).

    v0.2.12+
    """
    _preflight_initialized()
    from .continuation import ContinuationNotFound, ContinuationStore
    store = ContinuationStore(SETTINGS.paths.continuations_dir)
    try:
        store.get(task_id)
    except ContinuationNotFound:
        _die(ExitCode.USAGE, f"continuation not found: {task_id}")

    safe = all(c.isalnum() or c in "-_." for c in alias) and alias
    if not safe:
        _die(ExitCode.USAGE,
             f"alias must be alphanum / -_.; got {alias!r}")

    aliases_file = SETTINGS.paths.config_dir / "continuation-aliases.yaml"
    data: dict = {}
    if aliases_file.exists():
        try:
            data = yaml.safe_load(aliases_file.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            data = {}
    data[alias] = task_id
    aliases_file.write_text(yaml.safe_dump(data, sort_keys=True), encoding="utf-8")

    if STATE.json_out:
        _emit_json({"ok": True, "alias": alias, "task_id": task_id})
    else:
        _print(f"[green]alias[/green] · {alias} → {task_id}")


# ════════════════════════════════════════════════════════════════════════════
# v0.2.13 — top-level commands and new sub-apps
# ════════════════════════════════════════════════════════════════════════════


@app.command()
def status() -> None:
    """Show a one-glance summary of dreams, continuations, projects, palace.

    Promoted from `sov do status` to a real top-level command in v0.2.13
    because it's the most-used read action.
    """
    from .continuation import ContinuationStore
    from .dream import DreamStore
    from .projects import ProjectStore

    paths = SETTINGS.paths
    cont_store = ContinuationStore(paths.continuations_dir)
    dream_store = DreamStore(
        root=paths.data_dir / "dreams",
        work_root=paths.data_dir / "dream-sessions",
    )
    proj_store = ProjectStore(paths.data_dir / "projects")

    try:
        conts = cont_store.list_all()
    except Exception:  # noqa: BLE001
        conts = []
    try:
        dreams = dream_store.list_all()
    except Exception:  # noqa: BLE001
        dreams = []
    try:
        projects = proj_store.list_all()
    except Exception:  # noqa: BLE001
        projects = []

    cont_in_progress = sum(1 for c in conts if c.status == "in_progress")
    cont_paused = sum(1 for c in conts if c.status == "paused")
    cont_done = sum(1 for c in conts if c.status == "done")
    dream_active = sum(1 for d in dreams if d.status == "active")
    dream_paused = sum(1 for d in dreams if d.status == "paused")

    if STATE.json_out:
        _emit_json({
            "ok": True,
            "continuations": {
                "total": len(conts), "in_progress": cont_in_progress,
                "paused": cont_paused, "done": cont_done,
            },
            "dreams": {
                "total": len(dreams), "active": dream_active,
                "paused": dream_paused,
            },
            "projects": {"total": len(projects)},
        })
        return

    t = Table(show_header=False, box=None, padding=(0, 1))
    t.add_column(style="dim")
    t.add_column()
    t.add_row("continuations",
              f"{len(conts)} total · {cont_in_progress} in-progress · "
              f"{cont_paused} paused · {cont_done} done")
    t.add_row("dreams",
              f"{len(dreams)} total · {dream_active} active · "
              f"{dream_paused} paused")
    t.add_row("projects", f"{len(projects)} tracked")
    _print(Panel(t, title="◊ sovereign-agent status", border_style="cyan"))


# ─── Health sub-app ─────────────────────────────────────────────────────────


health_app = typer.Typer(
    help="◊ anti-zombie / anti-ghost detection (v0.2.13)",
)
app.add_typer(health_app, name="health")


@health_app.command("check")
def health_check_cmd(
    zombie_hours: int = typer.Option(
        6, "--zombie-hours",
        help="Stalled in_progress threshold (hours)",
    ),
    idle_window: int = typer.Option(
        3, "--idle-window",
        help="Number of recent cycles checked for idle detection",
    ),
) -> None:
    """Scan for zombies, ghosts, stale locks, and idle dream cycles."""
    from .continuation import ContinuationStore
    from .dream import DreamStore
    from .health import run_full_scan

    paths = SETTINGS.paths
    cont_store = ContinuationStore(paths.continuations_dir)
    dream_store = DreamStore(
        root=paths.data_dir / "dreams",
        work_root=paths.data_dir / "dream-sessions",
    )

    report = run_full_scan(
        cont_store, dream_store,
        zombie_threshold=zombie_hours * 3600,
        idle_window=idle_window,
    )

    if STATE.json_out:
        _emit_json({
            "ok": report.ok,
            "summary": report.summary_line(),
            "findings": [
                {
                    "edge_case_id": f.edge_case_id,
                    "severity": f.severity,
                    "target": f.target,
                    "target_kind": f.target_kind,
                    "summary": f.summary,
                }
                for f in report.findings
            ],
        })
        return

    if not report.findings:
        _print("[green]✓ no health issues detected[/green]")
        return

    t = Table(title="◊ health findings", box=None, show_lines=False)
    t.add_column("ID", style="cyan", no_wrap=True)
    t.add_column("Severity", style="yellow")
    t.add_column("Target", style="magenta")
    t.add_column("Summary")
    for f in report.findings:
        t.add_row(f.edge_case_id, f.severity, f.target, f.summary)
    _print(t)
    _print(f"\n[dim]{report.summary_line()}[/dim]")
    _print("[dim]Use `sov health repair --dry-run` to see proposed "
           "fixes.[/dim]")


@health_app.command("repair")
def health_repair_cmd(
    dry_run: bool = typer.Option(
        True, "--dry-run/--apply",
        help="Default: dry-run. Pass --apply to actually fix.",
    ),
) -> None:
    """Plan (and optionally apply) repairs for health findings."""
    from .continuation import ContinuationStore
    from .dream import DreamStore
    from .health import apply_repairs, plan_repairs, run_full_scan

    paths = SETTINGS.paths
    cont_store = ContinuationStore(paths.continuations_dir)
    dream_store = DreamStore(
        root=paths.data_dir / "dreams",
        work_root=paths.data_dir / "dream-sessions",
    )

    report = run_full_scan(cont_store, dream_store)
    actions = plan_repairs(report)

    if not actions:
        _print("[green]nothing to repair[/green]")
        return

    if STATE.json_out:
        _emit_json({
            "ok": True, "dry_run": dry_run,
            "actions": [
                {"kind": a.kind, "target": a.target,
                 "description": a.description}
                for a in actions
            ],
        })
        return

    t = Table(title=f"◊ repairs ({'dry-run' if dry_run else 'will apply'})",
              box=None)
    t.add_column("Kind", style="cyan")
    t.add_column("Target", style="magenta")
    t.add_column("Description")
    for a in actions:
        t.add_row(a.kind, a.target, a.description)
    _print(t)

    if dry_run:
        _print("\n[dim]Re-run with --apply to execute.[/dim]")
        return

    if not typer.confirm(f"Apply {len(actions)} repair(s)?"):
        _print("[yellow]aborted[/yellow]")
        return

    applied = apply_repairs(
        actions, cont_store=cont_store, dream_store=dream_store, dry_run=False,
    )
    success = sum(1 for a in applied if a.applied)
    failed = sum(1 for a in applied if not a.applied)
    _print(f"[green]applied {success}[/green] · [red]failed {failed}[/red]")
    for a in applied:
        if a.error:
            _print(f"  [red]✗[/red] {a.target}: {a.error}")


# ─── Edge-cases sub-app ─────────────────────────────────────────────────────


edge_cases_app = typer.Typer(
    help="◊ edge-case registry (v0.2.13)",
)
app.add_typer(edge_cases_app, name="edge-cases")


@edge_cases_app.command("list")
def edge_cases_list_cmd(
    subsystem: str = typer.Option(
        "", "--subsystem", "-s",
        help="Filter by id prefix (e.g. EC-DREAM, EC-VAL)",
    ),
    severity: str = typer.Option(
        "", "--severity",
        help="Filter by severity: info | warn | error | critical",
    ),
) -> None:
    """List all registered edge cases with their ids, locations, severities."""
    from .edge_cases import by_severity, by_subsystem, list_all

    if subsystem:
        entries = by_subsystem(subsystem)
    elif severity:
        entries = by_severity(severity)  # type: ignore[arg-type]
    else:
        entries = list_all()

    if STATE.json_out:
        _emit_json({
            "ok": True, "count": len(entries),
            "entries": [
                {"id": e.id, "title": e.title, "location": e.location,
                 "severity": e.severity, "introduced_in": e.introduced_in}
                for e in entries
            ],
        })
        return

    t = Table(title="◊ registered edge cases", box=None, show_lines=False)
    t.add_column("ID", style="cyan", no_wrap=True)
    t.add_column("Title")
    t.add_column("Severity", style="yellow", no_wrap=True)
    t.add_column("Where", style="dim", no_wrap=True)
    t.add_column("v", style="dim")
    for e in entries:
        t.add_row(e.id, e.title, e.severity, e.location, e.introduced_in)
    _print(t)


@edge_cases_app.command("show")
def edge_cases_show_cmd(
    edge_case_id: str = typer.Argument(..., help="e.g. EC-DREAM-001"),
) -> None:
    """Show full detail for one edge case."""
    from .edge_cases import get
    try:
        ec = get(edge_case_id.upper())
    except KeyError:
        _print(f"[red]unknown edge case: {edge_case_id}[/red]")
        _print("[dim]Use `sov edge-cases list` to see all.[/dim]")
        raise typer.Exit(code=1)

    if STATE.json_out:
        _emit_json({
            "ok": True,
            "id": ec.id, "title": ec.title, "location": ec.location,
            "description": ec.description, "fires_when": ec.fires_when,
            "recovery": ec.recovery, "severity": ec.severity,
            "introduced_in": ec.introduced_in,
        })
        return

    t = Table(show_header=False, box=None, padding=(0, 1))
    t.add_column(style="dim", no_wrap=True)
    t.add_column()
    t.add_row("id", ec.id)
    t.add_row("title", ec.title)
    t.add_row("location", ec.location)
    t.add_row("severity", f"[yellow]{ec.severity}[/yellow]")
    t.add_row("introduced", ec.introduced_in or "-")
    t.add_row("description", ec.description)
    t.add_row("fires when", ec.fires_when)
    t.add_row("recovery", ec.recovery)
    _print(Panel(t, title=f"◊ {ec.id}", border_style="cyan"))


# ─── Personas sub-app ───────────────────────────────────────────────────────


personas_app = typer.Typer(
    help="◊ persona registry (v0.2.13)",
)
app.add_typer(personas_app, name="personas")


@personas_app.command("list")
def personas_list_cmd() -> None:
    """List registered personas."""
    from .personas import REGISTRY

    if STATE.json_out:
        _emit_json({
            "ok": True,
            "personas": [
                {"name": p.name, "voice": p.voice,
                 "principles_count": len(p.principles)}
                for p in REGISTRY.values()
            ],
        })
        return

    t = Table(title="◊ registered personas", box=None)
    t.add_column("Name", style="cyan", no_wrap=True)
    t.add_column("Principles", style="dim", no_wrap=True)
    t.add_column("Voice")
    for p in REGISTRY.values():
        t.add_row(p.name, str(len(p.principles)), p.voice[:60])
    _print(t)


@personas_app.command("show")
def personas_show_cmd(
    name: str = typer.Argument(..., help="e.g. master-architect"),
) -> None:
    """Show the full rendered persona."""
    from .personas import get_persona
    try:
        p = get_persona(name)
    except KeyError:
        _print(f"[red]unknown persona: {name}[/red]")
        _print("[dim]Use `sov personas list` to see all.[/dim]")
        raise typer.Exit(code=1)

    if STATE.json_out:
        _emit_json({
            "ok": True, "name": p.name, "role": p.role,
            "principles": list(p.principles),
            "anti_patterns": list(p.anti_patterns),
            "voice": p.voice, "signature": p.signature,
            "rendered": p.render(),
        })
        return

    _print(Panel(p.render(), title=f"◊ {p.name}", border_style="cyan"))


# ─── Dream sub-app: tail + gc + branch ─────────────────────────────────────


@dream_app.command("tail")
def dream_tail_cmd(
    dream_id: str = typer.Argument(..., help="dream id to tail"),
    lines: int = typer.Option(
        50, "--lines", "-n",
        help="Lines per file to show",
    ),
) -> None:
    """Stream the latest cycle's idea.md / architecture.md / README.md."""
    from .dream import DreamStore

    paths = SETTINGS.paths
    store = DreamStore(
        root=paths.data_dir / "dreams",
        work_root=paths.data_dir / "dream-sessions",
    )
    try:
        d = store.get(dream_id)
    except Exception as e:  # noqa: BLE001
        _print(f"[red]{e}[/red]")
        raise typer.Exit(code=1)

    if not d.cycles:
        _print(f"[dim]dream {dream_id}: no cycles yet[/dim]")
        return

    last = d.cycles[-1]
    if not last.cycle_dir:
        _print(f"[dim]cycle {last.cycle_number}: no cycle_dir on record[/dim]")
        return

    cycle_dir = Path(last.cycle_dir)
    for name in ("idea.md", "architecture.md", "README.md"):
        p = cycle_dir / name
        if not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        body = "\n".join(text.splitlines()[:lines])
        _print(Panel(body, title=f"◊ cycle-{last.cycle_number:03d}/{name}",
                     border_style="cyan"))


@dream_app.command("gc")
def dream_gc_cmd(
    older_than_days: int = typer.Option(
        30, "--older-than",
        help="Delete work_dirs of terminal dreams older than N days",
    ),
    dry_run: bool = typer.Option(
        True, "--dry-run/--apply",
        help="Default: dry-run.",
    ),
) -> None:
    """Garbage-collect work_dirs of completed/exhausted/halted dreams.

    Only touches the WORK_DIR (cycle source files). The dream YAML
    record stays — atoms.db references survive too. This is purely a
    disk reclaim for source trees you're done iterating on.
    """
    from datetime import datetime, timezone, timedelta
    from .dream import DreamStore

    paths = SETTINGS.paths
    store = DreamStore(
        root=paths.data_dir / "dreams",
        work_root=paths.data_dir / "dream-sessions",
    )
    try:
        dreams = store.list_all()
    except Exception:  # noqa: BLE001
        dreams = []

    cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
    eligible = []
    for d in dreams:
        if d.status not in ("completed", "exhausted", "halted"):
            continue
        try:
            updated = datetime.strptime(
                d.updated_at, "%Y-%m-%dT%H:%M:%S.%fZ",
            ).replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue
        if updated > cutoff:
            continue
        work_dir = Path(d.work_dir) if d.work_dir else None
        if work_dir and work_dir.exists():
            eligible.append((d, work_dir))

    if not eligible:
        _print(f"[green]nothing to GC[/green] "
               f"(no terminal dreams older than {older_than_days}d "
               f"with extant work_dirs)")
        return

    if STATE.json_out:
        _emit_json({
            "ok": True, "dry_run": dry_run,
            "eligible": [
                {"dream_id": d.dream_id, "status": d.status,
                 "work_dir": str(wd)}
                for d, wd in eligible
            ],
        })
        return

    t = Table(title=f"◊ gc candidates ({'dry-run' if dry_run else 'will delete'})",
              box=None)
    t.add_column("Dream", style="cyan")
    t.add_column("Status", style="yellow")
    t.add_column("Work dir", style="dim")
    for d, wd in eligible:
        t.add_row(d.dream_id, d.status, str(wd))
    _print(t)

    if dry_run:
        _print("\n[dim]Re-run with --apply to delete.[/dim]")
        return

    if not typer.confirm(f"Delete {len(eligible)} work_dir(s)?"):
        _print("[yellow]aborted[/yellow]")
        return

    import shutil
    deleted = 0
    for _, wd in eligible:
        try:
            shutil.rmtree(wd)
            deleted += 1
        except OSError as e:
            _print(f"  [red]✗[/red] {wd}: {e}")
    _print(f"[green]deleted {deleted}[/green]")



# ════════════════════════════════════════════════════════════════════════════
# v0.2.14 — Aria, channels, financial, horizon, appendix
# ════════════════════════════════════════════════════════════════════════════


@app.command()
def aria() -> None:
    """Show Aria-Sovereign-V1's current state — kernel, mood, inventory."""
    from .aria import load_state
    from .db import open_atoms_db
    # Make sure all channels are registered
    from . import mem_channels  # noqa: F401

    conn = open_atoms_db()
    try:
        state = load_state(conn)
    finally:
        conn.close()

    if STATE.json_out:
        _emit_json({
            "ok": True,
            "designation": state.designation,
            "tagline": state.tagline,
            "mood": state.current_mood,
            "focus": state.current_focus,
            "self_narrative": state.self_narrative,
            "active_goals": state.active_goals,
            "open_intentions": state.open_intentions,
            "tracked_projects": state.tracked_projects,
        })
        return

    _print(state.render_card())


# ─── Channels sub-app ──────────────────────────────────────────────────────


channels_app = typer.Typer(
    help="◊ modular memory channels (v0.2.14)",
)
app.add_typer(channels_app, name="channels")


@channels_app.command("list")
def channels_list_cmd() -> None:
    """List all registered memory channels."""
    from . import mem_channels  # noqa: F401
    from .channels import list_channels
    specs = list_channels()

    if STATE.json_out:
        _emit_json({
            "ok": True, "count": len(specs),
            "channels": [
                {"name": s.name, "tier": s.authority_tier,
                 "description": s.description, "voice": s.voice}
                for s in specs
            ],
        })
        return

    t = Table(title="◊ memory channels", box=None)
    t.add_column("Channel", style="cyan", no_wrap=True)
    t.add_column("Tier", style="yellow", no_wrap=True)
    t.add_column("Voice", style="dim")
    t.add_column("Purpose")
    for s in specs:
        t.add_row(s.name, str(s.authority_tier), s.voice[:40],
                  s.description[:60])
    _print(t)


@channels_app.command("show")
def channels_show_cmd(
    name: str = typer.Argument(..., help="channel name"),
) -> None:
    """Show one channel's spec and recent atoms."""
    from . import mem_channels  # noqa: F401
    from .channels import get_channel, list_channels
    from .db import open_atoms_db

    spec = next((s for s in list_channels() if s.name == name), None)
    if spec is None:
        _print(f"[red]unknown channel: {name}[/red]")
        raise typer.Exit(code=1)

    conn = open_atoms_db()
    try:
        ch = get_channel(name, conn)
        recent = ch.list_atoms(limit=10)
    finally:
        conn.close()

    if STATE.json_out:
        _emit_json({
            "ok": True, "spec": {
                "name": spec.name, "tier": spec.authority_tier,
                "description": spec.description, "voice": spec.voice,
            },
            "recent_atoms": recent,
        })
        return

    t = Table(show_header=False, box=None, padding=(0, 1))
    t.add_column(style="dim")
    t.add_column()
    t.add_row("name", spec.name)
    t.add_row("tier", str(spec.authority_tier))
    t.add_row("description", spec.description)
    t.add_row("voice", spec.voice)
    t.add_row("idempotency", "required" if spec.requires_idempotency else "optional")
    _print(Panel(t, title=f"◊ channel: {spec.name}", border_style="cyan"))

    if recent:
        rt = Table(title=f"recent atoms ({len(recent)})", box=None)
        rt.add_column("ID", style="dim", no_wrap=True)
        rt.add_column("Confidence", style="yellow", no_wrap=True)
        rt.add_column("Summary")
        for a in recent:
            rt.add_row(a["atom_id"][:24] + "…", f"{a['confidence']:.2f}",
                       a["summary"][:80])
        _print(rt)


# ─── Financial sub-app ─────────────────────────────────────────────────────


financial_app = typer.Typer(
    help="◊ per-project investment & earnings ledger (v0.2.14)",
)
app.add_typer(financial_app, name="financial")


def _open_financial_channel():
    from . import mem_channels  # noqa: F401
    from .db import open_atoms_db
    from .mem_channels.financial import FinancialChannel
    conn = open_atoms_db()
    return FinancialChannel(conn), conn


@financial_app.command("invest")
def financial_invest_cmd(
    project: str = typer.Argument(..., help="project name"),
    amount: float = typer.Argument(..., help="amount invested"),
    note: str = typer.Option("", "--note", "-n"),
    currency: str = typer.Option("USD", "--currency"),
    yes: bool = typer.Option(False, "-y", "--yes", help="skip confirmation"),
) -> None:
    """Record an INVESTMENT (Tier 3 — operator confirmation required)."""
    import uuid
    from .mem_channels.financial import CurrencyMismatchError
    if not yes and not STATE.json_out:
        _print(f"[yellow]Tier 3 action[/yellow]: investing "
               f"[bold]{amount} {currency}[/bold] in [cyan]{project}[/cyan]")
        if note:
            _print(f"  note: {note}")
        if not typer.confirm("Confirm?"):
            _print("[yellow]aborted[/yellow]")
            return

    fc, conn = _open_financial_channel()
    try:
        try:
            entry = fc.record(
                project=project, kind="invest", amount=amount,
                currency=currency, note=note,
                idempotency_id=str(uuid.uuid4()),
            )
        except CurrencyMismatchError as exc:
            if STATE.json_out:
                _emit_json({"ok": False, "error": "currency_mismatch",
                            "detail": str(exc)})
            else:
                _print(f"[red]✗ currency mismatch[/red]: {exc}")
            raise typer.Exit(code=1)
        except ValueError as exc:
            if STATE.json_out:
                _emit_json({"ok": False, "error": "invalid_input",
                            "detail": str(exc)})
            else:
                _print(f"[red]✗ invalid input[/red]: {exc}")
            raise typer.Exit(code=1)
    finally:
        conn.close()

    if STATE.json_out:
        _emit_json({"ok": True, "entry_id": entry.entry_id,
                    "project": entry.project, "amount": entry.amount})
    else:
        _print(f"[green]✓[/green] invested {entry.amount} {entry.currency} "
               f"in {entry.project} ({entry.entry_id})")


@financial_app.command("earn")
def financial_earn_cmd(
    project: str = typer.Argument(..., help="project name"),
    amount: float = typer.Argument(..., help="amount earned"),
    note: str = typer.Option("", "--note", "-n"),
    currency: str = typer.Option("USD", "--currency"),
    yes: bool = typer.Option(False, "-y", "--yes"),
) -> None:
    """Record EARNINGS (Tier 3 — operator confirmation required)."""
    import uuid
    from .mem_channels.financial import CurrencyMismatchError
    if not yes and not STATE.json_out:
        _print(f"[yellow]Tier 3 action[/yellow]: recording earnings of "
               f"[bold]{amount} {currency}[/bold] for [cyan]{project}[/cyan]")
        if note:
            _print(f"  note: {note}")
        if not typer.confirm("Confirm?"):
            _print("[yellow]aborted[/yellow]")
            return

    fc, conn = _open_financial_channel()
    try:
        try:
            entry = fc.record(
                project=project, kind="earn", amount=amount,
                currency=currency, note=note,
                idempotency_id=str(uuid.uuid4()),
            )
        except CurrencyMismatchError as exc:
            if STATE.json_out:
                _emit_json({"ok": False, "error": "currency_mismatch",
                            "detail": str(exc)})
            else:
                _print(f"[red]✗ currency mismatch[/red]: {exc}")
            raise typer.Exit(code=1)
        except ValueError as exc:
            if STATE.json_out:
                _emit_json({"ok": False, "error": "invalid_input",
                            "detail": str(exc)})
            else:
                _print(f"[red]✗ invalid input[/red]: {exc}")
            raise typer.Exit(code=1)
    finally:
        conn.close()

    if STATE.json_out:
        _emit_json({"ok": True, "entry_id": entry.entry_id,
                    "project": entry.project, "amount": entry.amount})
    else:
        _print(f"[green]✓[/green] earned {entry.amount} {entry.currency} "
               f"on {entry.project} ({entry.entry_id})")


@financial_app.command("show")
def financial_show_cmd(
    project: str = typer.Argument(..., help="project name"),
) -> None:
    """Show a project's lifetime balance and ROI."""
    fc, conn = _open_financial_channel()
    try:
        bal = fc.project_balance(project)
    finally:
        conn.close()

    if STATE.json_out:
        _emit_json({
            "ok": True, "project": bal.project,
            "invested": bal.invested, "earned": bal.earned,
            "net": bal.net,
            "roi_ratio": bal.roi_ratio,
            "currency": bal.currency,
            "entry_count": bal.entry_count,
            "first_event": bal.first_event,
            "last_event": bal.last_event,
        })
        return

    t = Table(show_header=False, box=None, padding=(0, 1))
    t.add_column(style="dim")
    t.add_column()
    t.add_row("project", bal.project)
    t.add_row("invested", f"{bal.invested:.2f} {bal.currency}")
    t.add_row("earned", f"{bal.earned:.2f} {bal.currency}")
    net_color = "green" if bal.net >= 0 else "red"
    t.add_row("net", f"[{net_color}]{bal.net:+.2f} {bal.currency}[/{net_color}]")
    if bal.roi_ratio is not None:
        roi_color = "green" if bal.roi_ratio >= 1.0 else "yellow"
        t.add_row("ROI", f"[{roi_color}]{bal.roi_ratio:.2f}x[/{roi_color}]")
    else:
        t.add_row("ROI", "[dim]undefined ($0 invested)[/dim]")
    t.add_row("entries", str(bal.entry_count))
    if bal.first_event:
        t.add_row("first event", bal.first_event)
    velocity = bal.velocity_per_day()
    if velocity is not None:
        t.add_row("velocity", f"{velocity:.2f} {bal.currency}/day")
    _print(Panel(t, title=f"◊ financial: {bal.project}", border_style="cyan"))


@financial_app.command("ranking")
def financial_ranking_cmd(
    by: str = typer.Option(
        "roi", "--by",
        help="sort key: roi | net | earned | velocity",
    ),
) -> None:
    """Rank all tracked projects by ROI / net / earned / velocity."""
    if by not in ("roi", "net", "earned", "velocity"):
        _print(f"[red]invalid --by: {by}[/red]")
        raise typer.Exit(code=1)

    fc, conn = _open_financial_channel()
    try:
        balances = fc.ranking(by=by)  # type: ignore[arg-type]
    finally:
        conn.close()

    if STATE.json_out:
        _emit_json({
            "ok": True, "by": by,
            "ranking": [
                {"project": b.project, "invested": b.invested,
                 "earned": b.earned, "net": b.net,
                 "roi_ratio": b.roi_ratio,
                 "velocity_per_day": b.velocity_per_day()}
                for b in balances
            ],
        })
        return

    t = Table(title=f"◊ projects ranked by {by}", box=None)
    t.add_column("#", style="dim", no_wrap=True)
    t.add_column("Project", style="cyan")
    t.add_column("Invested", style="yellow", justify="right")
    t.add_column("Earned", style="green", justify="right")
    t.add_column("Net", justify="right")
    t.add_column("ROI", style="magenta", justify="right")
    for i, b in enumerate(balances, 1):
        net_color = "green" if b.net >= 0 else "red"
        roi_str = f"{b.roi_ratio:.2f}x" if b.roi_ratio is not None else "—"
        t.add_row(
            str(i), b.project,
            f"{b.invested:.2f}", f"{b.earned:.2f}",
            f"[{net_color}]{b.net:+.2f}[/{net_color}]",
            roi_str,
        )
    _print(t)


@financial_app.command("audit")
def financial_audit_cmd() -> None:
    """Verify ledger integrity. Read-only invariant check.

    Reports orphaned companion atoms, dangling reverts, currency
    violations, malformed entry IDs, and bad timestamps. Exits 0 if
    clean, 1 if violations found.
    """
    fc, conn = _open_financial_channel()
    try:
        result = fc.audit()
    finally:
        conn.close()

    if STATE.json_out:
        _emit_json({
            "ok": result.ok,
            "ledger_rows": result.ledger_rows,
            "violations": result.violations,
            "orphaned_atoms": result.orphaned_atoms,
            "orphaned_reverts": result.orphaned_reverts,
            "currency_mixed_projects": result.currency_mixed_projects,
            "bad_entry_ids": result.bad_entry_ids,
            "bad_timestamps": result.bad_timestamps,
        })
        if not result.ok:
            raise typer.Exit(code=1)
        return

    color = "green" if result.ok else "red"
    _print(f"[{color}]{result.render()}[/{color}]")
    if not result.ok:
        raise typer.Exit(code=1)


# ─── Cockpit (TUI) ─────────────────────────────────────────────────────────


@app.command()
def cockpit() -> None:
    """Launch the operator cockpit — full-screen TUI for talking to the agent.

    Chat on the left, live event stream on the right, status bar at the
    bottom. Plain-English input routes through ``sovereign do``; slash
    commands handle ops (snap, halt, audit, etc). F1 inside the cockpit
    shows full help.

    The cockpit is a CLIENT of the agent — it doesn't replace the daemon.
    The systemd service keeps running the busy-drain loop in the background;
    the cockpit gives you a conversational surface on top.

    Requires textual (installed automatically with sovereign-agent>=0.2.14.4).
    """
    try:
        from .cockpit import run as run_cockpit
    except ImportError as exc:
        _print(f"[red]✗ cockpit unavailable: {exc}[/red]")
        _print("  Try: re-run ./install.sh from the sovereign-agent source tree")
        _print("  (textual is a declared dependency; uv sync should pull it in)")
        raise typer.Exit(code=1)
    run_cockpit()


# NOTE: A bare `chat()` alias for cockpit used to live here, but it was
# overridden by the `chat` sub-Typer (defined later in this file) once
# subcommands like `chat status` / `chat request` were added. The
# canonical launcher contract is restored via the chat sub-Typer's
# `invoke_without_command` callback. See ~line 6107.


# ─── Backup sub-app ────────────────────────────────────────────────────────


backup_app = typer.Typer(
    help="Backup, verify, prune, and restore snapshots. Application-aware "
         "(SQLite online backup; staged audit before restore).",
    no_args_is_help=True,
)


def _format_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f}{unit}"
        n /= 1024.0
    return f"{n}B"


def _format_age(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    if seconds < 60:
        return f"{seconds:.0f}s"
    if seconds < 3600:
        return f"{seconds/60:.0f}m"
    if seconds < 86400:
        return f"{seconds/3600:.1f}h"
    return f"{seconds/86400:.1f}d"


@backup_app.command("snapshot")
def backup_snapshot_cmd(
    label: str = typer.Option("", "--label", "-l",
                              help="optional retention tag (kept forever)"),
    root: str = typer.Option("", "--root",
                             help="destination root; defaults to "
                                  "~/AA-Erebo/sov-backups"),
) -> None:
    """Capture an application-consistent snapshot. Tier 2."""
    from . import backup as backup_mod
    from pathlib import Path
    backup_root = Path(root).expanduser() if root else None
    try:
        manifest = backup_mod.snapshot(backup_root=backup_root, label=label)
    except Exception as exc:  # noqa: BLE001
        if STATE.json_out:
            _emit_json({"ok": False, "error": str(exc)})
        else:
            _print(f"[red]✗ snapshot failed: {exc}[/red]")
        raise typer.Exit(code=1)

    if STATE.json_out:
        _emit_json({
            "ok": True,
            "snapshot_id": manifest.snapshot_id,
            "total_bytes": manifest.total_bytes,
            "file_count": manifest.file_count,
            "atoms_count": manifest.atoms_count,
            "ledger_count": manifest.financial_ledger_count,
            "audit_clean": manifest.audit_at_snapshot.get("ok", False),
        })
    else:
        _print(f"[green]✓[/green] snapshot · {manifest.snapshot_id}")
        _print(f"  files: {manifest.file_count}  "
               f"size: {_format_bytes(manifest.total_bytes)}  "
               f"atoms: {manifest.atoms_count}  "
               f"ledger: {manifest.financial_ledger_count}")
        if not manifest.audit_at_snapshot.get("ok", False):
            _print("[yellow]  ⚠ audit at snapshot was not clean — "
                   "snapshot still captured but flagged[/yellow]")


@backup_app.command("list")
def backup_list_cmd(
    root: str = typer.Option("", "--root"),
) -> None:
    """List all snapshots, newest-first. Tier 0."""
    from . import backup as backup_mod
    from pathlib import Path
    backup_root = Path(root).expanduser() if root else None
    snaps = backup_mod.list_snapshots(backup_root=backup_root)

    if STATE.json_out:
        _emit_json({
            "ok": True, "count": len(snaps),
            "snapshots": [
                {
                    "snapshot_id": s.snapshot_id,
                    "created_at": s.created_at,
                    "label": s.label,
                    "source_version": s.source_version,
                    "total_bytes": s.total_bytes,
                    "file_count": s.file_count,
                    "atoms_count": s.atoms_count,
                    "audit_clean": s.audit_at_snapshot.get("ok", False),
                } for s in snaps
            ],
        })
        return

    if not snaps:
        _print("[dim](no snapshots)[/dim]")
        return

    t = Table(title="◊ snapshots", box=None)
    t.add_column("ID", style="cyan", no_wrap=True)
    t.add_column("Created", style="dim", no_wrap=True)
    t.add_column("Version", no_wrap=True)
    t.add_column("Size", justify="right")
    t.add_column("Atoms", justify="right")
    t.add_column("Audit", no_wrap=True)
    t.add_column("Label", style="yellow")
    for s in snaps:
        audit_color = "green" if s.audit_at_snapshot.get("ok", False) else "red"
        audit_mark = "✓" if s.audit_at_snapshot.get("ok", False) else "✗"
        t.add_row(
            s.snapshot_id[:38],
            s.created_at[:19].replace("T", " "),
            s.source_version,
            _format_bytes(s.total_bytes),
            str(s.atoms_count),
            f"[{audit_color}]{audit_mark}[/{audit_color}]",
            s.label,
        )
    _print(t)


@backup_app.command("verify")
def backup_verify_cmd(
    snapshot_id: str = typer.Argument("", help="snapshot id (prefix OK); "
                                                "omit to verify all"),
    all_snaps: bool = typer.Option(False, "--all"),
    root: str = typer.Option("", "--root"),
    skip_audit: bool = typer.Option(False, "--skip-audit",
                                     help="hash check only; no atoms.db audit"),
) -> None:
    """Re-hash a snapshot and check the manifest. Tier 0."""
    from . import backup as backup_mod
    from pathlib import Path
    backup_root = Path(root).expanduser() if root else None

    if all_snaps or not snapshot_id:
        snaps = backup_mod.list_snapshots(backup_root=backup_root)
        if not snaps:
            _print("[dim](no snapshots to verify)[/dim]")
            return
        results = [
            backup_mod.verify(s.snapshot_id, backup_root=backup_root,
                              run_audit=not skip_audit)
            for s in snaps
        ]
        n_ok = sum(1 for r in results if r.ok)
        if STATE.json_out:
            _emit_json({
                "ok": all(r.ok for r in results),
                "verified": len(results),
                "passed": n_ok,
                "failed": len(results) - n_ok,
                "results": [
                    {
                        "snapshot_id": r.snapshot_id, "ok": r.ok,
                        "manifest_hash_ok": r.manifest_hash_ok,
                        "mismatched": r.mismatched_files,
                        "missing": r.missing_files,
                        "extra": r.extra_files,
                        "audit_clean": r.audit_clean,
                    } for r in results
                ],
            })
            if n_ok != len(results):
                raise typer.Exit(code=1)
            return
        for r in results:
            mark = "[green]✓[/green]" if r.ok else "[red]✗[/red]"
            _print(f"  {mark} {r.snapshot_id[:38]}")
            if not r.ok:
                if not r.manifest_hash_ok:
                    _print("      [red]manifest hash mismatch[/red]")
                if r.mismatched_files:
                    _print(f"      [red]mismatched files: "
                           f"{len(r.mismatched_files)}[/red]")
                if r.missing_files:
                    _print(f"      [red]missing files: "
                           f"{len(r.missing_files)}[/red]")
                if not r.audit_clean:
                    _print(f"      [red]staged audit failed: "
                           f"{r.audit_violations[:3]}[/red]")
        _print(f"\n[bold]{n_ok}/{len(results)} snapshots verified clean[/bold]")
        if n_ok != len(results):
            raise typer.Exit(code=1)
        return

    # Single snapshot
    r = backup_mod.verify(snapshot_id, backup_root=backup_root,
                          run_audit=not skip_audit)
    if STATE.json_out:
        _emit_json({
            "ok": r.ok, "snapshot_id": r.snapshot_id,
            "manifest_hash_ok": r.manifest_hash_ok,
            "mismatched": r.mismatched_files,
            "missing": r.missing_files,
            "extra": r.extra_files,
            "audit_clean": r.audit_clean,
            "audit_violations": r.audit_violations,
        })
        if not r.ok:
            raise typer.Exit(code=1)
        return

    if r.ok:
        _print(f"[green]✓ snapshot {r.snapshot_id} verified clean[/green]  "
               f"({r.file_count_found} files)")
    else:
        _print(f"[red]✗ snapshot {r.snapshot_id} FAILED verification[/red]")
        if r.error:
            _print(f"  error: {r.error}")
        if not r.manifest_hash_ok:
            _print("  manifest hash mismatch (tampered or partial write)")
        if r.mismatched_files:
            _print(f"  mismatched: {r.mismatched_files[:5]}")
        if r.missing_files:
            _print(f"  missing: {r.missing_files[:5]}")
        if not r.audit_clean:
            _print(f"  staged audit violations: {r.audit_violations[:5]}")
        raise typer.Exit(code=1)


@backup_app.command("prune")
def backup_prune_cmd(
    dry_run: bool = typer.Option(False, "--dry-run"),
    root: str = typer.Option("", "--root"),
    yes: bool = typer.Option(False, "-y", "--yes"),
) -> None:
    """Apply retention policy: keep all <24h, daily, weekly, monthly,
    plus all labeled snapshots. Always preserves the newest. Tier 2."""
    from . import backup as backup_mod
    from pathlib import Path
    backup_root = Path(root).expanduser() if root else None

    # Dry-run preview first
    preview = backup_mod.prune(backup_root=backup_root, dry_run=True)
    if not preview.removed:
        if STATE.json_out:
            _emit_json({"ok": True, "removed": [], "kept": preview.kept,
                        "bytes_freed": 0, "dry_run": dry_run})
        else:
            _print(f"[dim](nothing to prune; "
                   f"keeping {len(preview.kept)} snapshots)[/dim]")
        return

    if dry_run:
        if STATE.json_out:
            _emit_json({"ok": True, "dry_run": True,
                        "would_remove": preview.removed,
                        "would_keep": preview.kept,
                        "bytes_to_free": preview.bytes_freed})
        else:
            _print(f"[yellow]would remove {len(preview.removed)} snapshots[/yellow] "
                   f"({_format_bytes(preview.bytes_freed)} freed):")
            for sid in preview.removed:
                _print(f"  - {sid}")
        return

    if not yes and not STATE.json_out:
        _print(f"[yellow]about to prune {len(preview.removed)} snapshots[/yellow] "
               f"({_format_bytes(preview.bytes_freed)})")
        if not typer.confirm("Proceed?"):
            _print("[yellow]aborted[/yellow]")
            return

    result = backup_mod.prune(backup_root=backup_root, dry_run=False)
    if STATE.json_out:
        _emit_json({"ok": True, "removed": result.removed,
                    "kept": result.kept,
                    "bytes_freed": result.bytes_freed,
                    "dry_run": False})
    else:
        _print(f"[green]✓[/green] pruned {len(result.removed)} snapshots "
               f"({_format_bytes(result.bytes_freed)} freed); "
               f"{len(result.kept)} kept")


@backup_app.command("restore")
def backup_restore_cmd(
    snapshot_id: str = typer.Argument(..., help="snapshot id (prefix OK)"),
    root: str = typer.Option("", "--root"),
    yes: bool = typer.Option(False, "-y", "--yes",
                              help="skip the Tier 3 confirmation prompt"),
) -> None:
    """Restore from a snapshot. TIER 3 — irreversible swap. The current
    live state is auto-snapshotted with label ``pre-restore-...`` first
    so you can roll the restore itself back."""
    from . import backup as backup_mod
    from pathlib import Path
    backup_root = Path(root).expanduser() if root else None

    # Resolve and show what's being restored.
    try:
        _, manifest = backup_mod._resolve_snapshot(
            snapshot_id, backup_root=backup_root,
        )
    except backup_mod.BackupError as exc:
        _print(f"[red]✗ {exc}[/red]")
        raise typer.Exit(code=1)

    if not yes and not STATE.json_out:
        _print(f"[red]Tier 3 RESTORE[/red]")
        _print(f"  snapshot:    {manifest.snapshot_id}")
        _print(f"  created:     {manifest.created_at}")
        _print(f"  source ver:  {manifest.source_version}")
        _print(f"  atoms:       {manifest.atoms_count}")
        _print(f"  ledger rows: {manifest.financial_ledger_count}")
        _print(f"  audit clean: {manifest.audit_at_snapshot.get('ok', False)}")
        _print()
        _print("This will SWAP your live data dir with the snapshot.")
        _print("Your current live state will be auto-snapshotted first.")
        if not typer.confirm("Proceed?"):
            _print("[yellow]aborted[/yellow]")
            return

    try:
        result = backup_mod.restore(
            snapshot_id, backup_root=backup_root, confirmed=True,
        )
    except backup_mod.RestoreRefusedError as exc:
        if STATE.json_out:
            _emit_json({"ok": False, "error": "refused", "detail": str(exc)})
        else:
            _print(f"[red]✗ restore refused[/red]: {exc}")
        raise typer.Exit(code=1)
    except backup_mod.BackupError as exc:
        if STATE.json_out:
            _emit_json({"ok": False, "error": "backup_error",
                        "detail": str(exc)})
        else:
            _print(f"[red]✗ {exc}[/red]")
        raise typer.Exit(code=1)

    if STATE.json_out:
        _emit_json({
            "ok": True,
            "restored_snapshot_id": result.snapshot_id,
            "pre_restore_snapshot_id": result.pre_restore_snapshot_id,
            "restored_at": result.restored_at,
        })
    else:
        _print(f"[green]✓[/green] restored from {result.snapshot_id}")
        _print(f"  pre-restore snapshot of prior live state: "
               f"[cyan]{result.pre_restore_snapshot_id}[/cyan]")
        _print("  [yellow]restart any running sovereign processes "
               "to pick up the new state[/yellow]")


@backup_app.command("status")
def backup_status_cmd(
    root: str = typer.Option("", "--root"),
) -> None:
    """Single-screen view of the backup state. Tier 0."""
    from . import backup as backup_mod
    from pathlib import Path
    backup_root = Path(root).expanduser() if root else None
    s = backup_mod.status(backup_root=backup_root)

    if STATE.json_out:
        _emit_json({
            "ok": True,
            "backup_root": s.backup_root,
            "snapshot_count": s.snapshot_count,
            "total_bytes": s.total_bytes,
            "most_recent_snapshot_id": s.most_recent_snapshot_id,
            "most_recent_age_seconds": s.most_recent_age_seconds,
            "oldest_snapshot_id": s.oldest_snapshot_id,
            "last_verify_ok": s.last_verify_ok,
        })
        return

    _print("═══ backup status ═══")
    _print(f"  root:        {s.backup_root}")
    _print(f"  snapshots:   {s.snapshot_count}")
    _print(f"  total size:  {_format_bytes(s.total_bytes)}")
    if s.most_recent_snapshot_id:
        age_color = (
            "green" if s.most_recent_age_seconds and
            s.most_recent_age_seconds < 86400 * 7 else "yellow"
        )
        _print(f"  most recent: {s.most_recent_snapshot_id}")
        _print(f"  age:         "
               f"[{age_color}]{_format_age(s.most_recent_age_seconds)}[/{age_color}]")
        verify_color = "green" if s.last_verify_ok else "red"
        verify_mark = "✓" if s.last_verify_ok else "✗"
        _print(f"  verify:      "
               f"[{verify_color}]{verify_mark}[/{verify_color}]")
    else:
        _print("  [yellow]no snapshots yet — run 'sovereign backup snapshot'"
               "[/yellow]")


app.add_typer(backup_app, name="backup")


# ─── Horizon sub-app ───────────────────────────────────────────────────────


@app.command()
def horizon(
    label: str = typer.Argument(..., help="short title"),
    decision: str = typer.Option(..., "--decision", "-d",
                                  help="what is being decided"),
    three_month: str = typer.Option("", "--3m"),
    twelve_month: str = typer.Option("", "--12m"),
    three_year: str = typer.Option("", "--3y"),
    seventh: str = typer.Option("", "--7g",
                                 help="7th-generation concern"),
    best_path: str = typer.Option("", "--best-path"),
    save: bool = typer.Option(False, "--save",
                               help="save through appendix system"),
) -> None:
    """Generate a MOS Horizon Scan markdown."""
    from .horizon import HorizonInputs, render, save_through_appendix

    inputs = HorizonInputs(
        label=label, decision=decision,
        three_month=three_month, twelve_month=twelve_month,
        three_year=three_year, seventh_generation=seventh,
        best_forward_path=best_path,
    )

    if save:
        from .db import open_atoms_db
        from . import mem_channels  # noqa: F401
        appendix_dir = SETTINGS.paths.data_dir / "appendix"
        conn = open_atoms_db()
        try:
            doc = save_through_appendix(
                conn, appendix_dir=appendix_dir, inputs=inputs,
            )
        finally:
            conn.close()
        if STATE.json_out:
            _emit_json({"ok": True, "doc_id": doc.doc_id,
                        "file_path": doc.file_path})
        else:
            _print(f"[green]✓[/green] saved horizon scan: {doc.file_path}")
        return

    text = render(inputs)
    if STATE.json_out:
        _emit_json({"ok": True, "markdown": text})
    else:
        _print(text)


# ─── Appendix sub-app ──────────────────────────────────────────────────────


appendix_app = typer.Typer(
    help="◊ markdown documents attached to atoms (v0.2.14)",
)
app.add_typer(appendix_app, name="appendix")


@appendix_app.command("list")
def appendix_list_cmd(
    kind: str = typer.Option("", "--kind",
                              help="filter: plan|note|insight|intuition|horizon"),
    limit: int = typer.Option(20, "--limit", "-n"),
) -> None:
    """List recent appendix documents."""
    from . import mem_channels  # noqa: F401
    from .appendix import list_recent
    from .db import open_atoms_db

    conn = open_atoms_db()
    try:
        from .appendix import ensure_appendix_schema
        ensure_appendix_schema(conn)
        docs = list_recent(conn, kind=kind or None, limit=limit)
    finally:
        conn.close()

    if STATE.json_out:
        _emit_json({"ok": True, "count": len(docs),
                    "docs": [d.__dict__ for d in docs]})
        return

    if not docs:
        _print("[dim]no appendix documents yet[/dim]")
        return

    t = Table(title="◊ appendix documents", box=None)
    t.add_column("ID", style="dim", no_wrap=True)
    t.add_column("Kind", style="cyan", no_wrap=True)
    t.add_column("Title")
    t.add_column("Created", style="dim", no_wrap=True)
    for d in docs:
        t.add_row(d.doc_id[:18] + "…", d.kind, d.title[:50],
                  d.created_at[:19])
    _print(t)


@appendix_app.command("show")
def appendix_show_cmd(
    doc_id: str = typer.Argument(..., help="appendix doc id"),
) -> None:
    """Show one appendix document's body."""
    from . import mem_channels  # noqa: F401
    from .appendix import ensure_appendix_schema, get_doc, read_body
    from .db import open_atoms_db

    conn = open_atoms_db()
    try:
        ensure_appendix_schema(conn)
        doc = get_doc(conn, doc_id)
        if doc is None:
            _print(f"[red]not found: {doc_id}[/red]")
            raise typer.Exit(code=1)
        body = read_body(doc)
    finally:
        conn.close()

    if STATE.json_out:
        _emit_json({"ok": True, "doc": doc.__dict__, "body": body})
        return

    _print(Panel(
        body or "[dim](body file not found)[/dim]",
        title=f"◊ {doc.kind}: {doc.title}",
        border_style="cyan",
    ))


@appendix_app.command("add")
def appendix_add_cmd(
    title: str = typer.Argument(..., help="document title"),
    kind: str = typer.Option("note", "--kind",
                              help="plan|note|insight|intuition|horizon|other"),
    body_file: str = typer.Option("", "--body-file",
                                   help="read body from this file"),
    body: str = typer.Option("", "--body", help="body text inline"),
    atom_id: str = typer.Option("", "--atom-id",
                                 help="attach to this atom"),
) -> None:
    """Create a new appendix document."""
    from . import mem_channels  # noqa: F401
    from .appendix import write_doc
    from .db import open_atoms_db

    if body_file:
        body = Path(body_file).read_text(encoding="utf-8")
    if not body:
        _print("[red]must supply --body or --body-file[/red]")
        raise typer.Exit(code=1)

    appendix_dir = SETTINGS.paths.data_dir / "appendix"
    conn = open_atoms_db()
    try:
        doc = write_doc(
            conn, appendix_dir=appendix_dir, kind=kind, title=title,
            body=body, atom_id=atom_id or None, created_by="operator",
        )
    finally:
        conn.close()

    if STATE.json_out:
        _emit_json({"ok": True, "doc_id": doc.doc_id,
                    "file_path": doc.file_path})
    else:
        _print(f"[green]✓[/green] {doc.kind}: {doc.title}  →  {doc.file_path}")


drafts_app = typer.Typer(help="◊ archive completed projects to <data_dir>/drafts/")
app.add_typer(drafts_app, name="drafts")


@drafts_app.command("archive")
def drafts_archive_cmd(
    title: str = typer.Argument(..., help="Human-readable project title"),
    source: Path = typer.Argument(..., help="Directory or file to archive"),
    label: str = typer.Option("", "--label", "-l", help="Short tag (e.g. v0.2.15.3)"),
    notes: str = typer.Option("", "--notes", "-n", help="Free-form notes"),
    exclude: list[str] = typer.Option(
        [], "--exclude", "-x",
        help="Glob patterns to skip (matched against relative paths). Repeatable.",
    ),
) -> None:
    """Zip a directory and store it as a draft under <data_dir>/drafts/.

    The archive lands at ``<data_dir>/drafts/<timestamp>-<slug>.zip`` with a
    sidecar JSON that records file count, byte total, sha256, and any notes.
    Use ``sov drafts list`` to see everything you've archived.
    """
    from .drafts import archive_project
    try:
        rec = archive_project(
            title, source, label=label, notes=notes,
            exclude_patterns=exclude or None,
        )
    except FileNotFoundError as exc:
        _die(ExitCode.USAGE, str(exc))
        return
    except OSError as exc:
        _die(ExitCode.IO, f"archive failed: {exc}")
        return
    _print(Panel.fit(
        f"[b]◊ drafted[/b]  {rec.title}\n"
        f"[dim]id     [/dim] {rec.id}\n"
        f"[dim]zip    [/dim] {rec.zip_path}\n"
        f"[dim]files  [/dim] {rec.file_count}\n"
        f"[dim]bytes  [/dim] {rec.bytes_total}\n"
        f"[dim]sha256 [/dim] {rec.sha256[:16]}…\n"
        f"[dim]label  [/dim] {rec.label or '(none)'}",
        border_style="green",
    ))


@drafts_app.command("list")
def drafts_list_cmd(
    limit: int = typer.Option(20, "--limit", "-n", help="Max rows to show"),
    json_out: bool = typer.Option(False, "--json", help="Emit JSON for piping"),
) -> None:
    """List archived drafts, newest first."""
    from .drafts import list_drafts
    rows = list_drafts()[:limit]
    if json_out:
        import json
        _print(json.dumps([r.to_dict() for r in rows], indent=2, default=str))
        return
    if not rows:
        _print("[dim](no drafts yet — try `sov drafts archive <title> <path>`)[/dim]")
        return
    table = Table(title=f"drafts — {len(rows)} most recent", border_style="cyan")
    table.add_column("id",      style="dim",    no_wrap=True)
    table.add_column("title",   style="bold")
    table.add_column("label",   style="cyan")
    table.add_column("files",   justify="right")
    table.add_column("size",    justify="right", style="green")
    for r in rows:
        size_mb = r.bytes_total / (1024 * 1024)
        size_s = f"{size_mb:.1f} MB" if size_mb >= 1 else f"{r.bytes_total} B"
        table.add_row(r.id, r.title, r.label or "—", str(r.file_count), size_s)
    _print(table)


@drafts_app.command("show")
def drafts_show_cmd(
    draft_id: str = typer.Argument(..., help="Draft id, e.g. 20260511-143205-myproject"),
) -> None:
    """Show the full sidecar metadata for one draft."""
    from .drafts import show_draft
    rec = show_draft(draft_id)
    if rec is None:
        _die(ExitCode.USAGE, f"no draft with id {draft_id!r}")
        return
    import json
    _print(json.dumps(rec.to_dict(), indent=2, default=str))


telemetry_app = typer.Typer(
    help="◊ inspect system telemetry recorded by the cockpit "
         "(<data>/telemetry/sys-YYYYMMDD.jsonl)"
)
app.add_typer(telemetry_app, name="telemetry")


@telemetry_app.command("path")
def telemetry_path_cmd() -> None:
    """Print the path to today's telemetry file."""
    from .cockpit.telemetry import current_path
    p = current_path()
    _print(str(p))
    if not p.exists():
        _print("[dim](file does not exist yet — start sov-chat to begin sampling)[/dim]")


@telemetry_app.command("tail")
def telemetry_tail_cmd(
    n: int = typer.Option(20, "-n", "--lines", help="Number of recent samples"),
    json_out: bool = typer.Option(False, "--json", help="Emit raw JSONL"),
) -> None:
    """Show the last N samples from today's telemetry file."""
    from .cockpit.telemetry import tail_today
    rows = tail_today(n)
    if not rows:
        _print("[dim](no telemetry yet — cockpit hasn't written samples for today)[/dim]")
        return
    if json_out:
        import json
        for r in rows:
            _print(json.dumps(r))
        return
    table = Table(title=f"telemetry — last {len(rows)} samples", border_style="cyan")
    table.add_column("ts",       style="dim",     no_wrap=True)
    table.add_column("cpu%",     justify="right")
    table.add_column("cpu°",     justify="right")
    table.add_column("ram%",     justify="right")
    table.add_column("vram%",    justify="right")
    table.add_column("vram°",    justify="right")
    table.add_column("disk%",    justify="right")
    table.add_column("load",     justify="right", style="dim")
    table.add_column("task",     style="cyan")
    for r in rows:
        table.add_row(
            r.get("ts", "?")[-8:].rstrip("Z"),   # HH:MM:SS only
            f"{r.get('cpu_pct', 0):.0f}",
            f"{r['cpu_temp_c']:.0f}" if "cpu_temp_c" in r else "—",
            f"{r.get('ram_pct', 0):.0f}",
            f"{r['vram_pct']:.0f}" if "vram_pct" in r else "—",
            f"{r['vram_temp_c']:.0f}" if "vram_temp_c" in r else "—",
            f"{r.get('disk_pct', 0):.0f}",
            f"{r.get('load_1m', 0):.2f}",
            r.get("task_directive", "")[:32] if "task_directive" in r else "",
        )
    _print(table)


@telemetry_app.command("summary")
def telemetry_summary_cmd(
    days: int = typer.Option(1, "-d", "--days", help="Look back N days (1 = today)"),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output"),
) -> None:
    """Min/avg/max for headline metrics across the last N days."""
    from .cockpit.telemetry import summarise
    out = summarise(days=days)
    if json_out:
        import json
        _print(json.dumps(out, indent=2, default=str))
        return
    if out["sample_count"] == 0:
        _print("[dim](no telemetry data in the requested window)[/dim]")
        return
    _print(
        f"[b]telemetry summary[/b] · "
        f"{out['files_read']} day file(s) · "
        f"{out['sample_count']} samples"
    )
    _print(f"[dim]first[/dim] {out.get('ts_first', '?')}")
    _print(f"[dim]last [/dim] {out.get('ts_last',  '?')}")
    _print("")
    table = Table(border_style="cyan", show_header=True)
    table.add_column("metric")
    table.add_column("min", justify="right")
    table.add_column("avg", justify="right", style="bold")
    table.add_column("max", justify="right")
    table.add_column("n",   justify="right", style="dim")
    for key in ("cpu_pct", "cpu_temp_c", "ram_pct", "vram_pct",
                "vram_temp_c", "disk_pct", "load_1m", "swap_pct"):
        v = out.get(key)
        if not isinstance(v, dict):
            continue
        table.add_row(
            key, f"{v['min']:.1f}", f"{v['avg']:.1f}",
            f"{v['max']:.1f}", str(v["n"]),
        )
    _print(table)


# ═══════════════════════════════════════════════════════════════════════════
#  v0.2.16.0 sub-apps:
#  people · recall · insights · task · qa · steward · home · chat (interrupts)
# ═══════════════════════════════════════════════════════════════════════════


def _get_atoms_conn():
    """Helper: open the atoms DB (with channel schema bootstrap)."""
    from .db import open_atoms_db
    return open_atoms_db()


def _utc_seed(prefix: str) -> str:
    """Generate a wall-clock-seeded idempotency id when the operator doesn't supply one."""
    import secrets
    return f"{prefix}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{secrets.token_hex(4)}"


# ─── sov people ────────────────────────────────────────────────────────────


people_app = typer.Typer(help="◊ people Aria knows (canonical names, aliases, facts)")
app.add_typer(people_app, name="people")


@people_app.command("list")
def people_list_cmd(
    include_pending: bool = typer.Option(False, "--include-pending",
                                          help="Show people with only pending facts"),
) -> None:
    from .mem_channels.people import PeopleChannel
    conn = _get_atoms_conn()
    pc = PeopleChannel(conn)
    people = pc.list_people()
    if STATE.json_out:
        _emit_json({"ok": True, "count": len(people),
                    "people": [{
                        "id": p.person_id, "canonical_name": p.canonical_name,
                        "is_principal": p.is_principal,
                    } for p in people]})
        return
    if not people:
        _print("[dim](no people recorded — try `sov people add <name>`)[/dim]")
        return
    t = Table(title=f"◊ people · {len(people)}", border_style="cyan")
    t.add_column("name", style="bold")
    t.add_column("principal", justify="center")
    t.add_column("id", style="dim")
    for p in people:
        t.add_row(p.canonical_name, "★" if p.is_principal else "", p.person_id)
    _print(t)


@people_app.command("show")
def people_show_cmd(name: str = typer.Argument(..., help="canonical name or alias")) -> None:
    from .mem_channels.people import PeopleChannel, PersonNotFoundError
    conn = _get_atoms_conn()
    pc = PeopleChannel(conn)
    try:
        profile = pc.profile(name)
    except PersonNotFoundError:
        _die(ExitCode.USAGE, f"no person found: {name!r}")
        return
    if STATE.json_out:
        _emit_json({"ok": True, "profile": profile.__dict__ if hasattr(profile, '__dict__') else str(profile)})
        return
    _print(profile.render())


@people_app.command("add")
def people_add_cmd(
    name: str = typer.Argument(..., help="canonical name"),
    principal: bool = typer.Option(False, "--principal", help="mark as THE operator"),
    idem: str | None = typer.Option(None, "--idem", help="idempotency id"),
) -> None:
    from .mem_channels.people import PeopleChannel, PrincipalConflictError
    conn = _get_atoms_conn()
    pc = PeopleChannel(conn)
    idempotency_id = idem or _utc_seed("upsert")
    try:
        p = pc.upsert_person(canonical_name=name, is_principal=principal,
                             idempotency_id=idempotency_id)
    except PrincipalConflictError as e:
        _die(ExitCode.USAGE, str(e),
             hint="another person is already the principal; pass --idem with --principal "
                  "only when intentionally switching")
        return
    if STATE.json_out:
        _emit_json({"ok": True, "person_id": p.person_id, "principal": p.is_principal})
        return
    _print(f"✓ {p.canonical_name} ({p.person_id})"
           + ("  ★ principal" if p.is_principal else ""))


@people_app.command("alias")
def people_alias_cmd(
    person: str = typer.Argument(..., help="canonical name or person_id"),
    alias: str = typer.Argument(..., help="alternative name to attach"),
    idem: str | None = typer.Option(None, "--idem"),
) -> None:
    from .mem_channels.people import PeopleChannel, PersonNotFoundError
    conn = _get_atoms_conn()
    pc = PeopleChannel(conn)
    p = pc.resolve(person)
    if p is None:
        _die(ExitCode.USAGE, f"unknown person: {person!r}")
        return
    pid = p.person_id
    pc.add_alias(person_id=pid, alias=alias, source="operator",
                 idempotency_id=idem or _utc_seed("alias"))
    if STATE.json_out:
        _emit_json({"ok": True, "person_id": pid, "alias": alias})
        return
    _print(f"✓ alias {alias!r} → {pid}")


@people_app.command("fact")
def people_fact_cmd(
    person: str = typer.Argument(..., help="canonical name or alias"),
    kind: str = typer.Argument(..., help="fact kind (role, research_area, lab, ...)"),
    value: str = typer.Argument(..., help="the fact value"),
    source: str = typer.Option("operator", "--source"),
    idem: str | None = typer.Option(None, "--idem"),
) -> None:
    from .mem_channels.people import PeopleChannel, PersonNotFoundError
    conn = _get_atoms_conn()
    pc = PeopleChannel(conn)
    p = pc.resolve(person)
    if p is None:
        _die(ExitCode.USAGE, f"unknown person: {person!r}")
        return
    pid = p.person_id
    f = pc.record_fact(person_id=pid, kind=kind, value=value, source=source,
                       idempotency_id=idem or _utc_seed("fact"))
    if STATE.json_out:
        _emit_json({"ok": True, "fact_id": f.fact_id, "status": f.status})
        return
    _print(f"✓ {f.fact_id}  [{f.status}]  {kind}={value}  (source={source})")


@people_app.command("audit")
def people_audit_cmd() -> None:
    from .mem_channels.people import PeopleChannel
    conn = _get_atoms_conn()
    pc = PeopleChannel(conn)
    a = pc.audit()
    if STATE.json_out:
        _emit_json({"ok": a.ok, "audit": a.__dict__ if hasattr(a, "__dict__") else str(a)})
        return
    glyph = "✓" if a.ok else "✗"
    _print(f"{glyph} people audit · ok={a.ok}  ·  {a}")


# ─── sov recall ────────────────────────────────────────────────────────────


recall_app = typer.Typer(help="◊ Aria's curated recalls (markdown in studio room)")
app.add_typer(recall_app, name="recall")


@recall_app.command("list")
def recall_list_cmd(
    status: str | None = typer.Option(None, "--status",
                                       help="fresh|stale|obsolete|redacted"),
    kind: str | None = typer.Option(None, "--kind"),
    limit: int = typer.Option(30, "-n", "--limit"),
) -> None:
    from .mem_channels.recall import RecallChannel
    conn = _get_atoms_conn()
    rc = RecallChannel(conn)
    items = rc.list_recalls(status=status, kind=kind, limit=limit)
    if STATE.json_out:
        _emit_json({"ok": True, "count": len(items),
                    "recalls": [{
                        "id": r.recall_id, "title": r.title,
                        "kind": r.kind, "status": r.status,
                        "created_at": r.created_at, "file": r.file_path,
                    } for r in items]})
        return
    if not items:
        _print("[dim](no recalls yet — try `sov recall add <title>`)[/dim]")
        return
    t = Table(title=f"◊ recalls · {len(items)}", border_style="cyan")
    t.add_column("title", style="bold")
    t.add_column("kind"); t.add_column("status"); t.add_column("created", style="dim")
    t.add_column("id", style="dim")
    for r in items:
        t.add_row(r.title[:48], r.kind, r.status, r.created_at[:10], r.recall_id)
    _print(t)


@recall_app.command("add")
def recall_add_cmd(
    title: str = typer.Argument(...),
    body: str = typer.Option(..., "--body", "-b", help="markdown body"),
    kind: str = typer.Option("ad-hoc", "--kind"),
    summary: str | None = typer.Option(None, "--summary"),
    subject: str | None = typer.Option(None, "--subject"),
    idem: str | None = typer.Option(None, "--idem"),
) -> None:
    from .mem_channels.recall import RecallChannel
    conn = _get_atoms_conn()
    rc = RecallChannel(conn)
    r = rc.record(
        title=title, body_md=body, kind=kind, summary=summary,
        subject_id=subject, idempotency_id=idem or _utc_seed("recall"),
    )
    if STATE.json_out:
        _emit_json({"ok": True, "id": r.recall_id, "file": r.file_path})
        return
    _print(f"✓ {r.recall_id}\n  {r.title}\n  file: {r.file_path}")


@recall_app.command("show")
def recall_show_cmd(recall_id: str = typer.Argument(...)) -> None:
    from .mem_channels.recall import RecallChannel, RecallNotFoundError
    conn = _get_atoms_conn()
    rc = RecallChannel(conn)
    try:
        r = rc.get(recall_id, include_redacted=True)
    except RecallNotFoundError:
        _die(ExitCode.USAGE, f"no recall: {recall_id}")
        return
    if STATE.json_out:
        _emit_json({"ok": True, "recall": {
            "id": r.recall_id, "title": r.title, "status": r.status,
            "body_md": r.body_md, "sources": [s.__dict__ for s in r.sources],
        }})
        return
    _print(r.render())
    _print(""); _print(r.body_md)


@recall_app.command("search")
def recall_search_cmd(
    query: str = typer.Argument(...),
    limit: int = typer.Option(10, "-n", "--limit"),
) -> None:
    from .mem_channels.recall import RecallChannel
    conn = _get_atoms_conn()
    rc = RecallChannel(conn)
    items = rc.search(query, limit=limit)
    if STATE.json_out:
        _emit_json({"ok": True, "matches": [{"id": r.recall_id, "title": r.title}
                                              for r in items]})
        return
    if not items:
        _print("[dim](no matches)[/dim]"); return
    for r in items:
        _print(f"  · [bold]{r.title}[/bold]  [dim]({r.recall_id}) {r.status}[/dim]")
        if r.summary:
            _print(f"      {r.summary.strip()[:120]}")


@recall_app.command("redact")
def recall_redact_cmd(
    recall_id: str = typer.Argument(...),
    reason: str | None = typer.Option(None, "--reason"),
    idem: str | None = typer.Option(None, "--idem"),
) -> None:
    from .mem_channels.recall import RecallChannel
    conn = _get_atoms_conn()
    rc = RecallChannel(conn)
    rc.redact(recall_id, idempotency_id=idem or _utc_seed("redact"), reason=reason)
    if STATE.json_out:
        _emit_json({"ok": True, "recall_id": recall_id})
        return
    _print(f"✓ redacted {recall_id}")


@recall_app.command("audit")
def recall_audit_cmd() -> None:
    from .mem_channels.recall import RecallChannel
    conn = _get_atoms_conn()
    rc = RecallChannel(conn)
    a = rc.audit()
    if STATE.json_out:
        _emit_json({"ok": a.ok, "audit": a.__dict__})
        return
    glyph = "✓" if a.ok else "✗"
    _print(f"{glyph} recall audit · ok={a.ok} · total={a.total} · "
           f"fresh={a.fresh} stale={a.stale} obsolete={a.obsolete} redacted={a.redacted}")
    if a.missing_files:
        _print(f"  missing files: {len(a.missing_files)}")
    if a.superseded_chains_broken:
        _print(f"  broken supersedes: {len(a.superseded_chains_broken)}")


# ─── sov insights ──────────────────────────────────────────────────────────


insights_app = typer.Typer(help="◊ insight synthesis over people facts")
app.add_typer(insights_app, name="insights")


@insights_app.command("person")
def insights_person_cmd(
    name: str = typer.Argument(...),
    persist: bool = typer.Option(False, "--persist",
                                  help="write top candidates as recalls"),
) -> None:
    from .insights import generate_person_insights, persist_insights
    conn = _get_atoms_conn()
    report = generate_person_insights(conn, name)
    if STATE.json_out:
        _emit_json({"ok": True, "report": {
            "subject": report.subject,
            "candidates": [c.__dict__ for c in report.candidates],
        }})
        return
    _print(report.render())
    if persist and report.candidates:
        n = persist_insights(conn, report, operator_note="cli")
        _print(f"\n✓ persisted {n} insight(s) as recalls")


@insights_app.command("horizon")
def insights_horizon_cmd(
    persist: bool = typer.Option(False, "--persist"),
) -> None:
    from .insights import generate_horizon_insight, persist_insights
    conn = _get_atoms_conn()
    report = generate_horizon_insight(conn)
    if STATE.json_out:
        _emit_json({"ok": True, "candidates": [c.__dict__ for c in report.candidates]})
        return
    _print(report.render())
    if persist and report.candidates:
        n = persist_insights(conn, report, operator_note="cli-horizon")
        _print(f"\n✓ persisted {n} horizon insight(s) as recalls")


# ─── sov task ─────────────────────────────────────────────────────────────


task_app = typer.Typer(help="◊ working memory of tasks Aria does")
app.add_typer(task_app, name="task")


@task_app.command("list")
def task_list_cmd(
    status: str | None = typer.Option(None, "--status"),
    limit: int = typer.Option(20, "-n", "--limit"),
) -> None:
    from .mem_channels.task import TaskChannel
    conn = _get_atoms_conn()
    tc = TaskChannel(conn)
    items = tc.list_tasks(status=status, limit=limit)
    if STATE.json_out:
        _emit_json({"ok": True, "tasks": [
            {"id": t.task_id, "title": t.title, "status": t.status,
             "emotion": t.agent_emotion, "started_at": t.started_at}
            for t in items
        ]})
        return
    if not items:
        _print("[dim](no tasks yet)[/dim]"); return
    t = Table(title=f"◊ tasks · {len(items)}", border_style="cyan")
    t.add_column("title", style="bold"); t.add_column("status")
    t.add_column("felt"); t.add_column("started", style="dim")
    t.add_column("id", style="dim")
    for tr in items:
        t.add_row(tr.title[:40], tr.status, tr.agent_emotion or "—",
                  tr.started_at[:16], tr.task_id)
    _print(t)


@task_app.command("show")
def task_show_cmd(task_id: str = typer.Argument(...)) -> None:
    from .mem_channels.task import TaskChannel, TaskNotFoundError
    conn = _get_atoms_conn()
    tc = TaskChannel(conn)
    try:
        tr = tc.get(task_id)
    except TaskNotFoundError:
        _die(ExitCode.USAGE, f"no task: {task_id}"); return
    if STATE.json_out:
        _emit_json({"ok": True, "task": {
            "id": tr.task_id, "title": tr.title, "status": tr.status,
            "started_at": tr.started_at, "finished_at": tr.finished_at,
            "outcome": tr.outcome_summary, "notes": tr.detailed_notes,
            "lessons": tr.lessons, "follow_ups": tr.follow_ups,
            "emotion": tr.agent_emotion, "emotion_note": tr.agent_emotion_note,
        }})
        return
    _print(tr.render())


@task_app.command("search")
def task_search_cmd(query: str = typer.Argument(...),
                    limit: int = typer.Option(10, "-n")) -> None:
    from .mem_channels.task import TaskChannel
    conn = _get_atoms_conn()
    tc = TaskChannel(conn)
    items = tc.search(query, limit=limit)
    if STATE.json_out:
        _emit_json({"ok": True, "matches": [{"id": t.task_id, "title": t.title,
                                              "status": t.status} for t in items]})
        return
    if not items:
        _print("[dim](no matches)[/dim]"); return
    for tr in items:
        _print(f"  · [bold]{tr.title}[/bold]  "
               f"[dim]({tr.task_id}) {tr.status}"
               f"{' · ' + tr.agent_emotion if tr.agent_emotion else ''}[/dim]")


@task_app.command("stats")
def task_stats_cmd() -> None:
    from .mem_channels.task import TaskChannel
    conn = _get_atoms_conn()
    tc = TaskChannel(conn)
    s = tc.stats()
    if STATE.json_out:
        _emit_json({"ok": True, "stats": s.__dict__})
        return
    _print(s.render())


@task_app.command("begin")
def task_begin_cmd(
    title: str = typer.Argument(...),
    description: str | None = typer.Option(None, "--desc", "-d"),
    parent: str | None = typer.Option(None, "--parent"),
    idem: str | None = typer.Option(None, "--idem"),
) -> None:
    from .mem_channels.task import TaskChannel
    conn = _get_atoms_conn()
    tc = TaskChannel(conn)
    tr = tc.begin(title=title, description=description, parent_task_id=parent,
                  idempotency_id=idem or _utc_seed("task"))
    if STATE.json_out:
        _emit_json({"ok": True, "task_id": tr.task_id}); return
    _print(f"✓ began {tr.task_id}\n  {tr.title}")


@task_app.command("finish")
def task_finish_cmd(
    task_id: str = typer.Argument(...),
    status: str = typer.Option("success", "--status",
                                help="success|partial|failed|abandoned"),
    outcome: str | None = typer.Option(None, "--outcome"),
    notes: str | None = typer.Option(None, "--notes"),
    lessons: str | None = typer.Option(None, "--lessons"),
    emotion: str | None = typer.Option(None, "--emotion",
                                        help="flowing|curious|focused|satisfied|"
                                             "uncertain|strained|tired|frustrated|neutral"),
    emotion_note: str | None = typer.Option(None, "--feel"),
    idem: str | None = typer.Option(None, "--idem"),
) -> None:
    from .mem_channels.task import TaskChannel, TaskStateError, TaskNotFoundError
    conn = _get_atoms_conn()
    tc = TaskChannel(conn)
    try:
        tr = tc.finish(task_id, status=status, outcome_summary=outcome,
                       detailed_notes=notes, lessons=lessons,
                       agent_emotion=emotion, agent_emotion_note=emotion_note,
                       idempotency_id=idem or _utc_seed("finish"))
    except (TaskStateError, TaskNotFoundError) as e:
        _die(ExitCode.USAGE, str(e)); return
    if STATE.json_out:
        _emit_json({"ok": True, "task_id": tr.task_id, "status": tr.status}); return
    _print(tr.render())


# ─── sov qa ───────────────────────────────────────────────────────────────


qa_app = typer.Typer(help="◊ tests, hardening checks, and edge-case batteries")
app.add_typer(qa_app, name="qa")


@qa_app.command("report")
def qa_report_cmd(
    target: str | None = typer.Option(None, "--target", "-t",
                                       help="path to test (default: tests/)"),
    keyword: str | None = typer.Option(None, "-k", "--keyword"),
    score: bool = typer.Option(False, "--score", help="also print quality score"),
) -> None:
    from .qa import run_tests, score_test_report
    rpt = run_tests(target=target or "tests/", keyword=keyword)
    if STATE.json_out:
        out = {"ok": rpt.failed == 0 and rpt.errored == 0,
               "report": {"total": rpt.total, "passed": rpt.passed,
                          "failed": rpt.failed, "errored": rpt.errored,
                          "skipped": rpt.skipped, "pass_rate": rpt.pass_rate,
                          "duration_s": rpt.duration_s}}
        if score:
            out["score"] = score_test_report(rpt).to_dict()
        _emit_json(out); return
    _print(rpt.render())
    if score:
        _print(""); _print(score_test_report(rpt).render())


@qa_app.command("harden")
def qa_harden_cmd(
    module_path: str = typer.Argument(..., help="path to a .py file"),
    score: bool = typer.Option(False, "--score"),
) -> None:
    from .qa import harden_module, score_hardening_report
    rpt = harden_module(module_path)
    if STATE.json_out:
        out = {"ok": rpt.ok, "report": {
            "target": rpt.target,
            "weighted_score": rpt.weighted_score,
            "checks": [{"name": c.name, "passed": c.passed,
                        "weight": c.weight, "detail": c.detail}
                       for c in rpt.checks],
        }}
        if score:
            out["score"] = score_hardening_report(rpt).to_dict()
        _emit_json(out); return
    _print(rpt.render())
    if score:
        _print(""); _print(score_hardening_report(rpt).render())


@qa_app.command("edge-cases")
def qa_edge_cases_cmd(
    target: str = typer.Argument(...),
    profile: str = typer.Option("auto", "--profile"),
) -> None:
    from .qa import generate_edge_cases
    plan = generate_edge_cases(target, profile=profile)
    if STATE.json_out:
        _emit_json({"ok": True, "plan": {
            "target": plan.target,
            "cases": [{"name": c.name, "category": c.category,
                       "rationale": c.rationale,
                       "sample_inputs": c.sample_inputs,
                       "expected_outcome": c.expected_outcome}
                      for c in plan.cases],
        }}); return
    _print(plan.render())


# ─── sov steward ──────────────────────────────────────────────────────────


steward_app = typer.Typer(help="◊ hygiene & invariants across every channel")
app.add_typer(steward_app, name="steward")


@steward_app.command("report")
def steward_report_cmd() -> None:
    from .steward import audit_all
    conn = _get_atoms_conn()
    report = audit_all(conn)
    if STATE.json_out:
        _emit_json({"ok": report.ok, "report": report.to_dict()}); return
    _print(report.render())


@steward_app.command("conflicts")
def steward_conflicts_cmd() -> None:
    from .steward import find_conflicts
    conn = _get_atoms_conn()
    out = find_conflicts(conn)
    if STATE.json_out:
        _emit_json({"ok": True, "conflicts": out}); return
    if not out:
        _print("[green]✓ no conflicts[/green]"); return
    for c in out:
        _print(f"  · {c['subject']} :: {c['kind']} = {c['values']}")


@steward_app.command("stale-recalls")
def steward_stale_cmd() -> None:
    from .steward import find_stale_recalls
    conn = _get_atoms_conn()
    out = find_stale_recalls(conn)
    if STATE.json_out:
        _emit_json({"ok": True, "stale_recalls": out}); return
    if not out:
        _print("[green]✓ no stale recalls[/green]"); return
    for rid in out:
        _print(f"  · {rid}")


@steward_app.command("integrity")
def steward_integrity_cmd() -> None:
    """SQLite PRAGMA integrity_check across the atoms and palace databases.

    Read-only. Heavy: scans the whole file. Use for periodic verification
    or after a suspected disk issue. Returns OK on a healthy database.
    """
    import sqlite3 as _sql
    from .config import SETTINGS as _S
    results = {}
    for label, path in (("atoms", _S.paths.atoms_db),
                        ("palace", _S.paths.palace_db),
                        ("events", _S.paths.events_db)):
        if not path.exists():
            results[label] = "not present"
            continue
        try:
            c = _sql.connect(str(path))
            row = c.execute("PRAGMA integrity_check").fetchone()
            results[label] = row[0] if row else "no result"
            c.close()
        except Exception as e:
            results[label] = f"error: {e}"
    if STATE.json_out:
        _emit_json({"ok": all(v == "ok" for v in results.values()),
                    "checks": results}); return
    for label, val in results.items():
        glyph = "✓" if val == "ok" else "✗" if val != "not present" else " "
        _print(f"  {glyph} {label:<8}  {val}")


@steward_app.command("compact")
def steward_compact_cmd(
    confirm: bool = typer.Option(False, "--yes",
                                  help="acknowledge that VACUUM rewrites the DB file"),
) -> None:
    """VACUUM and ANALYZE the atoms DB to reclaim space and refresh stats.

    This rewrites the entire file. Safe but slow. Requires --yes.
    """
    if not confirm:
        _die(ExitCode.USAGE, "compact rewrites the DB file; pass --yes to proceed")
        return
    conn = _get_atoms_conn()
    conn.execute("VACUUM")
    conn.execute("ANALYZE")
    if STATE.json_out:
        _emit_json({"ok": True, "action": "vacuum+analyze"}); return
    _print("✓ vacuum + analyze complete")


# ─── sov home ─────────────────────────────────────────────────────────────


home_app = typer.Typer(help="◊ Aria's data layout — atrium, library, studio, hearth…")
app.add_typer(home_app, name="home")


@home_app.command("map")
def home_map_cmd() -> None:
    from .home import map_home
    m = map_home()
    if STATE.json_out:
        _emit_json({"ok": True, "home": m.to_dict()}); return
    _print(m.render())


@home_app.command("room")
def home_room_cmd(name: str = typer.Argument(...)) -> None:
    from .home import find_room
    r = find_room(name)
    if r is None:
        _die(ExitCode.USAGE, f"no room named {name!r}"); return
    if STATE.json_out:
        _emit_json({"ok": True, "room": {
            "name": r.name, "description": r.description,
            "purpose": r.purpose, "paths": [str(p) for p in r.paths],
            "exists": r.exists(), "size_bytes": r.size_bytes(),
            "file_count": r.file_count()}}); return
    _print(f"[bold]{r.name}[/bold] · {r.description}")
    _print(f"  purpose:  {r.purpose}")
    _print(f"  paths:    {', '.join(str(p) for p in r.paths)}")
    _print(f"  exists:   {r.exists()}")
    if r.exists():
        _print(f"  size:     {r.size_bytes()} bytes")
        _print(f"  files:    {r.file_count()}")


# ─── sov chat (cockpit launcher + conversation-mode toggle) ──────────────


# MOS-SURFACE S5 — keys are contracts. The bare `sov chat` invocation
# has been the cockpit launcher since v0.2.10. Adding subcommands under
# `chat` (status / request / cancel / resume) broke that contract in
# v0.2.18.0. v0.2.18.3 restores it via Typer's invoke_without_command
# callback: `sov chat` with no args launches the cockpit; `sov chat
# <subcommand>` routes to conversation-mode toggle commands.
chat_app = typer.Typer(
    help="◊ talk to Aria — bare invocation launches the cockpit; "
         "subcommands toggle conversation-mode",
    invoke_without_command=True,
    no_args_is_help=False,
)
app.add_typer(chat_app, name="chat")


@chat_app.callback()
def chat_callback(ctx: typer.Context) -> None:
    """When `sov chat` is invoked with no subcommand, launch the cockpit.

    With a subcommand (`status`, `request`, `cancel`, `resume`), route
    to that subcommand instead.
    """
    if ctx.invoked_subcommand is not None:
        return  # Typer will dispatch to the subcommand
    # Bare invocation — launch the cockpit
    try:
        from .cockpit import run as run_cockpit
    except ImportError as exc:
        _print(f"[red]✗ cockpit unavailable: {exc}[/red]")
        _print("  Try: re-run ./install.sh from the sovereign-agent source tree")
        _print("  (textual is a declared dependency; uv sync should pull it in)")
        raise typer.Exit(code=1)
    run_cockpit()


@chat_app.command("status")
def chat_status_cmd() -> None:
    from .interrupts import status as conv_status
    s = conv_status()
    if STATE.json_out:
        _emit_json({"ok": True, "state": {
            "requested": s.requested, "acknowledged": s.acknowledged,
            "resume_pending": s.resume_pending, "note": s.note,
            "is_paused": s.is_paused, "is_working": s.is_working,
        }}); return
    _print(s.render())


@chat_app.command("request")
def chat_request_cmd(
    note: str | None = typer.Option(None, "--note", "-n",
                                     help="short message for Aria"),
) -> None:
    """Ask Aria to pause at her next safe checkpoint."""
    from .interrupts import request_conversation
    s = request_conversation(note=note)
    if STATE.json_out:
        _emit_json({"ok": True, "requested": True, "state": s.__dict__}); return
    _print("✓ requested — Aria will pause at the next safe checkpoint")
    _print(s.render())


@chat_app.command("cancel")
def chat_cancel_cmd() -> None:
    """Cancel a pending conversation request."""
    from .interrupts import clear_conversation_request
    clear_conversation_request()
    if STATE.json_out:
        _emit_json({"ok": True, "cancelled": True}); return
    _print("✓ cancelled — Aria continues working")


@chat_app.command("resume")
def chat_resume_cmd() -> None:
    """Tell Aria to return to work."""
    from .interrupts import request_resume
    s = request_resume()
    if STATE.json_out:
        _emit_json({"ok": True, "resume_requested": True, "state": s.__dict__}); return
    _print("✓ resume requested — Aria will return to work on her next check")


@chat_app.command("send")
def chat_send_cmd(
    text: str = typer.Argument(..., help="What you want to say or ask"),
    no_llm: bool = typer.Option(
        False, "--no-llm",
        help="Skip the LLM interpreter; use the deterministic fallback only.",
    ),
    json_out_flag: bool = typer.Option(
        False, "--json", "-j",
        help="Emit the structured Turn as JSON instead of prose.",
    ),
) -> None:
    """◊ Talk to Aria in natural language. She decides what to do.

    Unlike `sov do`, `sov chat send` does NOT pattern-match keywords
    into a fixed directive taxonomy. It interprets the message via the
    LLM (with a deterministic fallback) and chooses among:

      • Conversation — save to memory channels and respond in voice
      • Work — name a project, run vetted commands, emit events
      • Recall — look up something Aria already knows
      • Ambiguous — ask ONE focused question; fall back to conversation

    Aria writes the commands. The operator gives English direction.
    Tier-3 (irreversible) actions still require a one-word `ok`
    confirm — but normal chat NEVER traps the operator in a yes/no
    prompt.

    Examples:
        sov chat send "good morning"
        sov chat send "my back is killing me"
        sov chat send "inventory the markdown in ~/AA-Erebo/Genesis-Seeds"
        sov chat send "what do I have on quantum coherence?"
        sov chat send "I updated genesis-seeds"

    Introduced: v0.2.19.0
    """
    import asyncio as _asyncio
    from .conversation import (
        converse,
        make_default_channel_writer,
        make_default_event_sink,
    )
    from .ollama_client import OllamaClient
    from .projects import ProjectStore

    store = ProjectStore(SETTINGS.paths.projects_dir)
    store.ensure_root()

    client = None
    if not no_llm:
        try:
            client = OllamaClient()
        except Exception:  # noqa: BLE001
            client = None

    turn = _asyncio.run(converse(
        text,
        ollama_client=client,
        project_store=store,
        channel_writer=make_default_channel_writer(),
        event_sink=make_default_event_sink(),
        surface="cli",
    ))

    if json_out_flag or STATE.json_out:
        payload = {
            "ok": True,
            "text": turn.text,
            "kind": turn.kind,
            "intent_kind": getattr(turn.intent, "kind", "?"),
            "messages": list(turn.messages),
            "executed": list(turn.result.executed_commands),
            "rationale": (
                getattr(turn.intent, "rationale", "") or
                getattr(turn.intent, "reply_hint", "")
            ),
        }
        _emit_json(payload)
        return

    for line in turn.messages:
        _print(line)

    if turn.has_pending and turn.result.pending is not None:
        pending = turn.result.pending
        _print(f"\n[bold]{pending.question}[/bold]")
        try:
            answer = input("  > ").strip()
        except (EOFError, KeyboardInterrupt):
            _print("[yellow]aborted[/yellow]")
            raise typer.Abort()
        followup = pending.callback(answer)
        for line in followup.messages:
            _print(line)


# ─── sov reward ────────────────────────────────────────────────────────────


reward_app = typer.Typer(help="◊ what Aria reinforces in herself")
app.add_typer(reward_app, name="reward")


@reward_app.command("log")
def reward_log_cmd(
    behavior: str = typer.Argument(..., help="behavior_kind (gap_found, uncertainty_named, ...)"),
    evidence: str = typer.Option(..., "--evidence", "-e"),
    intensity: int = typer.Option(1, "--intensity", "-i", help="1 small | 2 notable | 3 large"),
    note: str | None = typer.Option(None, "--note"),
    idem: str | None = typer.Option(None, "--idem"),
) -> None:
    from .mem_channels.reward import RewardChannel
    conn = _get_atoms_conn()
    rc = RewardChannel(conn)
    try:
        e = rc.record(behavior_kind=behavior, evidence=evidence,
                       intensity=intensity, note=note,
                       idempotency_id=idem or _utc_seed("reward"))
    except ValueError as err:
        _die(ExitCode.USAGE, str(err)); return
    if STATE.json_out:
        _emit_json({"ok": True, "reward_id": e.reward_id, "points": e.points,
                    "polarity": e.polarity}); return
    _print(f"  {e.render()}")


@reward_app.command("summary")
def reward_summary_cmd() -> None:
    from .mem_channels.reward import RewardChannel
    conn = _get_atoms_conn()
    rc = RewardChannel(conn)
    s = rc.summary()
    if STATE.json_out:
        _emit_json({"ok": True, "summary": {
            "total_points": s.total_points,
            "positive_points": s.positive_points,
            "corrective_points": s.corrective_points,
            "by_kind": s.by_kind,
        }}); return
    _print(s.render())


@reward_app.command("recent")
def reward_recent_cmd(limit: int = typer.Option(20, "-n", "--limit")) -> None:
    from .mem_channels.reward import RewardChannel
    conn = _get_atoms_conn()
    rc = RewardChannel(conn)
    items = rc.list_recent(limit=limit)
    if STATE.json_out:
        _emit_json({"ok": True, "rewards": [{
            "id": e.reward_id, "kind": e.behavior_kind, "points": e.points,
            "polarity": e.polarity, "evidence": e.evidence,
            "created_at": e.created_at,
        } for e in items]}); return
    for e in items:
        _print("  " + e.render())


@reward_app.command("kinds")
def reward_kinds_cmd() -> None:
    """List the constrained vocabulary of reward behaviours."""
    from .mem_channels.reward import POSITIVE_BEHAVIORS, CORRECTIVE_BEHAVIORS
    if STATE.json_out:
        _emit_json({"ok": True,
                    "positive": sorted(POSITIVE_BEHAVIORS),
                    "corrective": sorted(CORRECTIVE_BEHAVIORS)}); return
    _print("[bold]positive:[/bold]")
    for k in sorted(POSITIVE_BEHAVIORS):
        _print(f"  · {k}")
    _print("\n[bold]corrective:[/bold]")
    for k in sorted(CORRECTIVE_BEHAVIORS):
        _print(f"  · {k}")


# ─── sov lens ────────────────────────────────────────────────────────────


lens_app = typer.Typer(help="◊ three-channel impact lens (physical/mental/financial)")
app.add_typer(lens_app, name="lens")


@lens_app.command("show")
def lens_show_cmd() -> None:
    """Show the three lenses and what each one asks."""
    if STATE.json_out:
        _emit_json({"ok": True, "lenses": [
            {"name": "physical",  "asks": "bodies, environments, hardware, supply chains, sensory load"},
            {"name": "mental",    "asks": "attention, stress, autonomy, competence, trust, dignity"},
            {"name": "financial", "asks": "money, time, opportunity cost, debt, dependency, leverage"},
        ]}); return
    _print("[bold]physical[/bold]   bodies, environments, hardware, supply chains, sensory load")
    _print("[bold]mental[/bold]     attention, stress, autonomy, competence, trust, dignity")
    _print("[bold]financial[/bold]  money, time, opportunity cost, debt, dependency, leverage")


# ─── sov profile ───────────────────────────────────────────────────────────


profile_app = typer.Typer(help="◊ profile hot paths in Aria's runtime")
app.add_typer(profile_app, name="profile")


@profile_app.command("summary")
def profile_summary_cmd(
    days: int = typer.Option(1, "-d", "--days"),
) -> None:
    from .profiler import read_samples, summarize
    samples = read_samples(days=days)
    out = summarize(samples)
    if STATE.json_out:
        _emit_json({"ok": True, "samples": len(samples), "summary": out}); return
    if not samples:
        _print("[dim](no profile samples — enable with `sov profile enable`)[/dim]")
        return
    _print(f"profile · {len(samples)} sample(s) across {days} day(s)")
    _print("")
    t = Table(border_style="cyan")
    t.add_column("label", style="bold")
    t.add_column("count", justify="right")
    t.add_column("sum ms", justify="right")
    t.add_column("mean ms", justify="right")
    t.add_column("p95 ms", justify="right")
    t.add_column("max ms", justify="right")
    for label, row in out.items():
        t.add_row(label, str(row["count"]),
                  f"{row['sum_ms']:.1f}", f"{row['mean_ms']:.2f}",
                  f"{row['p95_ms']:.2f}", f"{row['max_ms']:.2f}")
    _print(t)


@profile_app.command("enable")
def profile_enable_cmd() -> None:
    """Enable disk-sample writing for this process (off by default)."""
    from .profiler import enable_disk_samples
    enable_disk_samples(True)
    if STATE.json_out:
        _emit_json({"ok": True, "disk_samples": True}); return
    _print("✓ disk samples enabled for this process")


@task_app.command("lessons")
def task_lessons_cmd(
    from_status: str | None = typer.Option("failed", "--from",
                                            help="status to draw lessons from (default: failed)"),
    limit: int = typer.Option(20, "-n", "--limit"),
) -> None:
    """Surface lessons from completed tasks — defaults to FAILED tasks.

    The negative-results view: what did Aria learn from work that didn't
    pan out? Re-reading these prevents her from re-trying paths she's
    already shown don't work. Pass --from success to see what worked.
    """
    from .mem_channels.task import TaskChannel
    conn = _get_atoms_conn()
    tc = TaskChannel(conn)
    items = tc.list_tasks(status=from_status, limit=limit) if from_status else tc.list_tasks(limit=limit)
    items_with_lessons = [t for t in items if t.lessons]
    if STATE.json_out:
        _emit_json({"ok": True, "lessons": [
            {"task_id": t.task_id, "title": t.title, "status": t.status,
             "emotion": t.agent_emotion, "lessons": t.lessons}
            for t in items_with_lessons
        ]}); return
    if not items_with_lessons:
        _print(f"[dim](no tasks with lessons in status={from_status!r})[/dim]"); return
    for t in items_with_lessons:
        glyph = {"success": "✓", "partial": "≈", "failed": "✗", "abandoned": "↩"}.get(t.status, "?")
        _print(f"{glyph} [bold]{t.title}[/bold]  [dim]({t.task_id})[/dim]")
        for line in (t.lessons or "").split("\n"):
            if line.strip():
                _print(f"    {line.strip()}")
        if t.agent_emotion:
            _print(f"    [dim]felt: {t.agent_emotion}[/dim]")
        _print("")


# ─── sov episode ───────────────────────────────────────────────────────────


episode_app = typer.Typer(help="◊ named, time-bounded sessions of activity")
app.add_typer(episode_app, name="episode")


@episode_app.command("list")
def episode_list_cmd(
    status: str | None = typer.Option(None, "--status",
                                       help="open|closed|archived"),
    include_archived: bool = typer.Option(False, "--include-archived"),
    limit: int = typer.Option(30, "-n", "--limit"),
) -> None:
    from .mem_channels.episodes import EpisodesChannel
    conn = _get_atoms_conn()
    ec = EpisodesChannel(conn)
    items = ec.list_episodes(status=status, include_archived=include_archived,
                              limit=limit)
    if STATE.json_out:
        _emit_json({"ok": True, "episodes": [
            {"id": e.episode_id, "title": e.title, "status": e.status,
             "significance": e.significance, "started_at": e.started_at,
             "closed_at": e.closed_at}
            for e in items
        ]}); return
    if not items:
        _print("[dim](no episodes — try `sov episode open <title>`)[/dim]"); return
    t = Table(title=f"◊ episodes · {len(items)}", border_style="cyan")
    t.add_column("title", style="bold")
    t.add_column("status"); t.add_column("sig", justify="center")
    t.add_column("members", justify="right")
    t.add_column("started", style="dim")
    t.add_column("id", style="dim")
    sig_label = {1: "·", 2: "▪", 3: "★"}
    for e in items:
        t.add_row(e.title[:40], e.status, sig_label.get(e.significance, "?"),
                  str(len(e.members)), e.started_at[:16], e.episode_id)
    _print(t)


@episode_app.command("show")
def episode_show_cmd(episode_id: str = typer.Argument(...)) -> None:
    from .mem_channels.episodes import EpisodesChannel, EpisodeNotFoundError
    conn = _get_atoms_conn()
    ec = EpisodesChannel(conn)
    try:
        e = ec.get(episode_id)
    except EpisodeNotFoundError:
        _die(ExitCode.USAGE, f"no episode: {episode_id}"); return
    if STATE.json_out:
        _emit_json({"ok": True, "episode": {
            "id": e.episode_id, "title": e.title, "status": e.status,
            "significance": e.significance, "started_at": e.started_at,
            "closed_at": e.closed_at, "summary": e.summary,
            "tags": e.tags,
            "members": [
                {"kind": m.member_kind, "ref": m.member_ref,
                 "role": m.role, "note": m.note}
                for m in e.members
            ],
        }}); return
    _print(e.render())


@episode_app.command("open")
def episode_open_cmd(
    title: str = typer.Argument(...),
    description: str | None = typer.Option(None, "--desc", "-d"),
    significance: int = typer.Option(1, "-s", "--significance",
                                      help="1 routine | 2 notable | 3 landmark"),
    tags: str | None = typer.Option(None, "--tags", help="comma-separated"),
    parent: str | None = typer.Option(None, "--parent"),
    idem: str | None = typer.Option(None, "--idem"),
) -> None:
    from .mem_channels.episodes import EpisodesChannel
    conn = _get_atoms_conn()
    ec = EpisodesChannel(conn)
    tag_list = [t.strip() for t in tags.split(",")] if tags else None
    try:
        e = ec.open(title=title, description=description,
                    significance=significance, tags=tag_list,
                    parent_episode_id=parent,
                    idempotency_id=idem or _utc_seed("episode"))
    except ValueError as err:
        _die(ExitCode.USAGE, str(err)); return
    if STATE.json_out:
        _emit_json({"ok": True, "episode_id": e.episode_id}); return
    _print(f"◯ opened {e.episode_id}\n  {e.title}")


@episode_app.command("close")
def episode_close_cmd(
    episode_id: str = typer.Argument(...),
    summary: str | None = typer.Option(None, "--summary", "-s"),
) -> None:
    from .mem_channels.episodes import EpisodesChannel, EpisodeNotFoundError
    conn = _get_atoms_conn()
    ec = EpisodesChannel(conn)
    try:
        e = ec.close(episode_id, summary=summary)
    except EpisodeNotFoundError:
        _die(ExitCode.USAGE, f"no episode: {episode_id}"); return
    if STATE.json_out:
        _emit_json({"ok": True, "episode_id": e.episode_id,
                    "status": e.status}); return
    _print(f"● closed {e.episode_id}")


@episode_app.command("add")
def episode_add_cmd(
    episode_id: str = typer.Argument(...),
    kind: str = typer.Argument(..., help="atom|task|recall|person|fact|reward"),
    ref: str = typer.Argument(..., help="the referenced id"),
    role: str | None = typer.Option(None, "--role"),
    note: str | None = typer.Option(None, "--note"),
) -> None:
    from .mem_channels.episodes import EpisodesChannel
    conn = _get_atoms_conn()
    ec = EpisodesChannel(conn)
    try:
        m = ec.add_member(episode_id, member_kind=kind, member_ref=ref,
                          role=role, note=note)
    except (ValueError, KeyError) as err:
        _die(ExitCode.USAGE, str(err)); return
    if STATE.json_out:
        _emit_json({"ok": True, "member_id": m.member_id}); return
    _print(f"  ↳ added {kind} {ref}" + (f" [{role}]" if role else ""))


@episode_app.command("search")
def episode_search_cmd(
    query: str = typer.Argument(...),
    limit: int = typer.Option(10, "-n", "--limit"),
) -> None:
    from .mem_channels.episodes import EpisodesChannel
    conn = _get_atoms_conn()
    ec = EpisodesChannel(conn)
    items = ec.search(query, limit=limit)
    if STATE.json_out:
        _emit_json({"ok": True, "matches": [
            {"id": e.episode_id, "title": e.title, "status": e.status}
            for e in items
        ]}); return
    if not items:
        _print("[dim](no matches)[/dim]"); return
    for e in items:
        _print(f"  · [bold]{e.title}[/bold]  "
               f"[dim]({e.episode_id}) {e.status}[/dim]")


@episode_app.command("audit")
def episode_audit_cmd() -> None:
    from .mem_channels.episodes import EpisodesChannel
    conn = _get_atoms_conn()
    ec = EpisodesChannel(conn)
    a = ec.audit()
    if STATE.json_out:
        _emit_json({"ok": a.ok, "audit": {
            "total": a.total, "open": a.open, "closed": a.closed,
            "archived": a.archived, "dangling_members": a.dangling_members,
            "long_open": a.long_open,
        }}); return
    glyph = "✓" if a.ok else "✗"
    _print(f"{glyph} episode audit · ok={a.ok} · total={a.total}")
    _print(f"  open: {a.open}  closed: {a.closed}  archived: {a.archived}")
    if a.dangling_members:
        _print(f"  [red]dangling members: {a.dangling_members}[/red]")
    if a.long_open:
        _print(f"  [yellow]open > 30 days: {a.long_open}[/yellow]")


# ─── people as-of (bitemporal query) ───────────────────────────────────────


@people_app.command("as-of")
def people_as_of_cmd(
    name: str = typer.Argument(...),
    date: str = typer.Argument(..., help="ISO date, e.g. 2025-08-01T00:00:00Z"),
    kind: str | None = typer.Option(None, "--kind"),
    include_pending: bool = typer.Option(False, "--include-pending"),
) -> None:
    """Show what Aria believed about <name> on <date>.

    Bitemporal honesty: filters facts by (a) created on or before <date>,
    (b) not yet retracted as of <date>, (c) valid window includes <date>.
    """
    from .mem_channels.people import PeopleChannel
    conn = _get_atoms_conn()
    pc = PeopleChannel(conn)
    p = pc.resolve(name)
    if p is None:
        _die(ExitCode.USAGE, f"unknown person: {name!r}"); return
    facts = pc.as_of_facts(p.person_id, date, kind=kind,
                            include_pending=include_pending)
    if STATE.json_out:
        _emit_json({"ok": True, "as_of": date, "person_id": p.person_id,
                    "facts": [{"kind": f.kind, "value": f.value,
                                "status": f.status, "confidence": f.confidence}
                               for f in facts]}); return
    if not facts:
        _print(f"[dim](no facts about {p.canonical_name} known on {date})[/dim]")
        return
    _print(f"[bold]{p.canonical_name}[/bold] as of {date}:")
    for f in facts:
        _print(f"  {f.kind:<20}  {f.value}  [{f.status}]")


# ═══════════════════════════════════════════════════════════════════════════
# v0.2.18.0 sub-apps
# ═══════════════════════════════════════════════════════════════════════════


# ─── sov reasoning ─────────────────────────────────────────────────────────

reasoning_app = typer.Typer(help="◊ durable chain-of-thought traces")
app.add_typer(reasoning_app, name="reasoning")


@reasoning_app.command("open")
def reasoning_open_cmd(
    title: str = typer.Argument(...),
    related_task: str | None = typer.Option(None, "--task"),
    parent: str | None = typer.Option(None, "--parent"),
    idem: str | None = typer.Option(None, "--idem"),
) -> None:
    from .mem_channels.reasoning import ReasoningChannel
    conn = _get_atoms_conn()
    rc = ReasoningChannel(conn)
    try:
        t = rc.open(title=title, related_task_id=related_task,
                    parent_trace_id=parent,
                    idempotency_id=idem or _utc_seed("reasoning"))
    except ValueError as e:
        _die(ExitCode.USAGE, str(e)); return
    if STATE.json_out:
        _emit_json({"ok": True, "trace_id": t.trace_id}); return
    _print(f"◯ opened {t.trace_id}\n  {t.title}")


@reasoning_app.command("step")
def reasoning_step_cmd(
    trace_id: str = typer.Argument(...),
    kind: str = typer.Argument(..., help="observation|hypothesis|evidence|counter_evidence|revision|note"),
    content: str = typer.Argument(...),
    confidence: float = typer.Option(0.5, "-c", "--confidence"),
    sources: str | None = typer.Option(None, "--sources", help="comma-separated ids"),
) -> None:
    from .mem_channels.reasoning import ReasoningChannel, TraceNotFoundError, TraceStateError
    conn = _get_atoms_conn()
    rc = ReasoningChannel(conn)
    src_list = [s.strip() for s in sources.split(",")] if sources else []
    try:
        s = rc.add_step(trace_id, step_kind=kind, content=content,
                        confidence=confidence, sources=src_list)
    except (ValueError, TraceNotFoundError, TraceStateError) as e:
        _die(ExitCode.USAGE, str(e)); return
    if STATE.json_out:
        _emit_json({"ok": True, "step_id": s.step_id,
                    "step_number": s.step_number}); return
    _print(s.render())


@reasoning_app.command("conclude")
def reasoning_conclude_cmd(
    trace_id: str = typer.Argument(...),
    conclusion: str = typer.Argument(...),
    confidence: float = typer.Option(0.7, "-c", "--confidence"),
) -> None:
    from .mem_channels.reasoning import ReasoningChannel, TraceNotFoundError
    conn = _get_atoms_conn()
    rc = ReasoningChannel(conn)
    try:
        t = rc.conclude(trace_id, conclusion=conclusion, confidence=confidence)
    except TraceNotFoundError:
        _die(ExitCode.USAGE, f"no trace: {trace_id}"); return
    if STATE.json_out:
        _emit_json({"ok": True, "trace_id": t.trace_id,
                    "confidence": t.confidence}); return
    _print(f"● concluded {t.trace_id} ({t.confidence:.2f})")
    _print(f"  ⇒ {conclusion}")


@reasoning_app.command("show")
def reasoning_show_cmd(trace_id: str = typer.Argument(...)) -> None:
    from .mem_channels.reasoning import ReasoningChannel, TraceNotFoundError
    conn = _get_atoms_conn()
    rc = ReasoningChannel(conn)
    try:
        t = rc.get(trace_id)
    except TraceNotFoundError:
        _die(ExitCode.USAGE, f"no trace: {trace_id}"); return
    if STATE.json_out:
        _emit_json({"ok": True, "trace": {
            "id": t.trace_id, "title": t.title, "status": t.status,
            "confidence": t.confidence, "conclusion": t.conclusion,
            "steps": [
                {"n": s.step_number, "kind": s.step_kind,
                 "content": s.content, "confidence": s.confidence}
                for s in t.steps
            ],
        }}); return
    _print(t.render())


@reasoning_app.command("list")
def reasoning_list_cmd(
    status: str | None = typer.Option(None, "--status"),
    limit: int = typer.Option(20, "-n", "--limit"),
) -> None:
    from .mem_channels.reasoning import ReasoningChannel
    conn = _get_atoms_conn()
    rc = ReasoningChannel(conn)
    items = rc.list_traces(status=status, limit=limit)
    if STATE.json_out:
        _emit_json({"ok": True, "traces": [
            {"id": t.trace_id, "title": t.title, "status": t.status,
             "confidence": t.confidence}
            for t in items
        ]}); return
    if not items:
        _print("[dim](no traces)[/dim]"); return
    for t in items:
        glyph = {"open":"◯","concluded":"●","abandoned":"↩"}.get(t.status,"?")
        _print(f"  {glyph} [bold]{t.title}[/bold]  [dim]({t.trace_id}) {t.status}[/dim]")


@reasoning_app.command("search")
def reasoning_search_cmd(query: str = typer.Argument(...)) -> None:
    from .mem_channels.reasoning import ReasoningChannel
    conn = _get_atoms_conn()
    rc = ReasoningChannel(conn)
    items = rc.search(query)
    if STATE.json_out:
        _emit_json({"ok": True, "matches": [
            {"id": t.trace_id, "title": t.title} for t in items
        ]}); return
    if not items:
        _print("[dim](no matches)[/dim]"); return
    for t in items:
        _print(f"  · {t.title}  [dim]({t.trace_id})[/dim]")


@reasoning_app.command("audit")
def reasoning_audit_cmd() -> None:
    from .mem_channels.reasoning import ReasoningChannel
    conn = _get_atoms_conn()
    rc = ReasoningChannel(conn)
    a = rc.audit()
    if STATE.json_out:
        _emit_json({"ok": a.ok, "audit": {
            "total": a.total, "open": a.open, "concluded": a.concluded,
            "abandoned": a.abandoned, "long_open": a.long_open,
            "high_confidence_no_evidence": a.high_confidence_no_evidence,
        }}); return
    glyph = "✓" if a.ok else "✗"
    _print(f"{glyph} reasoning audit · total={a.total}")
    _print(f"  open: {a.open}  concluded: {a.concluded}  abandoned: {a.abandoned}")
    if a.long_open:
        _print(f"  [yellow]open > 7 days: {a.long_open}[/yellow]")
    if a.high_confidence_no_evidence:
        _print(f"  [red]high-confidence conclusions without evidence: {a.high_confidence_no_evidence}[/red]")


# ─── sov gaps ──────────────────────────────────────────────────────────────

gaps_app = typer.Typer(help="◊ known unknowns Aria wants to learn")
app.add_typer(gaps_app, name="gaps")


@gaps_app.command("open")
def gaps_open_cmd(
    title: str = typer.Argument(...),
    description: str | None = typer.Option(None, "--desc", "-d"),
    domain: str | None = typer.Option(None, "--domain"),
    subject: str | None = typer.Option(None, "--subject"),
    priority: int = typer.Option(2, "-p", "--priority"),
    idem: str | None = typer.Option(None, "--idem"),
) -> None:
    from .mem_channels.gaps import GapsChannel
    conn = _get_atoms_conn()
    gc = GapsChannel(conn)
    try:
        g = gc.open(title=title, description=description, domain=domain,
                    subject_ref=subject, priority=priority,
                    idempotency_id=idem or _utc_seed("gap"))
    except ValueError as e:
        _die(ExitCode.USAGE, str(e)); return
    if STATE.json_out:
        _emit_json({"ok": True, "gap_id": g.gap_id}); return
    _print(f"◯ gap opened {g.gap_id}")


@gaps_app.command("investigate")
def gaps_investigate_cmd(gap_id: str = typer.Argument(...)) -> None:
    from .mem_channels.gaps import GapsChannel, GapNotFoundError, GapStateError
    conn = _get_atoms_conn()
    gc = GapsChannel(conn)
    try:
        g = gc.investigate(gap_id)
    except (GapNotFoundError, GapStateError) as e:
        _die(ExitCode.USAGE, str(e)); return
    if STATE.json_out:
        _emit_json({"ok": True, "gap_id": g.gap_id, "status": g.status}); return
    _print(f"↻ investigating {g.gap_id}")


@gaps_app.command("close")
def gaps_close_cmd(
    gap_id: str = typer.Argument(...),
    resolution: str = typer.Option(..., "-r", "--resolution"),
    related_task: str | None = typer.Option(None, "--task"),
) -> None:
    from .mem_channels.gaps import GapsChannel, GapNotFoundError
    conn = _get_atoms_conn()
    gc = GapsChannel(conn)
    try:
        g = gc.close(gap_id, resolution=resolution, related_task_id=related_task)
    except (ValueError, GapNotFoundError) as e:
        _die(ExitCode.USAGE, str(e)); return
    if STATE.json_out:
        _emit_json({"ok": True, "gap_id": g.gap_id, "status": g.status}); return
    _print(f"✓ closed {g.gap_id}")


@gaps_app.command("shelve")
def gaps_shelve_cmd(
    gap_id: str = typer.Argument(...),
    reason: str | None = typer.Option(None, "-r", "--reason"),
) -> None:
    from .mem_channels.gaps import GapsChannel
    conn = _get_atoms_conn()
    gc = GapsChannel(conn)
    gc.shelve(gap_id, reason=reason)
    _print(f"▢ shelved {gap_id}")


@gaps_app.command("list")
def gaps_list_cmd(
    status: str | None = typer.Option(None, "--status"),
    priority: int | None = typer.Option(None, "-p", "--priority"),
    limit: int = typer.Option(30, "-n", "--limit"),
) -> None:
    from .mem_channels.gaps import GapsChannel
    conn = _get_atoms_conn()
    gc = GapsChannel(conn)
    items = gc.list_gaps(status=status, priority=priority, limit=limit)
    if STATE.json_out:
        _emit_json({"ok": True, "gaps": [
            {"id": g.gap_id, "title": g.title, "status": g.status,
             "priority": g.priority, "domain": g.domain}
            for g in items
        ]}); return
    if not items:
        _print("[dim](no gaps)[/dim]"); return
    glyph = {"open":"◯","investigating":"↻","closed":"✓","shelved":"▢"}
    for g in items:
        _print(f"  {glyph.get(g.status,'?')} {'★'*g.priority:<3} "
               f"[bold]{g.title}[/bold]  [dim]({g.gap_id})[/dim]")


@gaps_app.command("search")
def gaps_search_cmd(query: str = typer.Argument(...)) -> None:
    from .mem_channels.gaps import GapsChannel
    conn = _get_atoms_conn()
    gc = GapsChannel(conn)
    items = gc.search(query)
    if STATE.json_out:
        _emit_json({"ok": True, "matches": [
            {"id": g.gap_id, "title": g.title} for g in items
        ]}); return
    if not items:
        _print("[dim](no matches)[/dim]"); return
    for g in items:
        _print(f"  · {g.title}  [dim]({g.gap_id})[/dim]")


@gaps_app.command("stats")
def gaps_stats_cmd() -> None:
    from .mem_channels.gaps import GapsChannel
    conn = _get_atoms_conn()
    gc = GapsChannel(conn)
    s = gc.stats()
    if STATE.json_out:
        _emit_json({"ok": True, "stats": {
            "total": s.total, "open": s.open, "investigating": s.investigating,
            "closed": s.closed, "shelved": s.shelved,
            "close_rate": s.close_rate, "by_priority": s.by_priority,
        }}); return
    _print(s.render())


# ─── sov relationships ─────────────────────────────────────────────────────

rel_app = typer.Typer(help="◊ typed edges between people (Tier 3)")
app.add_typer(rel_app, name="relationships")


@rel_app.command("connect")
def rel_connect_cmd(
    from_name: str = typer.Argument(..., help="canonical name or alias"),
    kind: str = typer.Argument(...),
    to_name: str = typer.Argument(...),
    label: str | None = typer.Option(None, "--label"),
    since: str | None = typer.Option(None, "--since"),
    until: str | None = typer.Option(None, "--until"),
    note: str | None = typer.Option(None, "--note"),
    source: str = typer.Option("operator", "--source"),
    idem: str | None = typer.Option(None, "--idem"),
) -> None:
    from .mem_channels.people import PeopleChannel
    from .mem_channels.relationships import RelationshipsChannel
    conn = _get_atoms_conn()
    pc = PeopleChannel(conn); rc = RelationshipsChannel(conn)
    a = pc.resolve(from_name); b = pc.resolve(to_name)
    if a is None: _die(ExitCode.USAGE, f"unknown person: {from_name!r}"); return
    if b is None: _die(ExitCode.USAGE, f"unknown person: {to_name!r}"); return
    try:
        r = rc.connect(from_person_id=a.person_id, to_person_id=b.person_id,
                       kind=kind, label=label, started_at=since, ended_at=until,
                       note=note, source=source,
                       idempotency_id=idem or _utc_seed("rel"))
    except ValueError as e:
        _die(ExitCode.USAGE, str(e)); return
    if STATE.json_out:
        _emit_json({"ok": True, "relationship_id": r.relationship_id,
                    "status": r.status}); return
    _print(r.render())


@rel_app.command("confirm")
def rel_confirm_cmd(rel_id: str = typer.Argument(...)) -> None:
    from .mem_channels.relationships import RelationshipsChannel
    conn = _get_atoms_conn(); rc = RelationshipsChannel(conn)
    r = rc.confirm(rel_id)
    _print(f"✓ confirmed {r.relationship_id}")


@rel_app.command("retract")
def rel_retract_cmd(
    rel_id: str = typer.Argument(...),
    reason: str | None = typer.Option(None, "-r", "--reason"),
) -> None:
    from .mem_channels.relationships import RelationshipsChannel
    conn = _get_atoms_conn(); rc = RelationshipsChannel(conn)
    r = rc.retract(rel_id, reason=reason)
    _print(f"↩ retracted {r.relationship_id}")


@rel_app.command("path")
def rel_path_cmd(
    from_name: str = typer.Argument(...),
    to_name: str = typer.Argument(...),
    max_depth: int = typer.Option(6, "--max-depth"),
) -> None:
    from .mem_channels.people import PeopleChannel
    from .mem_channels.relationships import RelationshipsChannel
    conn = _get_atoms_conn()
    pc = PeopleChannel(conn); rc = RelationshipsChannel(conn)
    a = pc.resolve(from_name); b = pc.resolve(to_name)
    if a is None: _die(ExitCode.USAGE, f"unknown: {from_name!r}"); return
    if b is None: _die(ExitCode.USAGE, f"unknown: {to_name!r}"); return
    path = rc.shortest_path(a.person_id, b.person_id, max_depth=max_depth)
    if STATE.json_out:
        _emit_json({"ok": path is not None, "path": path}); return
    if path is None:
        _print(f"[dim](no path within {max_depth} hops)[/dim]"); return
    # Render with names
    name_map = {a.person_id: a.canonical_name, b.person_id: b.canonical_name}
    for pid in path:
        if pid not in name_map:
            p = pc.get(pid)
            name_map[pid] = p.canonical_name if p else pid
    _print(" → ".join(name_map.get(pid, pid) for pid in path))
    _print(f"[dim]({len(path) - 1} hop{'s' if len(path) > 2 else ''})[/dim]")


@rel_app.command("neighbours")
def rel_neighbours_cmd(
    name: str = typer.Argument(...),
    kind: str | None = typer.Option(None, "--kind"),
    include_inactive: bool = typer.Option(False, "--all"),
) -> None:
    from .mem_channels.people import PeopleChannel
    from .mem_channels.relationships import RelationshipsChannel
    conn = _get_atoms_conn()
    pc = PeopleChannel(conn); rc = RelationshipsChannel(conn)
    p = pc.resolve(name)
    if p is None: _die(ExitCode.USAGE, f"unknown: {name!r}"); return
    rels = rc.neighbours_of(p.person_id, kind=kind, active_only=not include_inactive)
    if STATE.json_out:
        _emit_json({"ok": True, "person": p.canonical_name,
                    "relationships": [
                        {"id": r.relationship_id, "from": r.from_person_id,
                         "to": r.to_person_id, "kind": r.kind,
                         "status": r.status}
                        for r in rels
                    ]}); return
    if not rels:
        _print(f"[dim](no relationships for {name})[/dim]"); return
    _print(f"[bold]{p.canonical_name}[/bold]'s relationships ({len(rels)}):")
    for r in rels:
        other_id = r.other_end(p.person_id)
        other = pc.get(other_id) if other_id else None
        other_name = other.canonical_name if other else other_id
        arrow = " ↔ " if r.kind in {"colleague","family","friend","collaborator","spouse","rival","acquaintance"} else " → "
        if r.from_person_id == p.person_id:
            _print(f"  {arrow.strip()} [{r.kind}] {other_name}  [dim]({r.relationship_id})[/dim]")
        else:
            _print(f"  ←[{r.kind}] {other_name}  [dim]({r.relationship_id})[/dim]")


# ─── sov commitments ───────────────────────────────────────────────────────

cm_app = typer.Typer(help="◊ promises with due dates")
app.add_typer(cm_app, name="commitments")


@cm_app.command("make")
def cm_make_cmd(
    title: str = typer.Argument(...),
    by_: str = typer.Option("aria", "--by"),
    to: str = typer.Option("operator", "--to"),
    due: str | None = typer.Option(None, "--due", help="ISO date"),
    description: str | None = typer.Option(None, "--desc", "-d"),
    priority: int = typer.Option(2, "-p", "--priority"),
    task: str | None = typer.Option(None, "--task"),
    idem: str | None = typer.Option(None, "--idem"),
) -> None:
    from .mem_channels.commitments import CommitmentsChannel
    conn = _get_atoms_conn()
    cc = CommitmentsChannel(conn)
    try:
        c = cc.make(title=title, committed_by=by_, committed_to=to,
                    description=description, due_at=due, priority=priority,
                    related_task_id=task,
                    idempotency_id=idem or _utc_seed("commitment"))
    except ValueError as e:
        _die(ExitCode.USAGE, str(e)); return
    if STATE.json_out:
        _emit_json({"ok": True, "commitment_id": c.commitment_id}); return
    _print(f"◯ made {c.commitment_id}\n  {c.title}")


@cm_app.command("start")
def cm_start_cmd(cid: str = typer.Argument(...)) -> None:
    from .mem_channels.commitments import CommitmentsChannel
    conn = _get_atoms_conn(); cc = CommitmentsChannel(conn)
    c = cc.start(cid)
    _print(f"↻ in_progress {c.commitment_id}")


@cm_app.command("keep")
def cm_keep_cmd(
    cid: str = typer.Argument(...),
    resolution: str | None = typer.Option(None, "-r", "--resolution"),
) -> None:
    from .mem_channels.commitments import CommitmentsChannel
    conn = _get_atoms_conn(); cc = CommitmentsChannel(conn)
    c = cc.keep(cid, resolution=resolution)
    _print(f"✓ kept {c.commitment_id}")


@cm_app.command("break")
def cm_break_cmd(
    cid: str = typer.Argument(...),
    resolution: str = typer.Option(..., "-r", "--resolution"),
) -> None:
    from .mem_channels.commitments import CommitmentsChannel
    conn = _get_atoms_conn(); cc = CommitmentsChannel(conn)
    try:
        c = cc.break_(cid, resolution=resolution)
    except ValueError as e:
        _die(ExitCode.USAGE, str(e)); return
    _print(f"✗ broken {c.commitment_id}\n  resolution: {resolution}")


@cm_app.command("release")
def cm_release_cmd(
    cid: str = typer.Argument(...),
    resolution: str | None = typer.Option(None, "-r", "--resolution"),
) -> None:
    from .mem_channels.commitments import CommitmentsChannel
    conn = _get_atoms_conn(); cc = CommitmentsChannel(conn)
    c = cc.release(cid, resolution=resolution)
    _print(f"↩ released {c.commitment_id}")


@cm_app.command("due-soon")
def cm_due_soon_cmd(
    within: int = typer.Option(7, "--within", help="days"),
) -> None:
    from .mem_channels.commitments import CommitmentsChannel
    conn = _get_atoms_conn(); cc = CommitmentsChannel(conn)
    items = cc.due_soon(within_days=within)
    if STATE.json_out:
        _emit_json({"ok": True, "commitments": [
            {"id": c.commitment_id, "title": c.title, "due_at": c.due_at,
             "priority": c.priority, "status": c.status}
            for c in items
        ]}); return
    if not items:
        _print("[dim](nothing due in window)[/dim]"); return
    for c in items:
        _print(f"  ◯ {'★'*c.priority:<3} due {c.due_at[:10]}  [bold]{c.title}[/bold]")


@cm_app.command("overdue")
def cm_overdue_cmd() -> None:
    from .mem_channels.commitments import CommitmentsChannel
    conn = _get_atoms_conn(); cc = CommitmentsChannel(conn)
    items = cc.overdue()
    if STATE.json_out:
        _emit_json({"ok": True, "overdue": [
            {"id": c.commitment_id, "title": c.title, "due_at": c.due_at}
            for c in items
        ]}); return
    if not items:
        _print("[dim](nothing overdue)[/dim]"); return
    for c in items:
        _print(f"  [red]⚠[/red] {c.title}  [dim]due {c.due_at[:10]}[/dim]")


@cm_app.command("stats")
def cm_stats_cmd() -> None:
    from .mem_channels.commitments import CommitmentsChannel
    conn = _get_atoms_conn(); cc = CommitmentsChannel(conn)
    s = cc.stats()
    if STATE.json_out:
        _emit_json({"ok": True, "stats": {
            "total": s.total, "open": s.open, "in_progress": s.in_progress,
            "kept": s.kept, "broken": s.broken, "released": s.released,
            "overdue_active": s.overdue_active, "keep_rate": s.keep_rate,
        }}); return
    _print(s.render())


# ─── sov heartbeat ─────────────────────────────────────────────────────────

hb_app = typer.Typer(help="♥ Aria's liveness pulse")
app.add_typer(hb_app, name="heartbeat")


@hb_app.command("pulse")
def hb_pulse_cmd(
    message: str = typer.Argument(...),
    task: str | None = typer.Option(None, "--task"),
    episode: str | None = typer.Option(None, "--episode"),
    emotion: str | None = typer.Option(None, "--emotion"),
    note: str | None = typer.Option(None, "--note"),
    idem: str | None = typer.Option(None, "--idem"),
) -> None:
    from .mem_channels.heartbeat import HeartbeatChannel
    conn = _get_atoms_conn()
    hc = HeartbeatChannel(conn)
    try:
        b = hc.pulse(message=message, current_task_id=task,
                     current_episode_id=episode, agent_emotion=emotion,
                     agent_emotion_note=note,
                     idempotency_id=idem or _utc_seed("heartbeat"))
    except ValueError as e:
        _die(ExitCode.USAGE, str(e)); return
    if STATE.json_out:
        _emit_json({"ok": True, "beat_id": b.beat_id}); return
    _print(b.render())


@hb_app.command("recent")
def hb_recent_cmd(
    limit: int = typer.Option(10, "-n", "--limit"),
) -> None:
    from .mem_channels.heartbeat import HeartbeatChannel
    conn = _get_atoms_conn()
    hc = HeartbeatChannel(conn)
    beats = hc.recent(limit=limit)
    if STATE.json_out:
        _emit_json({"ok": True, "beats": [
            {"id": b.beat_id, "message": b.message,
             "emotion": b.agent_emotion, "created_at": b.created_at}
            for b in beats
        ]}); return
    if not beats:
        _print("[dim](no heartbeats yet)[/dim]"); return
    age = hc.last_pulse_age_seconds()
    if age is not None:
        if age < 60:
            age_str = f"{age:.0f}s ago"
        elif age < 3600:
            age_str = f"{age/60:.0f}m ago"
        elif age < 86400:
            age_str = f"{age/3600:.1f}h ago"
        else:
            age_str = f"{age/86400:.1f}d ago"
        _print(f"[dim]last pulse: {age_str}[/dim]\n")
    for b in beats:
        _print(b.render())
        _print("")


# ─── sov constitution ──────────────────────────────────────────────────────

const_app = typer.Typer(help="◊ Aria's seven commitments")
app.add_typer(const_app, name="constitution")


@const_app.command("list")
def const_list_cmd() -> None:
    from .constitution import list_all
    items = list_all()
    if STATE.json_out:
        _emit_json({"ok": True, "commitments": [
            {"id": c.id, "title": c.title, "statement": c.statement,
             "introduced_in": c.introduced_in, "has_check": c.check is not None}
            for c in items
        ]}); return
    _print("[bold]Aria's seven commitments[/bold]\n")
    for c in items:
        mark = "[green]●[/green]" if c.check is not None else "[dim]○[/dim]"
        _print(f"{mark} [bold]{c.id}[/bold] — {c.title}")
        _print(f"   {c.statement}")
        _print("")


@const_app.command("check")
def const_check_cmd(
    tier: int = typer.Option(0, "--tier"),
    idem: str | None = typer.Option(None, "--idem"),
    confidence: float = typer.Option(0.5, "--confidence"),
    source: str | None = typer.Option(None, "--source"),
    delegated_to: str | None = typer.Option(None, "--delegated-to"),
    kind: str = typer.Option("manual_check", "--kind"),
) -> None:
    """Evaluate a hypothetical action against all seven commitments."""
    from .constitution import check_action
    action = {
        "tier": tier, "idempotency_id": idem, "confidence": confidence,
        "source": source, "delegated_to": delegated_to, "kind": kind,
    }
    report = check_action(action)
    if STATE.json_out:
        _emit_json({"ok": report.passed, "report": report.to_dict()}); return
    _print(report.render())
    if not report.passed:
        raise typer.Exit(code=1)


# ─── sov archive ───────────────────────────────────────────────────────────

archive_app = typer.Typer(help="◊ content-addressed durable blob store")
app.add_typer(archive_app, name="archive")


@archive_app.command("stats")
def archive_stats_cmd() -> None:
    from .archive import ContentArchive
    conn = _get_atoms_conn()
    arc = ContentArchive(conn)
    s = arc.stats()
    if STATE.json_out:
        _emit_json({"ok": True, "stats": {
            "total_objects": s.total_objects,
            "total_bytes": s.total_bytes,
            "sealed_objects": s.sealed_objects,
            "unique_content_types": s.unique_content_types,
            "avg_refcount": s.avg_refcount,
        }}); return
    _print(f"archive · {s.total_objects} objects · "
           f"{s.total_bytes:,} bytes total")
    _print(f"  sealed: {s.sealed_objects}  types: {s.unique_content_types}  "
           f"avg refs: {s.avg_refcount:.1f}")


@archive_app.command("verify")
def archive_verify_cmd(
    content_hash: str | None = typer.Argument(None, help="omit to verify all"),
) -> None:
    from .archive import ContentArchive
    conn = _get_atoms_conn()
    arc = ContentArchive(conn)
    if content_hash:
        ok = arc.verify(content_hash)
        if STATE.json_out:
            _emit_json({"ok": ok, "content_hash": content_hash}); return
        glyph = "✓" if ok else "✗"
        _print(f"{glyph} {content_hash[:12]}…")
        if not ok:
            raise typer.Exit(code=1)
    else:
        results = arc.verify_all()
        bad = [h for h, ok in results.items() if not ok]
        if STATE.json_out:
            _emit_json({"ok": len(bad) == 0,
                        "verified": len(results),
                        "tampered": bad}); return
        _print(f"verified {len(results)} object(s)")
        if bad:
            _print(f"[red]✗ {len(bad)} tampered:[/red]")
            for h in bad:
                _print(f"  {h}")
            raise typer.Exit(code=1)


@archive_app.command("gc")
def archive_gc_cmd(
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Delete unreferenced, unsealed blobs."""
    from .archive import ContentArchive
    conn = _get_atoms_conn()
    arc = ContentArchive(conn)
    removed = arc.gc(dry_run=dry_run)
    if STATE.json_out:
        _emit_json({"ok": True, "would_remove" if dry_run else "removed": len(removed)}); return
    label = "would remove" if dry_run else "removed"
    _print(f"{label} {len(removed)} blob(s)")


# ─── sov shards ────────────────────────────────────────────────────────────

shards_app = typer.Typer(help="◊ per-channel sharded storage")
app.add_typer(shards_app, name="shards")


@shards_app.command("list")
def shards_list_cmd() -> None:
    from .shards import list_shards
    items = list_shards()
    if STATE.json_out:
        _emit_json({"ok": True, "shards": items}); return
    if not items:
        _print("[dim](no shards configured — all channels use trunk atoms.db)[/dim]")
        return
    for sh in items:
        glyph = "●" if sh["exists"] else "○"
        size = f"{sh['size_bytes']:,} bytes" if sh["exists"] else "(not yet created)"
        _print(f"  {glyph} [bold]{sh['channel']}[/bold]  {size}")
        _print(f"      {sh['path']}")
        if sh["exists"]:
            _print(f"      tables: {sh['table_count']}")


@shards_app.command("add")
def shards_add_cmd(
    channel: str = typer.Argument(...),
    path: str | None = typer.Option(None, "--path",
                                     help="relative to data_dir; "
                                          "default shards/<channel>.db"),
) -> None:
    """Declare a channel should live in its own DB. Migration is separate."""
    from .shards import add_shard
    cfg = add_shard(channel, path)
    if STATE.json_out:
        _emit_json({"ok": True, "channel": channel, "shards": cfg.shards}); return
    _print(f"◯ shard declared for [bold]{channel}[/bold]")
    _print("[dim]use `sov shards migrate <channel>` to copy data over[/dim]")


@shards_app.command("migrate")
def shards_migrate_cmd(
    channel: str = typer.Argument(...),
    tables: str = typer.Option(..., "--tables",
                                help="comma-separated table names to move"),
    drop: bool = typer.Option(False, "--drop",
                               help="DROP tables from trunk after verifying"),
) -> None:
    """Copy a channel's tables from trunk into its shard. Verifies row counts."""
    from .shards import migrate_channel_to_shard
    conn = _get_atoms_conn()
    table_list = [t.strip() for t in tables.split(",") if t.strip()]
    result = migrate_channel_to_shard(
        channel, table_names=table_list, trunk_conn=conn,
        drop_from_trunk=drop,
    )
    if STATE.json_out:
        _emit_json({"ok": result["verified"], "result": result}); return
    glyph = "✓" if result["verified"] else "✗"
    _print(f"{glyph} migrate {channel}")
    for tname, info in result["tables"].items():
        _print(f"  · {tname}: {info}")
    if result["dropped"]:
        _print("[yellow]  trunk tables dropped[/yellow]")


@app.command("doctor")
def doctor_cmd(
    fix: bool = typer.Option(False, "--fix",
                              help="attempt automatic fixes (currently: backfill migrations)"),
    strict: bool = typer.Option(False, "--strict",
                                 help="exit non-zero on warnings or errors"),
) -> None:
    """Run a comprehensive environment + install diagnostic.

    Checks: Python version, installed sovereign-agent version, executable
    on PATH, install layout (with symlink detection), config/data dir
    writability, atoms.db integrity, migration status, registered channels,
    seven commitments codified, ARIA.md present, dependency versions,
    disk space.

    Use this if any `sov <command>` fails or behaves unexpectedly — it
    will tell you exactly what's installed and where.

    Exit code 0 by default (diagnostic is informational). Pass --strict
    to exit non-zero when there are warnings or errors.
    """
    from .doctor import run_diagnostic
    report = run_diagnostic()

    if STATE.json_out:
        # Backward-compatible contract: top-level keys plus full nested report
        flat_checks = [
            {"name": c.name, "level": c.level, "summary": c.summary,
             "detail": c.detail}
            for c in report.checks
        ]
        _emit_json({
            "ok": report.healthy,
            "verdict": report.verdict,
            "checks": flat_checks,
            "fail_count": len(report.errors),
            "warn_count": len(report.warnings),
            "report": report.to_dict(),
        })
        if strict and not report.healthy:
            raise typer.Exit(code=1)
        return

    _print(report.render())
    if fix:
        # Currently the only auto-fix is migration backfill
        needs_backfill = any(
            "backfill" in c.summary.lower() for c in report.warnings
        )
        if needs_backfill:
            _print("\n[bold]attempting fix: migration backfill[/bold]")
            from .migrations import backfill_applied, register_sql_dir
            from pathlib import Path
            sql_dir = Path(__file__).parent.parent.parent / "sql"
            register_sql_dir(sql_dir)
            conn = _get_atoms_conn()
            backfilled = backfill_applied(conn)
            _print(f"  backfilled {len(backfilled)} migration(s)")
            _print("\n[dim]re-run `sov doctor` to confirm[/dim]")
    if strict and not report.healthy:
        raise typer.Exit(code=1)


@app.command("info")
def info_cmd() -> None:
    """Print a concise summary of where Aria lives.

    Paths, version, atoms.db size, channel count, last heartbeat (if any).
    """
    from . import __version__
    from .config import SETTINGS
    from .doctor import _format_bytes
    paths = SETTINGS.paths

    info: dict = {"version": __version__}
    info["config_dir"] = str(paths.config_dir)
    info["data_dir"] = str(paths.data_dir)
    info["atoms_db"] = str(paths.atoms_db)

    if paths.atoms_db.is_file():
        size = paths.atoms_db.stat().st_size
        info["atoms_db_size_bytes"] = size
        info["atoms_db_size_human"] = _format_bytes(size)
        try:
            import sqlite3
            conn = sqlite3.connect(str(paths.atoms_db))
            info["atom_count"] = conn.execute(
                "SELECT COUNT(*) FROM atoms"
            ).fetchone()[0]
            conn.close()
        except sqlite3.Error:
            info["atom_count"] = None

    # Last heartbeat
    if paths.atoms_db.is_file():
        try:
            import sqlite3
            conn = sqlite3.connect(str(paths.atoms_db))
            row = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE name='heartbeats'"
            ).fetchone()
            if row:
                hb = conn.execute(
                    "SELECT message, created_at, agent_emotion "
                    "FROM heartbeats ORDER BY created_at DESC LIMIT 1"
                ).fetchone()
                if hb:
                    info["last_heartbeat"] = {
                        "message": hb[0], "at": hb[1], "emotion": hb[2],
                    }
            conn.close()
        except sqlite3.Error:
            pass

    if STATE.json_out:
        _emit_json({"ok": True, "info": info}); return

    _print(f"[bold]sovereign-agent[/bold]  v{info['version']}")
    _print(f"  config:    {info['config_dir']}")
    _print(f"  data:      {info['data_dir']}")
    _print(f"  atoms.db:  {info['atoms_db']}")
    if "atoms_db_size_human" in info:
        _print(f"             {info['atoms_db_size_human']}"
               + (f" · {info['atom_count']:,} atoms"
                  if info.get('atom_count') is not None else ""))
    else:
        _print(f"             [dim](not yet created)[/dim]")
    if "last_heartbeat" in info:
        hb = info["last_heartbeat"]
        emotion_tag = f" [{hb['emotion']}]" if hb.get("emotion") else ""
        _print(f"  ♥ last:    {hb['at'][:19]}{emotion_tag}")
        _print(f"             {hb['message'][:80]}")


# ─── sov migrations ────────────────────────────────────────────────────────

mig_app = typer.Typer(help="◊ versioned schema migrations")
app.add_typer(mig_app, name="migrations")


@mig_app.command("status")
def mig_status_cmd() -> None:
    from .migrations import status, register_sql_dir
    from pathlib import Path
    conn = _get_atoms_conn()
    sql_dir = Path(__file__).parent.parent.parent / "sql"
    register_sql_dir(sql_dir)
    items = status(conn)
    if STATE.json_out:
        _emit_json({"ok": True, "migrations": items}); return
    for m in items:
        glyph = "✓" if m["status"] == "applied" else "○"
        _print(f"  {glyph} {m['name']:<30}  {m['version']:<8}  {m['status']}")


@mig_app.command("backfill")
def mig_backfill_cmd() -> None:
    """Detect existing schema and mark migrations as applied without re-running them.

    Used when upgrading from a pre-migration-framework version of Aria.
    Safe to run multiple times — only marks new detections.
    """
    from .migrations import backfill_applied, register_sql_dir
    from pathlib import Path
    conn = _get_atoms_conn()
    sql_dir = Path(__file__).parent.parent.parent / "sql"
    register_sql_dir(sql_dir)
    backfilled = backfill_applied(conn)
    if STATE.json_out:
        _emit_json({"ok": True, "backfilled": backfilled}); return
    if not backfilled:
        _print("[dim](nothing to backfill — every applicable migration is already recorded)[/dim]"); return
    _print(f"✓ backfilled {len(backfilled)} migration(s) based on existing schema:")
    for n in backfilled:
        _print(f"  · {n}")


@mig_app.command("apply")
def mig_apply_cmd(
    dry_run: bool = typer.Option(False, "--dry-run"),
    no_backfill: bool = typer.Option(False, "--no-backfill",
                                      help="skip auto-backfill of detected schemas"),
) -> None:
    """Apply pending migrations.

    By default, also runs backfill first: any migration whose tables
    already exist on this DB is marked applied (without re-running its
    SQL body). This makes upgrades from pre-migration-framework versions
    safe — Aria figures out where you are and only runs the truly new
    schema steps.
    """
    from .migrations import apply_pending, backfill_applied, register_sql_dir
    from pathlib import Path
    conn = _get_atoms_conn()
    sql_dir = Path(__file__).parent.parent.parent / "sql"
    register_sql_dir(sql_dir)

    backfilled: list[str] = []
    if not no_backfill and not dry_run:
        backfilled = backfill_applied(conn)

    newly = apply_pending(conn, dry_run=dry_run)
    if STATE.json_out:
        _emit_json({"ok": True, "backfilled": backfilled,
                    "applied": newly, "dry_run": dry_run}); return
    if backfilled and not dry_run:
        _print(f"[dim]backfilled {len(backfilled)} pre-existing migration(s)[/dim]")
    label = "would apply" if dry_run else "applied"
    if not newly:
        _print(f"[dim](nothing pending)[/dim]"); return
    _print(f"{label} {len(newly)}:")
    for n in newly:
        _print(f"  · {n}")


# ─── sov provenance ────────────────────────────────────────────────────────


@app.command("provenance")
def provenance_cmd(
    node_id: str = typer.Argument(...),
    max_depth: int = typer.Option(20, "--max-depth"),
    max_nodes: int = typer.Option(500, "--max-nodes"),
) -> None:
    """Walk backward from any node through everything that informed it."""
    from .provenance import walk_backward
    conn = _get_atoms_conn()
    graph = walk_backward(conn, node_id, max_depth=max_depth, max_nodes=max_nodes)
    if STATE.json_out:
        _emit_json({"ok": True, "graph": graph.to_dict()}); return
    _print(graph.render())
    if graph.truncated:
        _print(f"\n[yellow](truncated — try --max-depth or --max-nodes)[/yellow]")


# ─── sov stewardship · sov honor · sov field-notes (v0.2.20.0) ─────────────


# ─── sov interpret (v0.2.21.0) ──────────────────────────────────────────────


interpret_app = typer.Typer(
    help="◊ inspect aria's interpretations — what she understood, what she did",
    invoke_without_command=False,
    no_args_is_help=True,
)
app.add_typer(interpret_app, name="interpret")


@interpret_app.command("recent")
def interpret_recent_cmd(
    n: int = typer.Option(10, "--n", "-n",
                           help="how many recent interpretations to show"),
) -> None:
    """Show recent interpretations with Aria's reasoning.

    This is the audit trail: for each message, what did Aria
    understand, why did she choose the action she chose, and what was
    she uncertain about? When something feels wrong, this is the first
    place to look.
    """
    import json as _json
    path = SETTINGS.paths.data_dir / "interpretations.ndjson"
    if not path.exists():
        _print("[dim](no interpretations recorded yet)[/dim]")
        return
    lines = path.read_text(encoding="utf-8").splitlines()
    lines = [ln for ln in lines if ln.strip()]
    recent = lines[-n:]
    records = []
    for ln in recent:
        try:
            records.append(_json.loads(ln))
        except _json.JSONDecodeError:
            continue
    if STATE.json_out:
        _emit_json({"ok": True, "count": len(records), "records": records})
        return
    if not records:
        _print("[dim](no interpretations recorded yet)[/dim]")
        return
    for r in records:
        _print(f"[dim]{r.get('ts','')[:19]}[/dim]  "
                f"[bold]{r.get('intent_kind','?')}[/bold]")
        text = r.get('text', '')
        if len(text) > 80:
            text = text[:77] + "..."
        _print(f"  [dark_orange]> {text}[/dark_orange]")
        if r.get("understanding"):
            _print(f"  [cyan]◊ understood:[/cyan] {r['understanding']}")
        if r.get("reasoning"):
            _print(f"  [dim]reasoning:[/dim] {r['reasoning']}")
        if r.get("save_to"):
            _print(f"  [dim]saved to:[/dim] {', '.join(r['save_to'])}")
        if r.get("commands"):
            for cmd in r["commands"]:
                _print(f"  [dim]ran:[/dim] {cmd}")
        if r.get("uncertain_about"):
            _print(f"  [yellow]uncertain:[/yellow] {r['uncertain_about']}")
        _print()


@interpret_app.command("count")
def interpret_count_cmd() -> None:
    """How many interpretations Aria has logged."""
    path = SETTINGS.paths.data_dir / "interpretations.ndjson"
    if not path.exists():
        if STATE.json_out:
            _emit_json({"ok": True, "count": 0}); return
        _print("0 interpretations")
        return
    n = sum(1 for ln in path.read_text(encoding="utf-8").splitlines()
              if ln.strip())
    if STATE.json_out:
        _emit_json({"ok": True, "count": n}); return
    _print(f"{n} interpretation{'s' if n != 1 else ''} logged")


@interpret_app.command("correct")
def interpret_correct_cmd(
    original_text: str = typer.Argument(...,
        help="snippet of what you said (matches the start of a logged turn)"),
    to: str = typer.Option(..., "--to", "-t",
        help="how aria should have classified it (e.g. \"save to humor not specialist\")"),
    explanation: str = typer.Option("", "--because", "-b",
        help="why — this is the most important field for aria's learning"),
) -> None:
    """Teach Aria. Correct a past misclassification.

    The correction is HMAC-signed with a local key and stored in
    corrections.jsonl. The next 5 verified corrections automatically
    enter the interpreter's in-context examples — Aria reads them
    before classifying future messages.

    No retraining. No fine-tuning. Just Aria reading her own audit log
    and adjusting. This is the apprentice loop in seed form.

    Examples:
        sov interpret correct "back is killing me" \\
            --to "save to back-pain, emotions" \\
            --because "this is body pain, not specialist content"

        sov interpret correct "Meeting you with love" \\
            --to "save to identity, intention, emotions" \\
            --because "introductions go to identity, not context"
    """
    from .stewardship.corrections import Correction, CorrectionsStore
    data_dir = SETTINGS.paths.data_dir
    store = CorrectionsStore(
        log_path=data_dir / "corrections.jsonl",
        key_path=data_dir / "corrections.key",
    )
    c = Correction(
        original_text=original_text,
        corrected_action=to,
        explanation=explanation,
    )
    store.append(c)
    if STATE.json_out:
        from dataclasses import asdict
        _emit_json({"ok": True, "correction": asdict(c)})
        return
    _print(f"[green]✓[/green] correction logged · id={c.correction_id[:8]}")
    _print(f"  [dim]aria will see this in her next 5 interpretations[/dim]")


@interpret_app.command("corrections")
def interpret_corrections_cmd(
    n: int = typer.Option(10, "--n", "-n", help="how many to show"),
    all_unverified: bool = typer.Option(
        False, "--all",
        help="include unverified entries (default: verified only)",
    ),
) -> None:
    """List corrections in the store.

    By default, only signature-verified corrections are shown — the
    same set Aria will see in her interpreter context. Use --all to
    inspect every entry (useful for spotting tampering).
    """
    from .stewardship.corrections import CorrectionsStore, verify_correction
    data_dir = SETTINGS.paths.data_dir
    store = CorrectionsStore(
        log_path=data_dir / "corrections.jsonl",
        key_path=data_dir / "corrections.key",
    )
    all_corr = list(store.iter_all())
    if not all_unverified:
        all_corr = [c for c in all_corr if verify_correction(c, store.signing_key)]
    recent = list(reversed(all_corr))[:n]
    if STATE.json_out:
        from dataclasses import asdict
        _emit_json({"ok": True, "count": len(recent),
                     "corrections": [asdict(c) for c in recent]})
        return
    if not recent:
        _print("[dim](no corrections yet — teach aria with `sov interpret correct ...`)[/dim]")
        return
    for c in recent:
        verified = verify_correction(c, store.signing_key)
        mark = "[green]✓[/green]" if verified else "[red]✗ unverified[/red]"
        _print(f"  {mark} [dim]{c.ts[:19]} · {c.correction_id[:8]}[/dim]")
        _print(f"     [dark_orange]\"{c.original_text[:80]}\"[/dark_orange]")
        _print(f"     [cyan]→ {c.corrected_action}[/cyan]")
        if c.explanation:
            _print(f"     [dim]because: {c.explanation}[/dim]")
        _print()


# ─── sov behavior (v0.2.24.0 — the self-perception layer) ──────────────────


behavior_app = typer.Typer(
    help="◊ aria's behavior patterns — her self-perception of valuable shapes",
    invoke_without_command=False,
    no_args_is_help=True,
)
app.add_typer(behavior_app, name="behavior")


def _behavior_store():
    from .stewardship.behavior import BehaviorPatternStore
    return BehaviorPatternStore(
        SETTINGS.paths.data_dir / "behavior-patterns.ndjson"
    )


@behavior_app.command("list")
def behavior_list_cmd(
    n: int = typer.Option(20, "--n", "-n", help="how many to show"),
    show_dormant: bool = typer.Option(
        False, "--all", help="include dormant patterns"),
    valuable_only: bool = typer.Option(
        False, "--valuable",
        help="only patterns where all three signals are favorable"),
) -> None:
    """List Aria's active behavior patterns.

    A pattern marked [yellow]✦[/yellow] is *valuable* — honor + calibration +
    survival all favorable AND ≥ 3 observations.
    """
    store = _behavior_store()
    if valuable_only:
        results = store.valuable()
    elif show_dormant:
        results = store.active(apply_dormancy=False)
    else:
        results = store.active(apply_dormancy=True)
    results = results[:n]
    if STATE.json_out:
        from dataclasses import asdict
        _emit_json({"ok": True, "count": len(results),
                     "patterns": [asdict(p) for p in results]})
        return
    if not results:
        _print("[dim](no active patterns yet — try "
                "`sov behavior discover` once you have ~20 interpretations)[/dim]")
        return
    for p in results:
        _print(p.render())
        _print()


@behavior_app.command("show")
def behavior_show_cmd(
    pattern_id: str = typer.Argument(...,
        help="pattern id (prefix-match: first 8 chars enough)"),
) -> None:
    """Show one pattern in full, including trigger conditions, action
    shape, evidence references, and outcome metrics."""
    store = _behavior_store()
    for p in store.all_patterns():
        if p.pattern_id.startswith(pattern_id):
            if STATE.json_out:
                from dataclasses import asdict
                _emit_json({"ok": True, "pattern": asdict(p)})
                return
            _print(p.render())
            _print()
            _print(f"  [dim]id: {p.pattern_id}[/dim]")
            _print(f"  [dim]status: {p.status}[/dim]")
            _print(f"  [dim]first observed: {p.ts_first_obs}[/dim]")
            _print(f"  [dim]last observed:  {p.ts_last_obs}[/dim]")
            _print()
            _print(f"  [bold]trigger:[/bold]")
            t = p.trigger
            if t.channels_any:
                _print(f"    channels_any: {t.channels_any}")
            if t.channels_all:
                _print(f"    channels_all: {t.channels_all}")
            if t.intent_kind:
                _print(f"    intent_kind:  {t.intent_kind}")
            if t.authority_tier_max is not None:
                _print(f"    tier_max:     {t.authority_tier_max}")
            if t.text_contains_any:
                _print(f"    text_any:     {t.text_contains_any}")
            if t.has_uncertainty is not None:
                _print(f"    uncertain:    {t.has_uncertainty}")
            _print()
            if p.action_shape:
                _print(f"  [bold]action shape:[/bold]")
                _print(f"    {p.action_shape}")
                _print()
            if p.evidence_refs:
                _print(f"  [bold]evidence ({len(p.evidence_refs)}):[/bold]")
                for ref in p.evidence_refs[:10]:
                    _print(f"    [dim]→ {ref}[/dim]")
                if len(p.evidence_refs) > 10:
                    _print(f"    [dim]... and {len(p.evidence_refs)-10} more[/dim]")
            return
    _die(ExitCode.USAGE, f"no pattern with id matching {pattern_id}")


@behavior_app.command("discover")
def behavior_discover_cmd(
    tail_provenance: int = typer.Option(50, "--tail-provenance"),
    tail_honor: int = typer.Option(20, "--tail-honor"),
    no_llm: bool = typer.Option(False, "--no-llm"),
) -> None:
    """Run a discovery pass — Aria reads her recent work and proposes
    new behavior patterns.

    Patterns are NEVER auto-applied. The proposed patterns enter the
    store with status=active but zero observations. As future turns
    match their triggers, observations accumulate and confidence rises.
    A pattern with sustained good outcomes becomes 'valuable' (✦).
    """
    import asyncio as _asyncio
    from .stewardship.discovery import discover_patterns
    from .ollama_client import OllamaClient

    client = None
    if not no_llm:
        try:
            client = OllamaClient()
        except Exception:  # noqa: BLE001
            client = None

    summary = _asyncio.run(discover_patterns(
        ollama_client=client,
        pattern_store=_behavior_store(),
        tail_provenance=tail_provenance,
        tail_honor=tail_honor,
    ))

    if STATE.json_out:
        _emit_json({"ok": True, "summary": summary})
        return

    _print("[bold]discovery pass complete[/bold]")
    _print(f"  provenance read:    {summary['provenance_read']}")
    _print(f"  honor read:         {summary['honor_read']}")
    _print(f"  existing patterns:  {summary['existing_patterns']}")
    _print(f"  patterns proposed:  {summary['patterns_proposed']}")
    _print(f"  patterns saved:     {summary['patterns_saved']}")
    if summary['skipped_offline']:
        _print(f"  [yellow]skipped (no llm)[/yellow]")
    if summary['errors']:
        _print(f"  [red]errors: {len(summary['errors'])}[/red]")
        for err in summary['errors'][:5]:
            _print(f"    [dim]{err}[/dim]")


@behavior_app.command("count")
def behavior_count_cmd() -> None:
    """Count active patterns."""
    store = _behavior_store()
    active = store.count()
    valuable = len(store.valuable())
    if STATE.json_out:
        _emit_json({"ok": True, "active": active, "valuable": valuable})
        return
    _print(f"  [bold]{active}[/bold] active pattern"
            f"{'s' if active != 1 else ''}")
    _print(f"  [bold]{valuable}[/bold] valuable [yellow]✦[/yellow] "
            f"pattern{'s' if valuable != 1 else ''}")


@behavior_app.command("architect")
def behavior_architect_cmd(
    min_evidence: int = typer.Option(3, "--min-evidence",
        help="minimum observations per parent to be eligible"),
    no_llm: bool = typer.Option(False, "--no-llm"),
) -> None:
    """Run an architect pass — propose composed patterns from trusted ones.

    Aria looks at her currently-active behavior patterns with enough
    evidence to trust (≥ min_evidence observations) and proposes new
    compositions: unions, intersections, specializations, generalizations.

    Composed patterns enter the store as ACTIVE but with zero observations
    — they must earn their valuable (✦) status by accumulating evidence
    in the wild. This is the experimentation discipline.

    Introduced: v0.2.25.0 ("The Garden")
    """
    import asyncio as _asyncio
    from .stewardship.architect import architect_patterns
    from .ollama_client import OllamaClient

    client = None
    if not no_llm:
        try:
            client = OllamaClient()
        except Exception:  # noqa: BLE001
            client = None

    summary = _asyncio.run(architect_patterns(
        ollama_client=client,
        pattern_store=_behavior_store(),
        min_evidence_per_parent=min_evidence,
    ))

    if STATE.json_out:
        _emit_json({"ok": True, "summary": summary})
        return

    _print("[bold]architect pass complete[/bold]")
    _print(f"  active patterns:      {summary['active_patterns']}")
    _print(f"  eligible parents:     {summary['eligible_parents']}")
    _print(f"  compositions proposed:{summary['compositions_proposed']}")
    _print(f"  compositions saved:   {summary['compositions_saved']}")
    if summary['skipped_offline']:
        _print(f"  [yellow]skipped (no llm)[/yellow]")
    if summary['errors']:
        _print(f"  [red]errors: {len(summary['errors'])}[/red]")
        for err in summary['errors'][:5]:
            _print(f"    [dim]{err}[/dim]")


# ─── sov memory (v0.2.25.0 — the garden) ───────────────────────────────────


memory_app = typer.Typer(
    help="◊ aria's memory garden — health, reorganization, and tending",
    invoke_without_command=False,
    no_args_is_help=True,
)
app.add_typer(memory_app, name="memory")


@memory_app.command("health")
def memory_health_cmd() -> None:
    """Survey the memory garden — counts, valuable patterns, hot channels.

    Read-only. Shows the same data the cockpit's memory pane shows,
    just in CLI form.
    """
    from .stewardship.memory_garden import survey_memory
    health = survey_memory(SETTINGS.paths.data_dir)
    if STATE.json_out:
        from dataclasses import asdict
        _emit_json({"ok": True, "health": asdict(health)})
        return

    reorg_mark = ""
    if health.total_memories >= 1000:
        reorg_mark = "  [yellow]◊ ready to tend (run `sov memory reorganize`)[/yellow]"
    _print(f"[bold]◊ total memories: {health.total_memories}[/bold]{reorg_mark}")
    _print()
    _print(f"[bold cyan]patterns[/bold cyan]")
    _print(f"  [yellow]✦[/yellow] valuable: {health.patterns_valuable}")
    _print(f"  ● active:   {health.patterns_active}")
    _print(f"  [dim]○ dormant:  {health.patterns_dormant}[/dim]")
    _print()
    _print(f"[bold cyan]atoms[/bold cyan]")
    _print(f"  ◊ active:     {health.atoms_active}")
    if health.atoms_total > health.atoms_active:
        _print(f"  [dim]⊘ superseded: "
                f"{health.atoms_total - health.atoms_active}[/dim]")
    _print()
    _print(f"[bold cyan]witness threads[/bold cyan]")
    _print(f"  [red]♥[/red] honor:       {health.honor_notes}")
    _print(f"  · field-notes: {health.field_notes}")
    _print()
    _print(f"[bold cyan]substrate[/bold cyan]")
    _print(f"  → interpretations: {health.provenance_entries}")
    _print(f"  ✎ corrections:     {health.corrections}")
    _print()
    if health.hot_channels:
        _print(f"[bold cyan]hot channels[/bold cyan]")
        for ch, count in health.hot_channels[:10]:
            _print(f"  [dim]{count:4d}[/dim]  {ch}")
        _print()
    _print(f"[bold cyan]storage[/bold cyan]")
    _print(f"  [dim]{SETTINGS.paths.data_dir}[/dim]")


@memory_app.command("reorganize")
def memory_reorganize_cmd(
    dormancy_days: int = typer.Option(30, "--dormancy-days",
        help="patterns unobserved for N days get marked dormant"),
    dry_run: bool = typer.Option(False, "--dry-run",
        help="show what would happen without changing anything"),
) -> None:
    """Run the garden tender — a safe, non-destructive reorganization pass.

    What it does:
      • Patterns unobserved for `dormancy_days` get status → dormant
        (reversible — the next observation re-activates them)
      • Surveys memory health
      • Identifies likely-duplicate atoms (suggestions only)

    What it does NOT do:
      • No deletions. Ever. (Palimpsest discipline)
      • No merges without explicit operator approval
      • No supersession (operator does that explicitly)

    Suggested cadence: every ~1000 total memories (per Kevin's design).
    """
    from .stewardship.memory_garden import reorganize, survey_memory
    if dry_run:
        health = survey_memory(SETTINGS.paths.data_dir)
        _print("[bold]would tend:[/bold]")
        candidates = health.dormancy_candidates
        _print(f"  patterns to mark dormant: {len(candidates)}")
        _print(f"  duplicate atom suggestions: "
                f"{len(health.duplicate_atom_suggestions)}")
        return

    result = reorganize(
        SETTINGS.paths.data_dir,
        dormancy_days=dormancy_days,
    )
    if STATE.json_out:
        from dataclasses import asdict
        _emit_json({"ok": True,
                     "patterns_marked_dormant": result.patterns_marked_dormant,
                     "suggestions": result.suggestions_for_operator,
                     "errors": result.errors})
        return
    _print(f"[bold]garden tending complete[/bold]")
    _print(f"  patterns marked dormant: {result.patterns_marked_dormant}")
    if result.suggestions_for_operator:
        _print()
        _print(f"[bold]suggestions for your review:[/bold]")
        for s in result.suggestions_for_operator:
            _print(f"  · {s}")
    if result.errors:
        _print()
        _print(f"  [red]errors: {len(result.errors)}[/red]")
        for err in result.errors[:5]:
            _print(f"    [dim]{err}[/dim]")


@behavior_app.command("match")
def behavior_match_cmd(
    text: str = typer.Argument(..., help="text to match against patterns"),
    channels: str = typer.Option("", "--channels", "-c",
        help="comma-separated channels to include in shape"),
    intent_kind: str = typer.Option("", "--intent-kind", "-k",
        help="Conversation | Work | Recall | Slash | Ambiguous"),
    tier: int = typer.Option(0, "--tier", "-t"),
) -> None:
    """Match a hypothetical turn against active patterns — useful for
    debugging or for exploring what patterns are active in your system."""
    from .stewardship.behavior import shape_of_turn
    store = _behavior_store()
    shape = shape_of_turn(
        text=text,
        intent_kind=intent_kind,
        channels=channels.split(",") if channels else [],
        authority_tier=tier,
    )
    matches = store.matching(shape, top_k=10)
    if STATE.json_out:
        from dataclasses import asdict
        _emit_json({"ok": True, "matches": [asdict(p) for p in matches]})
        return
    if not matches:
        _print("[dim](no active patterns match this shape)[/dim]")
        return
    _print(f"[bold]{len(matches)} pattern{'s' if len(matches) != 1 else ''} "
            f"match this shape:[/bold]")
    _print()
    for p in matches:
        _print(p.render())
        _print()


# ─── sov atoms · sov consolidate (v0.2.23.0) ────────────────────────────────


atoms_app = typer.Typer(
    help="◊ aria's semantic atoms — distilled patterns and facts",
    invoke_without_command=False,
    no_args_is_help=True,
)
app.add_typer(atoms_app, name="atoms")


def _atom_store():
    from .stewardship.atoms import AtomStore
    return AtomStore(SETTINGS.paths.data_dir / "atoms.ndjson")


@atoms_app.command("list")
def atoms_list_cmd(
    n: int = typer.Option(20, "--n", "-n", help="how many atoms to show"),
    kind: str = typer.Option("", "--kind", "-k",
                              help="filter: fact | pattern | rule"),
    channel: str = typer.Option("", "--channel", "-c",
                                 help="filter to atoms about a channel"),
    contains: str = typer.Option("", "--contains",
                                  help="text search in title or claim"),
) -> None:
    """List Aria's semantic atoms — what she has distilled from
    her own experience.

    Atoms are produced by the consolidation operator (sleep phase).
    They point back to the provenance entries that supported them,
    so retrieval can always drop to the raw episodes.
    """
    from .stewardship.atoms import AtomKind
    store = _atom_store()
    kind_filter = None
    if kind:
        try:
            kind_filter = AtomKind(kind)
        except ValueError:
            _die(ExitCode.USAGE, f"unknown kind: {kind}")
            return
    results = store.search(
        kind=kind_filter,
        channel=channel or None,
        text_contains=contains or None,
    )[:n]
    if STATE.json_out:
        from dataclasses import asdict
        _emit_json({"ok": True, "count": len(results),
                     "atoms": [asdict(a) for a in results]})
        return
    if not results:
        _print("[dim](no atoms yet — run `sov consolidate` to distill)[/dim]")
        return
    for atom in results:
        _print(atom.render())
        _print()


@atoms_app.command("show")
def atoms_show_cmd(
    atom_id: str = typer.Argument(...,
        help="atom id (prefix-matching: first 8 chars is enough)"),
) -> None:
    """Show one atom in full, including evidence references."""
    store = _atom_store()
    for atom in store.active():
        if atom.atom_id.startswith(atom_id):
            if STATE.json_out:
                from dataclasses import asdict
                _emit_json({"ok": True, "atom": asdict(atom)})
                return
            _print(atom.render())
            _print(f"  [dim]id: {atom.atom_id}[/dim]")
            _print(f"  [dim]created: {atom.ts_created}[/dim]")
            if atom.evidence_refs:
                _print(f"  [bold]evidence ({len(atom.evidence_refs)}):[/bold]")
                for ref in atom.evidence_refs:
                    _print(f"    [dim]→ {ref}[/dim]")
            return
    _die(ExitCode.USAGE, f"no atom with id matching {atom_id}")


@atoms_app.command("count")
def atoms_count_cmd() -> None:
    """How many active atoms Aria has."""
    n = _atom_store().count()
    if STATE.json_out:
        _emit_json({"ok": True, "count": n}); return
    _print(f"{n} active atom{'s' if n != 1 else ''}")


@app.command("consolidate")
def consolidate_cmd(
    tail_n: int = typer.Option(100, "--tail-n",
        help="how many recent provenance entries to consider"),
    min_cluster_size: int = typer.Option(3, "--min-cluster",
        help="smallest cluster size to consolidate"),
    max_clusters: int = typer.Option(10, "--max-clusters",
        help="upper bound on clusters processed per pass"),
    no_llm: bool = typer.Option(False, "--no-llm",
        help="skip the LLM — useful only for testing clustering"),
) -> None:
    """Run one consolidation pass — wake/sleep upward operator.

    Reads recent provenance entries, clusters them by channel
    co-occurrence, and asks Aria to distill semantic atoms from each
    cluster. Atoms are appended to atoms.ndjson and point back to
    the provenance entries that supported them.

    The provenance entries are NEVER deleted — this is the palimpsest
    discipline. You can always drop back to the raw observations that
    produced any atom.

    Introduced: v0.2.23.0 ("First Crystallization")
    """
    import asyncio as _asyncio
    from .stewardship.consolidate import consolidate
    from .ollama_client import OllamaClient

    client = None
    if not no_llm:
        try:
            client = OllamaClient()
        except Exception:  # noqa: BLE001
            client = None

    summary = _asyncio.run(consolidate(
        ollama_client=client,
        tail_n=tail_n,
        min_cluster_size=min_cluster_size,
        max_clusters=max_clusters,
    ))

    if STATE.json_out:
        _emit_json({"ok": True, "summary": summary})
        return

    _print(f"[bold]consolidation pass complete[/bold]")
    _print(f"  entries read:         {summary['entries_read']}")
    _print(f"  clusters found:       {summary['clusters_found']}")
    _print(f"  clusters distilled:   {summary['clusters_consolidated']}")
    _print(f"  atoms proposed:       {summary['atoms_proposed']}")
    _print(f"  atoms saved:          {summary['atoms_saved']}")
    if summary['skipped_offline']:
        _print(f"  [yellow]skipped (no llm):     "
                f"{summary['skipped_offline']}[/yellow]")
    if summary['errors']:
        _print(f"  [red]errors: {len(summary['errors'])}[/red]")
        for err in summary['errors'][:5]:
            _print(f"    [dim]{err}[/dim]")


# ─── sov honor · sov field-notes · sov stewardship (v0.2.20.0+) ─────────────


honor_app = typer.Typer(
    help="◊ the honor ledger — mutual recognition between you and aria",
    invoke_without_command=False,
    no_args_is_help=True,
)
app.add_typer(honor_app, name="honor")


def _stewardship_dir() -> Path:
    """Where stewardship artifacts live under the data dir."""
    p = SETTINGS.paths.data_dir / "stewardship"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _honor_ledger():
    from .stewardship.honor import HonorLedger
    return HonorLedger(_stewardship_dir() / "honor.jsonl")


@honor_app.command("note")
def honor_note_cmd(
    text: str = typer.Argument(..., help="what you witnessed in their work"),
    to: str = typer.Option(
        "aria", "--to", "-t",
        help="recipient: aria | kevin | self | <name>",
    ),
    by: str = typer.Option(
        "kevin", "--by", "-b",
        help="who is issuing this note: kevin | aria",
    ),
    tag: list[str] = typer.Option([], "--tag", help="tags (repeatable)"),
    triple_id: str = typer.Option("", "--triple",
                                   help="link to a stewardship triple"),
    signature: str = typer.Option("", "--signature", "-s",
                                   help="your signature; defaults to <3 for kevin"),
) -> None:
    """Write one honor note to the ledger.

    Examples:
        sov honor note "you caught the back-brace bug before it shipped" --to aria
        sov honor note "you sat through four iterations because you wanted it right" --by aria --to kevin
        sov honor note "I almost predicted F_macro=+0.5 without evidence" --by aria --to self
    """
    from .stewardship.honor import (
        HonorDirection, HonorNote,
        kevin_honors_aria, aria_honors_kevin, aria_honors_self,
        aria_honors_third,
    )
    by = by.lower().strip()
    to = to.lower().strip()
    note = None
    if by == "kevin" and to == "aria":
        note = kevin_honors_aria(text, tags=list(tag), triple_id=triple_id)
        if signature:
            note.signature = signature
    elif by == "aria" and to == "kevin":
        note = aria_honors_kevin(text, tags=list(tag), triple_id=triple_id)
    elif by == "aria" and to == "self":
        note = aria_honors_self(text, tags=list(tag), triple_id=triple_id)
    elif by == "kevin" and to == "self":
        note = HonorNote(
            direction=HonorDirection.KEVIN_TO_SELF,
            recipient="self",
            text=text,
            tags=list(tag),
            triple_id=triple_id,
            signature=signature or "<3",
        )
    elif by == "aria" and to not in ("kevin", "aria", "self"):
        note = aria_honors_third(text, recipient=to, tags=list(tag),
                                  triple_id=triple_id)
    elif by == "kevin" and to not in ("kevin", "aria", "self"):
        note = HonorNote(
            direction=HonorDirection.KEVIN_TO_THIRD,
            recipient=to,
            text=text,
            tags=list(tag),
            triple_id=triple_id,
            signature=signature or "<3",
        )
    else:
        _die(ExitCode.USAGE,
              f"invalid by/to combination: by={by} to={to}")
        return

    _honor_ledger().append(note)
    if STATE.json_out:
        from dataclasses import asdict
        _emit_json({"ok": True, "note": asdict(note)})
        return
    _print(note.render())


@honor_app.command("show")
def honor_show_cmd(
    n: int = typer.Option(10, "--n", "-n", help="how many notes to show"),
    direction: str = typer.Option("", "--direction", "-d"),
    tag: str = typer.Option("", "--tag", "-t"),
    contains: str = typer.Option("", "--contains", "-c"),
) -> None:
    """Show recent honor notes."""
    from .stewardship.honor import HonorDirection
    ledger = _honor_ledger()
    if direction or tag or contains:
        dir_filter = None
        if direction:
            try:
                dir_filter = HonorDirection(direction)
            except ValueError:
                _die(ExitCode.USAGE, f"unknown direction: {direction}")
                return
        notes = ledger.search(
            direction=dir_filter,
            tag=tag or None,
            text_contains=contains or None,
        )[-n:]
    else:
        notes = ledger.recent(n)
    if STATE.json_out:
        from dataclasses import asdict
        _emit_json({"ok": True, "count": len(notes),
                     "notes": [asdict(x) for x in notes]})
        return
    if not notes:
        _print("[dim](no honor notes yet)[/dim]")
        return
    for note in notes:
        _print(f"  [dim]{note.ts[:19]}[/dim]")
        _print(f"  {note.render()}")
        _print()


@honor_app.command("count")
def honor_count_cmd() -> None:
    """Total honor notes in the ledger."""
    ledger = _honor_ledger()
    c = ledger.count()
    if STATE.json_out:
        _emit_json({"ok": True, "count": c}); return
    _print(f"  {c} honor note{'s' if c != 1 else ''} in the ledger")


# ─── sov field-notes ────────────────────────────────────────────────────────


field_notes_app = typer.Typer(
    help="◊ aria's between-task narrative — short, textured observations",
    invoke_without_command=False,
    no_args_is_help=True,
)
app.add_typer(field_notes_app, name="field-notes")


def _field_notes_channel():
    from .stewardship.field_notes import FieldNotesChannel
    return FieldNotesChannel(_stewardship_dir() / "field-notes.jsonl")


@field_notes_app.command("add")
def field_notes_add_cmd(
    text: str = typer.Argument(...),
    flavor: str = typer.Option(
        "observation", "--flavor", "-f",
        help="observation | difficulty | beauty | uncertainty | question | gratitude",
    ),
    project: str = typer.Option("", "--project", "-p"),
    tag: list[str] = typer.Option([], "--tag", "-t"),
    triple_id: str = typer.Option("", "--triple"),
) -> None:
    """Write one field note."""
    from .stewardship.field_notes import FieldNote, FieldNoteFlavor
    try:
        flav = FieldNoteFlavor(flavor)
    except ValueError:
        _die(ExitCode.USAGE, f"unknown flavor: {flavor}")
        return
    note = FieldNote(
        flavor=flav, text=text, project=project,
        tags=list(tag), triple_id=triple_id,
    )
    _field_notes_channel().append(note)
    if STATE.json_out:
        from dataclasses import asdict
        _emit_json({"ok": True, "note": asdict(note)})
        return
    _print(note.render())


@field_notes_app.command("show")
def field_notes_show_cmd(
    n: int = typer.Option(10, "--n", "-n"),
    project: str = typer.Option("", "--project", "-p"),
) -> None:
    """Show recent field notes."""
    notes = _field_notes_channel().recent(n, project=project)
    if STATE.json_out:
        from dataclasses import asdict
        _emit_json({"ok": True, "count": len(notes),
                     "notes": [asdict(x) for x in notes]})
        return
    if not notes:
        _print("[dim](no field notes yet)[/dim]")
        return
    for note in notes:
        _print(f"  [dim]{note.ts[:19]}[/dim]  {note.render()}")


# ─── sov stewardship — Plan/Witness/IV inspection ──────────────────────────


stewardship_app = typer.Typer(
    help="◊ stewardship — plans, witnesses, impact vectors, honor scores",
    invoke_without_command=False,
    no_args_is_help=True,
)
app.add_typer(stewardship_app, name="stewardship")


@stewardship_app.command("score")
def stewardship_score_cmd(
    triple_path: Path = typer.Argument(...,
        exists=True, file_okay=True, dir_okay=False),
) -> None:
    """Compute the honor score for a stored stewardship triple.

    Shows the full breakdown — plan quality, calibration, impact,
    zombie penalty, almost-missed bonus, and the total. The point
    is transparency: Aria (and you) can see why the score is what
    it is.
    """
    import json as _json
    from .stewardship.calibration import honor_score
    from .stewardship.plan import (
        ExecutionWitness, Plan, StewardshipTriple,
    )
    from .stewardship.msims import (
        Cell, Dimension, Horizon, ImpactVector, Reversibility, Scale,
    )

    data = _json.loads(triple_path.read_text(encoding="utf-8"))
    # Re-hydrate. This is a minimal reconstruction — full
    # reconstruction lives in stewardship.plan but for scoring we
    # only need the predicted_iv, actual_iv, witness.almost_missed,
    # and plan.* quality fields.

    def _iv_from_dict(d):
        iv = ImpactVector(ts=d.get("ts", ""), label=d.get("label", ""))
        for cd in d.get("cells", []):
            try:
                dim = Dimension(cd["dimension"])
                sc = Scale(cd["scale"])
                hz = Horizon(cd.get("horizon", "immediate"))
                rv = Reversibility(cd.get("reversibility", "reversible"))
                iv.set(dim, sc, Cell(
                    value=cd.get("value", 0.0),
                    confidence=cd.get("confidence", 0.0),
                    horizon=hz, reversibility=rv,
                    evidence=cd.get("evidence", ""),
                    ts=cd.get("ts", ""),
                ))
            except (ValueError, KeyError):
                continue
        return iv

    p_data = data.get("plan", {})
    plan = Plan(
        plan_id=p_data.get("plan_id", ""),
        summary=p_data.get("summary", ""),
        commands=p_data.get("commands", []),
        rationale=p_data.get("rationale", ""),
        failure_modes_named=p_data.get("failure_modes_named", []),
        rollback_steps=p_data.get("rollback_steps", []),
        observability_points=p_data.get("observability_points", []),
        authority_tier=p_data.get("authority_tier", 1),
        uncertainty_notes=p_data.get("uncertainty_notes", []),
        predicted_iv=_iv_from_dict(p_data.get("predicted_iv", {})),
        ts_created=p_data.get("ts_created", ""),
    )
    w_data = data.get("witness", {})
    witness = ExecutionWitness(
        plan_id=w_data.get("plan_id", ""),
        executed_commands=w_data.get("executed_commands", []),
        exit_codes=w_data.get("exit_codes", []),
        duration_seconds=w_data.get("duration_seconds", 0.0),
        surprises=w_data.get("surprises", []),
        almost_missed=w_data.get("almost_missed", []),
        in_flight_notes=w_data.get("in_flight_notes", []),
        ts_started=w_data.get("ts_started", ""),
        ts_finished=w_data.get("ts_finished", ""),
    )
    actual_iv = _iv_from_dict(data.get("actual_iv", {}))
    triple = StewardshipTriple(plan=plan, witness=witness, actual_iv=actual_iv)

    breakdown = honor_score(triple)
    if STATE.json_out:
        from dataclasses import asdict
        _emit_json({"ok": True, "breakdown": asdict(breakdown)})
        return
    _print(f"[bold]{plan.summary}[/bold]")
    _print(f"  [dim]plan_id: {plan.plan_id}[/dim]")
    _print()
    _print(breakdown.render())


# ═══════════════════════════════════════════════════════════════════════════
#  RETRIEVE — Sovereign Retrieval Pipeline (v0.2.29.0)
# ═══════════════════════════════════════════════════════════════════════════


@app.command("retrieve")
def retrieve_cmd(
    query: str = typer.Argument(..., help="The query, in plain English."),
    top_k: int = typer.Option(5, "--top-k", "-k", help="Hits to return.", min=1, max=20),
    intent: str | None = typer.Option(
        None, "--intent",
        help=("Override intent classification. One of: factual, "
              "decision_support, exploration, conversational, debug, "
              "reflective."),
    ),
    stakes: str | None = typer.Option(
        None, "--stakes",
        help=("Override stakes detection. One of: low, medium, high. "
              "High filters LLM-source atoms and applies a 0.7 confidence "
              "floor."),
    ),
    as_known_at: str | None = typer.Option(
        None, "--as-known-at",
        help=("Bitemporal: limit to atoms created on or before this ISO "
              "timestamp. Useful for 'what did I know on date X?' queries."),
    ),
    no_embed: bool = typer.Option(
        False, "--no-embed",
        help=("Skip dense retrieval entirely (lexical + graph only, no "
              "Ollama embedding call). Faster, slightly narrower recall."),
    ),
) -> None:
    """Run the Sovereign Retrieval Pipeline against atoms.db.

    Examples:

      sov retrieve "what have I learned about rollbacks?"
      sov retrieve "should I ship the hotfix?" --stakes high
      sov retrieve "early notes on stewardship" --as-known-at 2026-04-01T00:00:00Z
    """
    _preflight_initialized()

    from .db import open_atoms_db
    from .retrieval import retrieve_from_state

    # Build embedder unless --no-embed
    embedder = None
    if not no_embed:
        embedder = _build_cli_embedder()

    conn = open_atoms_db()
    try:
        report = retrieve_from_state(
            query=query,
            conn=conn,
            intent_override=intent,  # type: ignore[arg-type]
            stakes_override=stakes,  # type: ignore[arg-type]
            as_known_at=as_known_at,
            embedder=embedder,
            top_k=top_k,
        )
    finally:
        conn.close()

    if STATE.json_out:
        from .tools.retrieve_memory import _serialize_report
        _emit_json({"ok": True, "report": _serialize_report(report)})
        return

    # Human rendering
    ctx = report.context
    _print(
        f"[bold]Query:[/bold] {query}\n"
        f"  intent={ctx.intent if ctx else '?'}  "
        f"stakes={ctx.stakes if ctx else '?'}  "
        f"semantic={report.semantic_source}"
    )
    _print(f"  confidence ceiling: [cyan]{report.confidence_ceiling:.2f}[/cyan]")
    _print()
    if not report.hits:
        _print("[yellow]no hits[/yellow]")
    for i, h in enumerate(report.hits, 1):
        actor_color = {"operator": "green", "system": "cyan",
                       "llm": "yellow"}.get(h.created_by_actor, "white")
        _print(
            f"[bold]{i}.[/bold] [{h.atom_id[:8]}] "
            f"[{actor_color}]{h.created_by_actor}[/{actor_color}] "
            f"(conf={h.confidence:.2f}, fused={h.score.fused:.3f})"
        )
        _print(f"    {h.summary[:200]}")
        if h.provenance_breadcrumb:
            chain = " ← ".join(a[:8] for a in h.provenance_breadcrumb)
            _print(f"    [dim]provenance: {chain}[/dim]")

    gr = report.gap_report
    if gr.constitutional_drops or gr.empty_retrievers or gr.inactive_retrievers:
        _print()
        _print("[bold]Gaps:[/bold]")
        if gr.constitutional_drops:
            for k, v in gr.constitutional_drops.items():
                _print(f"  [dim]dropped[/dim] {k}: {v}")
        if gr.empty_retrievers:
            _print(f"  [dim]empty[/dim]: {', '.join(gr.empty_retrievers)}")
        if gr.inactive_retrievers:
            _print(f"  [dim]inactive[/dim]: {', '.join(gr.inactive_retrievers)}")

    if report.expansion_hints:
        _print()
        _print("[bold]Hints:[/bold]")
        for h in report.expansion_hints:
            arg_str = f" {h.arg}" if h.arg else ""
            _print(f"  → [cyan]{h.action}[/cyan]{arg_str} — {h.rationale}")


def _build_cli_embedder():
    """Build an embedder closure for CLI use. Returns None if Ollama is
    unreachable so the pipeline can degrade to lexical+graph recall."""
    import asyncio

    from .ollama_client import OllamaClient

    client = OllamaClient()
    try:
        loop = asyncio.new_event_loop()
        test_vec = loop.run_until_complete(
            client.embed(model=SETTINGS.embed_model, prompt="probe")
        )
        if not test_vec:
            loop.close()
            return None
    except Exception:  # noqa: BLE001
        return None

    def _embed_sync(text: str) -> list[float] | None:
        try:
            return loop.run_until_complete(
                client.embed(model=SETTINGS.embed_model, prompt=text)
            )
        except Exception:
            return None

    return _embed_sync


def _sov_chat_entrypoint() -> None:
    """Entry point for the ``sov-chat`` console script (v0.2.30.0).

    Launches the cockpit immediately, the same way ``sov chat`` (with no
    subcommand) does. This exists so the operator does not need to source
    ``scripts/aliases.sh`` to get the most-used surface: just type
    ``sov-chat`` after install and the cockpit comes up.

    The cockpit is optional — it requires ``textual``. If it's missing, we
    print a friendly hint and exit cleanly with a non-zero code so shells
    and CI see the failure.
    """
    try:
        from .cockpit import run as run_cockpit
    except ImportError as exc:
        sys.stderr.write(
            f"✗ cockpit unavailable: {exc}\n"
            "  Try: re-run ./install.sh from the sovereign-agent source tree\n"
            "  (textual is a declared dependency; uv sync should pull it in)\n"
        )
        sys.exit(1)
    run_cockpit()


# ─── sov sentinels — the roster of inner watchers ─────────────────────────
#
# v0.2.34.0 — unified sentinel framework. Every sentinel inherits a common
# contract (manifest, hash-bound articles, kill switch, notification
# inbox, voice slot). This subapp is the operator's window into all of
# them at once.

sentinels_app = typer.Typer(
    name="sentinels",
    help="The roster of Aria's inner watchers — health, notifications, scans.",
    no_args_is_help=True,
)
app.add_typer(sentinels_app, name="sentinels")


@sentinels_app.command("list")
def sentinels_list_cmd() -> None:
    """Show every registered sentinel with health and unread inbox count."""
    from .stewardship import registry as _reg
    from .stewardship.base import MASTER_KILL_SWITCH_ENV
    import os

    health_list = _reg.gather_health(SETTINGS.paths.data_dir)
    sentinels = _reg.instantiate_all(SETTINGS.paths.data_dir)
    if STATE.json_out:
        out = []
        for s, h in zip(sentinels, health_list):
            unread = len(s.read_inbox(only_unread=True))
            out.append({
                "id": s.id, "title": s.title, "tier": s.tier,
                "level": h.level, "summary": h.summary, "unread": unread,
                "enabled": s.is_enabled(),
            })
        _emit_json(out)
        return

    if os.environ.get(MASTER_KILL_SWITCH_ENV):
        _print(f"[yellow]⚠ master kill switch active ({MASTER_KILL_SWITCH_ENV}=1) — all sentinels disabled[/yellow]\n")

    if not sentinels:
        _print("[dim]No sentinels registered yet.[/dim]")
        return

    _print(f"[bold]Sentinel roster ({len(sentinels)})[/bold]")
    color = {"ok": "green", "warning": "yellow", "error": "red", "unknown": "dim"}
    glyph = {"ok": "✓", "warning": "!", "error": "✗", "unknown": "?"}
    for s, h in zip(sentinels, health_list):
        unread = len(s.read_inbox(only_unread=True))
        c = color.get(h.level, "white")
        g = glyph.get(h.level, "·")
        inbox = f"  [yellow]({unread} unread)[/yellow]" if unread else ""
        disabled = "  [dim](kill switch active)[/dim]" if not s.is_enabled() else ""
        _print(f"  [{c}]{g}[/{c}] [bold]{s.id:12s}[/bold] T{s.tier}  {h.summary}{inbox}{disabled}")


@sentinels_app.command("scan")
def sentinels_scan_cmd(
    name: str | None = typer.Argument(None, help="Specific sentinel id, or omit for all."),
) -> None:
    """Run one or all sentinel scans. Catalogs persist; alerts auto-notify."""
    from .stewardship import registry as _reg

    if name:
        sentinel = _reg.instantiate(name, SETTINGS.paths.data_dir)
        if sentinel is None:
            _print(f"[red]✗ no sentinel registered with id {name!r}[/red]")
            _print(f"  Known: {', '.join(_reg.registered_ids())}")
            raise typer.Exit(code=1)
        sentinel.bootstrap()
        if not sentinel.is_enabled():
            _print(f"[yellow]sentinel {name!r} is disabled via kill switch[/yellow]")
            raise typer.Exit(code=1)
        report = sentinel.scan()
        reports = [report]
    else:
        _print("[dim]scanning all sentinels...[/dim]")
        reports = _reg.scan_all(SETTINGS.paths.data_dir)

    if STATE.json_out:
        from dataclasses import asdict
        _emit_json([asdict(r) for r in reports])
        return

    for r in reports:
        _print(f"[green]✓ {r.sentinel_id}[/green]  {r.summary}  [dim](catalog: {r.catalog_path})[/dim]")


@sentinels_app.command("show")
def sentinels_show_cmd(
    name: str = typer.Argument(..., help="Sentinel id (e.g., 'cache')."),
) -> None:
    """Full picture: manifest, articles, health, last scan, recent inbox."""
    from .stewardship import registry as _reg
    from dataclasses import asdict

    sentinel = _reg.instantiate(name, SETTINGS.paths.data_dir)
    if sentinel is None:
        _print(f"[red]✗ no sentinel registered with id {name!r}[/red]")
        _print(f"  Known: {', '.join(_reg.registered_ids())}")
        raise typer.Exit(code=1)
    manifest = sentinel.bootstrap()
    health = sentinel.health_status() if sentinel.is_enabled() else None
    catalog = sentinel.load_catalog("default")
    unread = sentinel.read_inbox(only_unread=True)

    if STATE.json_out:
        _emit_json({
            "manifest": asdict(manifest),
            "health": asdict(health) if health else None,
            "catalog": catalog,
            "unread_count": len(unread),
            "enabled": sentinel.is_enabled(),
        })
        return

    _print(f"[bold]{manifest.title}[/bold]  [dim](id: {manifest.id}, tier {manifest.tier})[/dim]")
    _print(f"  manifest-hash:  sha256:{manifest.manifest_hash[:24]}...")
    hash_ok = manifest.verify_hash()
    _print(f"  integrity:      {'[green]✓ verified[/green]' if hash_ok else '[red]✗ MISMATCH[/red]'}")
    _print(f"  kill switch:    {manifest.kill_switch_env or '(none)'}  "
           f"{'[red]ACTIVE[/red]' if not sentinel.is_enabled() else '[dim](dormant)[/dim]'}")
    if manifest.voice_model:
        _print(f"  voice model:    {manifest.voice_model}")
    _print()
    _print(f"[bold]Articles[/bold] ({len(manifest.articles)} self-bindings)")
    for i, article in enumerate(manifest.articles, 1):
        _print(f"  {i}. {article}")
    _print()
    if health:
        color = {"ok": "green", "warning": "yellow", "error": "red", "unknown": "dim"}
        c = color.get(health.level, "white")
        _print(f"[bold]Health:[/bold] [{c}]{health.level.upper()}[/{c}]  {health.summary}")
        if health.detail:
            _print(f"  [dim]{health.detail}[/dim]")
        _print()
    if catalog:
        counts = catalog.get("counts", {})
        if counts:
            _print(f"[bold]Last scan[/bold]  ({catalog.get('scanned_at', '?')})")
            for sev in ("alert", "warning", "info"):
                if counts.get(sev, 0) > 0:
                    color = {"alert": "red", "warning": "yellow", "info": "cyan"}[sev]
                    _print(f"  [{color}]{sev}:[/{color}] {counts[sev]}")
        findings = catalog.get("findings", [])[:5]
        if findings:
            _print("  recent findings:")
            for f in findings:
                _print(f"    [dim]{f.get('kind', '?'):20s}[/dim] {f.get('summary', '')[:60]}")
    if unread:
        _print(f"\n[bold]Unread notifications:[/bold] {len(unread)}")
        for n in unread[:3]:
            sev_color = {"info": "cyan", "warning": "yellow", "alert": "red"}.get(n.severity, "white")
            _print(f"  [{sev_color}]{n.severity}[/{sev_color}]  {n.title}")


@sentinels_app.command("notifications")
def sentinels_notifications_cmd(
    ack_all: bool = typer.Option(False, "--ack", help="Mark all unread notifications acknowledged after viewing."),
) -> None:
    """Unread notifications across every sentinel, newest first."""
    from .stewardship import registry as _reg
    notifications = _reg.gather_unread_notifications(SETTINGS.paths.data_dir)
    if STATE.json_out:
        from dataclasses import asdict
        _emit_json([asdict(n) for n in notifications])
        if ack_all:
            for s in _reg.instantiate_all(SETTINGS.paths.data_dir):
                s.acknowledge_all()
        return
    if not notifications:
        _print("[green]✓ no unread notifications.[/green]")
        return
    _print(f"[bold]{len(notifications)} unread notification(s)[/bold]")
    sev_color = {"info": "cyan", "warning": "yellow", "alert": "red"}
    for n in notifications:
        c = sev_color.get(n.severity, "white")
        _print(f"\n  [{c}]{n.severity.upper()}[/{c}]  [bold]{n.title}[/bold]  [dim]({n.sentinel_id} · {n.observed_at})[/dim]")
        for line in n.message.split("\n")[:4]:
            _print(f"    {line}")
    if ack_all:
        total = 0
        for s in _reg.instantiate_all(SETTINGS.paths.data_dir):
            total += s.acknowledge_all()
        _print(f"\n[green]✓ acknowledged {total} notification(s).[/green]")
    else:
        _print(f"\n[dim]To acknowledge all: [bold]sov sentinels notifications --ack[/bold][/dim]")


@sentinels_app.command("articles")
def sentinels_articles_cmd(
    name: str = typer.Argument(...),
) -> None:
    """Show one sentinel's self-binding articles (its mini-constitution)."""
    from .stewardship import registry as _reg
    sentinel = _reg.instantiate(name, SETTINGS.paths.data_dir)
    if sentinel is None:
        _print(f"[red]✗ no sentinel registered with id {name!r}[/red]")
        raise typer.Exit(code=1)
    manifest = sentinel.bootstrap()
    if STATE.json_out:
        _emit_json({"articles": manifest.articles, "hash": manifest.manifest_hash})
        return
    _print(f"[bold]{manifest.title}[/bold]  [dim](id: {manifest.id})[/dim]")
    _print(f"  hash: sha256:{manifest.manifest_hash[:24]}...")
    _print(f"  integrity: {'[green]verified[/green]' if manifest.verify_hash() else '[red]MISMATCH[/red]'}")
    _print()
    for i, article in enumerate(manifest.articles, 1):
        _print(f"  [bold]{i}.[/bold] {article}")


# ─── sov cadence — per-collaborator portraits ─────────────────────────────
#
# A working portrait of each person Aria collaborates with. Skills, velocity,
# moments, learning style, forgetting curves. Per-domain, not flat. Decays
# over time. Owned by the person — full transparency, never used as grading.

cadence_app = typer.Typer(
    name="cadence",
    help="Per-collaborator portraits — skills, velocity, moments, learning style.",
    no_args_is_help=True,
)
app.add_typer(cadence_app, name="cadence")


def _cadence_load_or_create(person_id: str):
    """Load profile, or create a fresh one if missing."""
    from . import cadence as _cad
    profile = _cad.load_profile(person_id, SETTINGS.paths.data_dir)
    if profile is None:
        # Auto-seed default operator if that's the requested id
        if person_id == "operator":
            profile = _cad.seed_default_operator(SETTINGS.paths.data_dir)
        else:
            profile = _cad.Profile(person_id=person_id, display_name=person_id)
            _cad.save_profile(profile, SETTINGS.paths.data_dir)
    return profile


@cadence_app.command("list")
def cadence_list_cmd() -> None:
    """List everyone with a portrait on file."""
    from . import cadence as _cad
    profiles = _cad.list_profiles(SETTINGS.paths.data_dir)
    if STATE.json_out:
        _emit_json([
            {"person_id": p.person_id, "display_name": p.display_name,
             "stretch_sigma": p.stretch_sigma,
             "skill_count": len(p.skills), "moment_count": len(p.moments),
             "last_active_at": p.last_active_at}
            for p in profiles
        ])
        return
    if not profiles:
        _print("[dim]No portraits on file yet. Try [bold]sov cadence profile operator[/bold] to seed.[/dim]")
        return
    _print(f"[bold]{len(profiles)} portrait(s):[/bold]")
    for p in profiles:
        _print(
            f"  [bold]{p.display_name or p.person_id:18s}[/bold] "
            f"σ={p.stretch_sigma:.2f}  skills={len(p.skills)}  "
            f"moments={len(p.moments)}  [dim]last: {p.last_active_at or 'never'}[/dim]"
        )


@cadence_app.command("profile")
def cadence_profile_cmd(
    person_id: str = typer.Argument("operator", help="Person id (default: 'operator')."),
) -> None:
    """Show the full portrait for a person."""
    from . import cadence as _cad
    profile = _cad.load_profile(person_id, SETTINGS.paths.data_dir)
    if profile is None:
        if person_id == "operator":
            profile = _cad.seed_default_operator(SETTINGS.paths.data_dir)
            _print(f"[green]✓ seeded default operator profile.[/green]\n")
        else:
            _print(f"[yellow]no portrait for {person_id!r}.[/yellow] "
                   f"Create with [bold]sov cadence log skill {person_id} ...[/bold]")
            raise typer.Exit(code=1)
    if STATE.json_out:
        from dataclasses import asdict
        _emit_json(asdict(profile))
        return
    now = _cad._iso_now()
    _print(f"[bold]Portrait: {profile.display_name or profile.person_id}[/bold]  "
           f"([dim]σ={profile.stretch_sigma:.2f}, last active {profile.last_active_at or 'never'}[/dim])\n")
    # Learning style
    ls = profile.learning_style
    modes = [m for m, v in [("kinetic", ls.kinetic), ("verbal", ls.verbal),
                            ("visual", ls.visual), ("ambient", ls.ambient),
                            ("context-first", ls.context_first), ("pair", ls.pair),
                            ("quiet", ls.quiet)] if v]
    _print(f"[bold]Learning style[/bold]  [dim]({ls.preferred_context_depth} depth)[/dim]")
    if modes:
        _print(f"  modes:   {', '.join(modes)}")
    if ls.notes:
        _print(f"  notes:   [dim]{ls.notes}[/dim]")
    # Skills by domain
    if profile.skills:
        _print(f"\n[bold]Skills[/bold]  ({len(profile.skills)} tracked)")
        domains: dict[str, list] = {}
        for key, skill in profile.skills.items():
            domains.setdefault(skill.domain, []).append(skill)
        for domain, skills in sorted(domains.items()):
            _print(f"  [dim]── {domain} ──[/dim]")
            for s in sorted(skills, key=lambda x: -x.current_confidence(now)):
                conf = s.current_confidence(now)
                bar = _conf_bar(conf)
                _print(f"    {s.name:24s} {bar} {conf:.2f}  [dim]×{s.practice_count}[/dim]")
    # Velocity EWMA
    if profile.velocity_ewma:
        _print(f"\n[bold]Velocity (EWMA seconds)[/bold]")
        for task_type, secs in sorted(profile.velocity_ewma.items()):
            _print(f"  {task_type:24s} {_fmt_duration(secs)}")
    # Recent moments
    if profile.moments:
        recent = profile.moments[-5:]
        _print(f"\n[bold]Recent moments[/bold]  (showing last {len(recent)} of {len(profile.moments)})")
        type_color = {"spark": "yellow", "breakthrough": "green",
                      "struggle": "magenta", "resonance": "cyan", "mastery": "bold green"}
        for m in recent:
            c = type_color.get(m.type, "white")
            _print(f"  [{c}]{m.type:14s}[/{c}] {m.domain:14s} {m.summary[:60]}")
    # Concepts due for review
    due = _cad.due_for_review(profile, now)
    if due:
        _print(f"\n[bold]Worth revisiting[/bold]  ({len(due)} concept(s))")
        for rc in due[:5]:
            _print(f"  [dim]{rc.domain}:[/dim]{rc.concept}  [dim](half-life {rc.half_life_days:.0f}d)[/dim]")


def _conf_bar(conf: float, width: int = 10) -> str:
    filled = int(round(conf * width))
    return "[" + "█" * filled + " " * (width - filled) + "]"


def _fmt_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f}s"
    if seconds < 3600:
        return f"{seconds/60:.1f}m"
    return f"{seconds/3600:.1f}h"


# ─── Sub-subapp: sov cadence log ─────────────────────────────────────────

cadence_log_app = typer.Typer(name="log", help="Record observations.", no_args_is_help=True)
cadence_app.add_typer(cadence_log_app, name="log")


@cadence_log_app.command("skill")
def cadence_log_skill_cmd(
    person_id: str = typer.Argument(...),
    domain: str = typer.Argument(..., help="e.g., 'python', 'security', 'writing'"),
    name: str = typer.Argument(..., help="The specific skill."),
    confidence: float = typer.Option(0.5, "--confidence", "-c", min=0.0, max=1.0),
    note: str = typer.Option("", "--note", "-n"),
) -> None:
    """Record a skill observation. Increments practice count + freshens lineage."""
    from . import cadence as _cad
    profile = _cadence_load_or_create(person_id)
    key = f"{domain}:{name}"
    now = _cad._iso_now()
    if key in profile.skills:
        s = profile.skills[key]
        # EWMA smooth the confidence
        s.confidence = 0.7 * s.confidence + 0.3 * confidence
        s.practice_count += 1
    else:
        s = _cad.SkillNode(
            domain=domain, name=name, confidence=confidence,
            first_observed_at=now, practice_count=1,
        )
        profile.skills[key] = s
    s.last_practiced_at = now
    if note:
        s.notes.append(f"{now}: {note}")
    # Detect resonance for new entries
    resonance = _cad.detect_resonance(profile, s) if profile.skills.get(key) is s else []
    _cad.save_profile(profile, SETTINGS.paths.data_dir)
    _print(f"[green]✓ logged[/green]  {key}  confidence={s.confidence:.2f}  practices={s.practice_count}")
    if resonance:
        _print(f"  [cyan]resonance candidates:[/cyan] {', '.join(resonance[:5])}")
        _print(f"  [dim](consider whether one of these explains your velocity here)[/dim]")


@cadence_log_app.command("velocity")
def cadence_log_velocity_cmd(
    person_id: str = typer.Argument(...),
    task_type: str = typer.Argument(...),
    duration_seconds: float = typer.Argument(...),
    outcome: str = typer.Option("ok", "--outcome", "-o", help="ok|partial|stuck"),
    note: str = typer.Option("", "--note", "-n"),
) -> None:
    """Record a velocity sample. EWMA updates; breakthroughs and struggles auto-flagged."""
    from . import cadence as _cad
    if outcome not in ("ok", "partial", "stuck"):
        _print(f"[red]✗ outcome must be ok|partial|stuck, got {outcome!r}[/red]")
        raise typer.Exit(code=2)
    profile = _cadence_load_or_create(person_id)
    sample = _cad.VelocitySample(
        task_type=task_type, duration_seconds=duration_seconds,
        outcome=outcome, observed_at=_cad._iso_now(), notes=note,
    )
    # Detect signals BEFORE updating EWMA (so we compare to prior)
    breakthrough = _cad.detect_breakthrough(profile, sample)
    struggle = _cad.detect_struggle(profile, sample)
    _cad.update_velocity_ewma(profile, sample)
    profile.velocity_samples.append(sample)
    # Cap stored samples (older ones already folded into EWMA)
    if len(profile.velocity_samples) > 100:
        profile.velocity_samples = profile.velocity_samples[-100:]
    # Auto-log moment if a signal fired
    if breakthrough:
        profile.moments.append(_cad.Moment(
            type="breakthrough", domain=task_type,
            summary=f"velocity {_fmt_duration(duration_seconds)} vs EWMA",
            observed_at=sample.observed_at,
        ))
    elif struggle:
        profile.moments.append(_cad.Moment(
            type="struggle", domain=task_type,
            summary=f"slowdown or stuck — worth revisiting",
            observed_at=sample.observed_at,
        ))
    _cad.save_profile(profile, SETTINGS.paths.data_dir)
    _print(f"[green]✓ logged[/green]  {task_type} {_fmt_duration(duration_seconds)} ({outcome})")
    new_ewma = profile.velocity_ewma.get(task_type, 0)
    _print(f"  EWMA: {_fmt_duration(new_ewma)}")
    if breakthrough:
        _print(f"  [green]✦ breakthrough[/green] — significantly faster than recent average")
    if struggle:
        _print(f"  [magenta]◇ worth revisiting[/magenta] — slower or stuck this time; no judgment, just data")


@cadence_log_app.command("moment")
def cadence_log_moment_cmd(
    person_id: str = typer.Argument(...),
    moment_type: str = typer.Argument(..., help="spark|breakthrough|struggle|resonance|mastery"),
    domain: str = typer.Argument(...),
    summary: str = typer.Argument(...),
    skills: str = typer.Option("", "--skills", help="Comma-separated related skills."),
) -> None:
    """Manually log a meaningful moment."""
    from . import cadence as _cad
    valid = ("spark", "breakthrough", "struggle", "resonance", "mastery")
    if moment_type not in valid:
        _print(f"[red]✗ moment_type must be one of {valid}[/red]")
        raise typer.Exit(code=2)
    profile = _cadence_load_or_create(person_id)
    related = [s.strip() for s in skills.split(",") if s.strip()] if skills else []
    m = _cad.Moment(
        type=moment_type, domain=domain, summary=summary,
        observed_at=_cad._iso_now(), related_skills=related,
    )
    profile.moments.append(m)
    _cad.save_profile(profile, SETTINGS.paths.data_dir)
    _print(f"[green]✓ moment logged[/green]  {moment_type} · {domain} · {summary}")


# ─── sov cadence suggest ─────────────────────────────────────────────────


@cadence_app.command("suggest")
def cadence_suggest_cmd(
    person_id: str = typer.Argument("operator"),
    domain: str | None = typer.Option(None, "--domain", "-d"),
) -> None:
    """What to focus on next: stretch edges + concepts worth revisiting."""
    from . import cadence as _cad
    profile = _cad.load_profile(person_id, SETTINGS.paths.data_dir)
    if profile is None:
        _print(f"[yellow]no portrait for {person_id!r}.[/yellow]")
        raise typer.Exit(code=1)
    now = _cad._iso_now()
    if STATE.json_out:
        out = {"due_for_review": [], "frontiers": {}}
        for rc in _cad.due_for_review(profile, now):
            out["due_for_review"].append({"concept": rc.concept, "domain": rc.domain,
                                          "half_life_days": rc.half_life_days})
        domains = {domain} if domain else {s.domain for s in profile.skills.values()}
        for d in domains:
            out["frontiers"][d] = _cad.stretch_vector(profile, d, now)
        _emit_json(out)
        return
    due = _cad.due_for_review(profile, now)
    if due:
        _print(f"[bold]Worth revisiting[/bold]")
        for rc in due[:5]:
            _print(f"  [dim]{rc.domain}:[/dim]{rc.concept}  [dim](half-life now {rc.half_life_days:.0f}d)[/dim]")
        _print()
    domains = {domain} if domain else {s.domain for s in profile.skills.values()}
    if not domains:
        _print("[dim]No skills logged yet. Use [bold]sov cadence log skill[/bold] to begin.[/dim]")
        return
    for d in sorted(domains):
        sv = _cad.stretch_vector(profile, d, now)
        _print(f"[bold]Frontier — {d}[/bold]")
        if sv["frontier_skills"]:
            _print(f"  edge skills:        {', '.join(sv['frontier_skills'][:5])}")
        if sv["mastered_skills"]:
            _print(f"  foundation:         {', '.join(sv['mastered_skills'][:3])}")
        if sv["unexplored_lineage"]:
            _print(f"  unexplored kin:     {', '.join(sv['unexplored_lineage'][:5])}")
        _print(f"  reach factor (σ·n): {sv['reach_factor']:.2f}")


# ─── sov cadence style ───────────────────────────────────────────────────


@cadence_app.command("style")
def cadence_style_cmd(
    person_id: str = typer.Argument("operator"),
    set_flag: list[str] = typer.Option([], "--set", "-s",
                                        help="key=value (kinetic|verbal|visual|ambient|context_first|pair|quiet=true/false, "
                                             "preferred_context_depth=shallow|medium|deep, notes='...')"),
) -> None:
    """Show or set learning style preferences."""
    from . import cadence as _cad
    profile = _cadence_load_or_create(person_id)
    if not set_flag:
        ls = profile.learning_style
        from dataclasses import asdict
        if STATE.json_out:
            _emit_json(asdict(ls))
            return
        _print(f"[bold]Learning style for {profile.display_name or person_id}[/bold]")
        for k, v in asdict(ls).items():
            _print(f"  {k:24s} {v}")
        return
    # Apply --set flags
    bool_keys = {"kinetic", "verbal", "visual", "ambient", "context_first", "pair", "quiet"}
    for flag in set_flag:
        if "=" not in flag:
            _print(f"[red]✗ --set requires key=value, got {flag!r}[/red]")
            raise typer.Exit(code=2)
        k, v = flag.split("=", 1)
        k = k.strip(); v = v.strip()
        if k in bool_keys:
            setattr(profile.learning_style, k, v.lower() in ("true", "yes", "1", "on"))
        elif k == "preferred_context_depth":
            if v not in ("shallow", "medium", "deep"):
                _print(f"[red]✗ preferred_context_depth must be shallow|medium|deep[/red]")
                raise typer.Exit(code=2)
            profile.learning_style.preferred_context_depth = v
        elif k == "notes":
            profile.learning_style.notes = v
        else:
            _print(f"[red]✗ unknown key: {k}[/red]")
            raise typer.Exit(code=2)
    _cad.save_profile(profile, SETTINGS.paths.data_dir)
    _print(f"[green]✓ style updated[/green]")


# ─── sov cadence recall ──────────────────────────────────────────────────


@cadence_app.command("recall")
def cadence_recall_cmd(
    person_id: str = typer.Argument(...),
    domain: str = typer.Argument(...),
    concept: str = typer.Argument(...),
    success: bool = typer.Option(True, "--success/--miss",
                                  help="Did the person successfully recall this?"),
) -> None:
    """Record a recall event. Successful → half-life doubles. Missed → halves."""
    from . import cadence as _cad
    profile = _cadence_load_or_create(person_id)
    rc = _cad.record_recall(profile, concept, domain, success)
    _cad.save_profile(profile, SETTINGS.paths.data_dir)
    word = "successful" if success else "missed"
    _print(f"[green]✓ {word} recall[/green]  {domain}:{concept}")
    _print(f"  half-life now {rc.half_life_days:.1f}d  (successes={rc.successful_recalls}, misses={rc.missed_recalls})")


# ─── sov cadence chapter ─────────────────────────────────────────────────
#
# Alignment-gated learning arcs. Aria can move ahead, but a chapter doesn't
# close until alignment is confirmed. Productivity isn't gated; understanding
# is.

cadence_chapter_app = typer.Typer(
    name="chapter",
    help="Alignment-gated learning arcs. A chapter closes only when understanding is in place.",
    no_args_is_help=True,
)
cadence_app.add_typer(cadence_chapter_app, name="chapter")


@cadence_chapter_app.command("open")
def cadence_chapter_open_cmd(
    person_id: str = typer.Argument(...),
    chapter_id: str = typer.Argument(..., help="Short slug, e.g., 'ch-013-decorators'"),
    title: str = typer.Argument(...),
    domain: str = typer.Option(..., "--domain", "-d"),
) -> None:
    """Open a new chapter. Records Aria's current pace as the opening depth."""
    from . import cadence as _cad
    profile = _cadence_load_or_create(person_id)
    chapter = _cad.open_chapter(profile, chapter_id, title, domain)
    _cad.save_profile(profile, SETTINGS.paths.data_dir)
    _print(f"[green]✓ chapter opened[/green]  {chapter_id} · [bold]{title}[/bold]")
    _print(f"  domain:               {domain}")
    _print(f"  Aria's pace at open:  {chapter.aria_pace_at_open:.2f}")
    _print(f"  [dim]Cannot close without `sov cadence chapter align ...`[/dim]")


@cadence_chapter_app.command("align")
def cadence_chapter_align_cmd(
    person_id: str = typer.Argument(...),
    chapter_id: str = typer.Argument(...),
    prompt: str = typer.Argument(..., help="What Aria asked to check understanding."),
    response: str = typer.Argument(..., help="What the person said back."),
    score: float = typer.Argument(..., min=0.0, max=1.0,
                                   help="0.0–1.0. <0.5 means circle back, don't close."),
) -> None:
    """Record an alignment check. This is the gate; chapters won't close without one."""
    from . import cadence as _cad
    profile = _cadence_load_or_create(person_id)
    ok = _cad.record_alignment_check(profile, chapter_id, prompt, response, score)
    if not ok:
        _print(f"[red]✗ chapter {chapter_id!r} not found or already closed[/red]")
        raise typer.Exit(code=1)
    _cad.save_profile(profile, SETTINGS.paths.data_dir)
    _print(f"[green]✓ alignment check recorded[/green]  score={score:.2f}")
    if score < 0.5:
        _print(f"  [magenta]◇ score below 0.5 — circle back before closing.[/magenta]")
        _print(f"     [dim]Reinforce the concepts in this chapter; record another align when ready.[/dim]")
    elif score < 0.8:
        _print(f"  [yellow]◇ workable, not yet solid — one more reinforcement pass recommended.[/yellow]")
    else:
        _print(f"  [green]◇ understanding looks in place. Safe to close.[/green]")


@cadence_chapter_app.command("close")
def cadence_chapter_close_cmd(
    person_id: str = typer.Argument(...),
    chapter_id: str = typer.Argument(...),
    summary: str = typer.Option("", "--summary", "-s"),
) -> None:
    """Close a chapter. Refuses if no alignment check has been recorded."""
    from . import cadence as _cad
    profile = _cadence_load_or_create(person_id)
    chapter = _cad.close_chapter(profile, chapter_id, summary)
    if chapter is None:
        _print(f"[red]✗ cannot close[/red]")
        _print(f"  Either the chapter isn't open, or no alignment check has been recorded.")
        _print(f"  Record one with: [bold]sov cadence chapter align {person_id} {chapter_id} \"...\" \"...\" 0.8[/bold]")
        raise typer.Exit(code=1)
    _cad.save_profile(profile, SETTINGS.paths.data_dir)
    _print(f"[green]✓ chapter closed[/green]  {chapter_id} · [bold]{chapter.title}[/bold]")
    _print(f"  Aria's pace:    {chapter.aria_pace_at_open:.2f} → {chapter.aria_pace_at_close:.2f}")
    _print(f"  alignment checks: {len(chapter.alignment_checks)}")
    if summary:
        _print(f"  summary: {summary}")


@cadence_chapter_app.command("list")
def cadence_chapter_list_cmd(
    person_id: str = typer.Argument("operator"),
) -> None:
    """List a person's chapters — open ones first, then closed history."""
    from . import cadence as _cad
    profile = _cad.load_profile(person_id, SETTINGS.paths.data_dir)
    if profile is None:
        _print(f"[yellow]no portrait for {person_id!r}.[/yellow]")
        raise typer.Exit(code=1)
    chapters = profile.chapters or []
    if STATE.json_out:
        from dataclasses import asdict
        _emit_json([asdict(c) for c in chapters])
        return
    open_ch = [c for c in chapters if c.is_open]
    closed_ch = [c for c in chapters if not c.is_open]
    if open_ch:
        _print(f"[bold]Open chapters ({len(open_ch)}):[/bold]")
        for c in open_ch:
            gate = "✓ alignment in" if c.has_alignment_check else "◇ awaiting alignment"
            _print(f"  [bold]{c.chapter_id:20s}[/bold] {c.title}")
            _print(f"    [dim]domain:[/dim] {c.domain}  [dim]opened:[/dim] {c.opened_at[:10]}  [dim]gate:[/dim] {gate}")
    if closed_ch:
        _print(f"\n[bold]Closed chapters ({len(closed_ch)}):[/bold]")
        for c in closed_ch[-10:]:
            _print(f"  [dim]{c.chapter_id:20s}[/dim] {c.title}  "
                   f"[dim]({c.aria_pace_at_open:.2f}→{c.aria_pace_at_close:.2f}, "
                   f"{len(c.alignment_checks)} check(s))[/dim]")
    if not chapters:
        _print(f"[dim]No chapters yet. Start one with [bold]sov cadence chapter open {person_id} ...[/bold][/dim]")


# ─── sov theme — the theme workshop ──────────────────────────────────────
#
# 16 themes ship curated in cockpit/themes.py. This subapp is the workbench
# where new ones get built, cloned, edited, applied, deleted. Storage is
# JSON, one file per theme, at data_dir/themes/.

theme_app = typer.Typer(
    name="theme",
    help="Build, clone, edit, and apply cockpit themes.",
    no_args_is_help=True,
)
app.add_typer(theme_app, name="theme")


def _theme_resolve_source(name: str):
    """Resolve a theme name to (curated_or_user, theme_obj). Returns (None, None) if missing."""
    from .cockpit.themes import get_theme_by_name
    from .cockpit import user_themes as _ut
    curated = get_theme_by_name(name)
    if curated is not None:
        return ("curated", curated)
    user = _ut.load(name, SETTINGS.paths.data_dir)
    if user is not None:
        return ("user", user)
    return (None, None)


@theme_app.command("list")
def theme_list_cmd() -> None:
    """List every theme available — curated and user, grouped."""
    from .cockpit.themes import CURATED_THEMES, themes_by_family
    from .cockpit import user_themes as _ut

    active = _ut.get_active_theme_name(SETTINGS.paths.data_dir)
    users = _ut.list_all(SETTINGS.paths.data_dir)

    if STATE.json_out:
        _emit_json({
            "active": active,
            "curated": [{"name": t.name, "family": t.family, "mood": t.mood, "dark": t.dark}
                        for t in CURATED_THEMES],
            "user": [{"name": t.name, "family": t.family, "mood": t.mood,
                      "dark": t.dark, "cloned_from": t.cloned_from,
                      "created_by": t.created_by}
                     for t in users],
            "user_capacity": {"used": len(users), "soft_cap": _ut.SOFT_CAP},
        })
        return

    if active:
        _print(f"[bold]Active:[/bold] [green]{active}[/green]")
    else:
        _print("[bold]Active:[/bold] [dim]<none — cockpit picks Textual's default>[/dim]")
    _print()
    _print("[bold]Curated themes (16):[/bold]")
    for family, themes in themes_by_family().items():
        _print(f"  [dim]── {family} ──[/dim]")
        for t in themes:
            marker = " [green]●[/green]" if t.name == active else "  "
            _print(f"    {marker} [bold]{t.name:18s}[/bold] [dim]{t.mood}[/dim]")
    _print()
    if users:
        _print(f"[bold]Your themes ({len(users)}/{_ut.SOFT_CAP}):[/bold]")
        for t in users:
            marker = " [green]●[/green]" if t.name == active else "  "
            origin = f"[dim](from {t.cloned_from})[/dim]" if t.cloned_from else "[dim](from scratch)[/dim]"
            _print(f"    {marker} [bold]{t.name:18s}[/bold] {origin}  [dim]{t.mood}[/dim]")
        if len(users) >= _ut.SOFT_CAP:
            _print(f"\n  [yellow]⚠ at soft cap ({_ut.SOFT_CAP}). New themes still allowed; consider pruning.[/yellow]")
    else:
        _print(f"[bold]Your themes (0/{_ut.SOFT_CAP}):[/bold] [dim]<none yet — try `sov theme clone aria-ember my-fire` to start>[/dim]")


@theme_app.command("show")
def theme_show_cmd(
    name: str = typer.Argument(..., help="Theme name (curated or user)."),
) -> None:
    """Inspect one theme's full palette."""
    kind, t = _theme_resolve_source(name)
    if t is None:
        _print(f"[red]✗ theme {name!r} not found.[/red]  Try [bold]sov theme list[/bold].")
        raise typer.Exit(code=1)
    from dataclasses import asdict
    if STATE.json_out:
        _emit_json({"kind": kind, "theme": asdict(t)})
        return
    _print(f"[bold]{t.name}[/bold]  [dim]({kind})[/dim]")
    _print(f"  family:   {t.family}")
    _print(f"  mood:     {t.mood}")
    _print(f"  dark:     {t.dark}")
    _print(f"  [dim]── palette ──[/dim]")
    for slot in ("background", "surface", "panel", "primary", "accent",
                 "secondary", "success", "warning", "error", "foreground", "boost"):
        val = getattr(t, slot, None)
        if val:
            _print(f"  {slot:14s}  [bold]{val}[/bold]")
    if kind == "user":
        _print(f"  [dim]── authorship ──[/dim]")
        _print(f"  created_by:    {t.created_by}")
        if t.cloned_from:
            _print(f"  cloned_from:   {t.cloned_from}")
        if t.created_at:
            _print(f"  created_at:    {t.created_at}")
        if t.modified_at and t.modified_at != t.created_at:
            _print(f"  modified_at:   {t.modified_at}")
        if t.notes:
            _print(f"  notes:         {t.notes}")
        if t.effects:
            _print(f"  effects:       {t.effects}")


@theme_app.command("clone")
def theme_clone_cmd(
    source: str = typer.Argument(..., help="Source theme name (curated or user)."),
    new_name: str = typer.Argument(..., help="Name for the new theme (e.g., 'my-fire')."),
    mood: str | None = typer.Option(None, "--mood", "-m", help="One-line vibe description."),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite if name already exists."),
) -> None:
    """Clone a theme so you can tweak its colors without modifying the original."""
    from .cockpit import user_themes as _ut

    kind, src = _theme_resolve_source(source)
    if src is None:
        _print(f"[red]✗ source theme {source!r} not found.[/red]")
        raise typer.Exit(code=1)
    users = _ut.list_all(SETTINGS.paths.data_dir)
    if len(users) >= _ut.SOFT_CAP and not any(u.name == new_name for u in users):
        _print(
            f"[yellow]⚠ at soft cap ({_ut.SOFT_CAP} user themes).[/yellow] "
            "Continuing — soft cap is a guideline, not a wall."
        )
    new_theme = _ut.clone(src, new_name=new_name, new_mood=mood)
    new_theme.family = "custom"  # cloned themes belong to the custom family
    try:
        path = _ut.save(new_theme, SETTINGS.paths.data_dir, force=force)
    except FileExistsError as e:
        _print(f"[red]✗ {e}[/red]")
        raise typer.Exit(code=1)
    except ValueError as e:
        _print(f"[red]✗ validation failed:[/red]\n{e}")
        raise typer.Exit(code=2)
    _print(f"[green]✓ cloned[/green]  {source} → {new_name}")
    _print(f"  file: {path}")
    _print(f"  next: edit the JSON to tweak colors, then [bold]sov theme apply {new_name}[/bold]")


@theme_app.command("apply")
def theme_apply_cmd(
    name: str = typer.Argument(..., help="Theme name to use as the cockpit's startup theme."),
) -> None:
    """Mark a theme as the cockpit's startup theme. Persists across sessions."""
    from .cockpit import user_themes as _ut

    kind, t = _theme_resolve_source(name)
    if t is None:
        _print(f"[red]✗ theme {name!r} not found.[/red]  Try [bold]sov theme list[/bold].")
        raise typer.Exit(code=1)
    path = _ut.set_active_theme_name(name, SETTINGS.paths.data_dir)
    _print(f"[green]✓ active theme:[/green] {name}  [dim]({kind})[/dim]")
    _print(f"  persisted to: {path}")
    _print(f"  next launch of [bold]sov-chat[/bold] will use this theme.")


@theme_app.command("delete")
def theme_delete_cmd(
    name: str = typer.Argument(..., help="User theme name to delete."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
) -> None:
    """Delete a user theme. Curated themes are protected."""
    from .cockpit import user_themes as _ut
    from .cockpit.themes import get_theme_by_name

    if get_theme_by_name(name) is not None:
        _print(f"[red]✗ {name!r} is a curated theme — cannot be deleted.[/red]")
        raise typer.Exit(code=1)
    if _ut.load(name, SETTINGS.paths.data_dir) is None:
        _print(f"[yellow]theme {name!r} not found.[/yellow]")
        raise typer.Exit(code=1)
    if not yes:
        confirm = typer.confirm(f"Delete user theme {name!r}?", default=False)
        if not confirm:
            _print("[dim]cancelled.[/dim]")
            raise typer.Exit(0)
    deleted = _ut.delete(name, SETTINGS.paths.data_dir)
    if deleted:
        _print(f"[green]✓ deleted[/green] {name}")
    else:
        _print(f"[red]✗ delete failed[/red]")
        raise typer.Exit(code=1)


@theme_app.command("active")
def theme_active_cmd() -> None:
    """Show the currently applied theme (whatever the cockpit will use on startup)."""
    from .cockpit import user_themes as _ut
    active = _ut.get_active_theme_name(SETTINGS.paths.data_dir)
    if STATE.json_out:
        _emit_json({"active": active})
        return
    if active:
        _print(f"active theme: [bold green]{active}[/bold green]")
    else:
        _print("active theme: [dim]<none set — cockpit uses Textual's default>[/dim]")


# ─── sov glyphs — visual identity sentinel ─────────────────────────────────
#
# Tier-1 stewardship: scan the source tree for non-ASCII glyphs, classify
# each (safe / borderline / unsafe), persist a catalog, propose replacements
# for unsafe glyphs that have known safe aliases, and surface coverage gaps
# where the system clearly wants a glyph it doesn't have a safe alias for.

glyphs_app = typer.Typer(
    name="glyphs",
    help="Glyph sentinel: catalog, classify, and propose safe replacements.",
    no_args_is_help=True,
)
app.add_typer(glyphs_app, name="glyphs")


def _glyphs_emit(flag: str, payload: dict) -> str | None:
    """Emit an event from a glyphs subcommand. Returns event_id or None on failure."""
    try:
        from .events import emit_event
        from ulid import ULID
        return emit_event(
            flag=flag, plane="meta", trace_id=str(ULID()), payload=payload,
        )
    except Exception:
        return None


@glyphs_app.command("scan")
def glyphs_scan_cmd(
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress progress; print only summary."),
) -> None:
    """Walk the source tree, build a fresh glyph catalog, persist it, emit an event."""
    from .stewardship import glyph_sentinel as _gs

    if not quiet:
        _print("[dim]scanning source tree...[/dim]")
    catalog = _gs.scan_source_tree()
    path = _gs.save_catalog(catalog, SETTINGS.paths.data_dir)
    event_id = _glyphs_emit("glyph_catalog_update", {
        "total_glyphs": len(catalog.glyphs),
        "safe_count": catalog.safe_count,
        "borderline_count": catalog.borderline_count,
        "unsafe_count": catalog.unsafe_count,
        "files_scanned": catalog.total_files_scanned,
        "catalog_path": str(path),
    })
    if STATE.json_out:
        _emit_json({
            "ok": True,
            "files_scanned": catalog.total_files_scanned,
            "total_glyphs": len(catalog.glyphs),
            "safe": catalog.safe_count,
            "borderline": catalog.borderline_count,
            "unsafe": catalog.unsafe_count,
            "catalog_path": str(path),
            "event_id": event_id,
        })
        return
    _print(f"[green]✓ catalog written:[/green] {path}")
    _print(f"  files scanned:    {catalog.total_files_scanned}")
    _print(f"  unique glyphs:    {len(catalog.glyphs)}")
    _print(f"  [green]safe:[/green]             {catalog.safe_count}")
    _print(f"  [yellow]borderline:[/yellow]       {catalog.borderline_count}")
    _print(f"  [red]unsafe:[/red]           {catalog.unsafe_count}")
    if catalog.replaceable_unsafe:
        n = len(catalog.replaceable_unsafe)
        _print(f"  [dim]→ {n} unsafe glyph(s) have known replacements (`sov glyphs proposals`)[/dim]")


@glyphs_app.command("status")
def glyphs_status_cmd() -> None:
    """Summarize the most recent catalog without rescanning."""
    from .stewardship import glyph_sentinel as _gs

    catalog = _gs.load_catalog(SETTINGS.paths.data_dir)
    if catalog is None:
        _print("[yellow]no catalog found.[/yellow] Run [bold]sov glyphs scan[/bold] first.")
        raise typer.Exit(code=1)
    if STATE.json_out:
        _emit_json({
            "generated_at": catalog.generated_at,
            "source_root": catalog.source_root,
            "files_scanned": catalog.total_files_scanned,
            "total_glyphs": len(catalog.glyphs),
            "safe": catalog.safe_count,
            "borderline": catalog.borderline_count,
            "unsafe": catalog.unsafe_count,
        })
        return
    _print(f"[bold]Glyph catalog[/bold]  ([dim]{catalog.generated_at}[/dim])")
    _print(f"  source root:      {catalog.source_root}")
    _print(f"  files scanned:    {catalog.total_files_scanned}")
    _print(f"  unique glyphs:    {len(catalog.glyphs)}")
    _print(f"  [green]safe:[/green]             {catalog.safe_count}")
    _print(f"  [yellow]borderline:[/yellow]       {catalog.borderline_count}")
    _print(f"  [red]unsafe:[/red]           {catalog.unsafe_count}")


@glyphs_app.command("show")
def glyphs_show_cmd(
    query: str = typer.Argument(..., help="A glyph (e.g., '◊'), or a codepoint (e.g., 'U+25CA')."),
) -> None:
    """Inspect one glyph: classification, the *reason* for it, where it appears,
    and how to upgrade it if it's not yet modern-materials-grade."""
    from .stewardship import glyph_sentinel as _gs

    catalog = _gs.load_catalog(SETTINGS.paths.data_dir)
    if catalog is None:
        _print("[yellow]no catalog found.[/yellow] Run [bold]sov glyphs scan[/bold] first.")
        raise typer.Exit(code=1)
    q = query.strip().upper()
    if q.startswith("U+"):
        codepoint = q
    elif len(query) == 1:
        codepoint = f"U+{ord(query):04X}"
    else:
        _print(f"[red]✗ query must be a single character or a U+XXXX codepoint, got: {query!r}[/red]")
        raise typer.Exit(code=2)
    entry = catalog.glyphs.get(codepoint)
    if entry is None:
        _print(f"[yellow]{codepoint} not in catalog.[/yellow]")
        raise typer.Exit(code=1)

    # Compose a human reason from the EAW property + classification.
    EAW_MEANINGS = {
        "N":  "Neutral — Unicode says one cell on every terminal. Safe.",
        "Na": "Narrow — half-width ASCII range. Safe.",
        "H":  "Halfwidth — explicit half-width. Safe.",
        "W":  "Wide — guaranteed two cells. Always unsafe for layouts.",
        "F":  "Fullwidth — explicit two-cell. Always unsafe for layouts.",
        "A":  "Ambiguous — one cell in Western locales, two in CJK. Risky.",
    }
    reason = EAW_MEANINGS.get(entry.east_asian_width, "unknown EAW property")

    upgrade_note = ""
    if entry.classification == "unsafe":
        if entry.proposed_replacement:
            upgrade_note = (
                f"[bold]Upgrade path:[/bold] replace with {entry.proposed_replacement!r}. "
                f"Modern-materials-2.0: hardened equivalent registered in glyphs.KNOWN_REPLACEMENTS."
            )
        else:
            upgrade_note = (
                "[bold]Coverage gap:[/bold] no registered safe alias yet. "
                "Pick a width-safe glyph that preserves the semantic role, "
                "add it to glyphs.KNOWN_REPLACEMENTS, then `sov glyphs scan` "
                "will propose the swap everywhere."
            )
    elif entry.classification == "borderline":
        upgrade_note = (
            "[bold]Borderline:[/bold] Unicode classifies this Ambiguous, but it's on "
            "the de-facto-narrow whitelist (empirically renders one cell in every "
            "terminal we've tested). Lower risk than unsafe; still worth replacing "
            "in width-critical contexts if a strictly-Neutral alternative exists."
        )
    elif entry.classification == "safe":
        upgrade_note = (
            "[bold]Safe:[/bold] Unicode-classified Neutral or Narrow — one cell on every "
            "terminal by spec. Use freely in banners, panels, and aligned layouts."
        )

    if STATE.json_out:
        from dataclasses import asdict
        d = asdict(entry)
        d["reason"] = reason
        d["upgrade_note"] = upgrade_note
        _emit_json(d)
        return

    color = {"safe": "green", "borderline": "yellow", "unsafe": "red"}[entry.classification]
    _print(f"[bold]{entry.codepoint}[/bold]  [{color}]{entry.classification.upper()}[/{color}]")
    _print(f"  char:                  {entry.char}")
    _print(f"  name:                  {entry.name}")
    _print(f"  east_asian_width:      {entry.east_asian_width}  [dim]({reason})[/dim]")
    _print(f"  de_facto_narrow:       {entry.de_facto_narrow}")
    _print(f"  total occurrences:     {entry.total_occurrences}")
    if entry.proposed_replacement:
        _print(f"  [bold]proposed replacement:[/bold]  {entry.proposed_replacement!r}")
    _print(f"  appears in {len(entry.appearances)} file(s):")
    for f, n in sorted(entry.appearances.items(), key=lambda kv: -kv[1])[:10]:
        _print(f"    {n:5d}  {f}")
    if len(entry.appearances) > 10:
        _print(f"    [dim]... and {len(entry.appearances) - 10} more[/dim]")
    if upgrade_note:
        _print(f"\n{upgrade_note}")


@glyphs_app.command("proposals")
def glyphs_proposals_cmd(
    limit: int = typer.Option(50, "--limit", "-n", help="Cap proposal count for legibility."),
) -> None:
    """Show actionable replacement proposals: unsafe glyphs with known safe aliases."""
    from .stewardship import glyph_sentinel as _gs

    catalog = _gs.load_catalog(SETTINGS.paths.data_dir)
    if catalog is None:
        _print("[yellow]no catalog.[/yellow] Run [bold]sov glyphs scan[/bold] first.")
        raise typer.Exit(code=1)
    props = _gs.generate_proposals(catalog)
    if STATE.json_out:
        from dataclasses import asdict
        _emit_json([asdict(p) for p in props[:limit]])
        return
    if not props:
        _print("[green]✓ no unsafe glyphs with known replacements found.[/green]")
        _print("  [dim]Either the codebase is already clean, or unsafe glyphs need new safe aliases (see `sov glyphs gaps`).[/dim]")
        return
    _print(f"[bold]{len(props)} replacement proposal(s)[/bold] (showing up to {limit})")
    for p in props[:limit]:
        _print(
            f"  [red]{p.char}[/red] {p.codepoint} → [green]{p.proposed_replacement!r}[/green]  "
            f"in [dim]{p.file_path}[/dim]  ×{p.occurrences}"
        )
    if len(props) > limit:
        _print(f"  [dim]... and {len(props) - limit} more (use --limit to see more)[/dim]")
    _print(
        "\n[dim]These are proposals, not auto-edits. The sentinel never modifies\n"
        "  source files. Apply selectively: read context, then edit.[/dim]"
    )


@glyphs_app.command("gaps")
def glyphs_gaps_cmd() -> None:
    """Show coverage gaps: unsafe glyphs with no registered safe replacement.

    Each gap is an opportunity to enrich glyphs.KNOWN_REPLACEMENTS with a
    new safe alias so future scans can propose it automatically.
    """
    from .stewardship import glyph_sentinel as _gs

    catalog = _gs.load_catalog(SETTINGS.paths.data_dir)
    if catalog is None:
        _print("[yellow]no catalog.[/yellow] Run [bold]sov glyphs scan[/bold] first.")
        raise typer.Exit(code=1)
    gaps = _gs.detect_coverage_gaps(catalog)
    if STATE.json_out:
        from dataclasses import asdict
        _emit_json([asdict(g) for g in gaps])
        return
    if not gaps:
        _print("[green]✓ no coverage gaps.[/green]")
        _print("  [dim]Every unsafe glyph in use has a registered safe replacement.[/dim]")
        return
    _print(f"[bold]{len(gaps)} coverage gap(s)[/bold] — unsafe glyphs without registered replacements:\n")
    for g in gaps:
        _print(f"  [red]{g.char}[/red]  {g.codepoint}  {g.name}")
        _print(f"      ×{g.occurrences} occurrence(s) across {len(g.files)} file(s)")
        _print(f"      [dim]{g.note}[/dim]")
        for f in g.files[:3]:
            _print(f"        - {f}")
        if len(g.files) > 3:
            _print(f"        - [dim]... +{len(g.files) - 3} more[/dim]")
        _print()


# ─── sov charter — Article V management ────────────────────────────────────
#
# This is the ONLY sanctioned write path to SIGNAL.md. The kill switch in
# the global callback permits dispatch to this subapp when integrity is
# violated, so amendments are always reachable.

charter_app = typer.Typer(
    name="charter",
    help="Inspect and amend the Sovereign System Design Charter (SIGNAL.md).",
    no_args_is_help=True,
)
app.add_typer(charter_app, name="charter")


@charter_app.command("status")
def charter_status_cmd() -> None:
    """Show the charter's integrity verdict (the same one the kill switch reads)."""
    from . import charter as _charter
    verdict = _charter.check_integrity()
    if STATE.json_out:
        _emit_json({
            "level": verdict.level,
            "summary": verdict.summary,
            "detail": verdict.detail,
            "kill_switch_active": verdict.kill_switch_active,
            "version": verdict.version,
            "recorded_hash": verdict.recorded_hash,
            "expected_hash": verdict.expected_hash,
            "charter_path": str(verdict.charter_path) if verdict.charter_path else None,
        })
        return
    glyph = {"ok": "✓", "warning": "⚠", "error": "✗"}[verdict.level]
    color = {"ok": "green", "warning": "yellow", "error": "red"}[verdict.level]
    _print(f"[{color}]{glyph} charter (SIGNAL.md): {verdict.summary}[/{color}]")
    if verdict.charter_path:
        _print(f"  [dim]path:[/dim] {verdict.charter_path}")
    if verdict.version:
        _print(f"  [dim]version:[/dim] {verdict.version}")
    if verdict.recorded_hash:
        _print(f"  [dim]recorded:[/dim] sha256:{verdict.recorded_hash}")
    if verdict.expected_hash and verdict.expected_hash != verdict.recorded_hash:
        _print(f"  [dim]computed:[/dim] sha256:{verdict.expected_hash}")
    if verdict.detail:
        _print(f"\n[dim]{verdict.detail}[/dim]")
    if verdict.kill_switch_active:
        _print(
            "\n[red bold]Kill switch is ACTIVE.[/red bold] "
            "Only `sov doctor` and `sov charter` will dispatch until resolved."
        )


@charter_app.command("amend")
def charter_amend_cmd(
    rationale: str = typer.Option(
        ..., "--rationale", "-r",
        help="Why is the charter being amended? Recorded in events.jsonl.",
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y",
        help="Skip the confirmation prompt (non-interactive use).",
    ),
) -> None:
    """Ratify or amend the charter: compute new hash, rewrite header, emit event.

    This is the only sanctioned way the charter's hash header may change.
    The kill switch is built so this command stays reachable even when
    every other command is refused.
    """
    from . import charter as _charter
    from .events import emit_event
    from ulid import ULID

    path = _charter.find_charter_path()
    if path is None:
        _die(2, "SIGNAL.md not found in the source tree.",
             hint="Ensure SIGNAL.md is at the sovereign-agent install root.")
        return

    text = path.read_text(encoding="utf-8")
    recorded_before = _charter.extract_recorded_hash(text)
    version_before = _charter.extract_version(text)
    expected_now = _charter.compute_content_hash(text)

    if recorded_before == expected_now:
        _print(
            "[yellow]⚠ charter already sealed at this content[/yellow]\n"
            f"  hash: sha256:{expected_now}\n"
            f"  version: {version_before}\n"
            "  Nothing to amend. To force a re-ratification, edit SIGNAL.md first."
        )
        raise typer.Exit(0)

    _print(f"[bold]Amendment summary[/bold]")
    _print(f"  charter:          {path}")
    _print(f"  version:          {version_before or '<unset>'}")
    _print(f"  recorded hash:    sha256:{recorded_before or '<PENDING>'}")
    _print(f"  new hash:         sha256:{expected_now}")
    _print(f"  rationale:        {rationale}")
    _print()
    if not yes:
        confirm = typer.confirm(
            "Apply this amendment? (writes to SIGNAL.md and events.jsonl)",
            default=False,
        )
        if not confirm:
            _print("[dim]aborted; no changes written.[/dim]")
            raise typer.Exit(0)

    # 1. Emit the event FIRST. Per the contract (charter.md amendment protocol),
    #    the amendment event must exist before the hash change is observable.
    trace_id = str(ULID())
    event_id = emit_event(
        flag="charter_amendment",
        plane="meta",
        trace_id=trace_id,
        payload={
            "version_before": version_before,
            "version_after": version_before,  # version bumps are a separate concern
            "hash_before": recorded_before,
            "hash_after": expected_now,
            "rationale": rationale,
            "charter_path": str(path),
        },
    )

    # 2. Rewrite the hash header in-place.
    new_text = _charter.rewrite_hash_in_text(text, expected_now)
    path.write_text(new_text, encoding="utf-8")

    _print(f"[green]✓ charter amended.[/green]")
    _print(f"  event_id:  {event_id}")
    _print(f"  new hash:  sha256:{expected_now}")
    _print(f"\n[dim]Run `sov doctor` to confirm integrity.[/dim]")


@charter_app.command("verify")
def charter_verify_cmd() -> None:
    """Alias for `charter status` — convenient post-edit check."""
    charter_status_cmd()


# ════════════════════════════════════════════════════════════════════════
# ◊ agentic — natural-language goal → plan → gap analysis → gated execute
#   (v0.2.35.0)  The flagship plain-English entry point. Aria plans, works
#   out which subsystems she needs vs. lacks, drafts proposals for the gaps,
#   routes flow-specific variants, and executes with a per-step approval gate.
#   Steps that would change Aria's own code/config always ask — even --yes.
# ════════════════════════════════════════════════════════════════════════


def _build_agentic_run():
    """Wire ErebloStore → ProjectsManager → AgenticLoop with the standard
    handlers; return (run, projects, project_id)."""
    from pathlib import Path
    from .persistence.store import ErebloStore
    from .persistence.projects import ProjectsManager
    from .workflow.agentic_loop import AgenticLoop
    from .workflow.handlers import ShellHandler, FileWriteHandler, FileReadHandler
    from .workflow.evolving_run import EvolvingAgenticRun
    from .workflow.requests import RequestStore

    store = ErebloStore(SETTINGS.paths.atoms_db)
    projects = ProjectsManager(store)
    loop = AgenticLoop(projects)
    requests = RequestStore(store)

    sandbox = SETTINGS.paths.sandbox_dir
    sandbox.mkdir(parents=True, exist_ok=True, mode=0o700)
    loop.register_tool_handler("shell", ShellHandler())
    loop.register_tool_handler("file_write", FileWriteHandler([sandbox]))
    loop.register_tool_handler("file_read", FileReadHandler([sandbox]))

    proj = projects.get_project_by_name("agentic")
    project_id = proj.project_id if proj else projects.create_project(
        "agentic", description="Goals run via `sov agentic`.")

    self_roots = [Path(__file__).resolve().parent, SETTINGS.paths.config_dir]
    proposals_root = SETTINGS.paths.data_dir / "proposals" / "capabilities"
    run = EvolvingAgenticRun(loop, proposals_root=proposals_root,
                             self_roots=self_roots, request_store=requests)
    return run, projects, project_id, requests


def _render_plan(plan) -> None:
    if STATE.json_out:
        _emit_json({
            "goal": plan.goal, "band": plan.band, "flow": plan.flow,
            "clarifying_questions": plan.clarifying_questions,
            "steps": [{"kind": s.action_kind, "title": s.title,
                       "input": s.action_input} for s in plan.steps],
            "gap": (None if not plan.gap_report else {
                "needed": plan.gap_report.needed,
                "available": plan.gap_report.available,
                "missing": plan.gap_report.missing}),
            "variant_choice": {k: (v[0].capability.name if v else None)
                               for k, v in plan.variant_choices.items()},
            "proposals_written": plan.proposals_written,
        })
        return
    _print(f"\n[bold cyan]◊ plan[/bold cyan]  [dim](maturity {plan.band})[/dim]")
    if plan.clarifying_questions:
        _print("[yellow]I need a little more to go on:[/yellow]")
        for q in plan.clarifying_questions:
            _print(f"  • {q}")
        return
    for i, s in enumerate(plan.steps, 1):
        best = plan.best_variant(s.action_kind)
        via = f"  [dim]via {best.capability.name} ({best.reason})[/dim]" if best else ""
        _print(f"  {i}. [{s.action_kind}] {s.title}{via}")
    if plan.gap_report:
        _print(f"\n[dim]subsystems — {plan.gap_report.summary_text()}[/dim]")
        if plan.gap_report.missing:
            _print(f"[yellow]missing: {', '.join(plan.gap_report.missing)}[/yellow]")
            for p in plan.proposals_written:
                _print(f"  [dim]drafted proposal:[/dim] {p}")
            _print("[dim]Review a draft, implement it, then move it into "
                   "workflow/handlers/ and register it to bring it online.[/dim]")


def _render_result(result) -> None:
    if STATE.json_out:
        _emit_json({"goal": result.goal, "decision": result.decision,
                    "workflow_id": result.workflow_id,
                    "final_status": result.final_status, "notes": result.notes})
        return
    colors = {"executed": "green", "paused_for_review": "yellow",
              "needs_capability": "yellow", "needs_clarification": "yellow",
              "blocked": "red"}
    c = colors.get(result.decision, "white")
    _render_plan(result.plan)
    _print(f"\n[bold {c}]◊ {result.decision.replace('_', ' ')}[/bold {c}]")
    for n in result.notes:
        _print(f"  • {n}")
    if result.final_status:
        bs = result.final_status.get("by_status", {})
        _print(f"  [dim]steps: {bs}[/dim]")
    if result.workflow_id:
        _print(f"  [dim]workflow: {result.workflow_id}  ·  watch with "
               f"`sov events --follow`[/dim]")


@app.command(name="agentic")
def agentic_cmd(
    goal: str = typer.Argument(..., help="Plain-English goal."),
    flow: str = typer.Option("", "--flow",
        help="Describe the flow/context so Aria routes the best variant."),
    plan_only: bool = typer.Option(False, "--plan",
        help="Plan + gap analysis only; don't execute."),
    yes: bool = typer.Option(False, "--yes", "-y",
        help="Batch-approve consequential steps (self-modifications still ask)."),
    allow_missing: bool = typer.Option(False, "--allow-missing",
        help="Proceed even if some subsystems are missing."),
) -> None:
    """Goal → maturity gate → plan → gap analysis → variant routing → gated run.

    M0 asks you to clarify · M1 writes a plan without running it · M2/M3 run
    with per-step approval. Any step that would modify Aria's own code or
    config always prompts, even with --yes.

        sov agentic "set up a python project skeleton with tests and a readme"
        sov agentic "inventory the sandbox for markdown" --plan
        sov agentic "build and test the parser" --flow "git, build, test"
    """
    run, _projects, project_id, _requests = _build_agentic_run()

    if plan_only:
        _render_plan(run.plan_only(goal, flow=flow))
        raise typer.Exit(ExitCode.OK)

    def approve(step, decision) -> bool:
        modifies_self = "code or configuration" in decision.reason
        if yes and not modifies_self:
            return True
        if STATE.json_out:
            return False  # can't prompt in json mode → hold for a human
        _print(f"\n[bold]proposed step[/bold]: {step.title}")
        _print(f"  kind: {step.action_kind}   input: {step.action_input}")
        _print(f"  [yellow]{decision.reason}[/yellow]")
        if modifies_self:
            _print("  [red]this touches Aria's own code/config — approval required[/red]")
        return typer.confirm("  run this step?")

    result = run.execute(goal, project_id, flow=flow, approve=approve,
                         allow_missing=allow_missing)
    _render_result(result)
    ok = result.decision in (
        "executed", "paused_for_review", "needs_clarification", "needs_capability")
    raise typer.Exit(ExitCode.OK if ok else ExitCode.ERROR)


@app.command(name="capabilities")
def capabilities_cmd(
    goal: str = typer.Option("", "--goal",
        help="Show the subsystem gap report for a goal."),
    route: str = typer.Option("", "--route",
        help="Show variant routing for this flow (pair with --kind)."),
    kind: str = typer.Option("shell", "--kind",
        help="Action kind to route when using --route."),
) -> None:
    """List Aria's subsystems; analyze gaps for a goal; route variants for a flow.

        sov capabilities
        sov capabilities --goal "schedule a daily backup reminder"
        sov capabilities --route "git, commit, branch" --kind shell
    """
    run, _projects, _pid, _requests = _build_agentic_run()
    reg = run.registry

    if goal:
        _render_plan(run.plan_only(goal))
        raise typer.Exit(ExitCode.OK)

    if route:
        from .workflow.capabilities import VariantRouter
        ranked = VariantRouter().rank(f"{kind}.default", route, reg)
        if STATE.json_out:
            _emit_json({"kind": kind, "flow": route,
                        "ranked": [{"name": r.capability.name, "score": r.score,
                                    "reason": r.reason} for r in ranked]})
            raise typer.Exit(ExitCode.OK)
        _print(f"\n[bold cyan]◊ variant routing[/bold cyan] for flow "
               f"[italic]{route!r}[/italic] (kind={kind})")
        if not ranked:
            _print("  [dim]no variants registered for this kind[/dim]")
        for i, r in enumerate(ranked, 1):
            mark = "★" if i == 1 else " "
            _print(f"  {mark} {r.capability.name}  [dim]score {r.score} — {r.reason}[/dim]")
        raise typer.Exit(ExitCode.OK)

    # default: list the registry
    caps = reg.all()
    if STATE.json_out:
        _emit_json({"capabilities": [
            {"name": c.name, "action_kind": c.action_kind, "status": c.status,
             "flow_tags": sorted(c.flow_tags), "variant_of": c.variant_of}
            for c in caps]})
        raise typer.Exit(ExitCode.OK)
    table = Table(title="◊ Aria's subsystems")
    table.add_column("name", style="cyan")
    table.add_column("kind")
    table.add_column("status")
    table.add_column("flows", overflow="fold", style="dim")
    for c in caps:
        style = "green" if c.status == "available" else "yellow"
        table.add_row(c.name, c.action_kind, f"[{style}]{c.status}[/{style}]",
                      ", ".join(sorted(c.flow_tags)))
    _print(table)
    missing = sorted(reg.missing_kinds())
    if missing:
        _print(f"[yellow]gaps: {', '.join(missing)}[/yellow] "
               f"[dim]— `sov agentic \"<goal needing it>\"` will draft a proposal[/dim]")


# ════════════════════════════════════════════════════════════════════════
# 📬 requests — the collaboration inbox (Aria ↔ human)  (v0.2.36.0)
#   A two-way work queue: Aria posts asks/suggestions/blockers, you answer,
#   items get logged. Pauses from `sov agentic` land here automatically.
# ════════════════════════════════════════════════════════════════════════


def _open_request_store():
    from .persistence.store import ErebloStore
    from .workflow.requests import RequestStore
    return RequestStore(ErebloStore(SETTINGS.paths.atoms_db))


requests_app = typer.Typer(
    help="📬 Collaboration inbox — Aria's asks and your answers.",
    invoke_without_command=True)


def _render_requests(items) -> None:
    if STATE.json_out:
        _emit_json([{"id": r.request_id, "short": r.request_id[-6:], "kind": r.kind,
                     "title": r.title, "status": r.status, "answer": r.answer,
                     "workflow_id": r.workflow_id, "created_at": r.created_at}
                    for r in items])
        return
    if not items:
        _print("📭 [dim]inbox is clear — nothing waiting on you[/dim]")
        return
    for r in items:
        _print(r.one_line())
        if r.body:
            for line in r.body.splitlines():
                _print(f"      [dim]{line}[/dim]")
        if r.answer:
            _print(f"      [green]↳ {r.answer}[/green]")


@requests_app.callback()
def requests_main(ctx: typer.Context) -> None:
    """With no subcommand, show what's open. 🟡"""
    if ctx.invoked_subcommand is not None:
        return
    rs = _open_request_store()
    _render_requests(rs.list_open())


@requests_app.command("list")
def requests_list_cmd(
    all_: bool = typer.Option(False, "--all", "-a", help="Include resolved/answered."),
    status: str = typer.Option("", "--status",
        help="Filter: open|answered|resolved|cancelled."),
) -> None:
    """List requests."""
    rs = _open_request_store()
    if status:
        _render_requests(rs.list(status=status))
    elif all_:
        _render_requests(rs.list())
    else:
        _render_requests(rs.list_open())


@requests_app.command("ask")
def requests_ask_cmd(
    title: str = typer.Argument(..., help="Short summary of the ask."),
    kind: str = typer.Option("question", "--kind", "-k",
        help="question|scan_files|suggestion|approval|decision|blocker|note|celebrate"),
    body: str = typer.Option("", "--body", "-b", help="Longer detail (optional)."),
) -> None:
    """File a request (Aria, a script, or you can use this)."""
    rs = _open_request_store()
    req = rs.open(kind, title, body=body)
    if STATE.json_out:
        _emit_json({"ok": True, "id": req.request_id, "short": req.request_id[-6:]})
        raise typer.Exit(ExitCode.OK)
    _print(f"{req.emoji} filed request [{req.request_id[-6:]}] — {req.title}")


@requests_app.command("show")
def requests_show_cmd(request_id: str = typer.Argument(..., help="Full or short id.")) -> None:
    """Show one request in full."""
    rs = _open_request_store()
    r = rs.get(request_id)
    if r is None:
        _die(ExitCode.USAGE, f"no request matching {request_id!r}")
    if STATE.json_out:
        _emit_json(r.__dict__); raise typer.Exit(ExitCode.OK)
    body = (f"{r.emoji} [bold]{r.title}[/bold]\n"
            f"[dim]id:[/dim] {r.request_id}\n"
            f"[dim]kind:[/dim] {r.kind}   [dim]status:[/dim] {r.status_emoji} {r.status}\n"
            f"[dim]created:[/dim] {r.created_at}\n")
    if r.workflow_id:
        body += f"[dim]workflow:[/dim] {r.workflow_id}\n"
    if r.body:
        body += f"\n{r.body}\n"
    if r.answer:
        body += f"\n[green]your answer:[/green] {r.answer}\n"
    _print(Panel(body, title=f"📨 request {r.request_id[-6:]}", border_style="cyan"))


@requests_app.command("answer")
def requests_answer_cmd(
    request_id: str = typer.Argument(..., help="Full or short id."),
    text: str = typer.Argument(..., help="Your answer / guidance / solution."),
) -> None:
    """Answer a request. 🟢"""
    rs = _open_request_store()
    r = rs.answer(request_id, text)
    if r is None:
        _die(ExitCode.USAGE, f"no request matching {request_id!r}")
    if STATE.json_out:
        _emit_json({"ok": True, "id": r.request_id, "status": r.status})
        raise typer.Exit(ExitCode.OK)
    _print(f"🟢 answered [{r.request_id[-6:]}] — thanks, that unblocks her ✨")


@requests_app.command("resolve")
def requests_resolve_cmd(request_id: str = typer.Argument(..., help="Full or short id.")) -> None:
    """Mark a request done and log it. ✅"""
    rs = _open_request_store()
    r = rs.resolve(request_id)
    if r is None:
        _die(ExitCode.USAGE, f"no request matching {request_id!r}")
    if STATE.json_out:
        _emit_json({"ok": True, "id": r.request_id, "status": r.status})
        raise typer.Exit(ExitCode.OK)
    _print(f"✅ resolved [{r.request_id[-6:]}] — onward 🚀")


@requests_app.command("cancel")
def requests_cancel_cmd(request_id: str = typer.Argument(..., help="Full or short id.")) -> None:
    """Cancel a request without acting on it. ⚪"""
    rs = _open_request_store()
    r = rs.cancel(request_id)
    if r is None:
        _die(ExitCode.USAGE, f"no request matching {request_id!r}")
    if STATE.json_out:
        _emit_json({"ok": True, "id": r.request_id, "status": r.status})
        raise typer.Exit(ExitCode.OK)
    _print(f"⚪ cancelled [{r.request_id[-6:]}]")


@requests_app.command("defer")
def requests_defer_cmd(request_id: str = typer.Argument(..., help="Full or short id.")) -> None:
    """Set a request aside for now — still on the board. ⏸️"""
    rs = _open_request_store()
    r = rs.defer(request_id)
    if r is None:
        _die(ExitCode.USAGE, f"no request matching {request_id!r}")
    if STATE.json_out:
        _emit_json({"ok": True, "id": r.request_id, "status": r.status})
        raise typer.Exit(ExitCode.OK)
    _print(f"⏸️  deferred [{r.request_id[-6:]}] — set aside for now")


@requests_app.command("flag")
def requests_flag_cmd(request_id: str = typer.Argument(..., help="Full or short id.")) -> None:
    """Flag a request as needing more attention. ⚠️"""
    rs = _open_request_store()
    r = rs.flag(request_id)
    if r is None:
        _die(ExitCode.USAGE, f"no request matching {request_id!r}")
    if STATE.json_out:
        _emit_json({"ok": True, "id": r.request_id, "status": r.status})
        raise typer.Exit(ExitCode.OK)
    _print(f"⚠️  flagged [{r.request_id[-6:]}] — needs more attention")


@requests_app.command("revisit")
def requests_revisit_cmd(request_id: str = typer.Argument(..., help="Full or short id.")) -> None:
    """Mark a request to come back to after more development. 🔖"""
    rs = _open_request_store()
    r = rs.revisit(request_id)
    if r is None:
        _die(ExitCode.USAGE, f"no request matching {request_id!r}")
    if STATE.json_out:
        _emit_json({"ok": True, "id": r.request_id, "status": r.status})
        raise typer.Exit(ExitCode.OK)
    _print(f"🔖 marked [{r.request_id[-6:]}] to revisit later")


app.add_typer(requests_app, name="requests")


# ════════════════════════════════════════════════════════════════════════
# 🔐 vault — owner-controlled encryption at rest  (v0.2.36.0)
#   Encrypts designated files so they're unreadable without YOUR passphrase.
#   The owner is you. The key is derived from your passphrase and never
#   stored. Rotate to change it. There is no backdoor — keep a backup of the
#   passphrase. This protects files at rest; it is not DRM and cannot make
#   software "obey" anyone. See security/vault.py for the full threat model.
# ════════════════════════════════════════════════════════════════════════


def _open_vault():
    from .security.vault import Vault
    return Vault(SETTINGS.paths.config_dir / "vault")


vault_app = typer.Typer(help="🔐 Owner-controlled encryption at rest.",
                        no_args_is_help=True)


@vault_app.command("init")
def vault_init_cmd() -> None:
    """Set the owner passphrase (one time). Refuses to overwrite — use rotate."""
    from .security.vault import VaultError
    v = _open_vault()
    if v.is_initialized:
        _die(ExitCode.USAGE, "owner already set", hint="use `sov vault rotate` to change it")
    pw = typer.prompt("Set owner passphrase", hide_input=True, confirmation_prompt=True)
    try:
        v.init_owner(pw)
    except VaultError as e:
        _die(ExitCode.USAGE, str(e))
    _print("🔐 [green]owner set.[/green] keep this passphrase safe — there is no backdoor.")
    _print("[dim]you are the owner. rotate any time with `sov vault rotate`.[/dim]")


@vault_app.command("status")
def vault_status_cmd() -> None:
    """Show vault status (never prints the key)."""
    v = _open_vault()
    st = v.status()
    if STATE.json_out:
        _emit_json(st); raise typer.Exit(ExitCode.OK)
    lock = "🔐 initialized" if st["initialized"] else "🔓 not initialized"
    crypto = "available" if st["crypto_available"] else "MISSING (pip install cryptography)"
    body = (f"{lock}\n[dim]crypto:[/dim] {crypto}\n"
            f"[dim]credential:[/dim] {st['credential_path']}\n")
    if st["initialized"]:
        body += f"[dim]created:[/dim] {st.get('created_at')}\n"
    _print(Panel(body, title="🔐 vault", border_style="green"))


@vault_app.command("verify")
def vault_verify_cmd() -> None:
    """Check a passphrase against the owner credential."""
    v = _open_vault()
    if not v.is_initialized:
        _die(ExitCode.USAGE, "vault not initialized", hint="run `sov vault init`")
    pw = typer.prompt("Owner passphrase", hide_input=True)
    ok = v.verify_owner(pw)
    if STATE.json_out:
        _emit_json({"verified": ok}); raise typer.Exit(ExitCode.OK if ok else ExitCode.ERROR)
    _print("✅ [green]verified — that's you.[/green]" if ok
           else "❌ [red]no match.[/red]")
    raise typer.Exit(ExitCode.OK if ok else ExitCode.ERROR)


@vault_app.command("encrypt")
def vault_encrypt_cmd(
    path: str = typer.Argument(..., help="File to encrypt."),
    remove: bool = typer.Option(False, "--remove",
        help="Delete the plaintext after encrypting."),
    out: str = typer.Option("", "--out", help="Output path (default: <file>.enc)."),
) -> None:
    """Encrypt a file under your passphrase. 🔒"""
    from pathlib import Path
    from .security.vault import VaultError, VaultLocked, VaultUnavailable
    v = _open_vault()
    pw = typer.prompt("Owner passphrase", hide_input=True)
    try:
        dest = v.encrypt_file(Path(path).expanduser(), pw,
                              dest=Path(out).expanduser() if out else None,
                              remove_plaintext=remove)
    except (VaultLocked, VaultUnavailable, VaultError) as e:
        _die(ExitCode.ERROR, str(e))
    if STATE.json_out:
        _emit_json({"ok": True, "encrypted": str(dest)}); raise typer.Exit(ExitCode.OK)
    _print(f"🔒 encrypted → {dest}" + ("  [dim](plaintext removed)[/dim]" if remove else ""))


@vault_app.command("decrypt")
def vault_decrypt_cmd(
    path: str = typer.Argument(..., help="Encrypted (.enc) file."),
    out: str = typer.Option("", "--out", help="Output path."),
) -> None:
    """Decrypt a file under your passphrase. 🔓"""
    from pathlib import Path
    from .security.vault import VaultError, VaultLocked, VaultUnavailable
    v = _open_vault()
    pw = typer.prompt("Owner passphrase", hide_input=True)
    try:
        dest = v.decrypt_file(Path(path).expanduser(), pw,
                              dest=Path(out).expanduser() if out else None)
    except (VaultLocked, VaultUnavailable, VaultError) as e:
        _die(ExitCode.ERROR, str(e))
    if STATE.json_out:
        _emit_json({"ok": True, "decrypted": str(dest)}); raise typer.Exit(ExitCode.OK)
    _print(f"🔓 decrypted → {dest}")


@vault_app.command("rotate")
def vault_rotate_cmd(
    files: list[str] = typer.Option([], "--file",
        help="Encrypted file to re-key (repeatable)."),
) -> None:
    """Change the owner passphrase; re-encrypt any --file under the new key."""
    from pathlib import Path
    from .security.vault import VaultError, VaultLocked
    v = _open_vault()
    if not v.is_initialized:
        _die(ExitCode.USAGE, "vault not initialized", hint="run `sov vault init`")
    old = typer.prompt("Current passphrase", hide_input=True)
    new = typer.prompt("New passphrase", hide_input=True, confirmation_prompt=True)
    try:
        rewritten = v.rotate(old, new,
                             files=tuple(Path(f).expanduser() for f in files))
    except (VaultLocked, VaultError) as e:
        _die(ExitCode.ERROR, str(e))
    if STATE.json_out:
        _emit_json({"ok": True, "rekeyed": [str(p) for p in rewritten]})
        raise typer.Exit(ExitCode.OK)
    _print("🔁 [green]passphrase rotated.[/green]")
    for p in rewritten:
        _print(f"   re-encrypted: {p}")


app.add_typer(vault_app, name="vault")


if __name__ == "__main__":
    app()
