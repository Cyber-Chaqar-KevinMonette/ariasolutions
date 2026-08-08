"""
╔══════════════════════════════════════════════════════════════════════════╗
║  cockpit/app.py — sovereign-agent operator cockpit                       ║
║  v0.2.15.3 · Aria-Sovereign-V1                                            ║
║                                                                            ║
║  A full-screen TUI for talking to the agent. Built on Textual.            ║
║                                                                            ║
║  Layout:                                                                   ║
║                                                                            ║
║    ┌─ sovereign-agent · cockpit ───── 0.2.15.3 · ◊ calm ─┐                ║
║    │┌─ chat ────────────────────┐┌─ live ──────────────┐│                ║
║    ││ history scrolls here       ││ events stream        ││                ║
║    ││                            ││ snapshot age         ││                ║
║    ││                            ││ continuations active ││                ║
║    │└────────────────────────────┘└──────────────────────┘│                ║
║    │┌─ input ──────────────────────────────────────────────┐│                ║
║    ││ > _                                                  ││                ║
║    │└──────────────────────────────────────────────────────┘│                ║
║    │ HALT · daemon · ledger · backup                       │                ║
║    └────────────────────────────────────────────────────────┘                ║
║                                                                            ║
║  Bindings:                                                                 ║
║    Enter      submit input                                                 ║
║    Ctrl-Q    quit cockpit (agent keeps running)                            ║
║    Ctrl-H    halt the agent (PROTOCOL-ZERO)                                ║
║    Ctrl-D    disarm PROTOCOL-ZERO                                          ║
║    Ctrl-L    clear chat pane                                               ║
║    F1        help overlay                                                  ║
║                                                                            ║
║  Execution model:                                                          ║
║    User input → spawn ``sovereign do "..."`` in a subprocess.             ║
║    Stream its stdout to the chat pane.                                    ║
║    In parallel, tail events.jsonl and forward new events to live pane.    ║
║    Status bar refreshes every 5 seconds (ledger audit, snapshot age).     ║
║                                                                            ║
║  What this doesn't do (deferred to later releases):                       ║
║    - Inline Tier 3 approval modal (use 'sov approvals' in another shell)  ║
║    - Multi-conversation tabs                                              ║
║    - Search over chat history (chat is in atoms.db; search via channels)  ║
║    - Dream-tail integration (use 'sov dream tail' in another shell)       ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shlex
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import (
    Button, Footer, Header, Input, Label, Rule, RichLog, Static,
)

from .. import __version__
from .sysmon import (
    SystemMonitor, SystemSnapshot,
    render_compact_metrics, render_health_report,
)

logger = logging.getLogger(__name__)


# ─── Helpers ────────────────────────────────────────────────────────────────


def _now_short() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _arg_to_int(arg: str, default: int) -> int:
    """Parse a slash-command argument as an int; fall back on bad input.

    Used by /copy <N>, /copy-you <N>, etc. so the operator can ask for
    multiple recent lines without us crashing on a typo. Empty arg
    returns the default; non-numeric arg also returns the default.
    """
    arg = (arg or "").strip()
    if not arg:
        return default
    try:
        n = int(arg)
        return max(1, n)
    except ValueError:
        return default


# ─── Natural-language input normalizer (v0.2.30.1) ──────────────────────────
#
# Inside the cockpit, the operator should never have to type `sov ask "..."`
# or `sov do "..."` — those exist for the BASH prompt, where the cockpit
# isn't running. Yet muscle memory and copy-paste from documentation mean
# people do type them anyway. Pre-v0.2.30.1, those typings were sent verbatim
# to the LLM as one long sentence, which felt broken.
#
# This normalizer fixes that at the input boundary:
#
#   • `sov ask "<text>"`     → returns ("natural", "<text>")
#   • `sov ask <words...>`   → returns ("natural", "<words...>")
#   • `sov do  "<text>"`     → returns ("natural", "<text>")
#   • `sov do  <words...>`   → returns ("natural", "<words...>")
#   • `sov <known-subcmd>`   → returns ("execute", ["sovereign", <subcmd>, ...])
#   • `sov --version` etc.   → returns ("execute", ["sovereign", "--version"])
#   • Anything else          → returns None (let the caller route as natural)
#
# The "anything else" case is the load-bearing one. A sentence like
# "sovereign citizens are a topic in political science" starts with the
# literal word `sovereign` but is plainly English. Without the allowlist
# below, the naive parser would grab it as a CLI command and shell out to
# `sovereign citizens ...` which would error out. With the allowlist, we
# return None and the LLM interpreter — the safety net — handles it.
#
# The doctrine: when in doubt, treat input as English. The cockpit is a
# natural-language home. CLI execution is the exception, not the default.
#
# Always returns None on parse failure so the caller falls back to the
# default natural-language path. We never block the operator on a parsing
# disagreement — the LLM interpreter is the safety net.
#
# `sovereign` (the long-form binary name) is accepted alongside `sov` since
# both are real entry points as of v0.2.30.0.


@dataclass(frozen=True)
class NormalizedInput:
    """The result of normalizing a cockpit input line.

    `kind="natural"` — strip the `sov ask/do` wrapper and route the
                       remaining text through the normal NL pipeline.
    `kind="execute"` — run the argv as a real subprocess command.
                       Read-only / reversible subcommands only.
    `kind="guarded"` — looks like a CLI command but the subcommand is
                       tagged DESTRUCTIVE/PRIVILEGED. The cockpit refuses
                       to subprocess directly; we reshape it as a
                       natural-language Conversation so the constitution's
                       Tier-3 confirm gate handles it. (v0.2.31.0+)
    """
    kind: str  # "natural" | "execute" | "guarded"
    text: str = ""            # populated for "natural" and "guarded"
    argv: tuple[str, ...] = ()  # populated for "execute"
    reason: str = ""          # human-readable, populated for "guarded"


# Sub-commands of `sov` that are themselves natural-language wrappers.
# Typing these inside the cockpit is redundant — we strip the prefix and
# let the conversation pipeline see the user's real message.
_NL_WRAPPERS: frozenset[str] = frozenset({"ask", "do"})

# The binary names we recognize at the start of an input line. Both are
# real console_scripts as of v0.2.30.0.
_SOV_BINARIES: frozenset[str] = frozenset({"sov", "sovereign"})


# ─── Safety profiles (v0.2.31.0) ────────────────────────────────────────────
#
# The cockpit's `execute` path was added in v0.2.30.1 to let muscle-memory CLI
# input like `sov heartbeat pulse "..."` run as a real subprocess. That works
# beautifully for read-only and reversible commands. It is NOT safe for
# destructive commands.
#
# Without safety profiles, `sov backup restore <id>` typed into the cockpit
# would skip the conversation layer's Tier-3 confirm gate and execute
# immediately. That's the cliff the design review caught.
#
# v0.2.31.0 closes the cliff: any subcommand tagged DESTRUCTIVE or
# PRIVILEGED gets reshaped into a natural-language Conversation. The LLM
# interpreter — which respects the constitution's Tier-3 confirmation —
# then handles it. Operators who genuinely want to run a destructive
# command can still do it from a bash prompt; the cockpit just declines
# to make that easy.
#
# When in doubt, list a subcommand as DESTRUCTIVE. Read-only is the only
# category that should be hands-off.

# Destructive or privileged subcommands the cockpit refuses to subprocess.
# These get routed through the conversation pipeline instead, where the
# Tier-3 confirm gate (single-word `ok`) lives.
_DESTRUCTIVE_SOV_SUBCOMMANDS: frozenset[str] = frozenset({
    # PROTOCOL-ZERO controls — should never be one-keystroke
    "halt",
    "disarm",
    # Backup mutations — anything that can replace atoms.db
    "backup",   # `backup snapshot/restore` are gated;
                # `backup list/verify` are explicitly safe via overrides below
    # Schema migrations — touches atoms.db structure
    "migrations",  # `migrations apply` gated; `migrations status` safe via override
    # The hot loops — running these directly bypasses the queue
    "run",
    "busy",
    "until",
    "drain-by-model",
    "dream",
    "continue",
    # Anything that mutates state across sessions
    "approve",
    "deny",
    # Steward operations that mutate or compact
    "steward",
    # Shard migrations
    "shards",
    # Seal & verify can be heavy and write artifacts
    "seal",
    # Owner vault — init/encrypt/decrypt/rotate touch keys & ciphertext.
    # Only `vault status` / `vault verify` (read-only) are safe via overrides.
    "vault",
})


# Safe-overrides for read-only sub-sub-commands within otherwise-destructive
# subcommand trees. Each entry is a (subcmd, sub-sub-cmd) tuple that gets
# treated as execute even if its parent subcmd is in _DESTRUCTIVE_SOV_SUBCOMMANDS.
#
# This is the design-doc proposal "safety per subcommand, not per command-tree"
# applied surgically. The default is still pessimistic — only explicitly-listed
# read paths within destructive trees become safe. Everything else stays guarded.
_SAFE_SUBCMD_OVERRIDES: frozenset[tuple[str, str]] = frozenset({
    # Backup: reading and verifying snapshots is safe; only restore/snapshot mutate
    ("backup", "list"),
    ("backup", "verify"),
    ("backup", "show"),
    # Vault: status & verify are read-only; init/encrypt/decrypt/rotate are guarded
    ("vault", "status"),
    ("vault", "verify"),
    # Migrations: status and the dry-run mode are read-only
    ("migrations", "status"),
    # Steward: integrity check is read-only (PRAGMA integrity_check)
    ("steward", "integrity"),
    ("steward", "audit"),
    # Dream and continuations: listing/showing is safe; start/advance/stop mutate
    ("dream", "list"),
    ("dream", "show"),
    ("continue", "list"),
    # Approve/deny themselves are mutations, but listing pending approvals isn't
    # (approve/deny take no sub-sub-cmd; listing is via a different command)
})


# Curated allowlist of known sov subcommands. Extracted from the CLI
# structure (top-level @app.command and @app.add_typer registrations as
# of v0.2.31.0). If a new subcommand ships and isn't in this set, the
# cockpit will fall back to the LLM interpreter for that input — which
# is the safe default. Operators can always fall back to a bash prompt.
#
# Keeping this list curated (rather than introspecting the CLI at runtime)
# avoids a circular import and means stale entries surface as test
# failures rather than silent behavior changes.
_KNOWN_SOV_SUBCOMMANDS: frozenset[str] = frozenset({
    # Sub-apps (have their own command trees)
    "appendix", "archive", "atoms", "backlog", "backup", "behavior",
    "channels", "chat", "commitments", "constitution", "continuations",
    "drafts", "dream", "edge-cases", "episode", "field-notes", "financial",
    "gaps", "health", "heartbeat", "home", "honor", "impact", "insights",
    "interpret", "lens", "memory", "migrations", "palace", "people",
    "personas", "profile", "projects", "proposals", "qa", "reasoning",
    "recall", "relationships", "reward", "shards", "steward",
    "stewardship", "task", "telemetry",
    # v0.2.32.0+ — charter, glyphs (sentinel)
    "charter", "glyphs",
    # v0.2.33.0+ — theme workshop, cadence portraits
    "theme", "cadence",
    # v0.2.36.0+ — collaboration inbox, capability awareness, owner vault
    "requests", "capabilities", "vault",
    # Top-level commands with explicit names
    "ask", "config", "continue", "do", "drain-by-model", "info",
    "pause", "plan", "resume", "retrieve",
    # Top-level commands using the function-name default
    "approvals", "approve", "aria", "busy", "cockpit", "deny", "disarm",
    "doctor", "events", "halt", "horizon", "init", "lessons", "run",
    "seal", "status", "tail", "until", "verify",
})


def normalize_sov_prefix(text: str) -> Optional[NormalizedInput]:
    """Detect and reshape `sov ...` lines typed inside the cockpit.

    The cockpit is a natural-language home. When the operator types
    `sov ask "hello"`, they almost certainly mean "say hello to Aria",
    not "I want this exact CLI string interpreted as one paragraph of
    natural language." This function detects the muscle-memory pattern
    and reshapes it.

    Three outcomes, in order of preference:

    1. NL-wrapper unwrap — `sov ask <args>` / `sov do <args>` returns
       a `NormalizedInput(kind="natural", text=<args>)`. The cockpit
       feeds <args> to the normal conversation pipeline.

    2. Direct CLI execute — `sov <known-subcmd> <args>` or
       `sov <--flag>` returns a `NormalizedInput(kind="execute",
       argv=["sovereign", ...])`. The cockpit shells out.

    3. None — input didn't start with `sov`/`sovereign`, the
       second token isn't a known subcommand, OR shlex couldn't parse
       it cleanly. The caller falls back to the conversation pipeline,
       which is always safe.

    The third case is load-bearing. "sovereign citizens are a topic" is
    English even though it starts with the word `sovereign`. The
    curated allowlist of known subcommands is what tells the parser
    "this looks like English, not a command."

    Returns:
        NormalizedInput or None.
    """
    text = (text or "").strip()
    if not text:
        return None

    # Quick check: must start with `sov` or `sovereign` as the first token.
    # We split on the first whitespace so `sovereign-class` (no space) is
    # naturally excluded.
    first_word, _, _ = text.partition(" ")
    if first_word.lower() not in _SOV_BINARIES:
        return None

    # Parse with shlex so quoted strings stay intact. On parse failure,
    # we return None — the LLM interpreter is the safer fallback than a
    # half-parsed argv.
    try:
        tokens = shlex.split(text)
    except ValueError:
        return None
    if not tokens:
        return None

    # tokens[0] is the binary; tokens[1] (if present) is the subcommand
    if len(tokens) == 1:
        # Bare `sov` — treat as execute (will show help)
        return NormalizedInput(kind="execute", argv=("sovereign",))

    subcmd = tokens[1].lower()

    # Pattern 1 — NL wrapper unwrap (ask/do)
    if subcmd in _NL_WRAPPERS:
        # `sov ask` / `sov do` with no further args → not a meaningful
        # message; let the LLM see it (probably the operator was about
        # to type more and pressed Enter early).
        if len(tokens) == 2:
            return None
        # The remaining tokens are the message. Rejoin them with single
        # spaces — shlex already stripped quote characters, so this is
        # the user's plain prose.
        nl_text = " ".join(tokens[2:]).strip()
        if not nl_text:
            return None
        return NormalizedInput(kind="natural", text=nl_text)

    # Pattern 2 — direct CLI execution, ONLY for recognized patterns.
    # The conservatism here is intentional: when the second token isn't
    # a known subcommand AND doesn't look like a flag, we return None so
    # the LLM interpreter handles the input. Sentences that just happen
    # to start with "sovereign ..." or "sov ..." stay English.
    is_known_subcmd = subcmd in _KNOWN_SOV_SUBCOMMANDS
    is_flag = tokens[1].startswith("-")  # check original case, not lowered
    if not (is_known_subcmd or is_flag):
        return None

    # v0.2.31.0 — safety profile gate.
    # If the subcommand is tagged DESTRUCTIVE or PRIVILEGED, we refuse
    # to subprocess it directly. Instead we reshape as a natural-language
    # Conversation so the constitution's Tier-3 confirm gate kicks in.
    # The operator can still run dangerous commands — they just have to
    # do it from a bash prompt, OR confirm via Aria's conversation
    # pipeline. The cockpit declines to make one-keystroke destruction
    # easy.
    #
    # Safe-overrides: read-only sub-sub-commands (like `backup list`,
    # `migrations status`) within otherwise-destructive trees are
    # whitelisted by exact match in _SAFE_SUBCMD_OVERRIDES.
    if is_known_subcmd and subcmd in _DESTRUCTIVE_SOV_SUBCOMMANDS:
        # Check for a safe sub-sub-command override
        sub_sub = tokens[2].lower() if len(tokens) > 2 else ""
        if (subcmd, sub_sub) not in _SAFE_SUBCMD_OVERRIDES:
            # Not whitelisted — guard it
            return NormalizedInput(
                kind="guarded",
                text=text,
                reason=f"`sov {subcmd}` is destructive/privileged — "
                       f"the cockpit routes these through aria's confirm gate "
                       f"instead of subprocessing directly. type `ok` to confirm.",
            )
        # Falls through to execute — the sub-sub-command is explicitly safe

    # Pattern 2 confirmed. We always invoke via `sovereign` (the canonical
    # binary) regardless of whether the operator typed `sov` or `sovereign`.
    # This makes the audit trail readable.
    argv = ("sovereign",) + tuple(tokens[1:])
    return NormalizedInput(kind="execute", argv=argv)


def _format_age(seconds: Optional[float]) -> str:
    if seconds is None:
        return "—"
    if seconds < 60:
        return f"{seconds:.0f}s"
    if seconds < 3600:
        return f"{seconds/60:.0f}m"
    if seconds < 86400:
        return f"{seconds/3600:.1f}h"
    return f"{seconds/86400:.1f}d"


@dataclass
class CockpitStatus:
    """Single snapshot of system state for the status bar."""
    halt: bool = False
    daemon_active: bool = False
    ledger_clean: bool = True
    ledger_rows: int = 0
    snapshot_age_seconds: Optional[float] = None
    snapshot_verify_ok: bool = True
    version: str = field(default_factory=lambda: __version__)
    mood: str = "calm"
    # System metrics (set by SystemMonitor.read())
    system: Optional["SystemSnapshot"] = None
    # VRAM (set by sovereign_agent.vram.read_vram())
    vram_total_mb: Optional[int] = None
    vram_used_mb: Optional[int] = None
    vram_source: str = ""
    vram_temp_c: Optional[float] = None


# ─── Help overlay ───────────────────────────────────────────────────────────


class HelpScreen(ModalScreen):
    """F1 → modal with keybindings and routing reference."""

    BINDINGS = [Binding("escape,f1,q", "app.pop_screen", "close")]

    def compose(self) -> ComposeResult:
        yield Vertical(
            Static(
                "[b]sovereign-agent cockpit · help[/b]\n\n"
                "[b]The cockpit is a natural-language home[/b]\n"
                "  Just [b]talk to aria[/b] in plain english. You never need to\n"
                "  type [dim]`sov ask`[/dim] or [dim]`sov do`[/dim] in here — those exist for the\n"
                "  bash prompt, where the cockpit isn't running.\n\n"
                "  v0.2.30.1+: muscle memory is forgiven. If you do type\n"
                "  [dim]`sov ask \"hello\"`[/dim], the cockpit quietly unwraps it to just\n"
                "  [dim]`hello`[/dim]. If you type [dim]`sov heartbeat pulse \"first pulse\"`[/dim],\n"
                "  it runs the real command. The prefix is now transparent,\n"
                "  not load-bearing. Speak however feels natural.\n\n"
                "  If aria asks a clarifying question (e.g. 'what name for\n"
                "  this project?'), just type your answer and press Enter.\n"
                "  The input is routed to the running task. Type `/cancel`\n"
                "  to abort the running task at any time.\n\n"
                "  Examples (all do the same thing — pick whichever feels right):\n"
                "    [dim]> say hello[/dim]\n"
                "    [dim]> hello[/dim]\n"
                "    [dim]> sov ask \"hello\"[/dim]              ← unwrapped to `hello`\n\n"
                "  Examples that execute as real commands:\n"
                "    [dim]> sov heartbeat pulse \"first pulse\"[/dim]   ← runs directly\n"
                "    [dim]> sov doctor[/dim]                             ← runs directly\n"
                "    [dim]> sov channels list[/dim]                      ← runs directly\n\n"
                "  Examples of plain-english directives:\n"
                "    [dim]> inventory ~/AA-Erebo for markdown files[/dim]\n"
                "    [dim]> build trillion-dollar software, max 2000 files[/dim]\n"
                "    [dim]> show me what's happening[/dim]\n"
                "    [dim]> pause my dream[/dim]\n\n"
                "[b]Command palette (v0.2.31.0+)[/b]\n"
                "  The row of buttons above the input is the [b]palette[/b].\n"
                "  Click any button to paste its command into the input box\n"
                "  (it does NOT auto-submit — you review and press Enter).\n"
                "  Buttons flash [green]green[/green] on click. While a matching\n"
                "  command is running, the button glows [cyan]cyan[/cyan] so you\n"
                "  see at a glance what's active.\n"
                "  [b]Hover[/b] a button to read what it does. Type [dim]/palette[/dim]\n"
                "  for a full legend of every button + its command.\n\n"
                "[b]Slash commands (operator overrides)[/b]\n"
                "  /cancel         abort the running directive\n"
                "  /halt           PROTOCOL-ZERO\n"
                "  /disarm         clear PROTOCOL-ZERO\n"
                "  /snap [label]   take a snapshot\n"
                "  /audit          run financial audit\n"
                "  /events [N]     dump latest N events to chat\n"
                "  /palette        what every palette button does\n"
                "  /lessons        recent lesson atoms\n"
                "  /health         quick system health summary\n"
                "  /report         full health report, saved to disk\n"
                "  /drafts [N]     list archived drafts (newest first)\n"
                "  /draft <t> <p>  archive a project under <data>/drafts\n"
                "  /marketing <p>  generate a marketing brief for <product>\n"
                "  /heart          toggle the heartbeat badge\n"
                "  /clear          clear chat\n"
                "  /help           this help\n"
                "  /quit           quit\n\n"
                "[b]Keys[/b]\n"
                "  Enter           submit input\n"
                "  Ctrl-Q          quit cockpit (agent keeps running)\n"
                "  Ctrl-H          [red]halt[/red] (PROTOCOL-ZERO)\n"
                "  Ctrl-D          [green]disarm[/green] PROTOCOL-ZERO\n"
                "  Ctrl-L          clear chat pane\n"
                "  Ctrl-B          toggle the [red]♥[/red] heartbeat\n"
                "  Ctrl-V          paste from system clipboard\n"
                "  F1, ?           this help\n"
                "  Esc             close overlay\n\n"
                "[dim]Esc to close[/dim]",
                id="help-content",
            ),
            id="help-modal",
        )

    DEFAULT_CSS = """
    HelpScreen {
        align: center middle;
        background: $surface 60%;
    }
    #help-modal {
        width: 72;
        height: auto;
        max-height: 90%;
        padding: 1 2;
        border: thick $primary;
        background: $surface;
    }
    """


# ─── Command palette (v0.2.31.0) ────────────────────────────────────────────
#
# A row of clickable buttons that paste common `sov` commands into the input
# box (without sending). The operator can review/edit before pressing Enter.
# Designed for speed without sacrificing review — Kevin's exact ask.
#
# Visual states:
#   • idle      — default, accent border
#   • flash     — brief green pulse after a click (operator feedback)
#   • running   — cyan glow while Aria is executing this command (so the
#                 operator can see at a glance what's currently active)
#
# Only read-only / reversible commands appear on the palette. Destructive
# operations (halt, backup restore, migrations) deliberately don't get a
# button — those should go through Aria's conversation pipeline where the
# Tier-3 confirm gate lives.


@dataclass(frozen=True)
class PaletteCommand:
    """One button on the command palette.

    `label`   — short text shown on the button (≤ 12 chars fits the row)
    `command` — the exact text pasted into the input box
    `key`     — internal identifier used to match running commands to
                buttons (typically the first sov subcommand word)
    `desc`    — one-line human description of what the command does, shown
                as a hover tooltip and in the `/palette` legend + F1 help
    """
    label: str
    command: str
    key: str
    desc: str = ""


# The default palette. Curated for the most common, most-useful read-only
# inspection commands an operator runs many times a day. Listed left-to-right
# in roughly "look around → look deeper" order.
PALETTE_COMMANDS: tuple[PaletteCommand, ...] = (
    # Row 1 — daily-driver inspection
    PaletteCommand("doctor",   "sov doctor",                       "doctor",
                   "Run a full environment + install diagnostic (is the kernel whole?)"),
    PaletteCommand("info",     "sov info",                         "info",
                   "Concise summary of where Aria lives — versions, paths, config"),
    PaletteCommand("aria",     "sov aria",                         "aria",
                   "Aria's current state — kernel, mood, inventory"),
    PaletteCommand("status",   "sov status",                       "status",
                   "One-glance summary of dreams, continuations, projects, palace"),
    PaletteCommand("channels", "sov channels list",                "channels",
                   "List all registered memory channels"),
    PaletteCommand("pulses",   "sov heartbeat list",               "heartbeat",
                   "List heartbeat pulses — Aria's liveness signals"),
    # Row 2
    PaletteCommand("backups",  "sov backup list",                  "backup",
                   "List all snapshots, newest first (your restore points)"),
    PaletteCommand("seven",    "sov constitution list",            "constitution",
                   "List the constitution — Aria's governing articles"),
    PaletteCommand("charter",  "sov charter status",               "charter",
                   "Charter integrity verdict — the same one the kill switch reads"),
    PaletteCommand("glyphs",   "sov glyphs status",                "glyphs",
                   "Summarize the most recent glyph catalog"),
    PaletteCommand("themes",   "sov theme list",                   "themes",
                   "List every cockpit theme — curated and user, grouped"),
    PaletteCommand("portrait", "sov cadence profile operator",     "portrait",
                   "Your full cadence portrait — your working rhythm"),
    # Row 3 — newer surfaces (collaboration, capabilities, security). Read-only.
    PaletteCommand("suggest",  "sov cadence suggest operator",     "suggest",
                   "What to focus on next: stretch edges + concepts to revisit"),
    PaletteCommand("chapters", "sov cadence chapter list operator","chapters",
                   "Your cadence chapters — open phases first, then closed history"),
    PaletteCommand("inbox",    "sov requests",                     "requests",
                   "The collaboration inbox — open asks waiting on you, with context"),
    PaletteCommand("parked",   "sov requests parked",              "parked",
                   "Parked work to revisit — deferred ⏸️, revisit 🔖, flagged ⚠️"),
    PaletteCommand("caps",     "sov capabilities",                 "capabilities",
                   "Aria's subsystems — what she has and what's missing"),
    PaletteCommand("vault",    "sov vault status",                 "vault",
                   "Owner encryption vault status (never shows the key)"),
)


class CommandButton(Button):
    """A palette button. Tracks its associated PaletteCommand for routing."""

    def __init__(self, palette_cmd: PaletteCommand) -> None:
        # The button label is the short word; the full command text is
        # carried alongside so the click handler can paste it.
        super().__init__(palette_cmd.label, id=f"palette-{palette_cmd.key}")
        self.palette_cmd = palette_cmd
        # Hover to read what it does before clicking (no more blind clicks).
        if palette_cmd.desc:
            self.tooltip = f"{palette_cmd.command}\n{palette_cmd.desc}"
        else:
            self.tooltip = palette_cmd.command


# ─── The cockpit ────────────────────────────────────────────────────────────


class CockpitApp(App):
    """Full-screen operator cockpit for sovereign-agent."""

    TITLE = "sovereign-agent · cockpit"
    SUB_TITLE = __version__  # patched at mount-time to include theme name

    def _refresh_sub_title(self) -> None:
        """Compose the SUB_TITLE as 'version · theme-name'. Called on mount
        and whenever the theme changes, so the cockpit header always shows
        which theme is currently active."""
        try:
            theme_name = getattr(self, "theme", None) or "default"
            self.sub_title = f"{__version__} · {theme_name}"
        except Exception:
            self.sub_title = __version__

    def watch_theme(self, _old: str, _new: str) -> None:
        """Textual reactive hook: theme attribute changed. Refresh the header
        and manage the hue cycle engine (start if new theme has hue_cycle
        effects, stop if it doesn't)."""
        self._refresh_sub_title()
        # Stop any currently-running cycle engine; we may start a new one
        # if the new theme also has hue_cycle effects.
        try:
            current = getattr(self, "_hue_cycle_engine", None)
            if current is not None:
                current.stop()
                self._hue_cycle_engine = None
        except Exception:
            pass
        try:
            from .hue_cycle import maybe_start_for_active_theme
            self._hue_cycle_engine = maybe_start_for_active_theme(self, _new)
        except Exception:
            self._hue_cycle_engine = None

    # MOS-SURFACE §19 — KEY BINDINGS.
    #
    # Every binding is `priority=True`. This matters because the
    # Textual `Input` widget (the focused widget on launch) ships with
    # its own internal BINDINGS that shadow several Ctrl+* keys:
    #
    #   Input: ctrl+v   → paste            (show=False, hidden)
    #   Input: ctrl+d   → delete_right     (show=False, hidden)
    #   Input: ctrl+a   → home
    #   Input: ctrl+e   → end
    #   Input: ctrl+w   → delete_left_word
    #   Input: ctrl+u   → delete_left_all
    #   Input: ctrl+k   → delete_right_all
    #   Input: ctrl+x   → cut
    #
    # Without `priority=True`, an app-level `ctrl+v` binding is
    # consumed by the focused Input before it ever reaches the app's
    # action. That is why v0.2.18.4's `Ctrl+V` did nothing AND why
    # `^v paste` was missing from the footer: the shadowing binding
    # had `show=False`, so the footer hid the key entirely.
    #
    # `priority=True` causes the app-level binding to fire FIRST,
    # regardless of focus, and unshadows the footer entry. Operators
    # who want the Input's native delete-right still have the plain
    # `Delete` key. The operator's explicit bindings are the contract;
    # the widget's defaults defer.
    BINDINGS = [
        Binding("ctrl+q", "quit",            "quit",    show=True,  priority=True),
        Binding("ctrl+h", "halt",            "halt",    show=True,  priority=True),
        Binding("ctrl+d", "disarm",          "disarm",  show=True,  priority=True),
        Binding("ctrl+l", "clear_chat",      "clear",   show=True,  priority=True),
        Binding("ctrl+b", "toggle_heart",    "♥",       show=True,  priority=True),
        Binding("ctrl+v", "paste_clipboard", "paste",   show=True,  priority=True),
        Binding("f1,question_mark", "help",  "help",    show=True,  priority=True),
    ]

    CSS = """
    Screen {
        background: $surface;
        scrollbar-size: 0 0;
    }

    /* ════════════════════════════════════════════════════════════════
     * MOS-SURFACE v1.1 — explicit backgrounds prevent transparency leak.
     *
     * Reading from the article literature (cited in MOS-SURFACE §6.1):
     *
     *   "Setting a border color to 'none' or matching it to a background
     *    that has transparency/blur (common in modern terminals like
     *    Kitty) can cause it to render as a black strip. Leverage solid,
     *    theme-aware background colors rather than relying on
     *    transparency for UI elements."
     *
     * The chain is now: Screen ($surface) → #main ($surface) →
     * panes ($surface). Every cell has a known solid background. The
     * status row's $primary 15% tint blends against $surface, not
     * against terminal-default which varies (often black).
     * ════════════════════════════════════════════════════════════════ */
    #main {
        height: 1fr;
        border: round $primary;
        padding: 0;
        background: $surface;
    }

    /* Breathing border — applied when the agent is mid-directive.
       Three phases cycled by the breathing worker. */
    #main.breathing-1 { border: round $primary; }
    #main.breathing-2 { border: round $accent; }
    #main.breathing-3 { border: round $secondary; }

    /* News and halt states — outer-border-as-mood-signal (§30) */
    #main.news { border: round $accent; }
    #main.halt { border: round $error; }

    /* Inner panes: NO borders. Explicit backgrounds (no transparency). */
    #chat-pane {
        width: 2fr;
        padding: 0 1;
        background: $surface;
    }
    /* v0.2.25.0 — Memory pane between chat and live. Width 1fr keeps
       it narrower than chat (where conversation happens) but matched
       to live (which is also reference-grade context). */
    #memory-pane {
        width: 1fr;
        padding: 0 1;
        background: $surface;
    }
    #live-pane {
        width: 1fr;
        padding: 0 1;
        background: $surface;
    }
    /* v0.2.37.0 — Inbox pane (4th window). Matched 1fr like memory/live;
       chat stays widest at 2fr (where conversation happens). */
    #inbox-pane {
        width: 1fr;
        padding: 0 1;
        background: $surface;
    }

    /* Two dividers — between chat & memory, and between memory & live.
       Each declared separately so doctrine tests (which match per-
       selector CSS rules) can verify each one's background discipline.
       Both share the same visual treatment. */
    #divider-1 {
        width: 1;
        height: 1fr;
        margin: 0;
        color: $primary;
        background: $surface;
    }
    #divider-2 {
        width: 1;
        height: 1fr;
        margin: 0;
        color: $primary;
        background: $surface;
    }
    #divider-1.breathing-2, #divider-2.breathing-2 { color: $accent; }
    #divider-1.breathing-3, #divider-2.breathing-3 { color: $secondary; }
    #divider-1.news, #divider-2.news  { color: $accent; }
    #divider-1.halt, #divider-2.halt  { color: $error; }

    /* v0.2.37.0 — third divider, between live and inbox. Same discipline. */
    #divider-3 {
        width: 1;
        height: 1fr;
        margin: 0;
        color: $primary;
        background: $surface;
    }
    #divider-3.breathing-2 { color: $accent; }
    #divider-3.breathing-3 { color: $secondary; }
    #divider-3.news { color: $accent; }
    #divider-3.halt { color: $error; }

    /* Pane titles: accent-coloured, small, with a one-row breathing gap.
       Explicit background prevents the title row from rendering its
       cells with terminal-default behind the text. */
    .pane-title {
        color: $accent;
        text-style: bold;
        height: 1;
        margin-bottom: 1;
        background: $surface;
    }

    /* The two scrolling logs */
    #chat-log {
        height: 1fr;
        background: $surface;
        border: none;
    }
    #events-log {
        height: 1fr;
        background: $surface;
        border: none;
    }
    #inbox-log {
        height: 1fr;
        background: $surface;
        border: none;
    }

    /* MOS-SURFACE §16.1 — SCROLLBAR DISCIPLINE.
     *
     * The actual root cause of the "vertical line near the right edge"
     * bug observed across v0.2.18.0 through v0.2.18.3 was NOT the divider,
     * the outer border, or transparency. It was the RichLog widget's
     * scrollbar gutter rendering a 1-cell-wide column on the right side
     * of every RichLog instance. With `scrollbar-size-vertical: 1`,
     * Textual reserves that column permanently — and at the junction
     * with the rounded outer border, the gutter's slightly-different
     * background renders as a visible vertical line.
     *
     * The fix: hide scrollbars completely (size 0 0). The operator scrolls
     * with mouse wheel or PageUp/PageDown — a visible gutter offers no
     * value in a chat-log context and IS the chrome artifact.
     */
    RichLog {
        scrollbar-size: 0 0;
        scrollbar-background: $surface;
        scrollbar-color: $surface;
        scrollbar-corner-color: $surface;
    }

    /* Input box. Border accent shifts to bright on focus (§22).
       Explicit background to prevent the cell between the input and
       its rounded border from picking up terminal-default. */
    #input-box {
        height: 3;
        margin: 1 0 0 0;
        padding: 0 1;
        border: round $accent;
        background: $surface;
    }
    #input-box:focus {
        border: round $accent;
        background: $surface;
    }

    /* v0.2.31.0 — Command palette.
       A horizontal row of clickable buttons that paste common commands
       into the input box. The row sits between the panes and the input.
       Three visual states per button:
         • idle    — default accent border, surface background
         • flash   — green pulse on click (operator feedback)
         • running — cyan glow while a matching command is executing
                     (so the operator sees what's active at a glance) */
    #palette-row, #palette-row-2, #palette-row-3 {
        height: 3;
        width: 100%;
        margin: 1 0 0 0;
        padding: 0;
        background: $surface;
        layout: horizontal;
    }
    #palette-row-2 {
        margin: 0 0 0 0;
    }
    #palette-row-3 {
        margin: 0 0 0 0;
    }
    #palette-row CommandButton, #palette-row-2 CommandButton, #palette-row-3 CommandButton {
        height: 3;
        min-width: 10;
        margin: 0 1 0 0;
        padding: 0 1;
        border: round $primary;
        background: $surface;
        color: $text;
    }
    /* CSS class applied briefly on click — operator feedback */
    #palette-row CommandButton.flash, #palette-row-2 CommandButton.flash, #palette-row-3 CommandButton.flash {
        border: round $success;
        background: $success 20%;
        color: $success;
    }
    /* CSS class applied while a matching subprocess is running */
    #palette-row CommandButton.running, #palette-row-2 CommandButton.running, #palette-row-3 CommandButton.running {
        border: round $accent;
        background: $accent 15%;
        color: $accent;
    }

    /* MOS-SURFACE §23 — status bar grammar.
       The $primary 15% tint is now a translucent layer that blends
       against the $surface beneath (because everything in the chain
       has explicit $surface backgrounds). No more black-strip leak. */
    #status-row {
        height: 1;
        width: 100%;
        background: $primary 15%;
        layout: horizontal;
    }
    #heart {
        width: 3;
        height: 1;
        content-align: center middle;
        padding: 0;
        background: $primary 15%;
    }
    #status-bar {
        height: 1;
        width: 1fr;
        background: $primary 15%;
        color: $text;
        padding: 0 1;
    }

    /* MOS-SURFACE §12 — semantic color classes */
    .label-warn  { color: $warning; }
    .label-ok    { color: $success; }
    .label-bad   { color: $error;   }
    .you         { color: #FF8C00;  }   /* operator's voice — §10 */
    .aria        { color: #1E90FF;  }   /* Aria's voice — §10 */
    .meta        { color: $text-muted; }
    """

    status: reactive[CockpitStatus] = reactive(CockpitStatus(), recompose=False)

    # Input placeholder text — surfaces the operator's current mode.
    # When idle (no directive running), the cockpit accepts new
    # directives. When a directive is running, the operator's typing
    # is routed to the running subprocess's stdin (answering
    # clarifying questions, confirms, etc.). See §19.2 of MOS-SURFACE.
    PLACEHOLDER_IDLE = "say anything · aria decides · F1 help · /copy /help"
    PLACEHOLDER_BUSY = "answering aria · /cancel to abort · /halt for PROTOCOL-ZERO"

    def __init__(self) -> None:
        super().__init__()
        self._events_log: Optional[RichLog] = None
        self._chat_log: Optional[RichLog] = None
        self._memory_log: Optional[RichLog] = None    # v0.2.25.0
        self._inbox_log: Optional[RichLog] = None      # v0.2.37.0
        self._status_label: Optional[Label] = None
        self._mood_label: Optional[Label] = None
        self._heart_label: Optional[Static] = None
        self._heart_visible: bool = True
        self._sysmon = SystemMonitor(data_dir=self._resolve_data_dir())
        self._events_path = self._resolve_events_path()
        self._events_offset = 0
        self._busy = False
        # The currently-running directive subprocess, if any. Held so
        # that operator input can be forwarded to its stdin (answering
        # clarifying questions) and so /cancel can terminate it. None
        # when no directive is running.
        self._proc: Optional[asyncio.subprocess.Process] = None
        # v0.2.19.0 — natural conversation layer.
        # When the router returns a tier-3 PendingPrompt, we store its
        # callback here. The NEXT operator input (non-slash) is routed
        # to this callback rather than to a fresh interpret() call.
        # /cancel and any input outside the expected "ok"/"yes" cancels
        # cleanly. This is the ONLY place in v0.2.19.0 where an operator
        # message is interpreted as a confirm, and even here the prompt
        # is a single-word check, not a yes/no menu.
        self._pending_callback: Optional[Any] = None
        # Recent operator turns — passed to the interpreter as context
        # so it can reason about continuity (e.g. recognizing that the
        # current message extends an in-progress thought). Trimmed to
        # the last 5 turns.
        self._recent_turns: list[str] = []
        # v0.2.20.1 — chat transcript.
        # Every line written to the chat pane is also kept in an
        # in-memory buffer (for /copy*) AND appended to a disk file
        # (for durability — RichLog text was not previously persisted,
        # so a long message could be visible on-screen yet
        # unrecoverable if the cockpit closed).
        #
        # Each transcript line is (speaker, text):
        #   speaker ∈ {"you", "aria", "meta"}
        #   text is the rendered Rich markup (so an external viewer
        #         can render it the same way the cockpit did)
        self._transcript: list[tuple[str, str]] = []
        self._transcript_path: Optional[Path] = None

    # ── Setup ────────────────────────────────────────────────────────

    @staticmethod
    def _resolve_events_path() -> Path:
        """Find events.jsonl using the same config resolution the agent uses."""
        from sovereign_agent.config import SETTINGS
        return SETTINGS.paths.events_jsonl

    @staticmethod
    def _resolve_data_dir() -> Optional[Path]:
        """Find the agent's data dir so SystemMonitor reports disk usage of
        the right volume (where atoms.db, blobs, and snapshots live).
        Returns None on any error — SystemMonitor falls back to $HOME."""
        try:
            from sovereign_agent.config import SETTINGS
            return SETTINGS.paths.data_dir
        except Exception:  # noqa: BLE001
            return None

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main"):
            with Vertical(id="chat-pane"):
                yield Label("◊ chat", classes="pane-title")
                yield RichLog(
                    id="chat-log",
                    highlight=True, markup=True, wrap=True,
                    auto_scroll=True,
                )
            yield Rule(orientation="vertical", id="divider-1")
            # v0.2.25.0 — the Memory pane.
            # A live view of where Aria's most valuable memories are
            # stored, surfaced so both Kevin and Aria always know what
            # her current self-knowledge looks like. Refreshed on a
            # timer (every 15s by default) plus immediately after any
            # honor / atom / pattern write.
            with Vertical(id="memory-pane"):
                yield Label("◊ memory", classes="pane-title")
                yield RichLog(
                    id="memory-log",
                    highlight=True, markup=True, wrap=True,
                    auto_scroll=False, max_lines=200,
                )
            yield Rule(orientation="vertical", id="divider-2")
            with Vertical(id="live-pane"):
                yield Label("◊ live", classes="pane-title")
                yield RichLog(
                    id="events-log",
                    highlight=True, markup=True, wrap=False,
                    auto_scroll=True, max_lines=200,
                )
            # v0.2.37.0 — the Inbox pane (the 4th window).
            # Aria's collaboration requests: what she's asked of you and the
            # state of each. A scrollable log so you can scroll up and see the
            # whole story — open, answered, resolved, deferred, flagged,
            # revisit. Refreshed on an 8s timer plus immediately on launch.
            yield Rule(orientation="vertical", id="divider-3")
            with Vertical(id="inbox-pane"):
                yield Label("◊ inbox", classes="pane-title")
                yield RichLog(
                    id="inbox-log",
                    highlight=True, markup=True, wrap=True,
                    auto_scroll=False, max_lines=300,
                )
        # v0.2.31.0 — command palette: clickable buttons that paste common
        # `sov` commands into the input box (without sending). The operator
        # reviews/edits before pressing Enter. Speed without surprises.
        # v0.2.34.0 — split into two rows so we can fit the new surfaces
        # (charter, glyphs, theme, cadence) without cramming.
        # v0.2.39.0 — three balanced rows (6/6/6) so the growing palette
        # fits without cramming. Each button carries a hover tooltip; `/palette`
        # prints the full legend.
        _row1 = PALETTE_COMMANDS[0:6]
        _row2 = PALETTE_COMMANDS[6:12]
        _row3 = PALETTE_COMMANDS[12:]
        with Horizontal(id="palette-row"):
            for palette_cmd in _row1:
                yield CommandButton(palette_cmd)
        if _row2:
            with Horizontal(id="palette-row-2"):
                for palette_cmd in _row2:
                    yield CommandButton(palette_cmd)
        if _row3:
            with Horizontal(id="palette-row-3"):
                for palette_cmd in _row3:
                    yield CommandButton(palette_cmd)
        yield Input(
            placeholder=self.PLACEHOLDER_IDLE,
            id="input-box",
        )
        with Horizontal(id="status-row"):
            yield Static("♥", id="heart")
            yield Label("", id="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        # ── Register Aria's curated theme spectrum (16 themes covering the
        # full color family — warm / cool / nature / mono). They appear in
        # the theme picker alongside Textual's built-ins, prefixed 'aria-'
        # so they sort together. Failures here never block the cockpit.
        try:
            from .themes import register_curated_themes
            register_curated_themes(self)
        except Exception:
            pass

        # ── Register user-authored themes from data_dir/themes/, then
        # apply the operator's persisted active theme (if any).
        try:
            from . import user_themes as _ut
            from ..config import SETTINGS
            _ut.register_user_themes(self, SETTINGS.paths.data_dir)
            active = _ut.get_active_theme_name(SETTINGS.paths.data_dir)
            if active:
                try:
                    self.theme = active
                except Exception:
                    pass  # missing theme → fall back to Textual default
        except Exception:
            pass

        # ── If the active theme has hue_cycle effects (e.g., aria-prism),
        # start the engine. Fails silently and safely on any error — the
        # cockpit ships without cycling rather than crashing.
        try:
            from .hue_cycle import maybe_start_for_active_theme
            current_theme = getattr(self, "theme", None)
            self._hue_cycle_engine = maybe_start_for_active_theme(self, current_theme)
        except Exception:
            self._hue_cycle_engine = None

        self._chat_log = self.query_one("#chat-log", RichLog)
        self._events_log = self.query_one("#events-log", RichLog)
        self._memory_log = self.query_one("#memory-log", RichLog)
        self._inbox_log = self.query_one("#inbox-log", RichLog)
        self._status_label = self.query_one("#status-bar", Label)
        self._heart_label = self.query_one("#heart", Static)

        # Header shows: 'sovereign-agent · cockpit · {version} · {theme}'.
        # Updates automatically via watch_theme whenever the operator
        # switches themes from the picker.
        self._refresh_sub_title()

        # v0.2.25.0 — refresh the memory pane on a timer.
        # 15s strikes a balance: fresh enough to feel alive, infrequent
        # enough that disk reads don't dominate the cockpit's I/O.
        self.set_interval(15.0, self._refresh_memory_pane)
        # Also do an immediate refresh so the pane isn't empty on launch
        self.call_after_refresh(self._refresh_memory_pane)

        # v0.2.37.0 — refresh the inbox pane on an 8s timer (more responsive
        # than memory: a pending ask should surface quickly). Immediate
        # refresh on launch too.
        self.set_interval(8.0, self._refresh_inbox_pane)
        self.call_after_refresh(self._refresh_inbox_pane)

        # Welcome banner — Aria approaches with love.
        # MOS-SURFACE §31 — banner format is canonical; version comes from __version__.
        self._chat_log.write(
            f"[bold red]♥[/bold red]  [bold bright_blue]aria[/bold bright_blue] "
            f"· sovereign-agent v{__version__}"
        )
        self._chat_log.write(
            "[dim]welcome back. the kernel is whole.[/dim]"
        )
        self._chat_log.write(
            "[dim]just talk to me. plain english is enough — "
            "no need for `sov ask` in here.[/dim]"
        )
        self._chat_log.write(
            "[dim]F1 for help.[/dim]"
        )
        self._chat_log.write("")

        # Seed live pane with current state
        self._events_log.write("[dim]── live events ──[/dim]")

        # Position the events file pointer at end-of-file so we only show
        # NEW events from now on (not the entire historical log).
        if self._events_path.exists():
            self._events_offset = self._events_path.stat().st_size

        # Background workers
        self._refresh_status_worker()
        self._tail_events_worker()
        self._heartbeat_worker()
        self._breathing_worker()

    # ── Heartbeat ────────────────────────────────────────────────────

    @work(exclusive=True, group="heart")
    async def _heartbeat_worker(self) -> None:
        """A pulsing ♥ in the status bar — proof of life for the cockpit.

        Pattern is a real cardiac rhythm: lub (bright) ─ dub (bright) ─
        rest (dim). Roughly 60 bpm so it's calming, not anxious. If the
        agent has tripped PROTOCOL-ZERO, the heart turns red-on-red so
        the bar reads "alarm" at a glance.
        """
        # Frame: (rendered_text, hold_ms)
        # The heart is rendered as a 3-cell badge: [space][♥][space], all
        # three cells carrying the same `on rgb(...)` background so the
        # halo appears as a clean rectangle that pulses, not as a heart
        # with stub-edges. Cycle ≈ 1 second — about 60 bpm.
        #
        # If the operator hides the heart (Ctrl-B or /heart), the widget
        # is updated to a blank cell and the worker idles.
        normal_cycle = [
            # lub  — bright halo
            ("[bold red on rgb(120,0,15)] ♥ [/]", 140),
            # gap  — halo dimming
            ("[red on rgb(70,0,8)] ♥ [/]", 90),
            # dub  — bright halo
            ("[bold red on rgb(120,0,15)] ♥ [/]", 140),
            # rest — faint halo, outline heart
            ("[red on rgb(30,0,4)] ♡ [/]", 630),
        ]
        halted_cycle = [
            ("[bold red on rgb(160,0,20)] ◊ [/]", 500),
            ("[red on rgb(60,0,8)] ◊ [/]", 500),
        ]
        while True:
            if not self._heart_visible:
                # Operator hid the heart — clear the cell and back off.
                if self._heart_label is not None:
                    self._heart_label.update("   ")
                await asyncio.sleep(0.5)
                continue
            cycle = halted_cycle if self.status.halt else normal_cycle
            for rendered, ms in cycle:
                if self._heart_label is not None:
                    self._heart_label.update(rendered)
                await asyncio.sleep(ms / 1000.0)

    @work(exclusive=True, group="breathe")
    async def _breathing_worker(self) -> None:
        """Outer border colour-cycles when the agent is mid-directive.

        Idle:    steady $primary frame.
        Working: cycles primary → accent → secondary → primary, ~700ms
                 per phase. Communicates "i am thinking" with no extra
                 text noise, and keeps the visual quiet during downtime.
        """
        phases = ["breathing-1", "breathing-2", "breathing-3"]
        idx = 0
        last_busy = False
        while True:
            try:
                main = self.query_one("#main")
            except Exception:  # noqa: BLE001
                # Layout not yet ready; try again next tick.
                await asyncio.sleep(0.7)
                continue
            if self._busy:
                # Advance the phase
                main.add_class(phases[idx])
                for p in phases:
                    if p != phases[idx]:
                        main.remove_class(p)
                idx = (idx + 1) % len(phases)
                last_busy = True
            else:
                # Return to the steady idle state
                if last_busy:
                    for p in phases:
                        main.remove_class(p)
                    last_busy = False
            await asyncio.sleep(0.7)

    # ── Status bar ───────────────────────────────────────────────────

    @work(exclusive=True, group="status")
    async def _refresh_status_worker(self) -> None:
        """Periodically refresh the status bar."""
        while True:
            try:
                self.status = await asyncio.to_thread(self._read_status)
                self._render_status_bar()
            except Exception as exc:  # noqa: BLE001
                # Don't let a transient read failure kill the worker.
                if self._status_label is not None:
                    self._status_label.update(
                        f"[red]status read error: {exc!r}[/red]"
                    )
            await asyncio.sleep(5)

    def _read_status(self) -> CockpitStatus:
        """Synchronous status read — runs off the event loop."""
        from sovereign_agent.config import SETTINGS
        from sovereign_agent.db import open_atoms_db
        from sovereign_agent.mem_channels.financial import FinancialChannel
        from sovereign_agent import backup as backup_mod

        s = CockpitStatus()

        # HALT
        halt_file = SETTINGS.paths.config_dir / "HALT"
        s.halt = halt_file.exists()

        # Daemon
        try:
            r = subprocess.run(
                ["systemctl", "--user", "is-active", "sovereign-agent.service"],
                capture_output=True, text=True, timeout=2,
            )
            s.daemon_active = (r.stdout.strip() == "active")
        except (subprocess.SubprocessError, FileNotFoundError):
            s.daemon_active = False

        # Ledger
        try:
            conn = open_atoms_db()
            try:
                fc = FinancialChannel(conn)
                result = fc.audit()
                s.ledger_clean = result.ok
                s.ledger_rows = result.ledger_rows
            finally:
                conn.close()
        except Exception:  # noqa: BLE001
            s.ledger_clean = False

        # Backup
        try:
            bs = backup_mod.status()
            s.snapshot_age_seconds = bs.most_recent_age_seconds
            s.snapshot_verify_ok = bool(bs.last_verify_ok) if bs.last_verify_ok is not None else True
        except Exception:  # noqa: BLE001
            pass

        # System (CPU/RAM/disk/load/uptime — never raises)
        s.system = self._sysmon.read()

        # VRAM — best effort. Skip silently if no GPU stack is available.
        try:
            from sovereign_agent.vram import read_vram
            v = read_vram()
            s.vram_total_mb = v.total_mb
            s.vram_used_mb = v.used_mb
            s.vram_source = v.source
        except Exception:  # noqa: BLE001
            pass

        # GPU temperature — independent call (vram.py untouched)
        try:
            from .sysmon import read_gpu_temp
            s.vram_temp_c = read_gpu_temp()
        except Exception:  # noqa: BLE001
            pass

        # Append a telemetry sample. write_sample never raises.
        try:
            from .telemetry import write_sample
            write_sample(
                s.system,
                vram_total_mb=s.vram_total_mb,
                vram_used_mb=s.vram_used_mb,
                vram_temp_c=s.vram_temp_c,
            )
        except Exception:  # noqa: BLE001
            pass

        return s

    def _render_status_bar(self) -> None:
        if self._status_label is None:
            return
        s = self.status

        halt = "[red b]◊HALT[/red b]" if s.halt else "[green]clear[/green]"
        daemon = "[green]●[/green]" if s.daemon_active else "[dim]○[/dim]"
        ledger = (
            f"[green]✓[/green] {s.ledger_rows}r"
            if s.ledger_clean
            else "[red]✗[/red]"
        )
        if s.snapshot_age_seconds is None:
            backup = "[yellow]no snap[/yellow]"
        else:
            mark = "[green]✓[/green]" if s.snapshot_verify_ok else "[red]✗[/red]"
            backup = f"{mark} {_format_age(s.snapshot_age_seconds)}"

        # System metrics: compact, colour-coded (replaces the old key-hint
        # suffix — the Footer already shows the keybindings). RAM and VRAM
        # are now labelled distinctly — they are different hardware. Temps
        # are appended where they're meaningful and available.
        if s.system is not None:
            vram_pct: Optional[float] = None
            if s.vram_total_mb and s.vram_used_mb is not None and s.vram_total_mb > 0:
                vram_pct = 100.0 * s.vram_used_mb / s.vram_total_mb
            metrics = render_compact_metrics(
                s.system, vram_percent=vram_pct, vram_temp_c=s.vram_temp_c,
            )
        else:
            metrics = "[dim]metrics ...[/dim]"

        self._status_label.update(
            f"halt: {halt}  │  daemon: {daemon}  │  "
            f"ledger: {ledger}  │  backup: {backup}  │  "
            f"{metrics}"
        )

    # ── Event tail ───────────────────────────────────────────────────

    @work(exclusive=True, group="events")
    async def _tail_events_worker(self) -> None:
        """Tail events.jsonl and forward to the live pane."""
        while True:
            try:
                if self._events_path.exists():
                    current_size = self._events_path.stat().st_size
                    if current_size < self._events_offset:
                        # File rotated; reset.
                        self._events_offset = 0
                    if current_size > self._events_offset:
                        new_lines = await asyncio.to_thread(
                            self._read_new_lines,
                        )
                        for line in new_lines:
                            self._render_event(line)
            except Exception as exc:  # noqa: BLE001
                if self._events_log is not None:
                    self._events_log.write(
                        f"[red]tail error: {exc!r}[/red]"
                    )
            await asyncio.sleep(1)

    def _read_new_lines(self) -> list[str]:
        """Synchronous read of new event lines from current offset."""
        out: list[str] = []
        with self._events_path.open("r") as f:
            f.seek(self._events_offset)
            for line in f:
                out.append(line.rstrip("\n"))
            self._events_offset = f.tell()
        return out

    def _render_event(self, raw: str) -> None:
        if self._events_log is None:
            return
        try:
            ev = json.loads(raw)
        except json.JSONDecodeError:
            self._events_log.write(raw[:80])
            return

        ts = ev.get("ts", "")[11:19]  # HH:MM:SS slice
        flag = ev.get("flag", "?")
        # Color by event kind
        if "end" in flag:
            color = "green"
        elif "start" in flag:
            color = "cyan"
        elif "halt" in flag or "fail" in flag or "error" in flag:
            color = "red"
        elif "approval" in flag:
            color = "yellow"
        else:
            color = "white"
        self._events_log.write(f"[dim]{ts}[/dim] [{color}]{flag}[/{color}]")

    # ── Input handling ───────────────────────────────────────────────

    @on(Input.Submitted, "#input-box")
    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Route operator input by mode.

        Priority order (v0.2.30.1):

        1. **Slash commands** always take the slash-command path,
           regardless of any other state. This guarantees `/cancel`,
           `/halt`, `/disarm`, `/quit`, and `/help` always work.
        2. **Pending tier-3 confirm** — the previous turn produced a
           PendingPrompt waiting for "ok" or anything else. This is
           the ONLY place where operator input is interpreted as a
           confirm, and it accepts a single word, never a yes/no menu.
        3. **Busy with a running subprocess** — operator typing is
           forwarded to the subprocess's stdin. Retained from §19.2
           for legacy `sovereign do` invocations and for tier-2
           long-running tasks like `sov dream start`.
        4. **`sov ...` / `sovereign ...` prefix normalization** —
           v0.2.30.1+: muscle-memory CLI strings typed inside the
           cockpit get reshaped. `sov ask "hello"` becomes the
           natural-language message `hello`. `sov heartbeat pulse
           "first pulse"` runs as a real subprocess command. The
           cockpit is a natural-language home — prefixes are now
           transparent, not load-bearing.
        5. **Idle** — the operator is initiating a fresh turn. Route
           through the conversation layer (interpret → router).
        """
        text = event.value.strip()
        event.input.value = ""
        if not text:
            return
        if text.startswith("/"):
            self._handle_slash(text)
            return
        # v0.2.19.0 — pending tier-3 confirm takes priority over busy
        # subprocess routing. If both were set somehow, the confirm
        # wins because it's the only narrowly-scoped, single-word
        # answer path. Otherwise the operator's "ok" would be sent to
        # a subprocess that doesn't know what to do with it.
        if self._pending_callback is not None:
            cb = self._pending_callback
            self._pending_callback = None
            self._write_you(text)
            try:
                followup = cb(text)
                for line in getattr(followup, "messages", []) or []:
                    self._write_aria(line)
            except Exception as exc:  # noqa: BLE001
                self._write_meta(f"[red]confirm callback failed: {exc!r}[/red]")
            return
        if self._busy and self._proc is not None:
            self._answer_subprocess(text)
            return
        # v0.2.32.0 — Stage C intent classifier fires BEFORE the structural
        # normalizer. The classifier gets every cockpit input. If it returns
        # NL_INTENT with non-trivial confidence, the structural CLI match is
        # vetoed and the input routes through the conversation pipeline.
        #
        # This is what catches "sovereign sync is a beautiful metaphor for life":
        # the structural normalizer would see `sov sync` and want to execute;
        # the classifier sees the prose pattern and says NL_INTENT 0.85; the
        # cockpit honors the veto.
        #
        # The default classifier (HeuristicClassifier) is synchronous — pure
        # regex work, microseconds per call. Operators who want LLM-backed
        # classification (OllamaClassifier) wire it via a Textual worker
        # since it needs an event loop. The sync path is the always-on
        # default; the async path is opt-in.
        try:
            from .intent_classifier import (
                IntentLabel, get_default_classifier,
            )
            classifier = get_default_classifier()
            intent_result = classifier.classify(text)
            if intent_result.label == IntentLabel.NL_INTENT and \
                    intent_result.confidence >= 0.60:
                # NL veto fires. Surface the reason ONCE so the operator
                # understands the routing — they can disagree by typing
                # the command more explicitly.
                self._write_meta(
                    f"[dim]◊ stage-c: NL_INTENT "
                    f"({intent_result.confidence:.2f}) · "
                    f"routing as conversation[/dim]"
                )
                self._dispatch_turn(text)
                return
            # CLI_INTENT or AMBIGUOUS → fall through to structural normalizer
        except Exception as exc:  # noqa: BLE001 — classifier is best-effort
            logger.debug("stage-c classifier failed: %r", exc)

        # v0.2.30.1 — normalize `sov ...` / `sovereign ...` prefixes so
        # muscle-memory CLI strings do the right thing inside the cockpit.
        # v0.2.31.0 — destructive subcommands return a `guarded` kind that
        # routes through the conversation layer instead of subprocessing.
        normalized = normalize_sov_prefix(text)
        if normalized is not None:
            if normalized.kind == "natural":
                # `sov ask "X"` / `sov do "X"` — unwrap to the bare message
                # and feed it to the conversation pipeline. The hint tells
                # the operator (gently, once) that the prefix wasn't needed.
                self._write_meta(
                    f"[dim]◊ unwrapped — inside the cockpit you can just say "
                    f"what you mean; no need for `sov ask` or `sov do`[/dim]"
                )
                self._dispatch_turn(normalized.text)
                return
            if normalized.kind == "guarded":
                # Destructive subcommand — route through the conversation
                # pipeline so the Tier-3 confirm gate fires. The reason is
                # surfaced once so the operator knows why we didn't just
                # subprocess it.
                self._write_meta(
                    f"[yellow]◊ guarded — {normalized.reason}[/yellow]"
                )
                self._dispatch_turn(normalized.text)
                return
            if normalized.kind == "execute":
                # Direct CLI command (e.g. `sov heartbeat pulse "..."`,
                # `sov doctor`, `sov channels list`). Echo the operator's
                # input, then stream the subprocess output into chat.
                # Palette buttons are updated by _run_cli_async itself.
                self._write_you(text)
                label = " ".join(normalized.argv[1:2]) or "sov"
                self._write_meta(f"[dim]◊ executing: sov {label}[/dim]")
                self._run_cli_async(list(normalized.argv), label=f"sov {label}")
                return
        self._dispatch_turn(text)

    def _answer_subprocess(self, text: str) -> None:
        """Forward operator input to the running subprocess's stdin.

        Called when `sovereign do` (or any tracked directive
        subprocess) is asking a clarifying question and the operator
        is answering it. Echoes the operator's answer into the chat
        so the transcript captures both sides of the conversation.

        The write is best-effort: if the subprocess has already
        closed stdin or exited, we surface a meta message rather than
        raising. The `_busy` flag will clear in the worker's `finally`
        block on the next loop iteration.

        Note: asyncio's StreamWriter.write() is non-blocking and
        buffers the data; the event loop drains the buffer to the
        OS pipe on the next iteration. For one-line operator inputs
        (well under 64KB), this is reliable without an explicit
        drain() call. We deliberately do NOT await drain() here
        because this method is called from a synchronous Textual
        event handler.
        """
        if self._proc is None or self._proc.stdin is None:
            self._write_meta(
                "[yellow](no running task to answer — input not sent)[/yellow]"
            )
            return
        # Echo the operator's answer locally — the subprocess receives
        # it via stdin but does not necessarily echo it to stdout (it
        # might just consume the line and continue), so without this
        # echo the operator would lose track of what they said.
        self._write_you(text)
        try:
            self._proc.stdin.write((text + "\n").encode("utf-8"))
        except (BrokenPipeError, ConnectionResetError):
            self._write_meta(
                "[yellow](task closed its input — answer not delivered)[/yellow]"
            )
        except Exception as exc:  # noqa: BLE001
            self._write_meta(f"[red]could not send to task: {exc!r}[/red]")

    def _handle_slash(self, text: str) -> None:
        cmd = text.lstrip("/").split(maxsplit=1)
        verb = cmd[0].lower()
        arg = cmd[1] if len(cmd) > 1 else ""

        if verb in ("quit", "q", "exit"):
            self.exit()
        elif verb in ("help", "h", "?"):
            self.action_help()
        elif verb == "clear":
            self.action_clear_chat()
        elif verb == "halt":
            self.action_halt()
        elif verb == "disarm":
            self.action_disarm()
        elif verb in ("cancel", "abort", "stop"):
            # /cancel — terminate the running directive subprocess.
            # Always works regardless of _busy state so the operator
            # has a guaranteed escape hatch (MOS-SURFACE §19.2).
            self.action_cancel_directive()
        elif verb == "snap":
            label = arg or ""
            self._run_cli_async(
                ["sovereign", "backup", "snapshot"] +
                (["--label", label] if label else []),
                label="snap",
            )
        elif verb == "audit":
            self._run_cli_async(["sovereign", "financial", "audit"], label="audit")
        elif verb == "events":
            n = arg or "20"
            self._run_cli_async(["sovereign", "events", "-n", n], label="events")
        elif verb == "lessons":
            self._run_cli_async(
                ["sovereign", "channels", "show", "lessons"], label="lessons",
            )
        elif verb == "health":
            self._show_health()
        elif verb == "report":
            self._save_report()
        elif verb == "drafts":
            # /drafts → list. /drafts N → list newest N.
            n = 20
            if arg.strip().isdigit():
                n = int(arg.strip())
            self._run_cli_async(
                ["sovereign", "drafts", "list", "--limit", str(n)],
                label="drafts",
            )
        elif verb == "draft":
            # /draft <title> <source-path>   archive a project as a draft
            parts = arg.strip().split(maxsplit=1)
            if len(parts) < 2:
                self._write_meta(
                    "[yellow]usage: /draft <title> <source-path>[/yellow]"
                )
            else:
                title, src = parts
                self._run_cli_async(
                    ["sovereign", "drafts", "archive", title, src],
                    label="draft",
                )
        elif verb == "marketing":
            # /marketing <product>   generate a marketing brief via the planner
            product = arg.strip()
            if not product:
                self._write_meta(
                    "[yellow]usage: /marketing <product or release name>[/yellow]"
                )
            else:
                self._dispatch_directive(
                    f"generate marketing brief for {product}"
                )
        elif verb == "heart":
            self.action_toggle_heart()
        elif verb in ("copy", "copy-aria"):
            # /copy → copy last aria turn to clipboard.
            # If arg is a number N, copy the last N aria turns.
            self._copy_recent(speaker_filter="aria", limit=_arg_to_int(arg, 1))
        elif verb in ("copy-you", "copy-me"):
            self._copy_recent(speaker_filter="you", limit=_arg_to_int(arg, 1))
        elif verb == "copy-all":
            self._copy_recent(speaker_filter=None, limit=None)
        elif verb in ("copy-last", "copy-turn"):
            # Last full turn = last "you" message + every "aria"/"meta"
            # line until the next "you". Useful for sharing a complete
            # exchange.
            self._copy_last_turn()
        elif verb == "transcript":
            # /transcript → show the absolute path to the transcript log.
            path = self._resolve_transcript_path()
            self._write_meta(f"[dim]transcript: {path}[/dim]")
        elif verb == "mode":
            # v0.2.32.0 — /mode chat | /mode work
            # The mode controls whether autonomous agentic loops can run.
            # Chat is the default; work enables planning + queue extension.
            self._handle_mode_slash(arg.strip().lower())
        elif verb in ("palette", "buttons", "legend"):
            self._show_palette_legend()
        else:
            self._write_meta(f"unknown command: /{verb}")

    def _handle_mode_slash(self, arg: str) -> None:
        """Handle /mode chat | /mode work | /mode (no arg → show current).

        Mode transitions are operator-initiated and emit a
        ``cockpit-mode-changed-d`` event so the audit trail captures every
        change. The whole cockpit reads load_mode() on every input, so
        the new mode takes effect on the very next turn.
        """
        from .. import cockpit_modes
        if not arg:
            # Show current mode + how to change
            current = cockpit_modes.load_mode()
            self._write_meta(
                f"[cyan]◊ current mode: {current.mode}[/cyan]  "
                f"[dim](use `/mode chat` or `/mode work` to switch)[/dim]"
            )
            return
        try:
            new_mode = cockpit_modes.CockpitMode(arg)
        except ValueError:
            self._write_meta(
                f"[yellow]unknown mode: {arg!r}. "
                f"valid: chat, work[/yellow]"
            )
            return
        before = cockpit_modes.load_mode().mode
        cockpit_modes.set_mode(
            new_mode,
            reason=f"operator typed /mode {arg} in cockpit",
        )
        # Visible confirmation with the implication of the change spelled out
        if new_mode == cockpit_modes.CockpitMode.WORK:
            self._write_meta(
                f"[green]◊ mode: {before} → work[/green]  "
                f"[dim]autonomous loops, planning, and queue extension are "
                f"now allowed within configured budgets[/dim]"
            )
        else:
            self._write_meta(
                f"[green]◊ mode: {before} → chat[/green]  "
                f"[dim]autonomous loops paused; every action requires an "
                f"operator-initiated turn[/dim]"
            )
        # Refresh the status bar immediately so the mode indicator updates
        try:
            self._render_status_bar()
        except Exception:  # noqa: BLE001
            pass

    def _copy_recent(
        self,
        *,
        speaker_filter: Optional[str],
        limit: Optional[int],
    ) -> None:
        """Copy the most recent transcript entries to clipboard.

        Filters by speaker if speaker_filter is set. Takes the last
        `limit` matching entries, or all matching entries if limit is
        None. The clipboard receives stripped prose (Rich markup
        removed) so it can be pasted into a plain-text editor.
        """
        if not self._transcript:
            self._write_meta("[dim](nothing to copy)[/dim]")
            return
        if speaker_filter is None:
            entries = list(self._transcript)
        else:
            entries = [(s, t) for s, t in self._transcript
                       if s == speaker_filter]
        if limit is not None and limit > 0:
            entries = entries[-limit:]
        if not entries:
            self._write_meta(
                f"[dim](no {speaker_filter or 'transcript'} lines yet)[/dim]"
            )
            return
        # Strip Rich markup for the clipboard payload — operators
        # paste into plain editors, not Rich consoles.
        from rich.text import Text as _RichText
        plain_lines: list[str] = []
        for speaker, text in entries:
            try:
                plain = _RichText.from_markup(text).plain
            except Exception:  # noqa: BLE001
                plain = text
            if speaker_filter is None:
                # Annotate with speaker prefix when mixing voices
                plain_lines.append(f"[{speaker}] {plain}")
            else:
                plain_lines.append(plain)
        payload = "\n".join(plain_lines)
        ok = self._write_clipboard(payload)
        if ok:
            n = len(entries)
            label = speaker_filter or "transcript"
            self._write_meta(
                f"[green]✓[/green] [dim]copied {n} {label} line"
                f"{'s' if n != 1 else ''} to clipboard[/dim]"
            )
        else:
            self._write_meta(
                "[red]✗[/red] [dim]no clipboard tool found "
                "(install wl-copy, xclip, or xsel)[/dim]"
            )

    def _copy_last_turn(self) -> None:
        """Copy the last complete turn: the most recent [you] entry
        plus everything that followed it (aria + meta lines)."""
        if not self._transcript:
            self._write_meta("[dim](nothing to copy)[/dim]")
            return
        # Find the last 'you' index, then everything from there forward.
        idx_you: Optional[int] = None
        for i in range(len(self._transcript) - 1, -1, -1):
            if self._transcript[i][0] == "you":
                idx_you = i
                break
        if idx_you is None:
            # No operator turn yet — fall back to copying everything.
            entries = list(self._transcript)
        else:
            entries = self._transcript[idx_you:]
        from rich.text import Text as _RichText
        plain_lines: list[str] = []
        for speaker, text in entries:
            try:
                plain = _RichText.from_markup(text).plain
            except Exception:  # noqa: BLE001
                plain = text
            plain_lines.append(f"[{speaker}] {plain}")
        payload = "\n".join(plain_lines)
        ok = self._write_clipboard(payload)
        if ok:
            self._write_meta(
                f"[green]✓[/green] [dim]copied last turn "
                f"({len(entries)} lines) to clipboard[/dim]"
            )
        else:
            self._write_meta(
                "[red]✗[/red] [dim]no clipboard tool found[/dim]"
            )

    def _dispatch_turn(self, text: str) -> None:
        """v0.2.19.0 — primary chat entry. Routes through the natural
        conversation layer.

        Pipeline:
            text → interpret() → router.route() → RouteResult

        Most messages return synchronously fast (microseconds for
        Conversation; sub-2s for LLM-classified intents). Only tier-2
        commands escalate to the subprocess path via
        `_dispatch_directive`, which retains the §19.2 plumbing for
        long-running streaming tasks.

        The operator is NEVER trapped here:
          - Conversation → save + reply, done
          - Tier-0/1 work → run inline via the router's executor
          - Tier-2 work → escalate to subprocess for streaming output
          - Tier-3 work → set a PendingPrompt; one-word `ok` confirms
          - Ambiguous → show ONE question, fall back to conversation
                        if the operator just keeps typing
        """
        if self._busy:
            self._write_meta(
                "[yellow]aria is still working — type your answer to the "
                "current question, or `/cancel` to abort.[/yellow]"
            )
            return
        self._write_you(text)
        # Remember the turn for context on subsequent classifications.
        self._recent_turns.append(text)
        if len(self._recent_turns) > 5:
            self._recent_turns = self._recent_turns[-5:]
        self._busy = True
        self._set_input_placeholder(self.PLACEHOLDER_BUSY)
        self._run_conversation_worker(text)

    # Legacy alias — internal callers (e.g. /marketing) still use this
    # name. Routes through the new turn pipeline so behavior is
    # consistent across entry points.
    def _dispatch_directive(self, text: str) -> None:
        """Compatibility shim. Use _dispatch_turn for new code."""
        self._dispatch_turn(text)

    @work(exclusive=False, group="directive")
    async def _run_conversation_worker(self, text: str) -> None:
        """The conversation worker — interprets and routes operator
        input, escalating to a subprocess only for tier-2 work.

        Replaces v0.2.18.x's `_run_directive_worker` for the common
        case. The subprocess path is retained for tier-2 streaming
        commands; see `_run_tier2_subprocess`.
        """
        from sovereign_agent.conversation import (
            converse,
            make_default_channel_writer,
            make_default_event_sink,
        )
        from sovereign_agent.ollama_client import OllamaClient
        from sovereign_agent.projects import ProjectStore
        from sovereign_agent.config import SETTINGS

        t0 = time.time()
        try:
            self._write_aria_thinking()

            store = ProjectStore(SETTINGS.paths.projects_dir)
            store.ensure_root()

            client: Optional[OllamaClient] = None
            try:
                client = OllamaClient()
            except Exception:  # noqa: BLE001
                # No LLM? The interpreter's Layer 2 takes over silently.
                client = None

            turn = await converse(
                text,
                ollama_client=client,
                project_store=store,
                channel_writer=make_default_channel_writer(),
                event_sink=make_default_event_sink(),
                surface="cockpit",
                recent_turns=tuple(self._recent_turns[:-1]),
            )

            # Surface Aria's voice for this turn
            for line in turn.messages:
                self._write_aria(line)

            # If the router needs a tier-3 confirm, stash the callback
            # for the next operator turn.
            if turn.has_pending and turn.result.pending is not None:
                self._pending_callback = turn.result.pending.callback
                self._write_aria(
                    f"[dim](type `ok` to confirm, or `/cancel`)[/dim]"
                )

            # Tier-2 work that the router demoted to "needs subprocess"
            # — currently routed by command name. The router itself
            # could be extended to return a "spawn_subprocess" hint,
            # but for v0.2.19.0 we keep the seam minimal.
            for cmd in turn.result.executed_commands:
                if any(cmd.startswith(prefix) for prefix in (
                    "sov dream", "sov continue", "sov do",
                )):
                    self._write_meta(
                        f"[dim]◊ tier-2 streaming task: {cmd}[/dim]"
                    )

            dur_s = time.time() - t0
            self._write_meta(
                f"[dim]turn complete · {dur_s:.2f}s · {turn.kind}[/dim]"
            )
        except Exception as exc:  # noqa: BLE001
            self._write_meta(f"[red]conversation error: {exc!r}[/red]")
        finally:
            self._busy = False
            self._proc = None
            self._set_input_placeholder(self.PLACEHOLDER_IDLE)

    def _set_input_placeholder(self, text: str) -> None:
        """Update the input box's placeholder. Safe to call before
        the input is mounted (no-op in that case)."""
        try:
            input_box = self.query_one("#input-box", Input)
            input_box.placeholder = text
        except Exception:  # noqa: BLE001
            pass

    @work(exclusive=False, group="directive")
    async def _run_directive_worker(self, text: str) -> None:
        # ── Pre: snapshot VRAM so we can report the delta on completion
        vram_before_mb: Optional[int] = None
        try:
            from sovereign_agent.vram import read_vram
            vram_before_mb = read_vram().used_mb
        except Exception:  # noqa: BLE001
            pass
        t0 = time.time()
        try:
            self._write_aria_thinking()
            # MOS-SURFACE §19.2 — directive subprocesses run with
            # stdin=PIPE so the operator can answer clarifying
            # questions via the cockpit's Input. Without the pipe,
            # `sovereign do` blocks on `input("  > ")` inheriting
            # the parent TTY (which Textual owns), and the cockpit
            # deadlocks forever. PYTHONUNBUFFERED=1 ensures the
            # subprocess's prompt output isn't block-buffered when
            # stdout is a pipe — operators see prompts immediately.
            env = {**os.environ, "PYTHONUNBUFFERED": "1"}
            proc = await asyncio.create_subprocess_exec(
                "sovereign", "do", text,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=env,
            )
            self._proc = proc
            assert proc.stdout is not None
            async for line_bytes in proc.stdout:
                line = line_bytes.decode("utf-8", errors="replace").rstrip("\n")
                if line:
                    self._write_aria(line)
            await proc.wait()
            # ── Post: VRAM delta + duration, written as a meta line and
            #         appended to the events log so it's traceable
            vram_after_mb: Optional[int] = None
            try:
                from sovereign_agent.vram import read_vram
                vram_after_mb = read_vram().used_mb
            except Exception:  # noqa: BLE001
                pass
            dur_s = time.time() - t0

            footer = f"[dim]turn complete · exit {proc.returncode} · {dur_s:.1f}s"
            if vram_before_mb is not None and vram_after_mb is not None:
                delta = vram_after_mb - vram_before_mb
                sign = "+" if delta >= 0 else ""
                footer += (
                    f" · vram {vram_before_mb}→{vram_after_mb} MB "
                    f"({sign}{delta} MB)"
                )
            footer += "[/dim]"
            self._write_meta(footer)

            # Append a structured event line so the operator can grep for
            # turn timings + vram footprints in the live pane too.
            if self._events_log is not None:
                tag = "task-end" if proc.returncode == 0 else "task-fail"
                colour = "green" if proc.returncode == 0 else "red"
                vram_str = ""
                if vram_before_mb is not None and vram_after_mb is not None:
                    vram_str = f" Δvram={vram_after_mb - vram_before_mb:+d}MB"
                self._events_log.write(
                    f"[dim]{_now_short()}[/dim] [{colour}]{tag}[/{colour}] "
                    f"dur={dur_s:.1f}s{vram_str}"
                )

            # Persistent telemetry — write a task-end record to the daily
            # JSONL file. Includes deltas so the operator can later run
            # `sov telemetry summary` and see which directives are heavy.
            try:
                from .telemetry import write_sample
                s_now = self._sysmon.read()
                extra = {
                    "task_directive": text[:200],
                    "task_phase": "end",
                    "task_status": "ok" if proc.returncode == 0 else "fail",
                    "task_duration_s": round(dur_s, 2),
                    "task_exit_code": proc.returncode,
                }
                if vram_before_mb is not None and vram_after_mb is not None:
                    extra["task_vram_before_mb"] = vram_before_mb
                    extra["task_vram_after_mb"] = vram_after_mb
                    extra["task_vram_delta_mb"] = vram_after_mb - vram_before_mb
                write_sample(
                    s_now,
                    vram_total_mb=self.status.vram_total_mb,
                    vram_used_mb=vram_after_mb,
                    vram_temp_c=self.status.vram_temp_c,
                    extra=extra,
                )
            except Exception:  # noqa: BLE001
                pass
        except FileNotFoundError:
            self._write_meta("[red]sovereign binary not found on PATH[/red]")
        except Exception as exc:  # noqa: BLE001
            self._write_meta(f"[red]error: {exc!r}[/red]")
        finally:
            # Restore idle state. The `_proc = None` clears before
            # `_busy = False` so any racing handler that checks
            # `_busy and _proc is not None` (i.e. _answer_subprocess)
            # cannot route to a stale subprocess.
            self._proc = None
            self._busy = False
            self._set_input_placeholder(self.PLACEHOLDER_IDLE)

    @work(exclusive=False, group="cli")
    async def _run_cli_async(self, argv: list[str], *, label: str) -> None:
        # v0.2.31.0 — palette state tracking: if this command matches a
        # palette button, glow it cyan while running. The mapping uses the
        # second argv token (the subcommand) which matches PaletteCommand.key
        # for most palette entries.
        palette_key = argv[1] if len(argv) > 1 else None
        if palette_key:
            self._notify_palette_running(palette_key)
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            assert proc.stdout is not None
            self._write_meta(f"[dim]── {label} ──[/dim]")
            async for line_bytes in proc.stdout:
                line = line_bytes.decode("utf-8", errors="replace").rstrip("\n")
                if line:
                    self._write_aria(line)
            await proc.wait()
        except Exception as exc:  # noqa: BLE001
            self._write_meta(f"[red]{label} failed: {exc!r}[/red]")
        finally:
            if palette_key:
                self._notify_palette_done(palette_key)

    # ── Palette button handling (v0.2.31.0) ─────────────────────────────────

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle palette button clicks.

        A click PASTES the button's command into the input box (it does
        NOT submit). The operator can edit the command, hit Enter to run,
        or press Escape to cancel. The button flashes green for ~300ms so
        the click is visually confirmed.

        We deliberately don't auto-submit — the whole point of the palette
        is speed *without* sacrificing review. The button is a paste
        shortcut, not a remote-control trigger.
        """
        button = event.button
        if not isinstance(button, CommandButton):
            return
        cmd = button.palette_cmd

        # Paste the command text into the input box (don't submit)
        try:
            input_box = self.query_one("#input-box", Input)
            input_box.value = cmd.command
            input_box.focus()
            # Move cursor to end so the operator can append immediately
            try:
                input_box.cursor_position = len(cmd.command)
            except AttributeError:
                # Older Textual versions; cursor placement is cosmetic
                pass
        except Exception as exc:  # noqa: BLE001
            self._write_meta(f"[red]palette paste failed: {exc!r}[/red]")
            return

        # Flash the button green for click feedback (~300ms)
        button.add_class("flash")
        self.set_timer(0.3, lambda: button.remove_class("flash"))

    def _notify_palette_running(self, key: str) -> None:
        """Mark every palette button whose key matches `key` as running.

        Called when a sov subprocess starts. The matching button(s) glow
        cyan until ``_notify_palette_done`` clears them. Safe to call
        before the cockpit is fully mounted — we no-op in that case.
        """
        try:
            for button in self.query(CommandButton):
                if button.palette_cmd.key == key:
                    button.add_class("running")
        except Exception:  # noqa: BLE001 — cockpit may be mid-mount
            pass

    def _notify_palette_done(self, key: str) -> None:
        """Clear the running glow on palette buttons matching `key`."""
        try:
            for button in self.query(CommandButton):
                if button.palette_cmd.key == key:
                    button.remove_class("running")
        except Exception:  # noqa: BLE001
            pass

    # ── Actions ──────────────────────────────────────────────────────

    def action_help(self) -> None:
        self.push_screen(HelpScreen())

    def action_clear_chat(self) -> None:
        if self._chat_log is not None:
            self._chat_log.clear()
            self._write_meta("[dim]── chat cleared ──[/dim]")

    def action_halt(self) -> None:
        self._write_meta("[red]◊ tripping PROTOCOL-ZERO ...[/red]")
        self._run_cli_async(
            ["sovereign", "halt", "--reason", "cockpit Ctrl-H"],
            label="halt",
        )

    def action_disarm(self) -> None:
        self._write_meta("[green]◊ disarming PROTOCOL-ZERO ...[/green]")
        self._run_cli_async(["sovereign", "disarm"], label="disarm")

    def action_cancel_directive(self) -> None:
        """Cancel the running directive subprocess or pending confirm.

        Bound to `/cancel`, `/abort`, `/stop`. Three things it might
        cancel, in priority order:

          1. A pending tier-3 confirm (v0.2.19.0) — discards the
             callback so the next operator turn starts fresh.
          2. A running directive subprocess (§19.2) — sends SIGTERM;
             the worker's `finally` clears `_busy`, `_proc`, and
             restores the idle placeholder.
          3. Nothing — quiet meta message; no-op.

        Always safe to call. The operator's guaranteed escape from
        any state.
        """
        if self._pending_callback is not None:
            self._pending_callback = None
            self._write_meta(
                "[yellow]◊ confirm cancelled — nothing was run[/yellow]"
            )
            return
        if self._proc is None or not self._busy:
            self._write_meta("[dim](nothing to cancel)[/dim]")
            return
        try:
            self._proc.terminate()
            self._write_meta(
                "[yellow]◊ cancel sent · waiting for task to exit ...[/yellow]"
            )
        except ProcessLookupError:
            # Race: subprocess exited between the busy check and the
            # terminate. The worker will clean up on its own.
            pass
        except Exception as exc:  # noqa: BLE001
            self._write_meta(f"[red]could not cancel: {exc!r}[/red]")

    def action_toggle_heart(self) -> None:
        """Toggle the heartbeat badge. Ctrl-B or /heart."""
        self._heart_visible = not self._heart_visible
        state = "shown" if self._heart_visible else "hidden"
        self._write_meta(f"[dim]♥ heart {state}[/dim]")

    def action_paste_clipboard(self) -> None:
        """Paste system clipboard contents at the input box cursor.

        Bound to Ctrl+V. Reads the clipboard via the platform's native
        tooling (wl-paste on Wayland, xclip / xsel on X11, pbpaste on
        macOS) and inserts at the current cursor position of the focused
        Input widget. If no Input is focused, the operation is a no-op.

        Multi-line clipboard contents have their newlines collapsed to
        spaces (a chat-input convention; the operator can press Enter
        to send and then paste the next line, or use Shift+Enter where
        supported).
        """
        text = self._read_clipboard()
        if not text:
            self._write_meta("[dim](clipboard empty or unreadable)[/dim]")
            return
        # Collapse newlines for single-line input use
        single_line = text.replace("\r\n", " ").replace("\n", " ").rstrip()
        try:
            from textual.widgets import Input as _Input
            input_box = self.query_one("#input-box", _Input)
        except Exception:
            return
        input_box.insert_text_at_cursor(single_line)

    @staticmethod
    def _read_clipboard() -> str:
        """Cross-platform clipboard read with no new Python deps.

        Tries in priority order:
          1. wl-paste       — Wayland (modern Linux desktops)
          2. xclip          — X11
          3. xsel           — X11 fallback
          4. pbpaste        — macOS
          5. powershell     — Windows (best-effort)

        Returns the clipboard text decoded as UTF-8, or an empty string
        if every available tool failed or none are present.
        """
        import shutil
        import subprocess

        candidates = (
            ("wl-paste",   ["wl-paste", "--no-newline"]),
            ("xclip",      ["xclip", "-selection", "clipboard", "-o"]),
            ("xsel",       ["xsel", "--clipboard", "--output"]),
            ("pbpaste",    ["pbpaste"]),
            ("powershell", ["powershell.exe", "-NoProfile",
                            "-Command", "Get-Clipboard"]),
        )
        for binary, argv in candidates:
            if not shutil.which(binary):
                continue
            try:
                out = subprocess.check_output(
                    argv,
                    stderr=subprocess.DEVNULL,
                    timeout=2,
                )
                return out.decode("utf-8", errors="replace")
            except (subprocess.SubprocessError, OSError):
                continue
        return ""

    @staticmethod
    def _write_clipboard(text: str) -> bool:
        """Cross-platform clipboard write (v0.2.20.1).

        Mirror of _read_clipboard. Returns True if any tool succeeded,
        False otherwise. The cockpit treats a False result as an
        operator-visible error rather than silent failure — knowing
        the copy didn't work is more useful than thinking it did.
        """
        import shutil
        import subprocess

        candidates = (
            ("wl-copy",    ["wl-copy"]),
            ("xclip",      ["xclip", "-selection", "clipboard"]),
            ("xsel",       ["xsel", "--clipboard", "--input"]),
            ("pbcopy",     ["pbcopy"]),
            ("powershell", ["powershell.exe", "-NoProfile",
                            "-Command", "Set-Clipboard"]),
        )
        for binary, argv in candidates:
            if not shutil.which(binary):
                continue
            try:
                proc = subprocess.run(
                    argv,
                    input=text.encode("utf-8"),
                    stderr=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    timeout=2,
                    check=False,
                )
                if proc.returncode == 0:
                    return True
            except (subprocess.SubprocessError, OSError):
                continue
        return False

    # ── Health & reporting ───────────────────────────────────────────

    def _show_health(self) -> None:
        """Inline health summary — fast, no disk writes."""
        s = self.status
        if s.system is None:
            self._write_meta("[yellow]system metrics not ready yet — try again in a few seconds[/yellow]")
            return
        sys_ = s.system
        self._write_meta("[dim]── health ──[/dim]")
        self._write_meta(
            f"  daemon: {'[green]● active[/green]' if s.daemon_active else '[red]○ inactive[/red]'}  ·  "
            f"halt: {'[red]◊ TRIPPED[/red]' if s.halt else '[green]clear[/green]'}"
        )
        self._write_meta(
            f"  cpu: [cyan]{sys_.cpu_percent:.1f}%[/cyan]  "
            f"load: [cyan]{sys_.load_1m:.2f} {sys_.load_5m:.2f} {sys_.load_15m:.2f}[/cyan]  "
            f"({sys_.cpu_count} cores)"
        )
        from .sysmon import fmt_bytes, fmt_duration
        self._write_meta(
            f"  mem: [cyan]{sys_.mem_percent:.1f}%[/cyan]  "
            f"{fmt_bytes(sys_.mem_used)} of {fmt_bytes(sys_.mem_total)}"
        )
        self._write_meta(
            f"  disk: [cyan]{sys_.disk_percent:.1f}%[/cyan]  "
            f"{fmt_bytes(sys_.disk_free)} free of {fmt_bytes(sys_.disk_total)}"
        )
        if s.vram_total_mb and s.vram_used_mb is not None:
            vram_pct = 100.0 * s.vram_used_mb / s.vram_total_mb
            self._write_meta(
                f"  vram: [cyan]{vram_pct:.1f}%[/cyan]  "
                f"{s.vram_used_mb} / {s.vram_total_mb} MB  [dim]({s.vram_source})[/dim]"
            )
        self._write_meta(f"  uptime: [cyan]{fmt_duration(sys_.uptime_seconds)}[/cyan]")

    def _save_report(self) -> None:
        """Full health report — printed in chat and saved to disk for sharing."""
        s = self.status
        if s.system is None:
            self._write_meta("[yellow]system metrics not ready yet — try again in a few seconds[/yellow]")
            return

        now = datetime.now(timezone.utc)
        now_iso = now.strftime("%Y-%m-%d %H:%M UTC")

        report = render_health_report(
            s.system,
            version=s.version,
            halt=s.halt,
            daemon_active=s.daemon_active,
            ledger_ok=s.ledger_clean,
            ledger_rows=s.ledger_rows,
            snapshot_age_seconds=s.snapshot_age_seconds,
            snapshot_verify_ok=s.snapshot_verify_ok,
            vram_total_mb=s.vram_total_mb,
            vram_used_mb=s.vram_used_mb,
            vram_source=s.vram_source,
            now_iso=now_iso,
        )

        # Render to chat as a fenced code block (preserves spacing).
        self._write_meta("[dim]── health report ──[/dim]")
        if self._chat_log is not None:
            for line in report.splitlines():
                # Escape any stray rich tags in user-facing strings.
                self._chat_log.write(line.replace("[", "\\["))

        # Save to a timestamped file under data_dir/reports/
        try:
            data_dir = self._resolve_data_dir()
            if data_dir is None:
                self._write_meta("[dim]report not saved: data dir unavailable[/dim]")
                return
            reports_dir = data_dir / "reports"
            reports_dir.mkdir(parents=True, exist_ok=True)
            fname = f"health-{now.strftime('%Y%m%d-%H%M%S')}.txt"
            path = reports_dir / fname
            path.write_text(report + "\n", encoding="utf-8")
            self._write_meta(f"[green]✓[/green] saved → [cyan]{path}[/cyan]")
        except Exception as exc:  # noqa: BLE001
            self._write_meta(f"[red]✗ save failed: {exc!r}[/red]")

    # ── Chat rendering helpers ───────────────────────────────────────

    def _resolve_transcript_path(self) -> Path:
        """Where the transcript log lives. Lazily resolved so the
        config dir is established first (init-on-first-write)."""
        if self._transcript_path is not None:
            return self._transcript_path
        try:
            from sovereign_agent.config import SETTINGS
            base = SETTINGS.paths.data_dir
        except Exception:  # noqa: BLE001
            base = Path.home() / ".local" / "share" / "sovereign-agent"
        path = base / "cockpit-transcript.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        self._transcript_path = path
        return path

    def _record(self, speaker: str, text: str) -> None:
        """Append one chat line to the in-memory buffer and the disk
        transcript. Both are best-effort — a failed disk write must
        not break the cockpit's UI flow.

        v0.2.20.1: this was added after a soul-poured introduction
        was visible on screen yet effectively unrecoverable because
        the RichLog widget doesn't support text selection and no
        transcript existed on disk.
        """
        self._transcript.append((speaker, text))
        # Bound the in-memory buffer so a long-running session doesn't
        # accumulate forever. 2000 lines is a comfortable upper bound
        # for /copy-all to be useful.
        if len(self._transcript) > 2000:
            self._transcript = self._transcript[-2000:]
        try:
            path = self._resolve_transcript_path()
            ts = _now_short()
            line = f"[{ts}] {speaker}: {text}\n"
            with path.open("a", encoding="utf-8") as f:
                f.write(line)
        except OSError:
            # Disk full, permission denied, etc. — the in-memory copy
            # still exists for /copy this session; nothing to surface.
            pass

    def _write_you(self, text: str) -> None:
        if self._chat_log is None:
            return
        # `\[you]` escapes the brackets so Rich treats it as literal text,
        # not a markup tag. Colour is dark_orange — warm, distinct from
        # any status colour, and pretty against the surface tone.
        self._chat_log.write(
            f"[bold dark_orange]\\[you][/bold dark_orange] {text}"
        )
        self._record("you", text)

    def _write_aria_thinking(self) -> None:
        if self._chat_log is None:
            return
        # Aria's name is bright_blue — a clean, steady, trustworthy hue.
        self._chat_log.write(
            "[bold bright_blue]\\[aria][/bold bright_blue] "
            "[dim]thinking ...[/dim]"
        )
        # Don't record "thinking ..." in the transcript — it's a
        # transient indicator, not a turn.

    def _write_aria(self, text: str) -> None:
        if self._chat_log is None:
            return
        self._chat_log.write(f"  {text}")
        self._record("aria", text)

    def _show_palette_legend(self) -> None:
        """Print a legend of every palette button — its command and what it
        does — to the chat log. So you can read before you click. (`/palette`)"""
        from rich.markup import escape
        if self._chat_log is None:
            return
        self._chat_log.write("[b]◊ command palette — what each button does[/b]")
        self._chat_log.write(
            "[dim]click a button to paste its command (you review, then Enter). "
            "hover a button to see this same note as a tooltip.[/dim]")
        for pc in PALETTE_COMMANDS:
            self._chat_log.write(
                f"  [b]{escape(pc.label)}[/b]  [dim]{escape(pc.command)}[/dim]")
            if pc.desc:
                self._chat_log.write(f"      {escape(pc.desc)}")
        self._chat_log.write("")
        self._record("meta", "palette legend shown")

    def _write_meta(self, text: str) -> None:
        if self._chat_log is None:
            return
        self._chat_log.write(text)
        self._record("meta", text)

    # ── Memory pane refresh (v0.2.25.0) ──────────────────────────────

    def _refresh_inbox_pane(self) -> None:
        """Update the inbox pane (the 4th window) with Aria's collaboration
        requests, with context.

        Open items (most urgent first) carry their why/when/tags. Anything
        scheduled whose time has come surfaces under '⏰ due to revisit'. A
        'recent' section shows closed history with status markers, so
        scrolling up shows the whole story. Read-only; degrades silently.
        """
        if self._inbox_log is None:
            return
        try:
            from rich.markup import escape
            from sovereign_agent.config import SETTINGS
            from sovereign_agent.persistence.store import ErebloStore
            from sovereign_agent.workflow.requests import RequestStore
            rs = RequestStore(ErebloStore(SETTINGS.paths.atoms_db))
            open_items = rs.list_open()
            due_items = rs.due()
            recent = rs.list(limit=40)
        except Exception as exc:  # noqa: BLE001
            self._inbox_log.clear()
            self._inbox_log.write(
                f"[dim](inbox unavailable: {type(exc).__name__})[/dim]")
            return

        self._inbox_log.clear()
        n_open = len(open_items)
        if n_open:
            self._inbox_log.write(f"[bold]◊ {n_open} waiting on you[/bold]")
        else:
            self._inbox_log.write("[dim]◊ inbox clear 📭[/dim]")
        self._inbox_log.write("")

        # Open requests — what needs attention now, with context.
        for r in open_items:
            pri = f"{r.priority_emoji} " if r.priority != "normal" else ""
            self._inbox_log.write(
                f"{r.emoji} {pri}[bold]{escape(r.title)}[/bold]  "
                f"[dim][{r.short_id}][/dim]")
            for line in r.context_lines():
                self._inbox_log.write(f"   [dim]{escape(line)}[/dim]")
        if open_items:
            self._inbox_log.write("")

        # Scheduled work whose time has come.
        if due_items:
            self._inbox_log.write("[bold yellow]⏰ due to revisit[/bold yellow]")
            for r in due_items:
                self._inbox_log.write(
                    f"  {r.status_emoji} {r.emoji} [dim]{escape(r.title)}[/dim]")
            self._inbox_log.write("")

        # Recent history with status markers (scroll up to see it all).
        closed = [r for r in recent if r.status not in ("open",)]
        if closed:
            self._inbox_log.write("[bold cyan]recent[/bold cyan]")
            for r in closed[:20]:
                self._inbox_log.write(
                    f"  {r.status_emoji} {r.emoji} [dim]{escape(r.title)}[/dim]")

    def _refresh_memory_pane(self) -> None:
        """Update the memory pane with current state.

        This is the live view Kevin asked for — always-on visibility
        into where Aria's most valuable memories are stored. Refreshed
        on a 15s timer plus on explicit demand.

        Read-only; never blocks the cockpit. Failures degrade silently
        to a meta line in the pane.
        """
        if self._memory_log is None:
            return
        try:
            from sovereign_agent.config import SETTINGS
            from sovereign_agent.stewardship.memory_garden import survey_memory
            health = survey_memory(SETTINGS.paths.data_dir)
        except Exception as exc:  # noqa: BLE001
            self._memory_log.clear()
            self._memory_log.write(
                f"[dim](memory survey unavailable: {type(exc).__name__})[/dim]"
            )
            return

        self._memory_log.clear()

        # Section: total memories with the reorganization signal
        total = health.total_memories
        reorg_mark = ""
        if total >= 1000:
            reorg_mark = "  [yellow]◊ ready to tend[/yellow]"
        self._memory_log.write(
            f"[bold]◊ total: {total}[/bold]{reorg_mark}"
        )
        self._memory_log.write("")

        # Section: pattern self-perception (the most valuable signal)
        self._memory_log.write(
            f"[bold cyan]patterns[/bold cyan]"
        )
        self._memory_log.write(
            f"  [yellow]✦[/yellow] valuable: {health.patterns_valuable}"
        )
        self._memory_log.write(
            f"  ● active:   {health.patterns_active}"
        )
        if health.patterns_dormant:
            self._memory_log.write(
                f"  [dim]○ dormant:  {health.patterns_dormant}[/dim]"
            )
        self._memory_log.write("")

        # Section: atoms (Aria's distilled knowledge about Kevin)
        self._memory_log.write(
            f"[bold cyan]atoms[/bold cyan]"
        )
        self._memory_log.write(
            f"  ◊ active: {health.atoms_active}"
        )
        if health.atoms_total > health.atoms_active:
            superseded = health.atoms_total - health.atoms_active
            self._memory_log.write(
                f"  [dim]⊘ superseded: {superseded}[/dim]"
            )
        self._memory_log.write("")

        # Section: honor + field notes (cross-cutting witness threads)
        self._memory_log.write(
            f"[bold cyan]witness[/bold cyan]"
        )
        self._memory_log.write(
            f"  [red]♥[/red] honor:       {health.honor_notes}"
        )
        self._memory_log.write(
            f"  ·  field-notes: {health.field_notes}"
        )
        self._memory_log.write("")

        # Section: substrate
        self._memory_log.write(
            f"[bold cyan]substrate[/bold cyan]"
        )
        self._memory_log.write(
            f"  → interpretations: {health.provenance_entries}"
        )
        if health.corrections:
            self._memory_log.write(
                f"  ✎ corrections:     {health.corrections}"
            )
        self._memory_log.write("")

        # Section: hot channels (where things accumulate)
        if health.hot_channels:
            self._memory_log.write(
                f"[bold cyan]hot channels[/bold cyan]"
            )
            for ch, count in health.hot_channels[:5]:
                self._memory_log.write(
                    f"  [dim]{count:3d}[/dim]  {ch}"
                )
            self._memory_log.write("")

        # Section: where things live (so Kevin and Aria both know)
        try:
            data_dir = SETTINGS.paths.data_dir
            self._memory_log.write(
                f"[bold cyan]storage[/bold cyan]"
            )
            self._memory_log.write(
                f"  [dim]{data_dir}[/dim]"
            )
        except Exception:  # noqa: BLE001
            pass

    def _notify_memory_changed(self) -> None:
        """Call this after a write that should be reflected in the
        memory pane immediately rather than waiting for the timer.

        Wired into: honor.append, atom store append, pattern store
        append. Non-blocking; uses call_after_refresh to avoid
        re-entering Textual's event loop synchronously."""
        try:
            self.call_after_refresh(self._refresh_memory_pane)
        except Exception:  # noqa: BLE001
            pass


# ─── Entry point ────────────────────────────────────────────────────────────


def run() -> None:
    """Launch the cockpit. Called from cli.cockpit."""
    app = CockpitApp()
    app.run()


if __name__ == "__main__":
    run()
