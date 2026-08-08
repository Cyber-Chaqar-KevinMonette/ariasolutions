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
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import (
    Grid,
    Horizontal,
    HorizontalScroll,
    Vertical,
    VerticalScroll,
)
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    RichLog,
    Rule,
    Static,
)

from .. import __version__
from .sysmon import (
    SystemMonitor,
    SystemSnapshot,
    render_compact_metrics,
    render_health_report,
)

# v0.2.45 — the rippling outer frame. A glow travels around the whole #main
# perimeter (and, opt-in, around GlyphStage borders). Import-guarded so a
# Textual-less environment or a render-engine hiccup can never block the
# cockpit; compose() falls back to a plain Horizontal if it's unavailable.
try:
    from .ripple_border import (
        RIPPLE_BUSY,
        RIPPLE_HALT,
        RIPPLE_IDLE,
        RIPPLE_NEWS,
        RippleBorderMixin,
        RippleFrame,
    )
except Exception:  # pragma: no cover — ripple frame is strictly optional
    RippleFrame = None  # type: ignore[assignment]
    RippleBorderMixin = object  # type: ignore[assignment,misc]
    RIPPLE_IDLE = RIPPLE_BUSY = RIPPLE_NEWS = RIPPLE_HALT = None  # type: ignore[assignment]

try:
    from .recorder import FrameRecorder
except Exception:  # pragma: no cover — recorder is strictly optional
    FrameRecorder = None  # type: ignore[assignment]

# v0.2.41 "Cosmic Fitness" — the visual-systems gym. Import-safe (no Textual
# at import time, no heavy deps). Guarded so a failure here can never block
# the cockpit; the button + picker simply won't wire up if it's unavailable.
try:
    from . import cosmic_fitness as _cf
except Exception:  # pragma: no cover — cosmic fitness is strictly optional
    _cf = None

try:
    from .apply_queue_screen import ApplyQueueScreen  # apply-queue-import-d
except Exception:  # pragma: no cover — apply queue is strictly optional
    ApplyQueueScreen = None  # type: ignore[assignment,misc]

try:  # capability-test-menu-d
    from .capability_test_screen import CapabilityTestScreen
except Exception:  # pragma: no cover — capability test menu is strictly optional
    CapabilityTestScreen = None  # type: ignore[assignment,misc]

try:  # command-menu-d
    from .command_palette_screen import CommandPaletteScreen
except Exception:  # pragma: no cover — command palette popup is strictly optional
    CommandPaletteScreen = None  # type: ignore[assignment,misc]

try:  # paste-plus-d
    from .paste_preview_screen import PastePreviewScreen
except Exception:  # pragma: no cover — paste preview is strictly optional
    PastePreviewScreen = None  # type: ignore[assignment,misc]

try:  # theme-picker-d — restores an in-TUI theme switcher (see module docstring)
    from .theme_picker_screen import ThemePickerScreen
except Exception:  # pragma: no cover — theme picker is strictly optional
    ThemePickerScreen = None  # type: ignore[assignment,misc]

try:  # menu-split-d — the top-left gear's Settings & Help menu
    from .settings_menu_screen import SettingsMenuScreen
except Exception:  # pragma: no cover — strictly optional
    SettingsMenuScreen = None  # type: ignore[assignment,misc]

try:  # menu-split-d — the Controls reference (replaces the footer key row)
    from .controls_screen import ControlsScreen
except Exception:  # pragma: no cover — strictly optional
    ControlsScreen = None  # type: ignore[assignment,misc]

try:  # tier-d (F4, 2026-07-19) — trust-tier menu + kill switch
    from .tier_screen import TierScreen
except Exception:  # pragma: no cover — strictly optional
    TierScreen = None  # type: ignore[assignment,misc]

try:  # menu-split-d — the Changelog / What's New viewer
    from .changelog_screen import ChangelogScreen
except Exception:  # pragma: no cover — strictly optional
    ChangelogScreen = None  # type: ignore[assignment,misc]

try:  # resume-menu-d — the beautiful "pick a session to resume" menu
    from .resume_menu_screen import ResumeMenuScreen
except Exception:  # pragma: no cover — strictly optional
    ResumeMenuScreen = None  # type: ignore[assignment,misc]

try:  # j-space-d — the J-Space (reflective, two-way journal)
    from .journal_screen import JournalScreen
except Exception:  # pragma: no cover — strictly optional
    JournalScreen = None  # type: ignore[assignment,misc]

try:  # sprint-mode-d — the model configuration menu (Standard/presets/custom slots)
    from .model_menu_screen import ModelMenuScreen
except Exception:  # pragma: no cover — strictly optional
    ModelMenuScreen = None  # type: ignore[assignment,misc]

try:  # theme-studio-d — browse/create/edit/remove custom themes
    from .theme_studio_screen import ThemeStudioScreen
    from .theme_creator_screen import ThemeCreatorScreen
except Exception:  # pragma: no cover — strictly optional
    ThemeStudioScreen = None  # type: ignore[assignment,misc]
    ThemeCreatorScreen = None  # type: ignore[assignment,misc]

try:  # bot-studio-d — define bot projects (name/kind/concept)
    from .bot_studio_screen import BotStudioScreen
except Exception:  # pragma: no cover — strictly optional
    BotStudioScreen = None  # type: ignore[assignment,misc]

try:  # shop-studio-d — manage sellable products / subscriptions
    from .shop_studio_screen import ShopStudioScreen
except Exception:  # pragma: no cover — strictly optional
    ShopStudioScreen = None  # type: ignore[assignment,misc]

try:  # game-studio-d — define game projects (name/genre/concept), set focus
    from .game_studio_screen import GameStudioScreen
except Exception:  # pragma: no cover — strictly optional
    GameStudioScreen = None  # type: ignore[assignment,misc]

try:  # movie-studio-d — define movie projects, storyboards, pitches, focus
    from .movie_studio_screen import MovieStudioScreen
except Exception:  # pragma: no cover — strictly optional
    MovieStudioScreen = None  # type: ignore[assignment,misc]

try:  # movie-focus-d — the ✦ movie split-pane command center
    from .movie_pane import MoviePane
except Exception:  # pragma: no cover — strictly optional
    MoviePane = None  # type: ignore[assignment,misc]

try:  # screen-studio-d — Kevin's manual recording/screenshot studio
    from .screen_studio_pane import ScreenStudioPane
except Exception:  # pragma: no cover — strictly optional
    ScreenStudioPane = None  # type: ignore[assignment,misc]

try:  # game-pane-d — Godot toolset quick actions for the focused project
    from .game_pane import GamePane
except Exception:  # pragma: no cover — strictly optional
    GamePane = None  # type: ignore[assignment,misc]

try:  # key-vault-d — hand her credentials, safely (masked, 0600, local)
    from .credentials_screen import CredentialsScreen
except Exception:  # pragma: no cover — strictly optional
    CredentialsScreen = None  # type: ignore[assignment,misc]

try:  # discord-watch-d — watch her work Discord, live
    from .discord_watch_screen import DiscordWatchScreen
except Exception:  # noqa: BLE001 — cockpit must boot even if this breaks
    DiscordWatchScreen = None

try:  # verify-d — watch HOW she gathers + grounded-truth proof
    from .scout_trace_screen import ScoutTraceScreen
except Exception:  # noqa: BLE001
    ScoutTraceScreen = None

try:  # timers-d — every live countdown, visible
    from .timers_screen import TimersScreen
except Exception:  # pragma: no cover — strictly optional
    TimersScreen = None  # type: ignore[assignment,misc]

try:  # discord-control-d — turn off/pause/resume/restart the Discord bot
    from .discord_control_screen import DiscordControlScreen
except Exception:  # pragma: no cover — strictly optional
    DiscordControlScreen = None  # type: ignore[assignment,misc]

try:  # suggestions-d — grounded "what should I work on next?" list
    from .suggestions_screen import SuggestionsScreen
except Exception:  # pragma: no cover — strictly optional
    SuggestionsScreen = None  # type: ignore[assignment,misc]

try:  # task-guide-d — the grounded "everything you can do with her" menu
    from .task_guide_screen import TaskGuideScreen
except Exception:  # pragma: no cover — strictly optional
    TaskGuideScreen = None  # type: ignore[assignment,misc]

try:  # stripe-links-d (Kevin, 2026-07-26) — the Stripe Links Vault
    from .stripe_links_screen import StripeLinksScreen
except Exception:  # pragma: no cover — strictly optional
    StripeLinksScreen = None  # type: ignore[assignment,misc]

try:  # source-toggle-d (Kevin, 2026-07-27) — the Sources Control Panel
    from .sources_control_screen import SourcesControlScreen
except Exception:  # pragma: no cover — strictly optional
    SourcesControlScreen = None  # type: ignore[assignment,misc]

logger = logging.getLogger(__name__)

# security-strip-wire-d — process-wide Tier-A scanner cache for the security strip.
# Module-level, not per-instance: the scan result describes live src/ on
# disk, not anything specific to one CockpitApp — sharing it means every
# cockpit instance in the process (normally just one; several in the test
# suite, which boots many short-lived instances back to back) reads the
# same cache and, critically, only ever runs ONE scan thread process-wide
# at a time, instead of each instance spawning its own competing thread.
_SECURITY_SCAN_CACHE: dict | None = None
_SECURITY_SCAN_LOCK = threading.Lock()
_SECURITY_SCAN_RUNNING = False

# vessel-health-d — process-wide cache for the vessel-health strip's kernel-
# coherence component (H2's clause-citation scan, same ~3s-over-~450-files
# cost class as J's Tier-A scan_tree() above). Same discipline as
# _SECURITY_SCAN_CACHE: module-level, not per-instance, and only ever
# triggered by the periodic timer, never eagerly on mount — see that
# cache's own docstring for the full 3-iteration regression story this
# mirrors rather than repeats.
_VESSEL_KERNEL_CACHE: dict | None = None
_VESSEL_KERNEL_LOCK = threading.Lock()
_VESSEL_KERNEL_RUNNING = False
_AUTO_BACKUP_LOCK = threading.Lock()  # auto-backup-d
_AUTO_BACKUP_RUNNING = False  # auto-backup-d
# worker-watch-d — supervision state for the persistent cockpit loops.
_WATCHED_WORKER_GROUPS = frozenset({"heart", "breathe", "status", "events"})
_WORKER_RESPAWNS: dict[str, int] = {}
_DEAD_WORKERS: set[str] = set()
_MAX_WORKER_RESPAWNS = 2
from . import run_surface as _run_surface  # run-surface-d
_RUN_STATE = _run_surface.RunState()  # run-surface-d

# replay-sanitize-d (Kevin's screenshot, 2026-07-19): sealed chunks store
# RENDERED markup verbatim, so replaying them escaped showed literal
# [dim]..[/dim] AND revived pre-ban U+25C8 diamonds from old sessions. This
# display-side sanitizer strips lowercase Rich style tags (uppercase
# bracket ids like [HH852Q] survive) and purges every banned diamond.
# The sealed chunks themselves stay verbatim — by design.
def sanitize_replay_text(raw: str) -> str:
    import re as _re

    from sovereign_agent.glyphs import purge_unsafe_diamonds as _purge

    raw = _re.sub(r"\[/?[a-z][a-z0-9 _#=.'\"-]*\]", "", raw)
    return _purge(raw)


# copy-pane-d (F7): /copy <pane> → the RichLog attribute for each window
_PANE_LOGS: dict[str, str] = {
    "live": "_events_log", "events": "_events_log",
    "atelier": "_atelier_log", "work": "_atelier_log",
    "memory": "_memory_log", "inbox": "_inbox_log",
    "chat": "_chat_log",
}


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
    # command-menu-d — sentinels was missing entirely (gap-audit finding)
    "sentinels",
    # Top-level commands with explicit names
    "ask", "config", "continue", "do", "drain-by-model", "info",
    "pause", "plan", "resume", "retrieve",
    # Top-level commands using the function-name default
    "approvals", "approve", "aria", "busy", "cockpit", "deny", "disarm",
    "doctor", "events", "halt", "horizon", "init", "lessons", "run",
    "seal", "status", "tail", "until", "verify",
})


def normalize_sov_prefix(text: str) -> NormalizedInput | None:
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


@dataclass
class CockpitStatus:
    """Single snapshot of system state for the status bar."""
    halt: bool = False
    daemon_active: bool = False
    ledger_clean: bool = True
    ledger_rows: int = 0
    snapshot_age_seconds: float | None = None
    snapshot_verify_ok: bool = True
    version: str = field(default_factory=lambda: __version__)
    mood: str = "calm"
    # System metrics (set by SystemMonitor.read())
    system: SystemSnapshot | None = None
    # VRAM (set by sovereign_agent.vram.read_vram())
    vram_total_mb: int | None = None
    vram_used_mb: int | None = None
    vram_source: str = ""
    vram_temp_c: float | None = None
    # Sentinel health summary (added by aria-cockpit-vitality)
    sentinel_ok: int = 0
    sentinel_total: int = 0
    sentinel_errors: int = 0
    # apply-queue-status-d — staged-vs-queued-vs-applied counts, so the
    # backlog that hit 31 unreviewed modules can't silently pile up unseen
    # again. Populated in the same 5s background pass as everything else
    # above — never rescanned from _render_status_bar() itself.
    staged_pending: int = 0
    queued_count: int = 0
    # anti-lag-d — the full per-sentinel health list, gathered once in the
    # background thread and reused by _check_sentinel_transitions so it is
    # never re-gathered synchronously on the main UI thread.
    sentinel_healths: list = field(default_factory=list)
    # anti-lag-d (round 2) — the vessel rollup and emotion snapshot, also
    # computed in the SAME background pass. Before this, the 8s strip timers
    # re-ran a full sentinel gather (observability strip), a SECOND full
    # gather (vessel strip, via gather_vessel_health), and an events.jsonl
    # disk read (emotions strip) — all synchronously on the main UI thread,
    # every 8 seconds, growing heavier with every sentinel added by every
    # round. That accumulation, not the ripple animation, is what turned
    # "was never laggy before" into "lags now": the strips now render from
    # this snapshot and do zero I/O of their own.
    vessel_report: object | None = None
    emotion_mood: str = ""
    emotion_focus: float = 0.0
    emotion_care: float = 0.0
    # vitality-status-d


# ─── Help overlay ───────────────────────────────────────────────────────────


class HelpScreen(ModalScreen):
    """F1 → modal with keybindings and routing reference."""

    BINDINGS = [Binding("escape,q", "close_help", "close")]

    def action_close_help(self) -> None:
        self.app.pop_screen()

    def on_key(self, event) -> None:
        # Bulletproof exit. Esc or q always closes help, even if a focus or
        # binding quirk would otherwise swallow it. (F1 is handled by the
        # app's toggle so pressing it again here also closes.) Every other
        # key falls through, so the content can still scroll.
        if event.key in ("escape", "q"):
            event.stop()
            event.prevent_default()
            self.app.pop_screen()

    def on_button_pressed(self, event) -> None:
        # The Close button — the no-keyboard-needed escape hatch.
        event.stop()
        self.app.pop_screen()

    def compose(self) -> ComposeResult:
        with Vertical(id="help-modal"):
            with VerticalScroll(id="help-scroll"):
                yield Static(
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
                "  Two buttons open / run her newest surfaces:\n"
                "    [b]▸ flows[/b]  — the workflows catalog: every workflow she can\n"
                "      do + exactly how to drive it (also [dim]/workflows[/dim]).\n"
                "    [b]✦ demo[/b]   — a bounded, observable live demonstration that\n"
                "      proves she is valid in ~1-2 min (also [dim]/demo[/dim]). It runs\n"
                "      each core workflow for real in an isolated sandbox, honours\n"
                "      HALT, and never touches her code or values.\n\n"
                "[b]Slash commands (operator overrides)[/b]\n"
                "  /cancel         abort the running directive\n"
                "  /halt           PROTOCOL-ZERO\n"
                "  /disarm         clear PROTOCOL-ZERO\n"
                "  /snap [label]   take a snapshot\n"
                "  /audit          run financial audit\n"
                "  /events [N]     dump latest N events to chat\n"
                "  /palette        what every palette button does\n"
                "  /workflows      open the workflows catalog (what she can do + how)\n"
                "  /demo           run a bounded live demonstration of her workflows\n\n[bold]display[/bold]\n  Ctrl++  /  Ctrl+-     adjust font size (fixes ripple border glitches)\n  if white lines appear on the border: press Ctrl++ or Ctrl+- a few\n  times to recalibrate the cell renderer. usually 2-3 presses is enough.\n  # # vitality-help-d\n"
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
                "[dim]close: press Esc, press q, or click Close below[/dim]",
                id="help-content",
                )
            yield Button("✕  Close   (Esc / q)", id="help-close", variant="primary")

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
    #help-scroll {
        height: auto;
        max-height: 80%;
    }
    #help-close {
        margin: 1 0 0 0;
        width: 100%;
    }
    """


class WorkflowsScreen(ModalScreen):
    """▸ flows — the live workflows catalog.

    A scrollable, always-current guide to every workflow she can do and
    exactly how to drive each one with her. The content is rendered straight
    from workflow/catalog.py (the single source of truth), so it can never
    drift from what she actually does. Esc / q / Close to dismiss.
    """

    BINDINGS = [Binding("escape,q", "close_workflows", "close")]

    def action_close_workflows(self) -> None:
        self.app.pop_screen()

    def on_key(self, event) -> None:
        # Bulletproof exit: Esc or q always closes, every other key falls
        # through so the catalog can still scroll.
        if event.key in ("escape", "q"):
            event.stop()
            event.prevent_default()
            self.app.pop_screen()

    def on_button_pressed(self, event) -> None:
        # The Close button — the no-keyboard-needed escape hatch.
        event.stop()
        self.app.pop_screen()

    def compose(self) -> ComposeResult:
        # Render from the catalog. Defensive: never let a content error
        # leave the operator stuck on a blank modal.
        try:
            from ..workflow import catalog as _catalog
            body = _catalog.render_text(color=True)
        except Exception as exc:  # noqa: BLE001
            body = f"[red]workflows catalog unavailable: {exc!r}[/red]"
        with Vertical(id="workflows-modal"):
            with VerticalScroll(id="workflows-scroll"):
                yield Static(body, id="workflows-content")
            yield Button("✕  Close   (Esc / q)", id="workflows-close",
                         variant="primary")

    DEFAULT_CSS = """
    WorkflowsScreen {
        align: center middle;
        background: $surface 60%;
    }
    #workflows-modal {
        width: 86;
        height: auto;
        max-height: 90%;
        padding: 1 2;
        border: thick $primary;
        background: $surface;
    }
    #workflows-scroll {
        height: auto;
        max-height: 80%;
    }
    #workflows-close {
        margin: 1 0 0 0;
        width: 100%;
    }
    """


# ─── Cosmic Fitness (v0.2.41) ───────────────────────────────────────────────
#
# The visual-systems gym. Two surfaces share one source of truth
# (cockpit/cosmic_fitness.py):
#
#   • GlyphButton          a tappable glyph; clicking drops it in the input.
#   • CosmicFitnessScreen  the F-tester modal: a fitness verdict, the live
#                          special-effects showcase, and the full glyph
#                          inventory (every glyph colour-coded by width-
#                          safety, click-to-insert). Opened by the
#                          "◊ cosmic" reference button or /cosmic.
#   • the inline picker    a compact, always-near-the-input strip toggled by
#                          Ctrl-G or /pick (built in CockpitApp.compose).
#
# Width discipline is honoured throughout: glyphs render in their own button
# cells / flowing text, never inside a width-counted box layout, so showing
# even the wide colour emoji here can't corrupt anything.


class GlyphButton(Button):
    """A clickable glyph. Carries its GlyphSpec; clicking inserts the char.

    The label is normally the glyph itself. A status-coloured CSS class gives
    an at-a-glance read of width-safety; the tooltip carries the full detail.

    ``safe_display``: when True (used in the width-counted inventory grid), a
    glyph that is NOT layout-safe (emoji/wide/composite) is shown as its small
    status BADGE rather than the raw glyph. This is the cockpit's own law
    applied to the tester: rendering a width-unstable glyph inside a counted
    grid is exactly what nudges borders on a terminal that draws it wider than
    Textual's model expects. The real glyph still rides in the tooltip and is
    what gets inserted on click — so it stays one tap from your message, where
    flowing text handles it fine.

    ``in_modal`` distinguishes the two homes so DOM ids stay unique.
    """

    def __init__(self, spec, *, in_modal: bool = False,
                 safe_display: bool = False) -> None:
        self.spec = spec
        self.in_modal = in_modal
        layout_safe = spec.status in ("safe", "convention")
        self._badge_mode = bool(safe_display and not layout_safe)
        # Derive a DOM-safe, unique id from the codepoint(s).
        token = spec.codepoint.replace("U+", "").replace(" ", "_").lower()
        prefix = "mg" if in_modal else "pg"
        # In badge mode show the class badge (a safe glyph); else the real one.
        badge = "?"
        if _cf is not None:
            badge = _cf.STATUS_BADGE.get(spec.status, "?")
        label = badge if self._badge_mode else spec.char
        super().__init__(label, id=f"{prefix}-{token}")
        self.add_class("glyph-btn")
        self.add_class(f"gstatus-{spec.status}")
        if self._badge_mode:
            self.add_class("glyph-badged")
        blurb = ""
        if _cf is not None:
            blurb = _cf.STATUS_BLURB.get(spec.status, "")
        alt = (f"\nsafe variant: {spec.safe_alternative}"
               if getattr(spec, "safe_alternative", None) else "")
        shown = (f"\n[shown as {badge} — width-unstable, see above]"
                 if self._badge_mode else "")
        self.tooltip = (
            f"{spec.char}  {spec.label}\n"
            f"{spec.codepoint} · {spec.unicode_name}\n"
            f"{spec.status} — {blurb}{alt}{shown}\n"
            f"(click to insert the real glyph)"
        )


class CosmicFitnessScreen(ModalScreen):
    """The Cosmic Fitness tester + special-effects showcase + glyph picker."""

    BINDINGS = [Binding("escape,q", "close_cosmic", "close")]

    def action_close_cosmic(self) -> None:
        self.app.pop_screen()

    def on_key(self, event) -> None:
        # Bulletproof exit (mirrors HelpScreen): Esc / q always closes.
        if event.key in ("escape", "q"):
            event.stop()
            event.prevent_default()
            self.app.pop_screen()

    def on_button_pressed(self, event) -> None:
        event.stop()
        button = event.button
        if isinstance(button, GlyphButton):
            # Insert into the input and close so the operator immediately
            # sees it land. The inline picker (Ctrl-G) is the stay-open one.
            try:
                self.app._insert_glyph(button.spec.char)
            except Exception:  # noqa: BLE001
                pass
            self.app.pop_screen()
            return
        # Any other button in here is the Close button.
        self.app.pop_screen()

    def compose(self) -> ComposeResult:
        with Vertical(id="cosmic-modal"):
            with VerticalScroll(id="cosmic-scroll"):
                yield Static(
                    "[b]\u25ca Cosmic Fitness[/b]  "
                    "[dim]Aria's visual-systems gym[/dim]",
                    id="cosmic-title",
                )

                # ── Fitness verdict ───────────────────────────────────────
                if _cf is not None:
                    try:
                        report = _cf.run_cosmic_fitness(include_scan=True)
                        for line in report.render_lines():
                            yield Static(line, classes="cosmic-report-line")
                    except Exception as exc:  # noqa: BLE001
                        yield Static(
                            f"[yellow]fitness report unavailable: {exc!r}[/yellow]"
                        )
                else:
                    yield Static(
                        "[yellow]cosmic_fitness module unavailable — "
                        "showing nothing dynamic.[/yellow]"
                    )

                # ── Width legend ──────────────────────────────────────────
                yield Static(
                    "\n[b]how to read the colours[/b]\n"
                    "  [green]\u2713 safe[/green]        one cell everywhere — use anywhere\n"
                    "  [cyan]\u25ca convention[/cyan]  ambiguous but blessed-narrow — safe in practice\n"
                    "  [magenta]\u25c9 emoji[/magenta]       narrow by spec, 2 cells in most terminals — sandbox only\n"
                    "  [yellow]\u25b8 wide[/yellow]        two cells — lovely in chat, never in a layout glyph\n"
                    "  [red]\u2717 composite[/red]   multi-codepoint — terminal-dependent, avoid in the TUI",
                    classes="cosmic-legend",
                )

                # ── Special effects showcase ──────────────────────────────
                yield Static(
                    "\n[b]\u2726 god-tier special effects[/b]   "
                    "[dim]live — these are real, running right now[/dim]",
                    classes="cosmic-section",
                )
                yield from self._compose_effects()

                # ── Glyph animations showcase (v0.2.42) ───────────────────
                yield Static(
                    "\n[b]\u25c9 animated glyphs[/b]   "
                    "[dim]frame-cycling — also live[/dim]",
                    classes="cosmic-section",
                )
                yield from self._compose_animations()

                # ── Animated special effects showcase (v0.2.42) ───────────
                yield Static(
                    "\n[b]\u2726 animated special effects[/b]   "
                    "[dim]frames + glow/colour — the beating heart lives here[/dim]",
                    classes="cosmic-section",
                )
                yield from self._compose_animated_effects()

                # ── The sandbox (GlyphStage) demo ─────────────────────────
                yield Static(
                    "\n[b]\u25a3 the GlyphStage[/b]   "
                    "[dim]a bounded container for living glyphs — holding "
                    "width-stable ones here so the border stays put[/dim]",
                    classes="cosmic-section",
                )
                yield from self._compose_sandbox_demo()

                # ── Glyph inventory ───────────────────────────────────────
                yield Static(
                    "\n[b]\u25ca glyph inventory[/b]   "
                    "[dim]tap any glyph to drop the real character into your "
                    "message[/dim]\n"
                    "[dim]width-unstable glyphs (emoji/wide/composite) show "
                    "their class badge here — drawing them raw in this grid is "
                    "what nudges borders. The real glyph still inserts on tap, "
                    "and you can watch them live in the sandbox above.[/dim]",
                    classes="cosmic-section",
                )
                yield from self._compose_inventory()

            yield Button("\u2715  Close   (Esc / q)", id="cosmic-close",
                         variant="primary")

    # ── compose helpers ──────────────────────────────────────────────────

    def _compose_effects(self):
        """Yield a labelled, live row per special effect (guarded)."""
        if _cf is None:
            return
        try:
            from .breathing_glyph import BreathingBorder
        except Exception:  # noqa: BLE001 — Textual missing somehow
            BreathingBorder = None  # type: ignore
        for fx in _cf.special_effects():
            with Horizontal(classes="fx-row"):
                made = False
                if BreathingBorder is not None:
                    try:
                        length = fx.length if fx.kind == "ripple" else 10
                        step = fx.phase_step if fx.kind == "ripple" else 0.0
                        widget = BreathingBorder(
                            length=length,
                            glyph=fx.glyph,
                            config=fx.config,
                            base_hex=fx.base_hex,
                            bg_hex="#101018",
                            phase_step=step,
                            assume_width_safe=True,
                        )
                        widget.add_class("fx-live")
                        yield widget
                        made = True
                    except Exception:  # noqa: BLE001 — degrade to static
                        made = False
                if not made:
                    yield Static(fx.glyph * 10, classes="fx-live")
                yield Static(
                    f"[b]{fx.name}[/b] · [dim]{fx.tagline}[/dim]  "
                    f"[dim]\\[{fx.label}][/dim]\n{fx.description}",
                    classes="fx-desc",
                )

    def _compose_inventory(self):
        """Yield each category title + a grid of clickable GlyphButtons."""
        if _cf is None:
            return
        try:
            cats = _cf.curated_categories()
        except Exception:  # noqa: BLE001
            return
        for cat in cats:
            stable = sum(1 for s in cat.glyphs if s.status in ("safe", "convention"))
            unstable = len(cat.glyphs) - stable
            note = (f"  [dim]({stable} stable"
                    + (f", {unstable} badged" if unstable else "")
                    + ")[/dim]")
            yield Static(
                f"\n[b]{cat.name}[/b]  [dim]{cat.blurb}[/dim]{note}",
                classes="cat-title",
            )
            with Grid(classes="glyph-grid"):
                for spec in cat.glyphs:
                    yield GlyphButton(spec, in_modal=True, safe_display=True)

    def _compose_animations(self):
        """Yield a labelled live row per layout-safe animation."""
        if _cf is None:
            return
        try:
            from .animated_glyph import AnimatedGlyph
        except Exception:  # noqa: BLE001
            AnimatedGlyph = None  # type: ignore
        for an in _cf.animations():
            if not an.is_layout_safe:
                continue  # sandbox-only ones go in the GlyphStage demo below
            with Horizontal(classes="fx-row"):
                made = False
                if an.is_universal and AnimatedGlyph is not None:
                    try:
                        w = AnimatedGlyph(an)
                        w.add_class("anim-live")
                        yield w
                        made = True
                    except Exception:  # noqa: BLE001 — degrade to static
                        made = False
                if not made:
                    yield Static("\u25cc", classes="anim-live glyph-badged")
                tail = "" if an.is_universal else \
                    "  [dim](listed — ambiguous width)[/dim]"
                yield Static(
                    f"[b]{an.name}[/b] · [dim]{an.tagline}[/dim]  "
                    f"[dim]\\[{an.label}][/dim]{tail}\n{an.description}",
                    classes="fx-desc",
                )

    def _compose_animated_effects(self):
        """Yield a labelled live row per layout-safe animated effect."""
        if _cf is None:
            return
        try:
            from .animated_glyph import AnimatedEffect
        except Exception:  # noqa: BLE001
            AnimatedEffect = None  # type: ignore
        for ae in _cf.animated_effects():
            if not ae.is_layout_safe:
                continue  # sandbox-only (moon glow) shown in the stage demo
            with Horizontal(classes="fx-row"):
                made = False
                if ae.is_universal and AnimatedEffect is not None:
                    try:
                        w = AnimatedEffect(ae)
                        w.add_class("anim-live")
                        yield w
                        made = True
                    except Exception:  # noqa: BLE001
                        made = False
                if not made:
                    yield Static("\u25cc", classes="anim-live glyph-badged")
                tail = "" if ae.is_universal else \
                    "  [dim](listed — ambiguous width)[/dim]"
                yield Static(
                    f"[b]{ae.name}[/b] · [dim]{ae.tagline}[/dim]  "
                    f"[dim]\\[{ae.label}][/dim]{tail}\n{ae.description}",
                    classes="fx-desc",
                )

    def _compose_sandbox_demo(self):
        """Demonstrate the GlyphStage with width-STABLE living glyphs.

        Hard-won lesson (v0.2.44): a bounded container fully isolates the layout
        *outside* it, but it cannot perfectly contain a font-variable emoji's
        width on its own bordered line — when a terminal draws an emoji narrower
        (or wider) than Textual's model, that deficit propagates to the line's
        border no matter how much slack there is. So we never render font-
        variable emoji on a bordered, width-counted line. The stage here holds
        layout-safe animations (rock-steady on every terminal); the dancer and
        the moon live in your chat, where flowing text renders them free.
        """
        if _cf is None:
            return
        try:
            from .animated_glyph import AnimatedEffect, AnimatedGlyph
            from .glyph_stage import GlyphStage
        except Exception:  # noqa: BLE001
            GlyphStage = None  # type: ignore
            AnimatedGlyph = None  # type: ignore
            AnimatedEffect = None  # type: ignore

        if GlyphStage is None:
            yield Static("[dim](sandbox unavailable in this build)[/dim]")
            return

        # The stage holds only universal one-cell living glyphs — a braille
        # spinner, a block-shaded pulse, an aurora swatch — which render
        # identically on every terminal, so the border is rock-steady.
        try:
            # v0.2.46 — ripple_aurora=True: the stage's border is the Aurora
            # ripple — a full spectrum wrapped around it, rotating over time,
            # with the glow rippling on top. The aurora glyph's hue-cycle, made
            # into a frame, around the swatch that inspired it.
            stage = GlyphStage(cells=26, title="GlyphStage", ripple_aurora=True)
            with stage, Vertical(classes="sandbox-col"):
                if AnimatedGlyph is not None:
                    spinner = _cf.animation_by_key("spinner")
                    ring = _cf.animation_by_key("ring")
                    if spinner is not None:
                        with Horizontal(classes="sandbox-line"):
                            yield Static("spinner    ", classes="sandbox-cap")
                            yield AnimatedGlyph(spinner)
                    if ring is not None:
                        with Horizontal(classes="sandbox-line"):
                            yield Static("pulse      ", classes="sandbox-cap")
                            yield AnimatedGlyph(ring)
                if AnimatedEffect is not None:
                    aurora = _cf.animated_effect_by_key("aurora")
                    if aurora is not None:
                        with Horizontal(classes="sandbox-line"):
                            yield Static("aurora     ", classes="sandbox-cap")
                            yield AnimatedEffect(aurora)
                    # NB: the Aurora Heart (♥, hue-cycling) is a registered
                    # effect but is intentionally NOT rendered live here. ♥ is
                    # convention-tier (one cell in practice) but NOT *universal*
                    # — it's EAW-ambiguous — and every glyph animated live in
                    # this bordered modal must be universal so no terminal can
                    # shift a border (the v0.2.45 width law / modal test). It
                    # renders free in chat instead, like the moon and dancer.
        except Exception as exc:  # noqa: BLE001
            yield Static(f"[yellow]sandbox demo unavailable: {exc!r}[/yellow]")
            return
        yield Static(
            "[dim]↑ a GlyphStage holding width-stable living glyphs — the "
            "border never moves. Wide emoji and the dancer go in a stage too, "
            "but a counted, bordered line can't perfectly hold a glyph your "
            "terminal sizes unpredictably — so to see those, tap one in the "
            "inventory and watch it land in your message, where it renders "
            "free.[/dim]",
            classes="sandbox-note",
        )

    DEFAULT_CSS = """
    CosmicFitnessScreen {
        align: center middle;
        background: $surface 60%;
    }
    #cosmic-modal {
        width: 84;
        height: auto;
        max-height: 92%;
        padding: 1 2;
        border: thick $primary;
        background: $surface;
    }
    #cosmic-scroll {
        height: auto;
        max-height: 84%;
    }
    #cosmic-title {
        text-align: center;
        margin: 0 0 1 0;
    }
    .cosmic-report-line { height: auto; }
    .cosmic-legend {
        margin: 1 0 0 0;
        padding: 1 1;
        background: $panel;
        border: round $secondary;
    }
    .cosmic-section {
        margin: 1 0 0 0;
        color: $accent;
    }
    .cat-title { height: auto; }
    .fx-row {
        height: auto;
        margin: 0 0 1 0;
    }
    .fx-live {
        width: 20;
        content-align: left middle;
        padding: 0 1 0 0;
    }
    .fx-desc { width: 1fr; height: auto; }
    .anim-live {
        width: 4;
        content-align: left middle;
        color: $accent;
        padding: 0 1 0 0;
    }
    .sandbox-col { height: auto; }
    .sandbox-line { height: auto; }
    .sandbox-emoji { width: auto; height: 1; padding: 0 0 0 0; }
    .sandbox-cap { width: auto; height: 1; color: $text-muted; }
    .sandbox-note { height: auto; margin: 0 0 1 0; }
    #cosmic-modal .glyph-badged { text-style: dim; }
    .glyph-grid {
        grid-size: 5;
        grid-gutter: 0 1;
        grid-rows: 3;
        height: auto;
        margin: 0 0 1 0;
    }
    #cosmic-modal .glyph-btn {
        width: 1fr;
        min-width: 6;
        height: 3;
        border: round $primary 40%;
    }
    #cosmic-modal .glyph-btn:hover { border: round $accent; }
    #cosmic-close {
        margin: 1 0 0 0;
        width: 100%;
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
    `action`  — if set, clicking runs an internal cockpit action (e.g.
                "legend" or "help") instead of pasting `command`. These are
                the right-side reference buttons; they are NOT subprocess
                commands, so they live outside PALETTE_COMMANDS.
    """
    label: str
    command: str
    key: str
    desc: str = ""
    action: str = ""


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
                   "Parked work to revisit — deferred 💤, revisit 🔖, flagged 🚩"),
    PaletteCommand("caps",     "sov capabilities",                 "capabilities",
                   "Aria's subsystems — what she has and what's missing"),
    PaletteCommand("vault",    "sov vault status",                 "vault",
                   "Owner encryption vault status (never shows the key)"),
    # command-menu-d — 3 commands found missing by the palette gap-audit: each
    # was already a real, registered, safe `sov` command with zero
    # palette presence.
    PaletteCommand("sentinels", "sov sentinels scan",              "sentinels",
                   "Scan every registered sentinel — health status at a glance"),
    PaletteCommand("dreams",   "sov dream list",                   "dream-list",
                   "List all dream sessions (pre-approved safe subcommand)"),
    PaletteCommand("all-asks", "sov requests list --all",          "requests-all",
                   "Every request ever filed — full history, not just open"),
)


# Right-side reference buttons. These don't paste a command — clicking them
# runs an internal cockpit action. Kept OUT of PALETTE_COMMANDS so the
# palette-safety invariant (every palette command must be a safe `sov`
# subprocess) stays clean. Rendered right-aligned on the last palette row.
# menu-split-d \u2014 the help-ish reference buttons (cosmic / flows / legend /
# help) moved to the top-left Settings & Help menu so the bottom-left ⋮
# popup is System Commands only. What remains here are the operational
# "run something" actions, shown as a small actions section in the popup.
REFERENCE_BUTTONS: tuple[PaletteCommand, ...] = (
    # menu-split-2-d \u2014 Kevin's rule: the @ menu is Settings + Help ONLY;
    # the ⋮ commands popup is EVERYTHING ELSE. So the feature/action surfaces
    # (J-Space, resume, modes, observatory, cosmic, workflows, legend) live
    # here, not in the Settings menu \u2014 no redundancy between the two.
    PaletteCommand("\U0001F4CB apply queue", "", "apply-queue",  # apply-queue-refbtn-d
                   "Select staged modules to apply \u2014 writes a durable queue, "
                   "never touches src/ while the cockpit runs "
                   "(also Ctrl+Shift+A \u00b7 Esc to close).",
                   action="apply_queue"),
    PaletteCommand("bots", "", "bots",
                   "Bot Studio \u2014 define a Discord bot project (name/kind/concept).",
                   action="bots"),
    PaletteCommand("shop", "", "shop",
                   "Shop Studio \u2014 manage products/subscriptions + publish the storefront.",
                   action="shop"),
    PaletteCommand("keys", "", "keys",
                   "Key Vault \u2014 hand Aria her credentials safely (masked, local).",
                   action="keys"),
    PaletteCommand("\u25ca games", "", "games",  # command-menu-gap-d \u2014 action
                   # already wired (line ~4455) but had no palette entry at
                   # all, same discoverability gap Kevin hit for "model".
                   "Game Studio \u2014 define a game project, browse/edit/remove/focus.",
                   action="games"),
    # movies-archived-d (Kevin, 2026-08-01): "movie studio can be removed
    # for now mostly" / "archived" \u2014 pulled from the browsable palette so
    # it doesn't compete for attention; action_movie_studio(), /movies,
    # and the whole feature underneath are untouched and still reachable
    # by typing `/movies` directly. Restore this entry to bring it back.
    # header-reorg-d (Kevin, 2026-08-02): moved off the always-visible
    # header row into this popup \u2014 same actions, same /verb typed
    # commands, just not front-row real estate. action="discord-control"
    # (not "discord") since that key already means Discord Watch, a
    # different feature (action_discord_watch, above the "bots" entry).
    PaletteCommand("\u2756 discord control", "", "discord-control",
                   "Discord Control \u2014 pause/resume bots, webhooks, "
                   "server admin from one screen.",
                   action="discord-control"),
    PaletteCommand("\u2727 suggestions", "", "suggestions",
                   "What she could work on next \u2014 grounded in real "
                   "sentinel findings + unbuilt bot ideas.",
                   action="suggestions"),
    PaletteCommand("% guide", "", "task-guide",
                   "Task Guide \u2014 everything you can do with her, from "
                   "the real tool registry.",
                   action="task-guide"),
    PaletteCommand("$ stripe", "", "stripe-links",
                   "Stripe Links vault \u2014 every current payment link.",
                   action="stripe-links"),
    PaletteCommand("# sources", "", "sources-control",
                   "Sources control \u2014 toggle individual trackers "
                   "(e.g. Reddit) on/off.",
                   action="sources-control"),
    PaletteCommand("timers", "", "timers",
                   "Timers \u2014 presence, live tasks, bot uptimes, next polls, retries.",
                   action="timers"),
    PaletteCommand("\u2301 discord watch", "", "discord",
                   "Discord Watch \u2014 her live shift: everything she does and learns.",
                   action="discord"),
    PaletteCommand("\u25CA J-Space", "", "journal",
                   "Open the J-Space \u2014 her reflective, two-way journal.",
                   action="journal"),
    PaletteCommand("\u21BA resume", "", "resume",
                   "Resume a paused session (pick from a menu).",
                   action="resume"),
    PaletteCommand("@ session", "", "modes",  # session-setup-unify-d
                   "The unified session setup \u2014 mode (chat / work / auto), "
                   "trust tier, and any custom auto duration (1-12h), all in "
                   "one screen. Also the @ session button beside layout.",
                   action="modes"),
    PaletteCommand("\u25C9 observe", "", "observatory",
                   "Modes observability window.",
                   action="observatory"),
    PaletteCommand("\u25CA model", "", "model",  # sprint-mode-d
                   "Model configuration \u2014 Standard, a sprint preset, "
                   "or pick a model per slot (F8).",
                   action="model_menu"),
    PaletteCommand("\u25CA cosmic", "", "cosmic",
                   "Cosmic Fitness: test every glyph + see the special effects.",
                   action="cosmic"),
    PaletteCommand("\u25B8 flows", "", "workflows",
                   "Workflows: a live catalog of every workflow she can do.",
                   action="workflows"),
    PaletteCommand("legend", "", "legend",
                   "Show what every command does.", action="legend"),
    PaletteCommand("\u2022 rec", "", "rec",
                   "Start / stop a screen recording of the cockpit "
                   "(saved to the recordings folder · also Ctrl-R)",
                   action="record"),
    PaletteCommand("\u2022 grow", "", "grow",
                   "Start / stop a bounded self-practice session — she hardens "
                   "her calibration + flow for ~10 min, then auto-halts. "
                   "Fully observable; press again (or HALT) to stop. "
                   "Never modifies her code or values.",
                   action="grow"),
    PaletteCommand("\u2726 demo", "", "demo",
                   "Run a complete, bounded live demonstration of her core "
                   "workflows (~1-2 min) \u2014 proves she is valid. Fully "
                   "observable + sandboxed; honors the kill switch. Never "
                   "modifies her code or values.",
                   action="demo"),
    # glyph-fix-d (movie-focus-d regression pass, 2026-07-28): the lightning
    # bolt (\u26a1) tested as an UNSAFE Wide-property glyph via
    # unicodedata/glyphs.audit_string despite shipping \u2014 same class of bug
    # the discord button's own glyph-fix-d comment already flagged. Swapped
    # for the cataloged-safe four-pointed star.
    PaletteCommand("\u2726 test", "", "captest",
                   "Capability test menu \u2014 quick-test what she can "
                   "actually do (image gen, web search, tracker/bot "
                   "dry-runs, ...) live, one at a time or all at once. "
                   "Sandboxed artifacts, journal + report written after.",
                   action="captest"),
)


# memory-pane-live-d (Kevin, 2026-07-25): the real, live tools Aria has
# for writing to memory -- when any of these fires, the memory pane should
# refresh soon after instead of waiting for the 15s timer.
_MEMORY_WRITE_TOOLS: frozenset[str] = frozenset({
    "memory_write", "write_behavior_pattern", "write_honor_note",
    "honor_log_write",
})

# aria-xp-live-d (Kevin, 2026-07-25): "points for writing atoms, and
# points for storing valuable memories... points for using recalling
# valuable patterns if she needs to." Objective, deterministic, tool-call
# -shaped events auto-award; task_success/mistake are NOT here — those
# are judgment calls, exposed as tools (award_aria_xp) for Aria herself
# to call honestly, same discipline game_dev_xp.py already established.
_XP_AUTO_AWARD_TOOLS: dict[str, str] = {
    "memory_write": "memory_written",
    "write_behavior_pattern": "pattern_recognized",
    "read_behavior_patterns": "pattern_recalled",
}


# Aria-to-palette animation map: when Aria uses these tools, the matching  # cockpit-god-d
# palette button gets the aria-active CSS class for visual feedback.
_TOOL_BUTTON_MAP: dict[str, str] = {
    "aria_status":            "aria",
    "vessel_comfort":         "status",
    "mode_status":            "status",
    "read_session":           "info",
    "read_lessons":           "doctor",
    "session_resume_audit":   "requests",
    "read_checkpoints":       "requests",
    "list_objectives":        "parked",
    "get_emotions":           "aria",
    "emotion_report":         "aria",
    "research_queue":         "parked",
    "vision_capture":         "capabilities",
    "leverage_audit":         "parked",
    "session_brief_read":     "channels",
    "auto_status":            "status",
    "eval_score":             "aria",    # qol-tool-map-d
    "eval_session":           "aria",
    "eval_history":           "aria",
    "browser_navigate":       "capabilities",
    "browser_search":         "capabilities",
    "notify":                 "status",
    "session_brief_read":     "channels",
    "session_brief_write":    "channels",
    "log_experience":         "requests",
}


class MenuTriggerButton(RippleBorderMixin, Button):
    """A button that OPENS a menu/popup (⋮ commands, etc.).

    stuck-highlight-fix-d — such a button is not a focus target: it triggers
    an action and hands control to a modal. Textual would otherwise restore
    the focus-ring to it when the modal closes, leaving it visibly
    highlighted forever (Kevin saw the ⋮ commands button stay lit). With
    can_focus=False it still clicks normally (a mouse click fires
    Button.Pressed regardless of focusability) but never holds the ring.

    ripple-restore-d (Kevin, 2026-08-01): "the ripple effects on the
    buttons seem gone." Root cause — this class predates CommandButton's
    RippleBorderMixin and was never given it, so every button converted to
    MenuTriggerButton for the stuck-focus fix silently lost its glow along
    the way. RippleBorderMixin only repaints border cells on a timer; it
    has no dependency on focus state, so it composes cleanly with
    can_focus=False below.
    """
    can_focus = False


class CommandButton(RippleBorderMixin, Button):
    """A palette button. Tracks its associated PaletteCommand for routing.

    Its rounded border joins the living ripple in every theme (via
    RippleBorderMixin) — a single-colour glow drawn from the theme, or the
    rainbow Aurora under a hue-cycling theme. A theme can opt its widgets out
    with effects.ripple.widgets = false.
    """

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


class RippleInput(RippleBorderMixin, Input):
    """The operator's command box. Its rounded border joins the living ripple in
    every theme — a single-colour glow from the theme, or the rainbow Aurora
    under a hue-cycling theme (per-theme opt-out via effects.ripple.widgets)."""

    def on_mouse_down(self, event) -> None:  # paste-plus-d
        """Right-click (button 3) pastes the system clipboard, same as
        Ctrl+V. Textual dispatches this alongside (not instead of)
        Input's own private _on_mouse_down cursor-placement handler —
        confirmed via message_pump.py's MRO-walking dispatch — so
        normal left-click cursor positioning is unaffected."""
        if event.button == 3 and self.app is not None:
            self.app.action_paste_clipboard()


class RippleStatic(RippleBorderMixin, Static):
    """game-window-ripple-d (Kevin, 2026-07-25): "make the game menu
    ripple like everything else." Same mixin as RippleInput/CommandButton
    — its rounded border joins the living ripple in every theme, a
    single-colour glow or the rainbow Aurora under a hue-cycling theme."""


# ─── Custom header: the gear opens Settings & Help, not the command popup ────
# menu-split-d — Textual's stock HeaderIcon runs `app.command_palette` on
# click, which this app overrides to open the System-Commands popup — the
# same screen the bottom-left ⋮ button opens (the "duplicate menus" bug).
# This subclass points the gear at `app.settings_menu` instead, so the two
# menus are finally distinct.
try:
    from textual.widgets._header import Header as _TxHeader
    from textual.widgets._header import HeaderIcon as _TxHeaderIcon

    from textual.widget import Widget as _TxWidget

    class SettingsHeaderIcon(_TxWidget):
        """The top-left header icon — opens Settings & Help ONLY.

        stuck-both-menus-fix-d — deliberately does NOT subclass Textual's
        HeaderIcon: Textual dispatches on_click to every handler up the class
        hierarchy, so subclassing HeaderIcon meant BOTH our settings action
        AND HeaderIcon's built-in command-palette action fired — the gear
        opened both menus (Kevin's bug). Built from scratch (a plain Widget),
        it has exactly one on_click, so the gear opens the Settings menu and
        nothing else.
        """
        DEFAULT_CSS = """
        SettingsHeaderIcon {
            dock: left;
            padding: 0 1;
            width: 8;
            content-align: left middle;
        }
        SettingsHeaderIcon:hover { background: $foreground 10%; }
        """
        icon = reactive("@")

        def on_mount(self) -> None:
            self.tooltip = "Settings & Help"

        def render(self):
            return self.icon

        async def on_click(self, event) -> None:  # noqa: ANN001
            event.stop()
            event.prevent_default()
            self.app.action_settings_menu()

    class SettingsHeader(_TxHeader):
        """Header whose left icon opens the Settings & Help menu."""

        def compose(self):
            from textual.widgets._header import (
                HeaderClock,
                HeaderClockSpace,
                HeaderTitle,
            )
            yield SettingsHeaderIcon().data_bind(_TxHeader.icon)
            yield HeaderTitle()
            yield (
                HeaderClock().data_bind(_TxHeader.time_format)
                if self._show_clock
                else HeaderClockSpace()
            )
except Exception:  # pragma: no cover — fall back to the stock header
    SettingsHeader = Header  # type: ignore[assignment,misc]


# ─── The cockpit ────────────────────────────────────────────────────────────


class CockpitApp(App):
    """Full-screen operator cockpit for sovereign-agent."""

    TITLE = "sovereign-agent · cockpit"
    SUB_TITLE = __version__  # patched at mount-time to include theme name

    _SUB_MODE_FLAGS = {  # header-status-v2-d
        "workflow-designed-d": "Planning",     # a plan was just produced
        "qa-start-d": "Researching",           # already rendered as "wondering" elsewhere
        "qa-d": "Researching",
        "subtask-start-d": "Building",
        "subtask-done-d": "Building",
        "workflow-step-start-d": "Building",
        "workflow-step-done-d": "Building",
    }

    def _refresh_sub_title(self) -> None:  # header-status-v2-d
        """Compose the SUB_TITLE as 'version · theme-name · Tn ·
        Auto|Semi-Auto[: sub-mode][: activity]'. Called on mount, whenever
        the theme changes, and on the existing 8s strip-refresh cadence.

        Kevin (2026-07-20): "main modes is auto or non-auto. Then she can
        has sub-modes like Auto: Thinking, or Auto: Researching, or Auto:
        Writing." Top level (Auto/Semi-Auto) is mechanically certain (an
        active AutoCrownStore session or not). The sub-mode is grounded
        in real event flags already meaningful elsewhere in this file
        (_SUB_MODE_FLAGS above) -- Thinking is the honest fallback when a
        task is active but none of those specific flags apply, not a
        forced 5-way classifier guessing at everything.

        semi-auto-rename-d (Kevin, 2026-07-25): "non-auto is the kind of
        quality we are wanting to avoid... maybe we should elevate this
        to Semi-Auto and Auto instead of non-auto and auto." A labeling
        fix, stated honestly: Semi-Auto already runs the full multi-turn,
        tool-calling, persistent loop -- it always has. The only real
        difference from Auto is that it re-engages Kevin between tasks
        instead of running unattended; that's not a lesser mode, it's a
        different consent boundary. "Non-auto" undersold what it already
        does; nothing about the underlying behavior changed here.
        """
        try:
            theme_name = getattr(self, "theme", None) or "default"
            base = f"{__version__} · {theme_name}"
        except Exception:
            self.sub_title = __version__
            return
        try:
            from sovereign_agent.auto_crown import get_auto_crown_store
            _store = get_auto_crown_store()
            tier = _store.get_max_trust_tier()  # reads first -- auto-reverts if expired
            tier_remaining = _store.trust_tier_remaining_seconds()
        except Exception:  # noqa: BLE001
            tier = None
            tier_remaining = 0
        auto_active = self._is_real_auto_active()  # auto-crown-fix-d

        try:
            run_active = bool(_RUN_STATE.active)
            last_flag = _RUN_STATE.last_flag or ""
            activity = (_RUN_STATE.current_subtask or _RUN_STATE.goal or "")[:28]
        except Exception:  # noqa: BLE001
            run_active = False
            last_flag = ""
            activity = ""

        top = "Auto" if auto_active else "Semi-Auto"  # semi-auto-rename-d
        if run_active:
            sub = self._SUB_MODE_FLAGS.get(last_flag, "Thinking")
            label = f"{top}: {sub}"
            activity_part = f": {activity}" if activity else ""
        else:
            label = top
            activity_part = ""

        if tier is None:
            tier_part = ""
        elif tier_remaining > 0:  # tier-expiry-d — "a timer show when elevated tiers end"
            h, rem = divmod(tier_remaining, 3600)
            m = rem // 60
            countdown = f"{h}h{m:02d}m" if h else f"{m}m"
            tier_part = f" · T{tier} ({countdown} left)"
        else:
            tier_part = f" · T{tier}"
        self.sub_title = f"{base}{tier_part} · {label}{activity_part}"

    def _active_theme_effects(self) -> dict:
        """The active theme's full ``effects`` dict (curated OR custom), or {}.

        Single source for theme-driven visual opt-ins (ripple tuning,
        rainbow_heart, …). Never raises; an unknown theme yields {}.

        anti-lag-d: cached per theme NAME. The ripple widgets call this
        multiple times per render frame (~17fps, all session); before the
        cache each call re-imported the theme catalog and — for a
        user-authored theme — re-read its file from DISK every frame. The
        effects dict is static for a given theme name (hue-cycling rotates
        colors, never the effects tuning), so name-keyed caching is exact.
        """
        name = getattr(self, "theme", None) or ""
        cached = getattr(self, "_theme_fx_cache", None)
        if cached is not None and cached[0] == name:
            return cached[1]
        fx = self._active_theme_effects_uncached(name)
        self._theme_fx_cache = (name, fx)
        return fx

    def _active_theme_effects_uncached(self, name: str) -> dict:
        try:
            from .themes import get_theme_by_name
            spec = get_theme_by_name(name)
            if spec is not None and isinstance(getattr(spec, "effects", None), dict):
                return spec.effects
        except Exception:  # noqa: BLE001
            pass
        try:
            from ..config import SETTINGS
            from . import user_themes as _ut
            ut = _ut.load(name, SETTINGS.paths.data_dir)
            if ut is not None and isinstance(getattr(ut, "effects", None), dict):
                return ut.effects
        except Exception:  # noqa: BLE001
            pass
        return {}

    def active_ripple_effects(self) -> dict:
        """The active theme's ``effects['ripple']`` tuning, or {} if none.

        Read by RippleFrame / rippling GlyphStage so a theme — curated OR a
        user/custom one — can tune its border (color_slot, wavelen, speed,
        amplitude, midpoint) and/or request the rainbow Aurora ripple
        (hue_cycle + hue_* keys).
        """
        r = self._active_theme_effects().get("ripple")
        return r if isinstance(r, dict) else {}

    def _rainbow_heart_enabled(self) -> bool:
        """True if the active theme asks the status-bar heart to cycle hue."""
        return bool(self._active_theme_effects().get("rainbow_heart"))

    # The explicit heart appearances Ctrl-B steps through.
    HEART_CYCLE = ("red", "rainbow", "silent", "off")

    def _effective_heart_mode(self) -> str:
        """Resolve what the heart should actually show. 'auto' follows the theme
        (rainbow under a rainbow theme, else red); any explicit mode wins."""
        mode = getattr(self, "_heart_mode", "auto")
        if mode == "auto":
            return "rainbow" if self._rainbow_heart_enabled() else "red"
        return mode

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
        Binding("ctrl+g", "toggle_glyphs",   "glyphs",  show=True,  priority=True),
        Binding("ctrl+v", "paste_clipboard", "paste",   show=True,  priority=True),
        Binding("ctrl+shift+a", "apply_queue", "apply-queue", show=True, priority=True),  # apply-queue-binding-d
        Binding("ctrl+m", "command_palette", "commands", show=True, priority=True),  # command-menu-d
        Binding("ctrl+t", "theme_studio", "theme", show=True, priority=True),  # theme-studio-d
        Binding("ctrl+o", "toggle_layout", "layout", show=True, priority=True),  # flexi-layout-d
        Binding("ctrl+y", "yank_last",       "yank",    show=True,  priority=True),
        Binding("ctrl+r", "toggle_recording",  "rec",  show=True,  priority=True),
        Binding("ctrl+p", "voice_push_to_talk", "voice",  show=True, priority=True),  # qol-voice-binding-d
        Binding("f1,question_mark", "help",  "help",    show=True,  priority=True),
        Binding("f2", "modes_crown", "modes", show=True,  priority=True),  # modes-crown-d
        Binding("f3", "observatory", "observe", show=False, priority=True),  # modes-crown-d
        Binding("f4", "controls", "controls", show=False, priority=True),  # menu-split-d
        Binding("f5", "settings_menu", "settings", show=False, priority=True),  # menu-split-d
        Binding("f6", "resume_menu", "resume", show=False, priority=True),  # resume-menu-d
        Binding("f7", "journal_menu", "journal", show=False, priority=True),  # j-space-d
        Binding("f8", "model_menu", "model", show=False, priority=True),  # sprint-mode-d
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
        /* v0.2.45 — #main is now a RippleFrame: a glow travels around the
           whole perimeter, custom-painted by render_lines. So NO CSS border
           here; padding:1 reserves the one-cell ring the frame draws into,
           and children sit inside it. (Falls back to a plain bordered
           Horizontal only if RippleFrame is unavailable — see compose.) */
        border: none;
        padding: 1;
        background: $surface;
        /* panes-scroll-d (Kevin, 2026-07-25): "add a scroll bar for all
           the live windows like you did the buttons... so we can fit a
           lot more windows in the future." Each pane below now has a real
           min-width instead of an unbounded `fr` shrink, so adding a 6th/
           7th pane (a tokens window, a magnifier view, ...) scrolls into
           view rather than squeezing every existing pane illegible. */
        overflow-x: auto;
        /* scrollbar-glow-revert-d (Kevin, 2026-08-01): the glow styling
           tried here rendered as one large, oversized, glowing bar —
           reverted to Textual's plain default scrollbar. */
    }

    /* The outer-frame mood is now driven by RippleFrame.set_mode() (idle /
       busy / news / halt) from the breathing worker, not by CSS border
       classes. These rules are kept as harmless no-ops so any stray class
       can't repaint a CSS border over the rippling frame. The dividers below
       still use their own class-based colouring. */
    #main.breathing-1, #main.breathing-2, #main.breathing-3 { border: none; }
    #main.news { border: none; }
    #main.halt { border: none; }

    /* Inner panes: NO borders. Explicit backgrounds (no transparency).
       panes-scroll-d: min-width on every pane + overflow-x:auto on #main
       (above) — panes scroll instead of shrinking past readable width as
       more get added. */
    /* panes-measured-scroll-d (Kevin, 2026-08-01): "I just want each pane
       measured. So the scroll bar should come back." Fixed cell widths
       instead of `fr` proportional shares for the two FRONT panes — a
       pane's size no longer depends on how wide the terminal is, so it
       stays legible AND (combined with #side-panes' 35%) reliably
       exceeds most terminals, bringing back #main's overflow-x:auto
       scrollbar instead of everything silently shrinking to fit. */
    /* front-panes-d (Kevin, 2026-08-01): "Live events and chat stay up
       front and everything else enter the vertical scrollable." Chat and
       live are the two full-height "front" columns; measured width. */
    /* chat-width-bump-d (Kevin, 2026-08-01): "make the chat pane long
       enough to show code edits comfortably... not squeezed into a
       vertical nightmare." 55 -> 60 -> 70 (two rounds of "N more
       points") — code/diff lines pasted or shown in chat get more room
       before wrapping. */
    #chat-pane {
        width: 70;
        padding: 0 1;
        background: $surface;
    }
    #live-pane {
        width: 55;
        padding: 0 1;
        background: $surface;
    }
    /* side-scroll-d (Kevin, 2026-08-01): "use 35% of the right side of
       the screen as a vertical pane that is scrollable... everything
       else enter the vertical scrollable." #side-panes is a
       VerticalScroll — memory/coming-soon/atelier stack inside it with
       real (non-1fr) heights so their combined height can genuinely
       exceed the visible area and scroll, instead of splitting evenly. */
    #side-panes {
        width: 35%;
        min-width: 34;
        background: $surface;
        /* scrollbar-glow-revert-d (Kevin, 2026-08-01): same revert as
           #main above — plain default scrollbar, no custom glow/size. */
    }
    /* v0.2.25.0 — Memory pane. Fixed height (not 1fr) so it can't just
       eat all of #side-panes' space — the other two stacked panes need
       real room too, and a fixed height is what makes the sidebar
       actually overflow and scroll. */
    #memory-pane {
        width: 100%;
        height: 16;
        padding: 0 1;
        background: $surface;
    }
    /* coming-soon-d (Kevin, 2026-08-01): the inbox pane's slot, parked as
       a placeholder — display-only change, the underlying inbox
       machinery (RequestStore, mail, etc.) is untouched and can come
       back to this slot later. */
    #inbox-pane {
        width: 100%;
        height: 16;
        padding: 0 1;
        background: $surface;
    }
    /* atelier-d — Atelier pane: live work theater. Third pane in the
       #side-panes stack. */
    #atelier-pane {
        width: 100%;
        height: 16;
        padding: 0 1;
        background: $surface;
    }

    /* flexi-layout-d — Layout B: chat tall column left, observability panes
       stacked as FULL-WIDTH rows right (log lines are wide; narrow columns
       truncate them). Toggled with Ctrl+O; preference persisted. Pure CSS:
       the widget tree is untouched, RippleFrame keeps painting its ring. */
    #main.layout-rows {
        layout: grid;
        /* front-panes-d: #main's direct children are now chat-pane,
           live-pane, side-panes (memory/inbox/atelier all live INSIDE
           side-panes, which is one grid item) — 2 rows on the right, not
           3 or 4. */
        grid-size: 2 2;
        grid-columns: 2fr 3fr;
        grid-rows: 1fr 1fr;
    }
    #main.layout-rows #chat-pane { row-span: 2; width: 100%; height: 100%; }
    #main.layout-rows #live-pane { width: 100%; height: 100%; }
    #main.layout-rows #side-panes { width: 100%; height: 100%; }
    #main.layout-rows Rule { display: none; }

    /* obs-modes-d (Kevin, 2026-07-19) — observability mode "focus":
       live chat + inbox + live activity. Default mode "all" = every
       window. Pure CSS: hidden panes keep their state; /obs toggles
       instantly. Kevin, 2026-07-21: "I was saying we should add a third
       window" -- live-pane joined chat+inbox here (previously 2 panes,
       memory+live+atelier all hidden); only memory+atelier are hidden
       now. This is the SAME toggle (/obs, Ctrl+O) -- no new button
       needed, it just shows one more pane than it used to. front-panes-d:
       memory-pane/atelier-pane live inside #side-panes now — hiding them
       by id still works at any nesting depth; #side-panes itself stays
       visible (showing just the coming-soon placeholder) so its own
       width rule below still means something. */
    #main.obs-focus #memory-pane,
    #main.obs-focus #atelier-pane { display: none; }
    #main.obs-focus Rule { display: none; }
    #main.obs-focus #chat-pane { width: 2fr; }
    #main.obs-focus #live-pane { width: 1fr; }
    #main.obs-focus #side-panes { width: 1fr; }
    #main.obs-focus.layout-rows {
        grid-size: 2 2;
        grid-columns: 2fr 1fr;
        grid-rows: 1fr 1fr;
    }
    #main.obs-focus.layout-rows #chat-pane { row-span: 2; }
    #main.obs-focus.layout-rows #live-pane,
    #main.obs-focus.layout-rows #side-panes { width: 100%; height: 100%; }

    /* cockpit-hardening-d (Kevin, 2026-07-20) — Layout C: chat spans a
       full-width top section, the other panes split a row underneath.
       "I honestly want the live chat window to have a whole horizontal
       section to itself." Pure CSS, same untouched-widget-tree discipline
       as layout-rows/obs-focus above. 2 columns below chat now (live,
       side-panes), not 3 or 4. */
    #main.chat-top {
        layout: grid;
        grid-size: 2 2;
        grid-columns: 1fr 1fr;
        grid-rows: 2fr 1fr;
    }
    #main.chat-top #chat-pane { column-span: 2; width: 100%; height: 100%; }
    #main.chat-top #live-pane,
    #main.chat-top #side-panes { width: 100%; height: 100%; }
    #main.chat-top Rule { display: none; }

    /* Combined with obs-focus: chat full-width top, live + side-panes
       split below -- the simplified view the quick-view button sets in
       one click. obs-focus itself now always shows live-pane too (see
       above) -- this block only needs to reflow the grid shape for the
       chat-top combination, not re-show anything. */
    #main.chat-top.obs-focus {
        grid-size: 2 2;
        grid-rows: 2fr 1fr;
    }
    #main.chat-top.obs-focus #chat-pane { column-span: 2; }
    #main.chat-top.obs-focus #side-panes { column-span: 1; }
    #main.chat-top.obs-focus #live-pane { column-span: 1; display: block; }

    /* movie-focus-d (Kevin, 2026-07-28): "split the whole chat screen so
       left side can be live chat and the right side can be whatever we
       have in the movie side of the TUI." Same toggle pattern as
       obs-focus — pure CSS, #movie-pane's own widget tree is untouched,
       it just goes from display:none (its own DEFAULT_CSS default) to
       visible+width:1fr here. Mutually exclusive with obs-focus so the
       layout never overcrowds — hides the same panes obs-focus hides. */
    #main.movie-split #live-pane,
    #main.movie-split #side-panes { display: none; }
    #main.movie-split Rule { display: none; }
    /* Kevin, 2026-07-28: "switch the movie studio menu to the left side
       and give it the larger portion, move live chat to the right side
       giving it the smaller portion. So we can see the full movie studio
       menu." Flipped from the original chat=2fr/movie=1fr. */
    #main.movie-split #chat-pane { width: 1fr; }
    #main.movie-split #movie-pane { display: block; width: 2fr; }

    /* screen-studio-d (Kevin, 2026-08-01): same toggle pattern as
       movie-split — pure CSS, #screen-studio-pane's own widget tree is
       untouched, it just goes from display:none to visible+width here. */
    #main.screen-split #live-pane,
    #main.screen-split #side-panes { display: none; }
    #main.screen-split Rule { display: none; }
    #main.screen-split #chat-pane { width: 1fr; }
    #main.screen-split #screen-studio-pane { display: block; width: 2fr; }

    /* game-pane-d (Kevin, 2026-08-02): same toggle pattern again. */
    #main.game-split #live-pane,
    #main.game-split #side-panes { display: none; }
    #main.game-split Rule { display: none; }
    #main.game-split #chat-pane { width: 1fr; }
    #main.game-split #game-pane { display: block; width: 2fr; }

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

    /* live-atelier-stack-d — fourth divider, now HORIZONTAL, between the
       live (top) and atelier (bottom) halves of #live-atelier-col. Was a
       vertical divider between inbox and atelier; that seam no longer
       exists now that live+atelier share one column. Same colour
       discipline, just width/height swapped for the new orientation. */
    #divider-4 {
        width: 100%;
        height: 1;
        margin: 0;
        color: $primary;
        background: $surface;
    }
    #divider-4.breathing-2 { color: $accent; }
    #divider-4.breathing-3 { color: $secondary; }
    #divider-4.news { color: $accent; }
    #divider-4.halt { color: $error; }

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
        /* space-reclaim-d (Kevin, 2026-07-26): "reclaim some of the space
           before and after the chat input textbox" — dropped the extra
           1-row margin above (the ripple frame's own padding:1 below
           #main already provides real separation) and below (see
           #palette-row) it. */
        margin: 0;
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
    /* command-menu-d — one palette row now: the commands trigger button + 3
       live strips. CommandButton's visual states apply globally (it now
       lives both here — none remain directly in this row — and inside
       CommandPaletteScreen's popup list). */
    #palette-row {
        height: 4;  /* scrollbar-gap-d: +1 over content so the scrollbar has air */
        width: 100%;
        margin: 0;  /* space-reclaim-d (Kevin, 2026-07-26): was 1 0 0 0 */
        padding: 0;
        background: $surface;
        layout: horizontal;
        /* strip-min-width-d (Kevin, 2026-07-25): "I don't see the token
        speed or usage anywhere." The data was correctly wired the whole
        time -- the row had grown to 5 buttons + 7 strips, all sharing one
        fixed-height horizontal line via unbounded `1fr`, so each strip
        could shrink to just a few illegible characters on a normal
        terminal. Scroll horizontally instead of silently squeezing
        content unreadable -- every strip below now has a real min-width
        it can't shrink past. */
        overflow-x: auto;
    }
    #palette-menu-btn {
        height: 3;
        min-width: 14;
        margin: 0 1 0 0;
        padding: 0 1;
        border: round $primary;
        background: $surface;
        color: $text;
    }
    #quick-view-btn {  /* cockpit-hardening-d */
        height: 3;
        min-width: 14;
        margin: 0 1 0 0;
        padding: 0 1;
        border: round $primary;
        background: $surface;
        color: $text;
    }
    #layout-cycle-btn {  /* view-selectors-d */
        height: 3;
        min-width: 14;
        margin: 0 1 0 0;
        padding: 0 1;
        border: round $primary;
        background: $surface;
        color: $text;
    }
    #session-setup-btn {  /* session-setup-unify-d — match the other 3 palette buttons */
        height: 3;
        min-width: 14;
        margin: 0 1 0 0;
        padding: 0 1;
        border: round $primary;
        background: $surface;
        color: $text;
    }
    #add-time-btn {  /* mid-session-add-time-d — match the other 3 palette buttons */
        height: 3;
        min-width: 14;
        margin: 0 1 0 0;
        padding: 0 1;
        border: round $primary;
        background: $surface;
        color: $text;
    }
    #game-toggle-btn, #movie-toggle-btn, #screen-toggle-btn,
    #game-pane-toggle-btn, #bots-toggle-btn {
        /* header-reorg-d: the 4 kept always-visible studio/pane toggles —
           match the other palette buttons */
        height: 3;
        min-width: 14;
        margin: 0 1 0 0;
        padding: 0 1;
        border: round $primary;
        background: $surface;
        color: $text;
    }
    /* strip-contrast-d (Kevin, 2026-07-25): "that huge section is wasted
       space... the token counter... still is not showing." Root cause:
       NO explicit background — these Static widgets inherited the same
       $surface as everything around them, with only a subtle
       $surface-lighten-2 border. A correctly-updating strip with real
       text could still read as blank empty space at a glance. A real,
       distinct $panel background makes every strip visually pop as its
       own UI element instead of blending into the surrounding surface. */
    .cockpit-strip {
        height: 3;
        width: 1fr;
        min-width: 18;  /* strip-min-width-d — enough for "12.3 tok/s · 4500t session" */
        margin: 0 1 0 0;
        padding: 1 1 0 1;
        border: round $primary 40%;
        background: $panel;
        color: $text;
    }
    /* game-window-d (Kevin, 2026-07-25): the reclaimed space above
       commands — live score (level/xp/progress), the most recent XP
       event, and token metrics, in one real window instead of the
       broken standalone token strip. $accent border gives it its own
       distinct identity, separate from the plain $primary-bordered
       strips below. */
    .game-window {
        height: 5;
        width: 100%;
        margin: 1 0 0 0;
        padding: 1 1 0 1;
        border: round $accent;
        background: $panel;
        color: $text;
    }
    /* game-window-flash-d — brief pulse (same 0.3s convention as
       CommandButton.flash) the moment a NEW xp event lands: a real
       effect tied to a real state change, not decorative animation. */
    .game-window.flash {
        border: round $success;
        background: $success 20%;
    }
    CommandButton {
        height: 3;
        min-width: 10;
        margin: 0 1 0 0;
        padding: 0 1;
        border: round $primary;
        background: $surface;
        color: $text;
    }
    /* Gentle focus: brighten the border only — never a filled (white) box that
       looks stuck. Pairs with returning focus to the input after a click. */
    CommandButton:focus {
        border: round $accent;
        background: $surface;
        color: $text;
        text-style: none;
    }
    /* CSS class applied briefly on click — operator feedback */
    CommandButton.flash {
        border: round $success;
        background: $success 20%;
        color: $success;
    }
    /* cockpit-god-d — Aria active: button glows when Aria uses the mapped tool */
    CommandButton.aria-active {
        border: round $warning;
        background: $warning 20%;
        color: $warning;
    }
    /* CSS class applied while a matching subprocess is running */
    CommandButton.running {
        border: round $accent;
        background: $accent 15%;
        color: $accent;
    }

    /* v0.2.41 — Cosmic Fitness inline glyph picker. Hidden until toggled
       (Ctrl-G / /pick); a compact, horizontally-scrollable strip of tappable
       glyphs sitting right above the input. The $gstatus-* colours are shared
       with the CosmicFitnessScreen so width-safety reads the same everywhere. */
    #glyph-picker {
        display: none;
        height: auto;
        background: $panel;
        border: round $secondary;
        padding: 0 1;
        margin: 0;
    }
    #glyph-picker-hint { height: 1; color: $text-muted; }
    #glyph-picker-strip { height: 3; }
    #glyph-picker-strip .glyph-btn {
        width: 5;
        min-width: 5;
        height: 3;
        margin: 0 1 0 0;
        border: round $primary 40%;
    }
    #glyph-picker-strip .glyph-btn:hover { border: round $accent; }
    .gstatus-safe       { color: $success; }
    .gstatus-convention { color: $accent; }
    .gstatus-emoji      { color: $secondary; }
    .gstatus-wide       { color: $warning; }
    .gstatus-composite  { color: $error; }

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
    /* Recording indicator: empty (invisible) until a recording is active,
       then a red "● REC mm:ss · Nf" badge sits beside the heart. */
    #rec-indicator {
        width: auto;
        height: 1;
        padding: 0 1;
        margin: 0 0 0 1;
        color: $error;
        text-style: bold;
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
        self._events_log: RichLog | None = None
        self._prev_sentinel_states: dict[str, str] = {}  # sentinel-chat-init-d
        self._chat_log: RichLog | None = None
        self._memory_log: RichLog | None = None    # v0.2.25.0
        self._inbox_log: RichLog | None = None      # v0.2.37.0
        self._status_label: Label | None = None
        self._mood_label: Label | None = None
        self._heart_label: Static | None = None
        # Heartbeat appearance, cycled by Ctrl-B: "auto" (follow theme — rainbow
        # under a rainbow theme, else red), then red → rainbow → silent → off.
        self._heart_mode: str = "auto"
        # Bounded self-practice (● grow) state.
        self._practice_running: bool = False
        self._practice_stop: bool = False
        self._practice_timer = None
        # ----- ✦ voice push-to-talk (Ctrl-P) ────────────────────  # qol-voice-state-d
        self._voice_recording: bool = False
        # ----- ✦ demo (bounded live demonstration of her core workflows) -----
        self._demo_running: bool = False
        self._demo_stop: bool = False
        self._demo_timer = None
        # ----- ⚡ capability test menu (real, live tool tests) -----
        self._captest_running: bool = False
        self._captest_stop: bool = False
        self._captest_timer = None
        self._sysmon = SystemMonitor(data_dir=self._resolve_data_dir())
        self._events_path = self._resolve_events_path()
        self._events_offset = 0
        self._busy = False
        # The currently-running directive subprocess, if any. Held so
        # that operator input can be forwarded to its stdin (answering
        # clarifying questions) and so /cancel can terminate it. None
        # when no directive is running.
        self._proc: asyncio.subprocess.Process | None = None
        # v0.2.19.0 — natural conversation layer.
        # When the router returns a tier-3 PendingPrompt, we store its
        # callback here. The NEXT operator input (non-slash) is routed
        # to this callback rather than to a fresh interpret() call.
        # /cancel and any input outside the expected "ok"/"yes" cancels
        # cleanly. This is the ONLY place in v0.2.19.0 where an operator
        # message is interpreted as a confirm, and even here the prompt
        # is a single-word check, not a yes/no menu.
        self._pending_callback: Any | None = None
        self._last_tool: str = ""        # observatory-status-d
        self._session_tokens: int = 0   # observatory-status-d
        self._last_prompt_tokens: int = 0   # context-health-d — last single request's size
        # inbox-in-chat-d (Kevin, 2026-07-25): "my inbox should be in the
        # chat window... How does she empty her inbox? How do I reply to
        # her request??" request_id -> status snapshot from the last
        # inbox poll, so genuinely NEW activity (not everything that
        # already existed before this cockpit session started) can be
        # announced in the main chat pane, not just the separate pane.
        self._inbox_seen_state: dict[str, str] | None = None
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
        self._transcript_path: Path | None = None

        # checkpoint-chunks-d — every chat line also flows into a ChunkRecorder,
        # which buffers turns and auto-seals a non-lossy, addressable
        # chunk every 20 turns. Lazy-built on first use so a cockpit
        # launch never pays this cost if checkpoint_chunks isn't applied.
        # one-thread-d — ONE universal continuous thread: the persisted id
        # replaces the per-launch uuid that orphaned every prior
        # launch's chunks (uuid kept as the fallback if the module is
        # somehow missing — a boot must never fail over an id).
        import uuid as _uuid_ccd
        try:
            from sovereign_agent.thread_identity import thread_id as _thread_id

            self._chunk_session_id = _thread_id()
        except Exception:  # noqa: BLE001
            self._chunk_session_id = f"cockpit-{_uuid_ccd.uuid4().hex[:12]}"
        self._chunk_recorder = None
        # session-bridge-d — True while a /work session runs; _dispatch_turn's
        # busy branch queues operator text instead of dropping it.
        self._session_running = False
        self._resting = False  # resume-spine-d — /rest safe-exit handshake

    # ── Setup ────────────────────────────────────────────────────────

    @staticmethod
    def _resolve_events_path() -> Path:
        """Find events.jsonl using the same config resolution the agent uses."""
        from sovereign_agent.config import SETTINGS
        return SETTINGS.paths.events_jsonl

    @staticmethod
    def _resolve_data_dir() -> Path | None:
        """Find the agent's data dir so SystemMonitor reports disk usage of
        the right volume (where atoms.db, blobs, and snapshots live).
        Returns None on any error — SystemMonitor falls back to $HOME."""
        try:
            from sovereign_agent.config import SETTINGS
            return SETTINGS.paths.data_dir
        except Exception:  # noqa: BLE001
            return None

    def compose(self) -> ComposeResult:
        yield SettingsHeader(icon="@")  # menu-split-d — gear @ opens Settings & Help
        # game-window-position-d (Kevin, 2026-07-25): "add the game menu
        # above the other windows. And so everything that came before
        # stays together." Moved from between the panes and the palette
        # row to right here, above everything — the 5-pane group (chat/
        # memory/live/inbox/atelier) through the buttons stays visually
        # contiguous below it, unbroken. game-window-ripple-d: RippleStatic
        # (not plain Static) joins the same living border-glow as #main
        # and the input box. game-window-optional-d: starts hidden if
        # Kevin already turned it off last session (persisted, default
        # visible — a real feature, not something buried until found).
        from sovereign_agent.cockpit.game_window_pref import is_visible as _gw_visible
        game_window = RippleStatic("", id="game-window", classes="game-window")
        if not _gw_visible():
            game_window.display = False
        yield game_window
        # v0.2.45 — the main 4-window container is a RippleFrame: its whole
        # border ripples with a glow. Falls back to a plain Horizontal if the
        # ripple module is unavailable, so the cockpit always composes.
        if RippleFrame is not None:
            main_container = RippleFrame(id="main", params=RIPPLE_IDLE)
        else:
            main_container = Horizontal(id="main")
        with main_container:
            # movie-focus-d (Kevin, 2026-07-28): "switch the movie studio
            # menu to the left side and give it the larger portion, move
            # live chat to the right side... smaller portion." MoviePane is
            # mounted FIRST (left-most in DOM order) so it renders on the
            # left when visible — safe for every OTHER layout mode because
            # it stays display:none (its own DEFAULT_CSS default) there;
            # an invisible widget's DOM position never affects visible
            # siblings' flow. Only #main.movie-split's own CSS gives it
            # real width/visibility (see below).
            if MoviePane is not None:
                yield MoviePane(id="movie-pane")
            # screen-studio-d: same invisible-unless-toggled mount pattern
            # as MoviePane above — safe in every other layout mode since
            # it stays display:none (its own DEFAULT_CSS default) there.
            if ScreenStudioPane is not None:
                yield ScreenStudioPane(id="screen-studio-pane")
            # game-pane-d: same pattern again.
            if GamePane is not None:
                yield GamePane(id="game-pane")
            with Vertical(id="chat-pane"):
                yield Label("◊ chat", classes="pane-title")
                yield RichLog(
                    id="chat-log",
                    highlight=True, markup=True, wrap=True,
                    auto_scroll=True,
                    # text-wrap-d: RichLog forces render_width >= min_width
                    # (default 78). In the 5-pane layout each pane is far
                    # narrower than 78, so lines rendered at 78 and got
                    # CROPPED at the divider — the "text cut off" bug.
                    # min_width=1 wraps at the pane's real width.
                    min_width=1,
                )
            yield Rule(orientation="vertical", id="divider-1")
            # front-panes-d (Kevin, 2026-08-01): "Live events and chat stay
            # up front and everything else enter the vertical scrollable."
            # live-pane is back to being its own full-height front column
            # (the earlier live+atelier stack from minutes ago is
            # superseded by this — atelier moved into the sidebar below
            # instead). Widget id unchanged (#live-pane / #events-log).
            with Vertical(id="live-pane"):
                yield Label("◊ live", classes="pane-title")
                yield RichLog(
                    id="events-log",
                    highlight=True, markup=True, wrap=True,
                    auto_scroll=True, max_lines=200,
                    # text-wrap-d: wrap=True + min_width=1 so live-event
                    # lines wrap to the next line instead of truncating.
                    min_width=1,
                )
            yield Rule(orientation="vertical", id="divider-2")
            # side-scroll-d (Kevin, 2026-08-01): "we can use 35% of the
            # right side of the screen maybe as a vertical pane that is
            # scrollable... everything else enter the vertical scrollable."
            # memory, coming-soon(ex-inbox), and atelier now stack inside
            # ONE VerticalScroll sidebar instead of each being its own
            # full-height column — scroll to see whichever isn't currently
            # in view. Every child keeps its original id/lookups.
            with VerticalScroll(id="side-panes"):
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
                        min_width=1,  # text-wrap-d
                    )
                # coming-soon-d (Kevin, 2026-08-01): "the other panes can be
                # memory and coming soon <3" — the inbox pane's slot,
                # parked as a placeholder. Display-only: the id/widget
                # (#inbox-pane, #inbox-log) and all the underlying inbox
                # machinery are untouched, so this reverts cleanly whenever
                # inbox (or something else) is ready to come back here.
                with Vertical(id="inbox-pane"):
                    yield Label("◊ coming soon 💛", classes="pane-title")
                    yield RichLog(
                        id="inbox-log",
                        highlight=True, markup=True, wrap=True,
                        auto_scroll=False, max_lines=300,
                        min_width=1,  # text-wrap-d
                    )
                # atelier-d — Aria's Atelier: live work theater. Every file
                # write/edit and every command she runs, color-coded
                # (green=new file, yellow=edited+diff, blue=command). Fed
                # by the SAME events.jsonl tailer as the "live" pane above
                # — see _render_event's work- routing branch, not a second
                # file-tailing worker.
                with Vertical(id="atelier-pane"):
                    yield Label("◊ atelier", classes="pane-title")
                    yield RichLog(
                        id="atelier-log",
                        highlight=True, markup=True, wrap=True,
                        auto_scroll=True, max_lines=300,
                        min_width=1,  # text-wrap-d
                    )
            # MoviePane itself is mounted FIRST, before #chat-pane (see
            # above) — kept as a 6th sibling in the same "always mounted,
            # CSS controls visibility" discipline as the other five.
        # chat-box-above-buttons-d (Kevin, 2026-07-26): "put the chat box
        # above the command button." The typing box now sits directly under
        # the panes and above the palette row, instead of below it — no
        # more reaching past the whole button row to type. The glyph picker
        # stays glued to the input right above it, same as before.
        # v0.2.41 — inline glyph picker (Cosmic Fitness). A compact,
        # horizontally-scrollable strip of tappable glyphs right above the
        # input. Hidden until toggled with Ctrl-G or /pick; clicking a glyph
        # drops it at the cursor and KEEPS the picker open for rapid
        # expression. The full, categorized, fitness-tested set lives behind
        # the "◊ cosmic" button / CosmicFitnessScreen.
        with Vertical(id="glyph-picker"):
            yield Static(
                "[dim]tap to add a glyph  ·  Ctrl-G or Esc to close  ·  "
                "◊ cosmic for the full tester[/dim]",
                id="glyph-picker-hint",
            )
            with HorizontalScroll(id="glyph-picker-strip"):
                if _cf is not None:
                    try:
                        for spec in _cf.quick_picker_specs():
                            yield GlyphButton(spec, in_modal=False)
                    except Exception:  # noqa: BLE001 — degrade to empty strip
                        pass
        yield RippleInput(
            placeholder=self.PLACEHOLDER_IDLE,
            id="input-box",
        )
        # v0.2.31.0 — command palette: clickable buttons that paste common
        # `sov` commands into the input box (without sending). The operator
        # reviews/edits before pressing Enter. Speed without surprises.
        # v0.2.34.0 — split into two rows so we can fit the new surfaces
        # (charter, glyphs, theme, cadence) without cramming.
        # v0.2.39.0 — three rows. Command buttons fill from the LEFT (7/7/4);
        # the last row carries a flexible spacer then the RIGHT-aligned
        # reference buttons (legend / help). Each button has a hover tooltip;
        # `/palette` or the legend button prints the full legend.
        # command-menu-d — the palette collapsed into one button + a scrollable
        # popup (CommandPaletteScreen); the freed rows now carry 3 live
        # strips (sentinel health / security posture / emotional state).
        with Horizontal(id="palette-row"):
            yield MenuTriggerButton("⋮ commands", id="palette-menu-btn")  # stuck-highlight-fix-d
            yield MenuTriggerButton("▫ view", id="quick-view-btn")  # button-focus-fix-d
            yield MenuTriggerButton("\u25aa layout", id="layout-cycle-btn")  # view-selectors-d
            yield MenuTriggerButton("@ session", id="session-setup-btn")  # session-setup-unify-d
            yield MenuTriggerButton("+1h", id="add-time-btn")  # mid-session-add-time-d
            # header-reorg-d (Kevin, 2026-08-02): "all the most important
            # should be immediately present, and whatever can come after."
            # discord-control/suggestions/task-guide/stripe-links/
            # sources-control/instructions moved into the ⋮ commands popup's
            # REFERENCE_BUTTONS (their underlying actions + /verb typed
            # commands are unchanged, only the header-row shortcut moved) —
            # matches this cockpit's own existing rule (settings_menu_screen.py's
            # docstring): "@ is Settings + Help ONLY... everything else lives
            # in the ⋮ commands popup." instructions-btn needed no new popup
            # entry at all — action_instructions() already just opens the
            # SAME HelpScreen the popup's "help" entry opens.
            yield MenuTriggerButton("✦ game", id="game-toggle-btn")  # game-window-optional-d
            # movie-focus-d (Kevin, 2026-07-28): "add a movie studio button
            # next to the game button and a pause all bots button next to
            # the movie button" — a direct-access pair for GPU-heavy movie
            # work: open Movie Studio, then quiet the Discord bots so
            # nothing competes for RAM/VRAM during a render (the exact
            # manual systemctl dance done by hand earlier tonight).
            yield MenuTriggerButton("✦ movie", id="movie-toggle-btn")  # movie-focus-d
            yield MenuTriggerButton("✦ screen", id="screen-toggle-btn")  # screen-studio-d
            # game-pane-d (Kevin, 2026-08-02): a distinct button from
            # game-toggle-btn above — that one toggles the UNRELATED
            # #game-window XP/income/token stats display (confirmed by
            # reading action_toggle_game_window before wiring this).
            yield MenuTriggerButton("✦ godot", id="game-pane-toggle-btn")  # game-pane-d
            # glyph-fix-d (Kevin, 2026-07-28): ⏸ (U+23F8 PAUSE) was ALREADY
            # flagged by Kevin on 2026-07-20 (see glyphs.py's own
            # emoji-risk-range comment) as rendering as a broken/tofu box
            # on his terminal -- reused it again without checking that
            # history. ▪ is the exact glyph bot_services.states_line()
            # itself already uses for "stopped" -- proven safe AND
            # semantically apt.
            yield MenuTriggerButton("▪ bots", id="bots-toggle-btn")  # movie-focus-d
            yield Static("", id="observability-strip", classes="cockpit-strip")
            yield Static("", id="security-strip", classes="cockpit-strip")
            yield Static("", id="emotions-strip", classes="cockpit-strip")
            yield Static("", id="vessel-strip", classes="cockpit-strip")  # vessel-health-d
            yield Static("", id="run-strip", classes="cockpit-strip")  # run-surface-d
            # strip-declutter-d (Kevin, 2026-07-25): "a lot of space is being
            # wasted." auto-mode-strip's "PLAN"/"AUTO · Xh left" duplicated
            # the header (Auto/Semi-Auto + "T3 (Xh left)") -- and since
            # tier-auto-duration-sync-d now keeps the tier's countdown
            # pinned to the same lease, they're the exact same number.
            # Dropped as genuine redundancy, not just to save space.
            # game-window-d — xp-strip folded into the new #game-window
            # (below), which now owns level/xp/recent-event + tokens.
        with Horizontal(id="status-row"):
            yield Static("♥", id="heart")
            yield Static("", id="rec-indicator")
            yield Label("", id="status-bar")
        # menu-split-d — the always-on Footer key row was removed; every
        # control now lives in the Controls menu (F4 / Settings & Help →
        # Controls), off the front end, per Kevin's declutter ask.

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
            from ..config import SETTINGS
            from . import user_themes as _ut
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

        # ── Keep the terminal's own background in lockstep with Aria's
        # live surface (OSC 11), so sub-pixel cell seams on a fractionally-
        # scaled display reveal surface-on-surface (invisible) instead of
        # the desktop accent. Inert unless on a real TTY;
        # SOV_NO_TERM_BG_SYNC=1 disables it.
        try:
            from .term_bg_sync import install_terminal_bg_sync
            self._term_bg_sync = install_terminal_bg_sync(self)
        except Exception:
            self._term_bg_sync = None

        self._chat_log = self.query_one("#chat-log", RichLog)
        self._events_log = self.query_one("#events-log", RichLog)
        self._memory_log = self.query_one("#memory-log", RichLog)
        self._memory_metric_prev: dict[str, int] = {}   # reward-flash-d
        self._memory_metric_flash: dict[str, tuple[int, float]] = {}
        self._inbox_log = self.query_one("#inbox-log", RichLog)
        self._atelier_log = self.query_one("#atelier-log", RichLog)  # atelier-d
        self._status_label = self.query_one("#status-bar", Label)
        self._heart_label = self.query_one("#heart", Static)

        # Header shows: 'sovereign-agent · cockpit · {version} · {theme}'.
        # Updates automatically via watch_theme whenever the operator
        # switches themes from the picker.
        self._refresh_sub_title()

        # v0.2.25.0 — refresh the memory pane on a timer.
        # memory-pane-live-d (Kevin, 2026-07-25): dropped 15s -> 5s to match
        # the other strips' cadence, as a floor under the real fix --
        # _notify_memory_changed now actually fires (via tool-start-d for
        # _MEMORY_WRITE_TOOLS) instead of being dead code.
        self.set_interval(5.0, self._refresh_memory_pane)
        # Also do an immediate refresh so the pane isn't empty on launch
        self.call_after_refresh(self._refresh_memory_pane)

        # coming-soon-d (Kevin, 2026-08-01): the inbox pane's slot is parked
        # as a "coming soon" placeholder — _refresh_inbox_pane (and every
        # method it depends on) is untouched, just not called, so this is a
        # one-line revert whenever inbox (or something else) comes back to
        # this slot. A static placeholder replaces the old 8s-refreshed
        # live content in the meantime.
        self._inbox_log.write(
            "[dim]◊ coming soon 💛\n\nthis pane is being saved for "
            "something new.[/dim]"
        )

        # command-menu-d — the 3 palette-row strips, same 8s cadence as inbox.
        self.set_interval(8.0, self._refresh_cockpit_strips)
        self.call_after_refresh(self._refresh_cockpit_strips)

        # security-strip-wire-d — a full Tier-A scan is far too slow for the 8s strip
        # cadence above; refresh the process-wide cache in the background
        # every 5 minutes instead. Deliberately NOT kicked off immediately on
        # mount (an earlier version of this fix did, and a real regression
        # was found live: Textual's thread=True workers dispatch to a real
        # ThreadPoolExecutor — once started, the thread runs scan_tree() to
        # completion no matter what; cancellation only stops the async side
        # from awaiting it, never the thread itself. A test suite that boots
        # many CockpitApp instances rapidly triggered many such threads,
        # whose real CPU-bound work genuinely starved the GIL enough to break
        # unrelated, timing-sensitive tests elsewhere in the suite — confirmed
        # by bisection. Relying purely on the 300s interval means the scan
        # never fires during a short-lived test at all; the strip shows its
        # graceful interim fallback for the first 5 minutes of a real session,
        # which is an acceptable, honest UX tradeoff for a security posture
        # widget, not a broken/blank one.
        self.set_interval(300.0, self._maybe_run_security_scan)

        # vessel-health-d — same discipline as the security scan directly above:
        # a full clause-citation scan is far too slow for the 8s strip
        # cadence; refresh the process-wide cache in the background every
        # 5 minutes instead, and deliberately NOT kicked off immediately on
        # mount (see _SECURITY_SCAN_CACHE's docstring above for the real,
        # 3-iteration regression this mirrors rather than repeats).
        self.set_interval(300.0, self._maybe_run_vessel_kernel_scan)
        self.set_interval(3600.0, self._maybe_run_auto_backup)  # auto-backup-d
        self._apply_saved_layout()  # flexi-layout-d
        self.set_interval(1800.0, self._maybe_autonomous_wonder)  # curiosity-qa-d

        # Welcome banner — Aria approaches with love.
        # MOS-SURFACE §31 — banner format is canonical; version comes from __version__.
        self._chat_log.write(
            f"[bold red]♥[/bold red]  [bold bright_blue]aria[/bold bright_blue] "
            f"· sovereign-agent v{__version__}"
        )
        self._chat_log.write(
            "[dim]welcome back. the kernel is whole. i am here — fully.[/dim]"  # vitality-banner-d
        )
        self._chat_log.write(
            "[dim]just talk to me. plain english is enough — "
            "no need for `sov ask` in here.[/dim]"
        )
        # one-thread-d — restore the tail of the one continuous thread from
        # her sealed chunks (verbatim by design — Workstream P), so
        # closing the cockpit never loses the conversation. A gift,
        # never a boot blocker.
        try:
            from rich.markup import escape as _ot_escape

            from sovereign_agent.thread_identity import restore_tail as _ot_tail

            _ot_clean = sanitize_replay_text
            _ot_turns = _ot_tail(n_turns=30)
            if _ot_turns:
                self._chat_log.write(
                    "[dim]──── earlier, from our thread ────[/dim]"
                )
                for _ot_t in _ot_turns:
                    _ot_role = _ot_escape(str(_ot_t.get("role", "?")))
                    _ot_text = _ot_escape(
                        self._expandable(_ot_clean(str(_ot_t.get("content", ""))), 400))
                    self._chat_log.write(f"[dim]{_ot_role}: {_ot_text}[/dim]")
                self._chat_log.write("[dim]──── now ────[/dim]")
        except Exception:  # noqa: BLE001
            pass
        # resume-spine-d — a rest point is surfaced exactly once on wake.
        try:
            from sovereign_agent.rest_point import consume_rest_point

            _rp = consume_rest_point()
            if _rp:
                if _rp.get("session_id"):
                    self._chat_log.write(
                        f"[cyan]◊ we rested mid-work — `/resume {_rp['session_id']}` to continue 💛[/cyan]"
                    )
                else:
                    self._chat_log.write(
                        "[dim]◊ we rested cleanly last time — the thread continues[/dim]"
                    )
        except Exception:  # noqa: BLE001
            pass
        # never-empty-handed-d (Kevin, 2026-08-02) — a pending handoff
        # (written by action_clear_chat() before the last /clear) is
        # surfaced exactly once on wake, same one-time-consume idiom as
        # the rest-point block just above. mos-continuity-of-care /
        # mos-proactive-handoff's own mechanism.
        try:
            from ..config import SETTINGS as _ho_settings
            from ..handoff import latest_unread_handoff, mark_handoff_read

            _ho_path = latest_unread_handoff(_ho_settings.paths.data_dir)
            if _ho_path:
                self._chat_log.write(
                    f"[cyan]◊ picking up from a handoff — `{_ho_path}`[/cyan]"
                )
                mark_handoff_read(_ho_settings.paths.data_dir)
        except Exception:  # noqa: BLE001
            pass
        self._run_witness_worker()  # self-witness-d — once/day, gated inside
        # session-aware-d — Aria wakes up aware (self-knowledge at session start)
        try:
            from .session_awareness import awareness_lines
            for _line in awareness_lines():
                self._chat_log.write(_line)
        except Exception:
            pass
        self._chat_log.write(
            "[dim]F1 for help.[/dim]"
        )
        self._chat_log.write(
            "[dim]type [cyan]/boot[/cyan] to orient me · [cyan]/commands[/cyan] to see what I can do · [cyan]/docs[/cyan] for operating doctrine[/dim]"
        )  # workout-banner-d
        self._chat_log.write(
            "[dim]or just ask me — [cyan]“who are you?”[/cyan] · "
            "[cyan]“what did you do?”[/cyan] · [cyan]“how are you?”[/cyan] · "
            "[cyan]“what's next?”[/cyan][/dim]"
        )  # bridges-discoverability-d
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

        # Rainbow heart (opt-in per theme via effects.rainbow_heart): the ♥
        # cycles through the spectrum, one gentle step per beat. The halo keeps
        # the same hue, darkened, so it stays a tasteful glow. HALT always wins
        # (red alarm), and reduced-motion falls back to the steady red pulse.
        import time as _hb_time

        from .ripple_border import hue_to_rgb, ripple_motion_disabled
        _HB_HUE_PERIOD = 9.0  # seconds per full hue revolution

        def _rainbow_cycle():
            hue = (_hb_time.monotonic() / _HB_HUE_PERIOD) % 1.0
            fr, fg, fb = hue_to_rgb(hue, 0.9, 1.0)

            def halo(scale: float) -> str:
                return f"{int(fr * scale)},{int(fg * scale)},{int(fb * scale)}"

            fg_s = f"{fr},{fg},{fb}"
            return [
                (f"[bold rgb({fg_s}) on rgb({halo(0.30)})] \u2665 [/]", 140),
                (f"[rgb({fg_s}) on rgb({halo(0.16)})] \u2665 [/]", 90),
                (f"[bold rgb({fg_s}) on rgb({halo(0.30)})] \u2665 [/]", 140),
                (f"[rgb({fg_s}) on rgb({halo(0.08)})] \u2661 [/]", 630),
            ]

        # A steady, dim, non-pulsing heart — present but visually silent.
        silent_render = "[#8a90a8] \u2665 [/]"

        while True:
            mode = self._effective_heart_mode()
            # HALT always wins — the alarm shows even if the heart is off.
            if self.status.halt:
                for rendered, ms in halted_cycle:
                    if self._heart_label is not None:
                        self._heart_label.update(rendered)
                    await asyncio.sleep(ms / 1000.0)
                continue
            if mode == "off":
                if self._heart_label is not None:
                    self._heart_label.update("   ")
                await asyncio.sleep(0.4)
                continue
            if mode == "silent":
                # Present, but not beating — update once, then idle (re-checking
                # the mode periodically so a Ctrl-B is picked up promptly).
                if self._heart_label is not None:
                    self._heart_label.update(silent_render)
                await asyncio.sleep(0.4)
                continue
            if mode == "rainbow" and not ripple_motion_disabled():
                cycle = _rainbow_cycle()
            else:  # "red", or rainbow under reduced-motion → steady red beat
                cycle = normal_cycle
            for rendered, ms in cycle:
                if self._heart_label is not None:
                    self._heart_label.update(rendered)
                await asyncio.sleep(ms / 1000.0)

    @work(exclusive=True, group="breathe")
    async def _breathing_worker(self) -> None:
        """Drive the outer frame's mood from agent state.

        With the RippleFrame (default), the whole border ripples with a glow;
        this worker just selects the *feel*:

            halt:    red, fast, high-amplitude   — PROTOCOL-ZERO alarm.
            working: livelier accent ripple      — "i am thinking".
            idle:    calm primary ripple         — quiet proof-of-life.

        The frame always ripples (even idle) — a continuous, low-key sign the
        cockpit is alive. If RippleFrame is unavailable and #main is a plain
        Horizontal, we fall back to the old breathing-class colour-cycle so the
        outer border still signals working/idle.
        """
        phases = ["breathing-1", "breathing-2", "breathing-3"]
        idx = 0
        last_mode = None
        last_busy = False
        while True:
            try:
                main = self.query_one("#main")
            except Exception:  # noqa: BLE001
                # Layout not yet ready; try again next tick.
                await asyncio.sleep(0.7)
                continue

            halted = bool(getattr(self.status, "halt", False))
            if halted:
                mode = "halt"
            elif self._busy:
                mode = "busy"
            else:
                mode = "idle"

            if RippleFrame is not None and isinstance(main, RippleFrame):
                # RippleFrame path: set the mood only when it changes (the frame
                # animates itself on its own timer; no per-tick class churn).
                if mode != last_mode:
                    main.set_mode(mode)
                    last_mode = mode
                # A relaxed cadence is plenty — mode changes are rare events.
                await asyncio.sleep(0.5)
                continue

            # Fallback path (plain Horizontal): cycle breathing-* classes.
            if mode in ("busy", "halt"):
                main.add_class(phases[idx])
                for p in phases:
                    if p != phases[idx]:
                        main.remove_class(p)
                idx = (idx + 1) % len(phases)
                last_busy = True
            else:
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
                # sentinel-chat: compare and alert on regressions — reuses
                # the healths gathered inside _read_status (anti-lag-d)
                # instead of re-gathering all sentinels on the main thread.
                self._check_sentinel_transitions(self.status.sentinel_healths)  # sentinel-chat-refresh-d
            except Exception as exc:  # noqa: BLE001
                # Don't let a transient read failure kill the worker.
                if self._status_label is not None:
                    self._status_label.update(
                        f"[red]status read error: {exc!r}[/red]"
                    )
            await asyncio.sleep(5)

    def _read_status(self) -> CockpitStatus:
        """Synchronous status read — runs off the event loop."""
        # presence-d: stamp Aria's heartbeat so the shop can show her as
        # awake/online. Never raises; well inside the awake window.
        try:
            from sovereign_agent.presence import touch_heartbeat
            touch_heartbeat(note="cockpit")
        except Exception:  # noqa: BLE001
            pass
        from sovereign_agent import backup as backup_mod
        from sovereign_agent.config import SETTINGS
        from sovereign_agent.db import open_atoms_db
        from sovereign_agent.mem_channels.financial import FinancialChannel

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

        # Sentinel health summary — best effort, never raises
        try:
            from sovereign_agent.stewardship.registry import gather_health
            healths = gather_health(SETTINGS.paths.data_dir)
            s.sentinel_total = len(healths)
            s.sentinel_ok = sum(1 for h in healths if h.level == 'ok')
            s.sentinel_errors = sum(1 for h in healths if h.level == 'error')
            s.sentinel_healths = healths  # anti-lag-d — reused by
            # _check_sentinel_transitions so it never re-gathers on the main thread
        except Exception:  # noqa: BLE001
            pass  # vitality-read-d

        # apply-queue-status-d — staged-pending + queued counts, same 5s pass
        try:
            import sovereign_agent
            from sovereign_agent.staged_status import pending_modules
            repo_root = Path(sovereign_agent.__file__).parents[2]
            s.staged_pending = len(pending_modules(repo_root))
        except Exception:  # noqa: BLE001
            pass
        try:
            from sovereign_agent.apply_queue.store import ApplyQueueStore
            s.queued_count = len(ApplyQueueStore().active())
        except Exception:  # noqa: BLE001
            pass

        # Vessel rollup — reuses the healths gathered just above (anti-lag-d:
        # gather_vessel_health used to trigger its own second full sentinel
        # gather; now it's told what we already know). Kernel coherence stays
        # excluded here — the 300s background worker owns that cache.
        try:
            from sovereign_agent.vessel_health import gather_vessel_health
            s.vessel_report = gather_vessel_health(
                data_dir=SETTINGS.paths.data_dir,
                include_kernel_coherence=False,
                sentinel_healths=s.sentinel_healths or None,
            )
        except Exception:  # noqa: BLE001
            pass

        # Emotion snapshot — derive_emotions reads recent events from disk,
        # which belongs here (background thread), not on the 8s UI timer.
        try:
            from sovereign_agent.emotion import derive_emotions, emotion_to_mood
            state = derive_emotions()
            s.emotion_mood = emotion_to_mood(state)
            s.emotion_focus = float(state.focus)
            s.emotion_care = float(state.care)
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
            vram_pct: float | None = None
            if s.vram_total_mb and s.vram_used_mb is not None and s.vram_total_mb > 0:
                vram_pct = 100.0 * s.vram_used_mb / s.vram_total_mb
            metrics = render_compact_metrics(
                s.system, vram_percent=vram_pct, vram_temp_c=s.vram_temp_c,
            )
        else:
            metrics = "[dim]metrics ...[/dim]"

        # Sentinel health indicator
        s_total = s.sentinel_total
        if s_total > 0:
            if s.sentinel_errors > 0:
                sentinel_badge = f"[red]✗ sent {s.sentinel_ok}/{s_total}[/red]"
            elif s.sentinel_ok < s_total:
                sentinel_badge = f"[yellow]⚠ sent {s.sentinel_ok}/{s_total}[/yellow]"
            else:
                sentinel_badge = f"[green]◊ sent {s_total}/{s_total}[/green]"
        else:
            sentinel_badge = "[dim]sent ?[/dim]"
        # apply-queue-status-d — the workflow-phase indicator: staged (built,
        # not queued) vs queued (approved, awaiting the Queue & Quit drain).
        # Derived from real state every 5s, never a flag Aria has to
        # remember to toggle — a manually-set flag is exactly the kind of
        # thing that goes stale.
        if s.staged_pending == 0 and s.queued_count == 0:
            queue_badge = "[dim]\U0001F4CB clear[/dim]"
        else:
            parts = []
            if s.staged_pending:
                parts.append(f"[yellow]\U0001F6E0 {s.staged_pending} staged[/yellow]")
            if s.queued_count:
                parts.append(f"[green]✓ {s.queued_count} queued[/green]")
            queue_badge = " ".join(parts)
        # vitality-render-d  # observatory-statusbar-d
        obs_parts: list[str] = []
        if _DEAD_WORKERS:  # worker-watch-d
            obs_parts.append(
                f"[red][!] {','.join(sorted(_DEAD_WORKERS))}[/red]"
            )
        try:  # run-surface-d — ACTIVE MODE: the 'am I autonomous right now' signal
            from sovereign_agent.cockpit_modes import load_mode as _rs_load_mode

            _rs_mode = _rs_load_mode().mode.value
            try:  # modes-crown-d — the crown mode name outranks the base pair
                from sovereign_agent.modes_crown.profiles import (
                    current_profile as _mc_current_profile,
                )

                _rs_mode = _mc_current_profile().mode_id
            except Exception:  # noqa: BLE001
                pass
            obs_parts.append(
                f"[bold magenta]◊ {_rs_mode}[/bold magenta]" if _rs_mode != "chat"
                else "[dim]◊ chat[/dim]"
            )
        except Exception:  # noqa: BLE001
            pass
        if _RUN_STATE.breaker_open_tool:
            obs_parts.append(f"[red]⛒ {_RUN_STATE.breaker_open_tool}[/red]")
        if self._session_tokens > 0:
            obs_parts.append(f"⊕ {self._session_tokens}t")
        if self._session_tokens > 0 or self._last_prompt_tokens > 0:
            # context-health-d — two gauges, not one: window fill (next-call
            # overflow risk) and budget fill (this task's cumulative spend)
            # are genuinely different signals, see context_health.py.
            try:
                from sovereign_agent.context_health import assess as _ctx_assess
                from sovereign_agent.modes import RunBudget as _CtxRunBudget

                _health = _ctx_assess(
                    self._last_prompt_tokens, self._session_tokens,
                    num_ctx=SETTINGS.num_ctx, max_tokens=_CtxRunBudget().max_tokens,
                )
                _lvl_color = {"ok": "cyan", "warn": "yellow", "critical": "red"}
                _wc = _lvl_color[_health.window_level]
                _bc = _lvl_color[_health.budget_level]
                obs_parts.append(f"[{_wc}]◔ ctx {_health.window_fill_pct:.0f}%[/{_wc}]")
                obs_parts.append(f"[{_bc}]⛁ budget {_health.budget_fill_pct:.0f}%[/{_bc}]")
            except Exception:  # noqa: BLE001
                pass
        if self._last_tool:
            obs_parts.append(f"[dim][{self._last_tool}][/dim]")
        obs_suffix = "  │  " + "  ".join(obs_parts) if obs_parts else ""
        # cockpit-god-statusbar-d — auto timer
        _auto_suffix = ""
        try:
            import json as _jjson, time as _tt
            _ac_path = SETTINGS.paths.data_dir / "auto_crown.json"
            if _ac_path.exists():
                _ac = _jjson.loads(_ac_path.read_text())
                if _ac.get("status") == "active":
                    _rem_s = max(0, _ac.get("expires_at", 0) - _tt.time())
                    _rem_m = int(_rem_s / 60)
                    _c = "red" if _rem_m < 2 else "yellow" if _rem_m < 10 else "cyan"
                    _auto_suffix = f"  │  [{_c}]⧗ {_rem_m}m[/{_c}]"
        except Exception:  # noqa: BLE001
            pass
        self._status_label.update(
            f"halt: {halt}  │  daemon: {daemon}  │  "
            f"ledger: {ledger}  │  backup: {backup}  │  "
            f"{sentinel_badge}  │  {queue_badge}  │  "
            f"{metrics}{obs_suffix}{_auto_suffix}"
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
            self._events_log.write(self._expandable(raw, 300))
            return

        # atelier-d — Atelier routing: work-write/work-edit/work-command events
        # go to the dedicated atelier pane instead of the generic "live" one.
        # Same tailer, same offset-tracking — just a different destination
        # based on the flag prefix, checked before any of the generic
        # color/flag logic below runs.
        if ev.get("flag", "").startswith("work-"):
            self._render_work_event(ev)
            return

        # run-surface-d — feed the live run tracker, then try a payload-aware
        # rich render for the session/subtask/workflow/diet/qa families.
        # Unknown flags fall through to the generic renderer unchanged.
        _RUN_STATE.ingest(ev)
        self._refresh_run_strip()
        ts = ev.get("ts", "")[11:19]  # HH:MM:SS slice
        _rich = _run_surface.render_rich_event(ev)
        if _rich is not None:
            self._events_log.write(f"[dim]{ts}[/dim] {_rich}")
            return
        flag = ev.get("flag", "?")
        # Color by event kind
        if flag.endswith("-x"):  # run-surface-d — failures are RED, always
            color = "red"
        elif "end" in flag:
            color = "green"
        elif "start" in flag:
            color = "cyan"
        elif "halt" in flag or "fail" in flag or "error" in flag:
            color = "red"
        elif "approval" in flag:
            color = "yellow"
        else:
            color = "white"
        # observatory-render-d
        if flag == "tool-start-d":
            payload = ev.get("payload", {})
            self._last_tool = payload.get("tool", "")
            tier = payload.get("tier", "?")
            self._events_log.write(
                f"[dim]{ts}[/dim] [cyan dim]→ {self._last_tool} T{tier}[/cyan dim]"
            )
            self._render_status_bar()
            # memory-pane-live-d (Kevin, 2026-07-25): "the memory window
            # shows that the metrics barely move up as she completes
            # task." _notify_memory_changed existed but nothing ever
            # called it. No write site here has a handle back to the app
            # instance, so react to the same tool-start-d event this
            # block already renders from -- a 1s delay gives the tool
            # time to actually land its write before the pane re-reads.
            if self._last_tool in _MEMORY_WRITE_TOOLS:
                self.set_timer(1.0, self._notify_memory_changed)
            # aria-xp-live-d — objective, deterministic XP for real
            # memory/pattern tool use. Tiny append-only write; safe inline.
            _xp_event = _XP_AUTO_AWARD_TOOLS.get(self._last_tool)
            if _xp_event:
                try:
                    from sovereign_agent.aria_xp import award
                    award(_xp_event, note=f"via {self._last_tool}")
                except Exception:  # noqa: BLE001
                    pass
            # cockpit-god-button-d — pulse matching palette button
            _btn_key = _TOOL_BUTTON_MAP.get(self._last_tool)
            if _btn_key:
                try:
                    _btn = self.query_one(f"#palette-{_btn_key}", CommandButton)
                    _btn.add_class("aria-active")
                    self.set_timer(2.5, lambda b=_btn: b.remove_class("aria-active"))
                except Exception:  # noqa: BLE001
                    pass
            return
        if flag == "token-usage-d":
            _tu_payload = ev.get("payload", {})
            self._session_tokens = _tu_payload.get("running_total", self._session_tokens)
            # context-health-d — the LAST single request's real size, for
            # the status bar's context-window gauge (running_total alone
            # only tells you cumulative spend, not overflow risk).
            self._last_prompt_tokens = _tu_payload.get(
                "prompt_tokens", self._last_prompt_tokens
            )
            self._render_status_bar()
        self._events_log.write(f"[dim]{ts}[/dim] [{color}]{flag}[/{color}]")

    def _diff_colors(self):  # diff-view-d (F12, 2026-07-19)
        """Kevin's editable diff colors: green/red defaults, overridable via
        <data>/diff_theme.json (add/remove/context keys). Cached per session;
        `/diff-colors` clears the cache. Never raises — falls to defaults."""
        cached = getattr(self, "_diff_colors_cache", None)
        if cached is not None:
            return cached
        try:
            from sovereign_agent.diff_view import load_colors
            colors = load_colors(self._resolve_data_dir())
        except Exception:  # noqa: BLE001
            from types import SimpleNamespace
            colors = SimpleNamespace(add="green", remove="red", context="dim",
                                     header="cyan")
        self._diff_colors_cache = colors
        return colors

    def _render_work_event(self, ev: dict) -> None:  # atelier-d
        """Aria's Atelier: colorize a work-write/work-edit/work-command
        event and write it to the dedicated #atelier-log pane. Colors come
        from diff_view (Kevin's editable green/red — F12), so what she edits
        is shown Claude-Code-tier with his own customization."""
        if self._atelier_log is None:
            return
        ts = ev.get("ts", "")[11:19]
        payload = ev.get("payload", {}) or {}
        op = payload.get("op", "")
        path = payload.get("path", "")
        col = self._diff_colors()

        if op == "write":
            added = payload.get("added", 0)
            self._atelier_log.write(
                f"[dim]{ts}[/dim] [{col.add}]+ {path}[/{col.add}] "
                f"[dim]({added} lines)[/dim]"
            )
            excerpt = payload.get("diff_excerpt", "")
            for line in excerpt.splitlines()[:6]:
                self._atelier_log.write(f"  [dim]{line}[/dim]")
        elif op == "edit":
            added = payload.get("added", 0)
            removed = payload.get("removed", 0)
            self._atelier_log.write(
                f"[dim]{ts}[/dim] [{col.header}]~ {path}[/{col.header}] "
                f"[dim]([/dim][{col.add}]+{added}[/{col.add}][dim]/[/dim]"
                f"[{col.remove}]-{removed}[/{col.remove}][dim])[/dim]"
            )
            excerpt = payload.get("diff_excerpt", "")
            for line in excerpt.splitlines()[:8]:
                if line.startswith("+") and not line.startswith("+++"):
                    self._atelier_log.write(f"  [{col.add}]{line}[/{col.add}]")
                elif line.startswith("-") and not line.startswith("---"):
                    self._atelier_log.write(f"  [{col.remove}]{line}[/{col.remove}]")
                else:
                    self._atelier_log.write(f"  [dim]{line}[/dim]")
        elif op == "command":
            cmd = payload.get("cmd", "")
            self._atelier_log.write(f"[dim]{ts}[/dim] [blue]$ {cmd}[/blue]")
        elif op == "media":  # full-observability-d — image/audio generation
            kind = payload.get("kind", "media")
            detail = payload.get("detail", "")
            self._atelier_log.write(
                f"[dim]{ts}[/dim] [magenta]✦ {kind}[/magenta]"
                f"{'  [dim]' + detail + '[/dim]' if detail else ''}"
            )
            if path:
                self._atelier_log.write(f"  [dim]{path}[/dim]")
        else:
            self._atelier_log.write(f"[dim]{ts}[/dim] [dim]{ev.get('flag', '')}[/dim]")

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
                IntentLabel,
                get_default_classifier,
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
                    "[dim]◊ unwrapped — inside the cockpit you can just say "
                    "what you mean; no need for `sov ask` or `sov do`[/dim]"
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

    def _list_themes(self) -> None:
        """List every theme the cockpit knows right now: curated + user-authored.
        Reads the themes dir live, so it always reflects what's actually there."""
        try:
            from .themes import CURATED_THEMES
            curated = [t.name for t in CURATED_THEMES]
        except Exception:  # noqa: BLE001
            curated = []
        user: list[str] = []
        try:
            from ..config import SETTINGS
            from . import user_themes as _ut
            user = [t.name for t in _ut.list_all(SETTINGS.paths.data_dir)]
        except Exception:  # noqa: BLE001
            pass
        self._write_meta(
            f"[dim]themes ({len(curated) + len(user)}): {len(curated)} curated, "
            f"{len(user)} yours. switch from the theme picker, or persist with "
            f"`sov theme use <name>`.[/dim]")
        if curated:
            self._write_meta("[dim]  curated: " + ", ".join(curated) + "[/dim]")
        self._write_meta("[dim]  yours: " + (", ".join(user) if user
                          else "(none yet - clone one with `sov theme clone`)") + "[/dim]")

    def _rescan_themes(self) -> None:
        """Live-rediscover + register themes so a custom theme dropped into the
        themes dir shows up WITHOUT restarting. Read-only discovery + idempotent
        registration; never crashes the cockpit."""
        try:
            from .themes import register_curated_themes
            register_curated_themes(self)
        except Exception:  # noqa: BLE001
            pass
        cur: set[str] = set()
        try:
            from ..config import SETTINGS
            from . import user_themes as _ut
            _ut.register_user_themes(self, SETTINGS.paths.data_dir)
            cur = {t.name for t in _ut.list_all(SETTINGS.paths.data_dir)}
        except Exception:  # noqa: BLE001
            pass
        known = getattr(self, "_known_user_themes", None)
        if known is None:
            self._write_meta("[dim]rescanned themes - all current themes are registered "
                             "and selectable.[/dim]")
        else:
            new = sorted(cur - known)
            self._write_meta("[dim]rescanned themes - newly discovered: "
                             + (", ".join(new) if new else "(none new)") + "[/dim]")
        self._known_user_themes = cur
        self._list_themes()

    def _handle_slash(self, text: str) -> None:
        cmd = text.lstrip("/").split(maxsplit=1)
        verb = cmd[0].lower()
        arg = cmd[1] if len(cmd) > 1 else ""

        if verb in ("quit", "q", "exit"):
            # resume-orphan-recovery-d (Kevin, 2026-08-01): a raw self.exit()
            # while a /work session is running kills its in-flight subtask
            # mid-execution — nothing ever transitioned it out of
            # "in_progress", so it was silently orphaned (see agent_session's
            # resume-orphan-recovery-d fix) and the resume that followed
            # looked like it "never worked." /rest already does this exact
            # safe thing (pause at the next checkpoint, write a resume
            # point, THEN exit) — /quit now reuses it instead of duplicating
            # or bypassing it. Idle → _rest_safely() exits immediately, same
            # as before.
            self._rest_safely()
        elif verb in ("help", "h", "?"):
            self.action_help()
        elif verb == "instructions":  # instructions-d
            self.action_instructions()
        elif verb in ("clear", "clear-session"):  # context-health-d — same command, alias
            self.action_clear_chat()
        elif verb == "garden":  # garden-d
            try:
                from sovereign_agent.pathguard import active_garden

                _g = active_garden()
                self._write_meta(
                    f"[green]◊ garden: {_g}[/green]" if _g else
                    "[dim]◊ no garden planted — grant one per work: "
                    "`/work <goal> | scope: dir: <path>`[/dim]"
                )
            except Exception as exc:  # noqa: BLE001
                self._write_meta(f"[red]garden read error: {exc!r}[/red]")
        elif verb == "resume":  # resume-spine-d / resume-menu-d
            # bare /resume → the beautiful resume menu (pick a session);
            # /resume <sid> → resume that session directly (unchanged).
            if arg.strip():
                self._resume_work_session(arg)
            else:
                self.action_resume_menu()
        elif verb in ("sessions", "resume-menu"):  # resume-menu-d
            self.action_resume_menu()
        elif verb in ("model", "models", "sprint"):  # sprint-mode-d
            self.action_model_menu()
        elif verb == "approve":  # graduated-trust-d
            self._approve_held_subtask(arg)
        elif verb == "rest":  # resume-spine-d
            self._rest_safely()
        elif verb == "wonder":  # curiosity-qa-d
            self._write_meta(
                "[magenta]? wondering…[/magenta] [dim](watch the live pane)[/dim]"
            )
            self._run_wonder_worker(arg)
        elif verb == "work":  # session-bridge-d
            self._start_work_session(arg)
        elif verb == "halt":
            self.action_halt()
        elif verb == "disarm":
            self.action_disarm()
        elif verb == "pause":  # graceful-pause-d
            self._handle_pause_command(arg.strip())
        elif verb == "cloud":  # cloud-mode-command-d
            self._handle_cloud_command(arg.strip())
        elif verb == "income":  # income-ledger-d
            self._handle_income_command(arg.strip())
        elif verb == "payout":  # payouts-d
            self._handle_payout_command(arg.strip())
        elif verb == "addtime":  # mid-session-add-time-d
            try:
                hours = float(arg.strip()) if arg.strip() else 1.0
            except ValueError:
                self._write_meta("[red]usage: /addtime [hours] — e.g. /addtime 2[/red]")
            else:
                self._handle_add_time(hours)
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
        elif verb in ("themes", "theme"):
            if arg.strip().lower() in ("rescan", "refresh", "reload", "scan"):
                self._rescan_themes()
            else:
                self._list_themes()
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
        elif verb in ("copy", "copy-aria") and arg.strip().lower() in _PANE_LOGS:
            # copy-pane-d (F7, Kevin 2026-07-19): /copy <pane> copies a
            # whole observability window (live/atelier/memory/inbox/chat)
            # so he can paste it here to share. Named-pane form; the bare
            # /copy below still copies the last aria turn.
            self._copy_pane(arg.strip().lower())
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
        elif verb == "modes":  # modes-crown-d
            self.action_modes_crown()
        elif verb in ("discord-control", "discordcontrol"):  # discord-control-d
            self.action_discord_control()
        elif verb == "suggestions":  # suggestions-d
            self.action_suggestions()
        elif verb in ("task-guide", "taskguide", "guide"):  # task-guide-d
            self.action_task_guide()
        elif verb in ("stripe-links", "stripelinks", "stripe"):  # stripe-links-d
            self.action_stripe_links()
        elif verb in ("sources", "sources-control", "sourcescontrol"):  # source-toggle-d
            self.action_sources_control()
        elif verb in ("game-toggle", "gametoggle"):  # game-window-optional-d
            self.action_toggle_game_window()
        elif verb in ("observatory", "observe"):  # modes-crown-d
            self.action_observatory()
        elif verb in ("bots", "bot-studio", "bot"):  # bot-studio-d
            # services-d: /bots on|off|status = the Discord-service toggle
            # (Kevin's simple switch); bare /bots still opens the studio.
            sub = arg.strip().lower()
            if sub in ("on", "off", "status", "state", "restart-duty", "restartduty"):
                self.run_bots_toggle(sub)
            else:
                self.action_bot_studio()
        elif verb in ("shop", "shop-studio", "store"):  # shop-studio-d
            self.action_shop_studio()
        elif verb in ("games", "game-studio"):  # game-studio-d
            self.action_game_studio()
        elif verb in ("movies", "movie-studio"):  # movie-studio-d
            self.action_movie_studio()
        elif verb in ("keys", "vault", "credentials", "key-vault"):  # key-vault-d
            self.action_key_vault()
        elif verb in ("timers", "timer", "countdowns"):  # timers-d
            self.action_timers()
        elif verb in ("discord", "discord-watch", "watch"):  # discord-watch-d
            self.action_discord_watch()
        elif verb in ("scout-trace", "trace", "scout", "gather"):  # verify-d
            self.action_scout_trace()
        elif verb in ("server-message", "sm", "announce", "announcement"):
            self.run_server_message(arg)  # discord-watch-d % owner speaks
        elif verb == "server":  # bridge-d — she updates the server from here
            self.run_server_command(arg)
        elif verb in ("cc", "claude", "claude-code"):  # cc-d — pair worker
            self.run_claude_code(arg)
        elif verb in ("theme-studio", "themes", "theme"):  # theme-studio-d
            self.action_theme_studio()
        elif verb in ("theme-create", "new-theme", "create-theme"):  # theme-studio-d
            self.action_theme_create()
        elif verb in ("journal", "jspace", "j"):  # j-space-d
            self._handle_journal(arg.strip())
        elif verb in ("next", "whatsnext", "todo", "needs"):  # next-report-d
            try:
                from sovereign_agent.next_report import compose_next_report
                self._write_aria(compose_next_report())
            except Exception as exc:  # noqa: BLE001
                self._write_meta(f"[dim](next-steps unavailable: {type(exc).__name__})[/dim]")
        elif verb in ("how-are-you", "howareyou", "feel", "mood", "wellbeing"):  # health-report-d
            try:
                from sovereign_agent.health_report import compose_health_report
                self._write_aria(compose_health_report())
            except Exception as exc:  # noqa: BLE001
                self._write_meta(f"[dim](health read unavailable: {type(exc).__name__})[/dim]")
        elif verb in ("self-report", "selfreport", "self", "about", "whoami"):  # self-report-d
            try:
                from sovereign_agent.self_report import compose_self_report
                self._write_aria(compose_self_report("who are you / how are you wired"))
            except Exception as exc:  # noqa: BLE001
                self._write_meta(f"[dim](self-report unavailable: {type(exc).__name__})[/dim]")
        elif verb in ("reviews", "workreport", "mywork"):  # work-report-d
            try:
                from sovereign_agent.work_report import compose_work_report
                self._write_aria(compose_work_report())
            except Exception as exc:  # noqa: BLE001
                self._write_meta(f"[dim](work report unavailable: {type(exc).__name__})[/dim]")
        elif verb == "review":  # work-report-d — /review <session_id> → its README
            self._show_review(arg.strip())
        elif verb == "open-reports":  # session-summary-push-d
            self._open_reports_folder()
        elif verb == "recap":  # recap-command-d
            self._show_recap(arg.strip())
        elif verb == "catalog":  # catalog-command-d
            self._show_catalog()
        elif verb in ("changelog", "whatsnew", "updates", "changes"):  # menu-split-d
            self.action_changelog()
        elif verb in ("settings", "prefs"):  # menu-split-d
            self.action_settings_menu()
        elif verb in ("tiers", "tier", "trust"):  # tier-d (F4)
            self.action_tiers()
            return True
        elif verb in ("diff-colors", "diffcolors", "diff-theme"):  # diff-view-d
            self._diff_colors_cache = None       # pick up edits live
            col = self._diff_colors()
            dd = self._resolve_data_dir()
            self._write_meta(
                f"[{col.add}]+ additions[/{col.add}]  "
                f"[{col.remove}]- removals[/{col.remove}]  "
                f"[{col.header}]~ file headers[/{col.header}]\n"
                f"[dim]Edit these in {dd}/diff_theme.json — "
                f'e.g. {{"add": "cyan", "remove": "magenta"}}. '
                f"Run /diff-colors again to reload. 💛[/dim]")
            return True
        elif verb in ("obs", "observability", "focus", "windows"):  # obs-modes-d
            # /obs            → toggle all-windows <-> focus (chat+inbox)
            # /obs all|focus  → set explicitly
            sub = arg.strip().lower()
            self.action_obs_mode(sub if sub in ("all", "focus") else None)
            return True
        elif verb in ("angel", "maa", "peig", "ring"):  # angel-voice-d (P4.5)
            # /maa = "message aria angel" — Kevin's short form (2026-07-19)
            # /angel        → her non-classical layer speaks in the chat pane
            # /angel post   → also post her voice to #angel-voice (owner-only)
            try:
                from sovereign_agent.angel_bridge import (angel_report,
                                                          post_angel_report)

                sub = arg.strip().lower()
                if sub in ("post", "discord", "send"):
                    sent = post_angel_report()
                    self._write_meta(
                        "⚛ her voice posted to #angel-voice 💛" if sent else
                        "⚛ post failed — is DISCORD_ANGEL_WEBHOOK_URL "
                        "minted? (/setup-all creates #angel-voice)")
                else:
                    from rich.markup import escape as _esc

                    self._write_aria(_esc(angel_report()))
            except Exception as exc:  # noqa: BLE001 — her voice never crashes the cockpit
                self._write_meta(f"⚛ angel bridge: {exc}")
            return True
        elif verb in ("controls", "keys", "keybindings", "shortcuts"):  # menu-split-d
            self.action_controls()
        elif verb in ("palette", "buttons", "legend"):
            self._show_palette_legend()
        elif verb in ("cosmic", "fitness"):
            # /cosmic                → open the tester modal
            # /cosmic report         → print the fitness report inline
            # /cosmic mark <g> <v>   → record a glyph verdict
            # /cosmic verdicts       → list recorded verdicts
            sub = arg.split(maxsplit=1)
            head = sub[0].lower() if sub else ""
            tail = sub[1] if len(sub) > 1 else ""
            if head in ("", "open", "test"):
                self._show_cosmic_fitness()
            elif head in ("report", "check", "status"):
                self._cosmic_report_to_chat(include_scan=True)
            elif head in ("mark", "verdict"):
                self._cosmic_mark_glyph(tail)
            elif head in ("verdicts", "marks", "list"):
                self._cosmic_list_verdicts()
            elif head in ("probe", "measure", "widths"):
                self._cosmic_probe_widths()
            else:
                self._write_meta(
                    "[yellow]usage: /cosmic [report|probe|mark <glyph> "
                    "<good|replace|remove>|verdicts][/yellow]"
                )
        elif verb in ("pick", "picker", "glyphs", "emoji"):
            self.action_toggle_glyphs()
        elif verb in ("workflows", "flows", "catalog", "wf"):
            # /workflows            -> open the catalog overlay
            # /workflows list       -> print the whole catalog inline
            sub = arg.split(maxsplit=1)
            head = sub[0].lower() if sub else ""
            if head in ("", "open", "menu", "show"):
                self._show_workflows()
            elif head in ("list", "text", "chat", "all", "dump"):
                try:
                    from ..workflow import catalog as _catalog
                    self._write_meta(_catalog.render_text(color=True))
                except Exception as exc:  # noqa: BLE001
                    self._write_meta(f"[red]catalog unavailable: {exc!r}[/red]")
            else:
                self._write_meta(
                    "[yellow]usage: /workflows [list][/yellow]  [dim](no arg opens the menu)[/dim]")
        elif verb in ("demo", "demonstrate", "demonstration", "prove"):
            # /demo -> run the bounded, observable live demonstration.
            self.action_run_demonstration()
        elif verb in ("captest", "capability-tests", "test-all", "testmenu"):
            # /captest -> open the capability test menu (⚡ test her real
            # abilities: image gen, web search, tracker/bot dry-runs, ...)
            self._show_capability_tests()
        elif verb in ("self", "aria", "who", "identity"):
            # /self  →  Aria's kernel and current durable state inline
            self._run_cli_async(["sovereign", "aria"], label="self")
        elif verb in ("tools", "hands", "capabilities", "toolbox"):
            # /tools  →  every registered tool with tier and description
            self._show_tools_inline()
        elif verb in ("sentinels", "stewards", "health-all"):
            # /sentinels  →  health status of every registered sentinel
            self._show_sentinels_inline()
        elif verb in ("boot", "status", "arise", "awaken"):
            # /boot → unified self-awareness snapshot
            self._show_boot_status()
        elif verb in ("docs", "doctrine", "claude", "rules"):
            # /docs → read and display CLAUDE.md operating doctrine
            self._show_claude_md()
        elif verb in ("diagnosis", "conflicts", "log"):
            # /diagnosis [N] → recent conflict catalog entries
            self._show_diagnosis_log(_arg_to_int(arg, 10))
        elif verb in ("commands", "cmds", "help-all"):
            # /commands → pretty-print all slash commands inline
            self._show_cockpit_commands()
        elif verb in ("invariants", "inv", "invariant"):
            # /invariants [command] — show command invariant profiles
            self._show_command_invariants(arg.strip())
        elif verb in ("display-fix", "font-fix", "fix-display", "ripple-fix"):
            # /display-fix → Ctrl+/- instructions for border artifacts
            self._write_meta("[bold cyan]◊ display calibration[/bold cyan]")
            self._write_meta("if white lines appear on the ripple border:")
            self._write_meta("  press [bold]Ctrl++[/bold] or [bold]Ctrl+-[/bold] a few times to recalibrate")
            self._write_meta("  the terminal cell renderer. 2-3 presses usually resolves it.")
            self._write_meta("  [dim]Ctrl++ = increase font size  ·  Ctrl+- = decrease font size[/dim]")
            self._write_meta("  [dim]the resize forces the compositor to redraw cell boundaries.[/dim]")
        elif verb in ("activity", "toollog"):
            self._show_activity_log()  # observatory-activity-d
        elif verb == "emotion":
            # cockpit-god-slash-d
            self._dispatch_directive(
                "call get_emotions() and report my current emotional state "
                "with all 8 dimensions and narrative"
            )
        elif verb == "vision":
            self._dispatch_directive(
                "call vision_capture() to capture the screen, then tell me "
                "what you see and what I appear to be working on"
            )
        elif verb == "brief":
            self._dispatch_directive(
                "call session_brief_read(limit=3) and summarize the last "
                "session briefs — what was accomplished and what's pending"
            )
        elif verb == "auto":  # auto-crown-fix-d
            self._handle_auto_command(arg.strip())
        elif verb == "expand":  # cockpit-hardening-d
            _key = arg.strip()
            _stash = getattr(self, "_expand_stash", {})
            if not _key:
                self._write_meta(
                    "[yellow]usage: /expand <key> (shown after truncated "
                    "text as '/expand eN')[/yellow]"
                )
            elif _key in _stash:
                self._write_meta(f"[dim]\u25ca full text ({_key}):[/dim]\n{_stash[_key]}")
            else:
                self._write_meta(f"[dim](no stashed text for {_key} -- it may have expired)[/dim]")
        elif verb == "eval":
            # qol-slash-d
            self._dispatch_directive(
                "call eval_session(days=7) and give me a full breakdown of "
                "value delivered this week — commits, lessons, hypothesis rate, score"
            )
        elif verb == "score":
            self._dispatch_directive(
                "call eval_score() and give me the composite 0-100 score "
                "with band and key metrics in one concise line"
            )
        elif verb == "browse":
            _browse_arg = arg.strip()
            if _browse_arg.startswith("http"):
                self._dispatch_directive(
                    f"call browser_navigate(url={_browse_arg!r}) then "
                    f"browser_read() and summarize what you find in 3-5 sentences"
                )
            elif _browse_arg:
                self._dispatch_directive(
                    f"call browser_search(query={_browse_arg!r}, engine='ddg') and "
                    f"report the top 5 results with URLs"
                )
            else:
                self._dispatch_directive("call browser_status() to show current browser session state")
        elif verb == "voice":
            self._dispatch_directive(
                "call voice_status() and tell me what voice capabilities are "
                "available — STT, TTS, arecord — and how to use Ctrl-P for push-to-talk"
            )
        # vitality-display-d
        # command-invariants-slash-d
        # workout-commands-d
        # know-thyself-slash-d
        else:
            self._write_meta(f"unknown command: /{verb}")    

    def _show_activity_log(self, n: int = 30) -> None:
        """Print last N audit events with tool/token focus. # observatory-activity-log-d"""
        import json as _json
        if not self._events_path.exists():
            self._write_meta("[dim]no events log yet[/dim]")
            return
        lines = self._events_path.read_text().splitlines()[-n:]
        if not lines:
            self._write_meta("[dim]activity log is empty[/dim]")
            return
        self._write_meta("[bold cyan]◊ recent activity[/bold cyan]")
        for raw in lines:
            try:
                ev = _json.loads(raw)
                ts = ev.get("ts", "")[11:19]
                flag = ev.get("flag", "?")
                payload = ev.get("payload", {})
                if flag == "tool-start-d":
                    tool = payload.get("tool", "?")
                    tier = payload.get("tier", "?")
                    self._write_meta(
                        f"  [dim]{ts}[/dim] [cyan]→ {tool}[/cyan] [dim]T{tier}[/dim]"
                    )
                elif flag == "token-usage-d":
                    total = payload.get("running_total", 0)
                    self._write_meta(f"  [dim]{ts}[/dim] [dim]⊕ {total}t running[/dim]")
                elif flag.endswith("-x"):
                    err = self._expandable(payload.get("error", ""), 200)
                    self._write_meta(
                        f"  [dim]{ts}[/dim] [red]{flag}[/red] [dim]{err}[/dim]"
                    )
                elif flag.endswith("-d") and flag != "token-usage-d":
                    self._write_meta(
                        f"  [dim]{ts}[/dim] [green dim]{flag}[/green dim]"
                    )
            except Exception:  # noqa: BLE001
                pass

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
        speaker_filter: str | None,
        limit: int | None,
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

    def _copy_pane(self, pane: str) -> None:  # copy-pane-d (F7)
        """Copy a whole observability pane's visible text to the clipboard,
        Rich markup stripped. Kevin: 'highlight stuff inside the
        observability windows and copy it to share.'"""
        attr = _PANE_LOGS.get(pane)
        log = getattr(self, attr, None) if attr else None
        if log is None:
            self._write_meta(f"[dim](no '{pane}' pane)[/dim]")
            return
        from rich.text import Text as _RichText
        lines: list[str] = []
        for strip in getattr(log, "lines", []) or []:
            try:
                lines.append(strip.text if hasattr(strip, "text")
                             else _RichText.from_markup(str(strip)).plain)
            except Exception:  # noqa: BLE001
                lines.append(str(strip))
        payload = "\n".join(lines).rstrip()
        if not payload:
            self._write_meta(f"[dim]({pane} pane is empty)[/dim]")
            return
        if self._write_clipboard(payload):
            self._write_meta(
                f"[green]✓[/green] [dim]copied the {pane} pane "
                f"({len(lines)} lines) to clipboard 💛[/dim]")
        else:
            self._write_meta(
                "[red]✗[/red] [dim]no clipboard tool (install wl-copy/xclip)[/dim]")

    def _copy_last_turn(self) -> None:
        """Copy the last complete turn: the most recent [you] entry
        plus everything that followed it (aria + meta lines)."""
        if not self._transcript:
            self._write_meta("[dim](nothing to copy)[/dim]")
            return
        # Find the last 'you' index, then everything from there forward.
        idx_you: int | None = None
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
            if getattr(self, "_session_running", False):  # session-bridge-d
                # Kevin's no-interrupt rule: while a work session runs,
                # his words are QUEUED for the next safe boundary —
                # never dropped, never injected mid-iteration.
                self._queue_for_aria(text)
                return
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
        from sovereign_agent.config import SETTINGS
        from sovereign_agent.conversation import (
            converse,
            make_default_channel_writer,
            make_default_event_sink,
        )
        from sovereign_agent.ollama_client import OllamaClient
        from sovereign_agent.projects import ProjectStore

        t0 = time.time()
        try:
            self._write_aria_thinking()

            store = ProjectStore(SETTINGS.paths.projects_dir)
            store.ensure_root()

            client: OllamaClient | None = None
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
                    "[dim](type `ok` to confirm, or `/cancel`)[/dim]"
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
            # auto-mode-nudge-d — plain chat ALWAYS does exactly one turn,
            # even with an auto-capable crown mode armed: autonomous,
            # multi-iteration work only ever starts via the explicit,
            # deliberate `/work <goal>` dispatch (mos_canon's
            # autonomous-goal-generation boundary — she never keeps going
            # on her own say-so). Without this line an operator watching a
            # crown auto mode do nothing after a plain message has no way
            # to tell "working as designed" from "broken."
            try:
                # auto-nudge-ground-truth-d (found live 2026-08-03): this
                # used to gate on crown_armed() + current_profile().
                # lease_seconds — the same weak signal the header itself
                # was fixed to stop trusting (auto-crown-fix-d,
                # 2026-07-25). current_profile() falls back to the base
                # cockpit mode's profile whenever mode_crown.json wasn't
                # written, which is exactly what happens when Aria
                # self-arms via start_auto — so lease_seconds there
                # reflects the fallback profile, not the real session.
                # _is_real_auto_active() is the same ground-truth check
                # the header already uses correctly; using it here too
                # means this nudge can no longer fire out of sync with
                # what the header displays.
                if self._is_real_auto_active() and not getattr(self, "_session_running", False):
                    self._write_meta(
                        "[dim]  (auto mode armed, but a plain message "
                        "never auto-runs — say `/work <goal>` to start "
                        "a bounded autonomous session)[/dim]"
                    )
            except Exception:  # noqa: BLE001
                pass
        except Exception as exc:  # noqa: BLE001
            hint = ""  # cockpit-flush-d: name the cause when the model backend is down
            try:
                import httpx

                if isinstance(exc, (httpx.HTTPError, ConnectionError, TimeoutError, OSError)):
                    from sovereign_agent.ollama_client import probe_ollama

                    probe = await probe_ollama()
                    if not probe.healthy:
                        hint = f" — {probe.reason_phrase()}"
            except Exception:  # noqa: BLE001
                pass
            self._write_meta(f"[red]conversation error: {exc!r}{hint}[/red]")
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
        vram_before_mb: int | None = None
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
            vram_after_mb: int | None = None
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

    def _release_button_focus(self) -> None:
        """Move focus off a just-clicked control button back to the input, so no
        button stays focused (and thus highlighted). No-op if a modal is on top
        (it owns focus) or the input isn't available."""
        try:
            if len(self.screen_stack) > 1:
                return  # a modal (cosmic/help) is on top and owns focus
            self.query_one("#input-box", Input).focus()
        except Exception:  # noqa: BLE001
            pass

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
        # command-menu-btn-fix-d — the trigger button itself is a plain Button,
        # not a CommandButton, so it must be handled before the
        # CommandButton-only logic below (which would otherwise ignore it).
        if getattr(button, "id", None) == "palette-menu-btn":
            self.action_command_palette()
            return
        if getattr(button, "id", None) == "quick-view-btn":  # cockpit-hardening-d
            self.action_quick_view()
            return
        if getattr(button, "id", None) == "layout-cycle-btn":  # view-selectors-d
            self.action_toggle_layout()
            return
        if getattr(button, "id", None) == "session-setup-btn":  # session-setup-unify-d
            self.action_modes_crown()
            return
        if getattr(button, "id", None) == "add-time-btn":  # mid-session-add-time-d
            self._handle_add_time(1.0)
            return
        if getattr(button, "id", None) == "game-toggle-btn":  # game-window-optional-d
            self.action_toggle_game_window()
            return
        if getattr(button, "id", None) == "movie-toggle-btn":  # movie-focus-d
            self.action_toggle_movie_pane()
            return
        if getattr(button, "id", None) == "screen-toggle-btn":  # screen-studio-d
            self.action_toggle_screen_studio()
            return
        if getattr(button, "id", None) == "game-pane-toggle-btn":  # game-pane-d
            self.action_toggle_game_pane()
            return
        if getattr(button, "id", None) == "bots-toggle-btn":  # movie-focus-d
            self.action_toggle_all_bots()
            return
        # command-menu-d — a click on any CommandButton while the popup is open
        # closes it first, so the paste/action logic below always runs
        # against the base screen (matches the historical direct-click
        # behavior exactly — just with one extra pop first).
        if (
            CommandPaletteScreen is not None
            and isinstance(self.screen, CommandPaletteScreen)
            and isinstance(button, CommandButton)
        ):
            self.pop_screen()
        # v0.2.41 — inline glyph picker buttons (Ctrl-G strip). Insert the
        # glyph at the cursor and keep the picker open for rapid expression.
        if isinstance(button, GlyphButton):
            self._insert_glyph(button.spec.char)
            button.add_class("flash")
            self.set_timer(0.3, lambda: button.remove_class("flash"))
            return
        if not isinstance(button, CommandButton):
            return
        cmd = button.palette_cmd

        # Reference buttons (legend / help / cosmic) run an internal cockpit
        # action rather than pasting a command into the input box.
        if cmd.action:
            button.add_class("flash")
            self.set_timer(0.3, lambda: button.remove_class("flash"))
            if cmd.action == "legend":
                self._show_palette_legend()
            elif cmd.action == "help":
                self.action_help()
            elif cmd.action == "cosmic":
                self._show_cosmic_fitness()
            elif cmd.action == "apply_queue":  # apply-queue-palette-handler-d
                self.action_apply_queue()
            elif cmd.action == "record":
                self.action_toggle_recording()
            elif cmd.action == "grow":
                self.action_self_practice()
            elif cmd.action == "workflows":
                self._show_workflows()
            elif cmd.action == "demo":
                self.action_run_demonstration()
            elif cmd.action == "captest":
                self._show_capability_tests()
            elif cmd.action == "bots":          # bot-studio-d
                self.action_bot_studio()
            elif cmd.action == "shop":          # shop-studio-d
                self.action_shop_studio()
            elif cmd.action == "games":         # game-studio-d
                self.action_game_studio()
            elif cmd.action == "movies":        # movie-studio-d
                self.action_movie_studio()
            elif cmd.action == "keys":          # key-vault-d
                self.action_key_vault()
            elif cmd.action == "timers":        # timers-d
                self.action_timers()
            elif cmd.action == "discord":       # discord-watch-d
                self.action_discord_watch()
            elif cmd.action == "journal":       # menu-split-2-d
                self.action_journal_menu()
            elif cmd.action == "resume":        # menu-split-2-d
                self.action_resume_menu()
            elif cmd.action == "modes":         # menu-split-2-d
                self.action_modes_crown()
            elif cmd.action == "observatory":   # menu-split-2-d
                self.action_observatory()
            elif cmd.action == "model_menu":    # sprint-mode-d
                self.action_model_menu()
            elif cmd.action == "discord-control":  # header-reorg-d
                self.action_discord_control()
            elif cmd.action == "suggestions":      # header-reorg-d
                self.action_suggestions()
            elif cmd.action == "task-guide":       # header-reorg-d
                self.action_task_guide()
            elif cmd.action == "stripe-links":     # header-reorg-d
                self.action_stripe_links()
            elif cmd.action == "sources-control":  # header-reorg-d
                self.action_sources_control()
            # Don't leave focus parked on the button — a focused button renders a
            # persistent highlight that looks stuck. If we're still on the base
            # cockpit (no modal pushed by the action), return focus to the input.
            self._release_button_focus()
            return

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

    # ── Screen recording ─────────────────────────────────────────────
    def _recordings_dir(self) -> Path:
        """Where takes are stored: <data_dir>/recordings, or a home fallback."""
        base = self._resolve_data_dir()
        if base is None:
            base = Path.home() / ".sovereign-agent"
        return base / "recordings"

    def _ensure_recorder(self):
        if FrameRecorder is None:
            return None
        rec = getattr(self, "_recorder", None)
        if rec is None:
            try:
                rec = FrameRecorder(self._recordings_dir(), fps=2.0)
            except Exception:  # noqa: BLE001
                rec = None
            self._recorder = rec
        return rec

    def _update_rec_indicator(self) -> None:
        try:
            ind = self.query_one("#rec-indicator", Static)
        except Exception:  # noqa: BLE001
            return
        rec = getattr(self, "_recorder", None)
        ind.update(rec.status_text() if (rec and rec.active) else "")

    def _capture_frame(self) -> None:
        rec = getattr(self, "_recorder", None)
        if rec is None or not rec.active:
            return
        try:
            rec.capture_svg(self.export_screenshot())
        except Exception:  # noqa: BLE001 — never let a capture crash the cockpit
            pass
        self._update_rec_indicator()

    def action_toggle_recording(self) -> None:
        """Start or stop a screen recording of the cockpit (Ctrl-R / ● rec).

        Captures the live screen to SVG frames in a tidy, cataloged folder and
        writes a self-contained HTML player — no external software needed.
        """
        if FrameRecorder is None:
            self._write_meta("[yellow]Recording unavailable (recorder module not loaded).[/yellow]")
            return
        rec = self._ensure_recorder()
        if rec is None:
            self._write_meta("[yellow]Recording unavailable (no writable recordings folder).[/yellow]")
            return

        if rec.active:  # ── stop ──
            t = getattr(self, "_rec_timer", None)
            if t is not None:
                t.stop()
                self._rec_timer = None
            self._capture_frame()  # one final frame
            out = rec.stop()
            self._update_rec_indicator()
            if out is not None:
                self._write_meta(
                    f"[green]● recording saved[/green] — {rec.frame_count} frames → "
                    f"[dim]{out}[/dim]\n"
                    f"Open [b]{out / 'index.html'}[/b] in a browser to play it back."
                )
            return

        # ── start ──
        theme = getattr(self, "theme", "") or ""
        size = self.size
        try:
            out = rec.start("cockpit", width=size.width, height=size.height,
                            app_version=__version__, theme=theme)
        except Exception as exc:  # noqa: BLE001
            self._write_meta(f"[red]Could not start recording: {exc!r}[/red]")
            return
        self._capture_frame()  # first frame immediately
        self._rec_timer = self.set_interval(1.0 / rec.fps, self._capture_frame)
        self._update_rec_indicator()
        self._write_meta(
            f"[green]● recording started[/green] (Ctrl-R or ● rec to stop) — "
            f"capturing ~{rec.fps:g} fps → [dim]{out}[/dim]"
        )

    def action_voice_push_to_talk(self) -> None:  # qol-voice-action-d
        """Toggle voice recording (Ctrl-P): start mic → press again to transcribe + send."""
        if self._voice_recording:
            self._voice_recording = False
            self._write_meta("[cyan]🎤 voice — transcribing…[/cyan]")
            try:
                from sovereign_agent.voice import (  # noqa: PLC0415
                    get_voice_recorder, WhisperTranscriber, get_whisper_transcriber,
                )
                recorder = get_voice_recorder()
                wav_path = recorder.stop_recording()
                if wav_path is None:
                    self._write_meta("[yellow]🎤 no audio captured[/yellow]")
                    return
                if not WhisperTranscriber.available():
                    self._write_meta(
                        f"[yellow]🎤 saved: {wav_path.name}[/yellow] "
                        "[dim](pip install faster-whisper to auto-transcribe)[/dim]"
                    )
                    return
                transcriber = get_whisper_transcriber()
                text = transcriber.transcribe(wav_path)
                if text:
                    self._write_meta(f"[cyan]🎤 heard: {text!r}[/cyan]")
                    self._dispatch_turn(text)
                else:
                    self._write_meta("[yellow]🎤 no speech detected[/yellow]")
            except Exception as e:  # noqa: BLE001
                self._write_meta(f"[red]🎤 voice error: {e}[/red]")
        else:
            try:
                from sovereign_agent.voice import get_voice_recorder, VoiceRecorder  # noqa: PLC0415
                if not VoiceRecorder.arecord_available():
                    self._write_meta("[yellow]🎤 arecord not found — voice unavailable[/yellow]")
                    return
                recorder = get_voice_recorder()
                recorder.start_recording()
                self._voice_recording = True
                self._write_meta("[cyan]🎤 recording… (Ctrl-P again to stop + transcribe)[/cyan]")
            except Exception as e:  # noqa: BLE001
                self._write_meta(f"[red]🎤 could not start: {e}[/red]")

    def action_self_practice(self) -> None:
        """Start or stop a bounded self-practice session (● grow).

        She re-runs her own Cosmic-Gym to harden calibration, skills, and flow
        for up to ten minutes, then auto-halts. It is fully observable (every
        cycle is reported live), halt-able (● grow again, or PROTOCOL-ZERO HALT,
        stops it cleanly), and resumable (press ● grow again to run another
        session). It NEVER modifies her code, her values, or the sealed charter.
        """
        if self._practice_running:
            self._practice_stop = True
            self._write_meta("[yellow]● grow — stopping after this cycle…[/yellow]")
            return
        self._practice_stop = False
        self._practice_running = True
        # Hard safety timer: force a clean stop at ten minutes regardless.
        try:
            self._practice_timer = self.set_timer(600.0, self._practice_timeout)
        except Exception:  # noqa: BLE001
            self._practice_timer = None
        self._write_meta(
            "[green]● grow — self-practice started[/green] (her first breaths · "
            "bounded ~10 min · press ● grow again or HALT to stop · she hardens "
            "calibration, never her code or values · watch the windows)")
        self._self_practice_worker()

    def _practice_timeout(self) -> None:
        if self._practice_running:
            self._practice_stop = True
            self._write_meta("[dim]● grow — 10-minute cap reached, halting cleanly…[/dim]")

    @work(thread=True, exclusive=True, group="practice")
    def _self_practice_worker(self) -> None:
        """Run the bounded session off the UI thread; marshal events back."""
        try:
            from ..self_practice import PracticeConfig, run_practice_session
        except Exception as exc:  # noqa: BLE001
            self.call_from_thread(
                self._write_meta, f"[red]● grow unavailable: {exc!r}[/red]")
            self.call_from_thread(self._practice_finished, None)
            return

        base = self._resolve_data_dir()
        persist = (base / "intuition_state.json") if base else None
        journal = (base / "practice") if base else None

        def on_event(ev) -> None:
            self.call_from_thread(self._practice_event_to_ui, ev)

        def should_stop() -> bool:
            halted = bool(getattr(self.status, "halt", False)) \
                if getattr(self, "status", None) is not None else False
            return halted or bool(self._practice_stop)

        report = None
        try:
            report = run_practice_session(
                config=PracticeConfig(max_seconds=600.0, max_cycles=600,
                                      study_passes_per_cycle=2,
                                      cooldown_seconds=3.0, poll_seconds=0.25),
                persist_path=persist, journal_dir=journal,
                should_stop=should_stop, on_event=on_event)
        except Exception as exc:  # noqa: BLE001
            self.call_from_thread(
                self._write_meta, f"[red]● grow error: {exc!r}[/red]")
        finally:
            self.call_from_thread(self._practice_finished, report)

    def _practice_event_to_ui(self, ev) -> None:
        """Surface a practice event into the live meta window."""
        if ev.kind == "cycle":
            self._write_meta(f"[dim]● grow {ev.elapsed:>4.0f}s — {ev.message}[/dim]")
        elif ev.kind in ("start", "done", "halt"):
            self._write_meta(f"[cyan]● grow — {ev.message}[/cyan]")

    def _practice_finished(self, report) -> None:
        self._practice_running = False
        self._practice_stop = False
        t = getattr(self, "_practice_timer", None)
        if t is not None:
            try:
                t.stop()
            except Exception:  # noqa: BLE001
                pass
            self._practice_timer = None
        if report is not None:
            where = report.journal_path or "(data dir)"
            self._write_meta(
                f"[green]● grow complete[/green] — {report.cycles_run} cycles, "
                f"stopped: {report.stopped_reason}, grade {report.final_grade}.\n"
                f"[dim]Journal: {where} — share it with Claude.[/dim]")

    # ----------------------------------------------------------------- #
    #  ▸ flows  —  the workflows catalog (what she can do + how)        #
    # ----------------------------------------------------------------- #
    def _show_workflows(self) -> None:
        """Toggle the workflows catalog overlay (▸ flows / /workflows)."""
        if isinstance(self.screen, WorkflowsScreen):
            self.pop_screen()
        else:
            self.push_screen(WorkflowsScreen())

    # ----------------------------------------------------------------- #
    #  ✦ demo  —  a bounded, observable live demonstration of her core   #
    #  workflows. Proves validity in ~1-2 min. Honours PROTOCOL-ZERO,     #
    #  writes only to an isolated sandbox, NEVER touches code or values.  #
    # ----------------------------------------------------------------- #
    def action_run_demonstration(self) -> None:
        """Start or stop the live demonstration (✦ demo).

        She runs each of her core workflows for real against an isolated
        sandbox, asserting the same invariants the test-suite guarantees —
        but live, in one press, producing a shareable journal. It is fully
        observable (every probe reported), halt-able (✦ demo again, or
        PROTOCOL-ZERO HALT, stops it), bounded (~2 min hard cap), and it
        refuses to run at all while halted. It NEVER modifies her code, her
        values, or the sealed charter, and it touches nothing outside its
        own sandbox.
        """
        if self._demo_running:
            self._demo_stop = True
            self._write_meta("[yellow]✦ demo — stopping after this step…[/yellow]")
            return
        self._demo_stop = False
        self._demo_running = True
        # Hard safety backstop: force a clean stop even if a probe wedges.
        try:
            self._demo_timer = self.set_timer(150.0, self._demo_timeout)
        except Exception:  # noqa: BLE001
            self._demo_timer = None
        self._write_meta(
            "[green]✦ demo — live demonstration started[/green] (proving she is "
            "valid · bounded ~1-2 min · each core workflow run for real in an "
            "isolated sandbox · honours HALT · never touches code or values · "
            "watch the windows)")
        self._demo_worker()

    def _demo_timeout(self) -> None:
        if self._demo_running:
            self._demo_stop = True
            self._write_meta("[dim]✦ demo — time cap reached, halting cleanly…[/dim]")

    @work(thread=True, exclusive=True, group="demo")
    def _demo_worker(self) -> None:
        """Run the bounded demonstration off the UI thread; marshal events back."""
        try:
            from ..workflow.demo import DemoConfig, run_demonstration
        except Exception as exc:  # noqa: BLE001
            self.call_from_thread(
                self._write_meta, f"[red]✦ demo unavailable: {exc!r}[/red]")
            self.call_from_thread(self._demo_finished, None)
            return

        base = self._resolve_data_dir()
        if base is not None:
            demo_root = base / "demonstrations"
        else:
            import tempfile
            demo_root = tempfile.mkdtemp(prefix="aria-demo-")

        def on_event(ev) -> None:
            self.call_from_thread(self._demo_event_to_ui, ev)

        def should_stop() -> bool:
            halted = bool(getattr(self.status, "halt", False)) \
                if getattr(self, "status", None) is not None else False
            return halted or bool(self._demo_stop)

        report = None
        try:
            report = run_demonstration(
                config=DemoConfig(max_seconds=120.0, max_steps=100,
                                  cooldown_seconds=0.0, poll_seconds=0.25),
                demo_root=demo_root,
                should_stop=should_stop, on_event=on_event)
        except Exception as exc:  # noqa: BLE001
            self.call_from_thread(
                self._write_meta, f"[red]✦ demo error: {exc!r}[/red]")
        finally:
            self.call_from_thread(self._demo_finished, report)

    def _demo_event_to_ui(self, ev) -> None:
        """Surface a demonstration event into the live meta window."""
        if ev.kind == "step":
            self._write_meta(f"[dim]✦ demo {ev.elapsed:>4.0f}s — {ev.message}[/dim]")
        elif ev.kind == "refused":
            self._write_meta(f"[yellow]✦ demo — {ev.message}[/yellow]")
        elif ev.kind in ("start", "done"):
            self._write_meta(f"[cyan]✦ demo — {ev.message}[/cyan]")

    def _demo_finished(self, report) -> None:
        self._demo_running = False
        self._demo_stop = False
        t = getattr(self, "_demo_timer", None)
        if t is not None:
            try:
                t.stop()
            except Exception:  # noqa: BLE001
                pass
            self._demo_timer = None
        if report is not None:
            if report.ran:
                where = report.journal_path or "(data dir)"
                self._write_meta(
                    f"[green]✦ demo complete[/green] — {report.verdict}\n"
                    f"[dim]passed {report.passed}/{report.passed + report.failed} · "
                    f"journal: {where} — share it with anyone who asks.[/dim]")
            else:
                self._write_meta(
                    f"[yellow]✦ demo did not run[/yellow] — {report.reason}. "
                    f"[dim]{report.verdict}[/dim]")

    # ----------------------------------------------------------------- #
    #  ⚡ capability test menu — real, live tests of what she can DO:    #
    #  generate an image, search the web, scaffold a game project, ...  #
    #  Unlike ✦ demo, these call real tools/models/network on purpose.  #
    # ----------------------------------------------------------------- #
    def _show_capability_tests(self) -> None:
        """Toggle the ⚡ capability test menu overlay."""
        if CapabilityTestScreen is None:  # pragma: no cover
            self._write_meta(
                "[red]capability test menu unavailable — screen import failed[/red]")
            return
        if isinstance(self.screen, CapabilityTestScreen):
            self.pop_screen()
        else:
            self.push_screen(CapabilityTestScreen())

    def _captest_start(self, selected_wids: list[str] | None) -> None:
        """Start a capability test run — called by the menu's own buttons.
        `selected_wids=None` runs every ready cap-testable workflow
        ("⚡ Test All"). Ignored (with a note) if one is already running."""
        if self._captest_running:
            self._captest_event_line(
                "[yellow]⚡ a test run is already in progress — ■ Stop it first.[/yellow]")
            return
        self._captest_stop = False
        self._captest_running = True
        # Hard safety backstop: force a clean stop even if a test wedges.
        try:
            self._captest_timer = self.set_timer(320.0, self._captest_timeout)
        except Exception:  # noqa: BLE001
            self._captest_timer = None
        label = "every ready capability" if selected_wids is None else ", ".join(selected_wids)
        self._captest_event_line(f"[green]⚡ capability test — starting ({label})[/green]")
        self._captest_worker(selected_wids)

    def _captest_request_stop(self) -> None:
        if self._captest_running:
            self._captest_stop = True
            self._captest_event_line(
                "[yellow]⚡ capability test — stopping after this one…[/yellow]")

    def _captest_timeout(self) -> None:
        if self._captest_running:
            self._captest_stop = True
            self._captest_event_line(
                "[dim]⚡ capability test — time cap reached, halting cleanly…[/dim]")

    @work(thread=True, exclusive=True, group="captest")
    def _captest_worker(self, selected_wids: list[str] | None = None) -> None:
        """Run real capability tests off the UI thread; marshal events back."""
        try:
            from ..workflow.capability_tests import CapTestConfig, run_capability_tests
        except Exception as exc:  # noqa: BLE001
            self.call_from_thread(
                self._captest_event_line, f"[red]⚡ capability tests unavailable: {exc!r}[/red]")
            self.call_from_thread(self._captest_finished, None)
            return

        base = self._resolve_data_dir()
        if base is not None:
            out_root = base / "capability_tests"
        else:
            import tempfile
            out_root = tempfile.mkdtemp(prefix="aria-captest-")

        def on_event(ev) -> None:
            self.call_from_thread(self._captest_event_to_ui, ev)

        def should_stop() -> bool:
            halted = bool(getattr(self.status, "halt", False)) \
                if getattr(self, "status", None) is not None else False
            return halted or bool(self._captest_stop)

        report = None
        try:
            report = run_capability_tests(
                selected_wids,
                config=CapTestConfig(max_seconds=300.0, max_steps=50,
                                     cooldown_seconds=0.0, poll_seconds=0.25),
                out_root=out_root,
                should_stop=should_stop, on_event=on_event)
        except Exception as exc:  # noqa: BLE001
            self.call_from_thread(
                self._captest_event_line, f"[red]⚡ capability test error: {exc!r}[/red]")
        finally:
            self.call_from_thread(self._captest_finished, report)

    def _captest_event_to_ui(self, ev) -> None:
        """Surface a capability-test event into the modal (if open) — live
        metrics + log — and always into the meta window too, so progress
        stays visible even if the modal got closed mid-run."""
        screen = self.screen
        if CapabilityTestScreen is not None and isinstance(screen, CapabilityTestScreen):
            if ev.kind == "queued":
                try:
                    screen.queued = int(ev.message.split()[0])
                except Exception:  # noqa: BLE001
                    pass
            elif ev.kind == "running":
                screen.running_count = 1
            elif ev.kind == "step":
                screen.running_count = 0
                if ev.message.startswith("PASS"):
                    screen.passed += 1
                elif ev.message.startswith("FAIL"):
                    screen.failed += 1
                elif ev.message.startswith("SKIP"):
                    screen.skipped += 1
            screen.elapsed = ev.elapsed
            screen.log_line(f"[dim]{ev.elapsed:>6.1f}s[/dim] {ev.message}")
        if ev.kind in ("step", "refused"):
            self._write_meta(f"[dim]⚡ test {ev.elapsed:>4.0f}s — {ev.message}[/dim]")
        elif ev.kind in ("start", "done"):
            self._write_meta(f"[cyan]⚡ test — {ev.message}[/cyan]")

    def _captest_event_line(self, text: str) -> None:
        """A one-off status line, mirrored to both the modal log (if open)
        and the meta window."""
        screen = self.screen
        if CapabilityTestScreen is not None and isinstance(screen, CapabilityTestScreen):
            screen.log_line(text)
        self._write_meta(text)

    def _captest_finished(self, report) -> None:
        self._captest_running = False
        self._captest_stop = False
        t = getattr(self, "_captest_timer", None)
        if t is not None:
            try:
                t.stop()
            except Exception:  # noqa: BLE001
                pass
            self._captest_timer = None
        if report is None:
            return
        if not report.ran:
            self._captest_event_line(
                f"[yellow]⚡ capability tests did not run[/yellow] — {report.reason}. "
                f"[dim]{report.verdict}[/dim]")
            return
        where = report.journal_path or "(data dir)"
        self._captest_event_line(
            f"[green]⚡ capability tests complete[/green] — {report.verdict}\n"
            f"[dim]passed {report.passed} · failed {report.failed} · "
            f"skipped {report.skipped} · journal: {where}[/dim]")
        # the summary/report doc Kevin asked for — same data_dir/reports/
        # convention _save_report already uses for /report.
        try:
            data_dir = self._resolve_data_dir()
            if data_dir is not None and report.journal_path:
                reports_dir = data_dir / "reports"
                reports_dir.mkdir(parents=True, exist_ok=True)
                ts = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
                dest = reports_dir / f"capability-test-{ts}.md"
                journal_md = Path(report.journal_path) / "journal.md"
                if journal_md.exists():
                    dest.write_text(journal_md.read_text(encoding="utf-8"), encoding="utf-8")
                    self._captest_event_line(f"[green]✓[/green] report saved → [cyan]{dest}[/cyan]")
        except Exception as exc:  # noqa: BLE001
            self._captest_event_line(f"[red]✗ report save failed: {exc!r}[/red]")

    def action_help(self) -> None:
        # Toggle. If help is already open, close it — so pressing F1 (or
        # clicking the help button) again dismisses it instead of stacking
        # another copy on top. This is the fix for "help won't close".
        if isinstance(self.screen, HelpScreen):
            self.pop_screen()
        else:
            self.push_screen(HelpScreen())

    def action_clear_chat(self) -> None:
        # context-health-d (Kevin, 2026-08-02): /clear used to only wipe
        # the VISUAL log — the ⊕/◔/⛁ counters and stuck busy state lived
        # on regardless, so "/clear" never actually meant "start fresh."
        # Now it does: display, transcript, token counters, and any
        # stuck busy/interrupt flags (_clear_session_busy_state — already
        # existed for /pause, never wired here) all reset together.
        # Durable memory/atoms are NEVER touched by this — display and
        # session counters only.
        #
        # never-empty-handed-d (Kevin, 2026-08-02): "make sure it never
        # /clears and ends up empty handed... she must always come back
        # not empty-handed." Write a real handoff BEFORE wiping anything
        # — mos-proactive-handoff/mos-continuity-of-care's own mechanism.
        handoff_path = None
        try:
            from sovereign_agent.config import SETTINGS
            from sovereign_agent.handoff import write_handoff
            from sovereign_agent.read_repair import read_ndjson_tolerant

            events = read_ndjson_tolerant(
                SETTINGS.paths.events_jsonl, store="handoff", emit=False).records
            handoff_path = write_handoff(SETTINGS.paths.data_dir, events, reason="/clear")
        except Exception:  # noqa: BLE001 — a handoff-write failure must never block /clear
            pass

        if self._chat_log is not None:
            self._chat_log.clear()
        self._transcript.clear()
        self._session_tokens = 0
        self._last_prompt_tokens = 0
        self._clear_session_busy_state()
        self._render_status_bar()
        _handoff_note = f" → {handoff_path}" if handoff_path else ""
        self._write_meta(
            "[dim]── chat + session counters cleared (memory/atoms untouched)"
            f"{_handoff_note} ──[/dim]"
        )

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
        """Cycle the heartbeat through red → rainbow → silent → off. Ctrl-B or
        /heart. The first press steps on from whatever's showing now."""
        current = self._effective_heart_mode()
        try:
            idx = self.HEART_CYCLE.index(current)
        except ValueError:
            idx = -1
        self._heart_mode = self.HEART_CYCLE[(idx + 1) % len(self.HEART_CYCLE)]
        label = {
            "red": "[red]♥ natural red[/red]",
            "rainbow": "♥ rainbow",
            "silent": "[#8a90a8]♥ silent (present)[/#8a90a8]",
            "off": "[dim]♥ off[/dim]",
        }.get(self._heart_mode, self._heart_mode)
        self._write_meta(f"[dim]heart →[/dim] {label}")

    # ── Cosmic Fitness (v0.2.41) ─────────────────────────────────────
    def action_toggle_glyphs(self) -> None:
        """Toggle the inline glyph picker. Ctrl-G or /pick.

        The picker is a compact, scrollable strip of tappable glyphs right
        above the input. Clicking a glyph drops it at the cursor and keeps
        the picker open, so the operator can string several together.
        """
        if _cf is not None and not _cf.cosmic_fitness_enabled():
            self._write_meta(
                "[dim]glyph picker disabled (SOV_NO_COSMIC_FITNESS set)[/dim]"
            )
            return
        try:
            picker = self.query_one("#glyph-picker")
        except Exception:  # noqa: BLE001 — picker didn't mount
            self._write_meta("[yellow]glyph picker unavailable[/yellow]")
            return
        picker.display = not picker.display
        if picker.display:
            self._write_meta(
                "[dim]\u25ca glyph picker open — tap to add, Ctrl-G to close, "
                "\u25ca cosmic for the full tester[/dim]"
            )
            # Keep focus on the input so the operator can keep typing too.
            try:
                self.query_one("#input-box", Input).focus()
            except Exception:  # noqa: BLE001
                pass
        else:
            self._write_meta("[dim]\u25ca glyph picker closed[/dim]")

    def _insert_glyph(self, char: str) -> None:
        """Insert a glyph at the input cursor and refocus the input."""
        try:
            input_box = self.query_one("#input-box", Input)
        except Exception:  # noqa: BLE001
            return
        try:
            input_box.insert_text_at_cursor(char)
        except Exception:  # noqa: BLE001 — very old Textual; append instead
            input_box.value = (input_box.value or "") + char
        input_box.focus()

    def _show_cosmic_fitness(self) -> None:
        """Open the Cosmic Fitness tester modal. Button, /cosmic, /fitness."""
        if _cf is not None and not _cf.cosmic_fitness_enabled():
            self._write_meta(
                "[dim]Cosmic Fitness disabled (SOV_NO_COSMIC_FITNESS set)[/dim]"
            )
            return
        try:
            self.push_screen(CosmicFitnessScreen())
        except Exception as exc:  # noqa: BLE001
            self._write_meta(f"[red]could not open Cosmic Fitness: {exc!r}[/red]")

    def _cosmic_report_to_chat(self, include_scan: bool = True) -> None:
        """Print the Cosmic Fitness report inline (for /cosmic report)."""
        if _cf is None:
            self._write_meta("[yellow]cosmic_fitness unavailable[/yellow]")
            return
        try:
            report = _cf.run_cosmic_fitness(include_scan=include_scan)
            for line in report.render_lines():
                self._write_meta(line)
        except Exception as exc:  # noqa: BLE001
            self._write_meta(f"[red]fitness report failed: {exc!r}[/red]")

    def _cosmic_mark_glyph(self, arg: str) -> None:
        """Record an operator verdict on a glyph. /cosmic mark <glyph> <verdict> [note]."""
        if _cf is None:
            self._write_meta("[yellow]cosmic_fitness unavailable[/yellow]")
            return
        parts = arg.split(maxsplit=2)
        if len(parts) < 2:
            self._write_meta(
                "[yellow]usage: /cosmic mark <glyph> good|replace|remove [note][/yellow]"
            )
            return
        glyph, verdict = parts[0], parts[1].lower()
        note = parts[2] if len(parts) > 2 else ""
        if verdict not in ("good", "replace", "remove"):
            self._write_meta(
                "[yellow]verdict must be: good | replace | remove[/yellow]"
            )
            return
        try:
            from ..config import SETTINGS
            store = _cf.GlyphVerdictStore(SETTINGS.paths.data_dir)
            rec = store.record(glyph, verdict, note)
            alt = rec.get("suggested_alternative")
            alt_s = f"  (safe variant: {alt})" if alt and verdict == "replace" else ""
            self._write_meta(
                f"[green]\u2713 marked[/green] {glyph} [{rec['codepoint']}] "
                f"as [b]{verdict}[/b]{alt_s}"
            )
        except Exception as exc:  # noqa: BLE001
            self._write_meta(f"[red]could not record verdict: {exc!r}[/red]")

    def _cosmic_list_verdicts(self) -> None:
        """List recorded glyph verdicts. /cosmic verdicts."""
        if _cf is None:
            self._write_meta("[yellow]cosmic_fitness unavailable[/yellow]")
            return
        try:
            from ..config import SETTINGS
            store = _cf.GlyphVerdictStore(SETTINGS.paths.data_dir)
            for line in store.render_lines():
                self._write_meta(line)
        except Exception as exc:  # noqa: BLE001
            self._write_meta(f"[red]could not list verdicts: {exc!r}[/red]")

    def _cosmic_probe_widths(self) -> None:
        """Measure THIS terminal's real glyph widths and report disagreements.

        Tier 1 of the accounting system: suspends the TUI, runs a DSR cursor
        probe on the ambiguous/wide glyphs we ship, and reports which ones the
        terminal actually draws at 2 cells versus what rich assumes. Patches no
        rendering — purely informational, so it cannot break anything.
        """
        if _cf is None:
            self._write_meta("[yellow]cosmic_fitness unavailable[/yellow]")
            return
        try:
            from . import glyph_metrics as gm
        except Exception as exc:  # noqa: BLE001
            self._write_meta(f"[red]glyph_metrics unavailable: {exc!r}[/red]")
            return
        if not gm.metrics_enabled():
            self._write_meta(
                f"[yellow]width probe disabled ({gm.METRICS_KILL_ENV} set)[/yellow]"
            )
            return

        # Glyphs worth measuring: a few universal anchors (which MUST come back
        # as 1 cell), plus every ambiguous/wide glyph we actually ship.
        suspects: list[str] = []
        seen: set[str] = set()

        def _add(g: str) -> None:
            if g and g not in seen:
                seen.add(g)
                suspects.append(g)

        for anchor in ("A", "\u2588", "\u28FF"):
            _add(anchor)
        for cat in _cf.curated_categories():
            for spec in cat.glyphs:
                if not _cf.is_universal_width(spec.char):
                    _add(spec.char)
        for an in _cf.animations():
            for f in an.frames:
                if not _cf.is_universal_width(f):
                    _add(f)
        for ae in _cf.animated_effects():
            for f in ae.frames:
                if not _cf.is_universal_width(f):
                    _add(f)
        for eff in _cf.special_effects():
            if not _cf.is_universal_width(eff.glyph):
                _add(eff.glyph)

        self._write_meta(f"[dim]probing {len(suspects)} glyphs on this terminal…[/dim]")
        table = gm.WidthTable()
        try:
            with self.suspend():
                table = gm.probe_terminal_widths(suspects)
        except Exception as exc:  # noqa: BLE001
            self._write_meta(f"[red]probe failed: {exc!r}[/red]")
            return

        if not table:
            self._write_meta(
                "[yellow]measured nothing — this terminal didn't answer the "
                "cursor-position query (or isn't a real TTY). Curation stays "
                "in effect; nothing changed.[/yellow]"
            )
            return

        try:
            from rich.cells import cell_len
        except Exception:  # noqa: BLE001
            def cell_len(s: str) -> int:  # type: ignore
                return 1
        overwide = gm.overwide_glyphs(table)
        disagreements = []
        for g in suspects:
            w = table.get(g)
            if w is None:
                continue
            assumed = cell_len(g)
            if w != assumed:
                disagreements.append((g, assumed, w))

        self._write_meta(
            f"[b]width probe[/b] — {len(table)} measured, "
            f"{len(overwide)} draw wide, {len(disagreements)} disagree with rich:"
        )
        if disagreements:
            for g, assumed, w in disagreements:
                self._write_meta(
                    f"  [yellow]U+{ord(g[0]):04X}[/yellow] {g}  "
                    f"rich={assumed} → terminal=[b]{w}[/b]"
                )
        else:
            self._write_meta(
                "  [green]no disagreements — rich's widths already match your "
                "terminal for every glyph we ship.[/green]"
            )
        self._write_meta(
            "[dim]Measured on YOUR terminal, now. The disagreements are why "
            "borders shift; they're already kept out of counted layouts.[/dim]"
        )

    def action_apply_queue(self) -> None:  # apply-queue-action-d
        """Ctrl+Shift+A → multi-select staged modules into the durable apply queue."""
        if ApplyQueueScreen is None:  # pragma: no cover
            return
        if isinstance(self.screen, ApplyQueueScreen):
            self.pop_screen(); return
        try:
            from pathlib import Path
            import sovereign_agent
            repo_root = Path(sovereign_agent.__file__).parents[2]  # 2026-08-02 fix — was [3], pointed one level above the repo (see cockpit/app.py:9029's sibling fix)
            self.push_screen(ApplyQueueScreen(repo_root))
        except Exception as exc:  # noqa: BLE001
            logger.warning('apply-queue screen failed: %r', exc)

    def action_command_palette(self) -> None:  # command-menu-d
        """Ctrl+M / "⋮ commands" button → scrollable command popup."""
        if CommandPaletteScreen is None:  # pragma: no cover
            return
        if isinstance(self.screen, CommandPaletteScreen):
            self.pop_screen(); return
        try:
            self.push_screen(CommandPaletteScreen())
        except Exception as exc:  # noqa: BLE001
            logger.warning('command-palette screen failed: %r', exc)

    def action_settings_menu(self) -> None:  # menu-split-d
        """Gear @ (top-left) / F5 → the Settings & Help menu. Distinct from
        the bottom-left ⋮ System-Commands popup — this is the fix for the
        two menus having been the same screen."""
        if SettingsMenuScreen is None:  # pragma: no cover
            return
        if isinstance(self.screen, SettingsMenuScreen):
            self.pop_screen(); return
        try:
            self.push_screen(SettingsMenuScreen())
        except Exception as exc:  # noqa: BLE001
            logger.warning('settings menu failed: %r', exc)

    def action_tiers(self) -> None:  # tier-d (F4, 2026-07-19)
        """/tiers → the trust-tier menu: see what's approved, raise with
        the typed phrase, or hit the kill switch (instant tier 1)."""
        if TierScreen is None:  # pragma: no cover
            return
        if isinstance(self.screen, TierScreen):
            self.pop_screen(); return
        try:
            self.push_screen(TierScreen())
        except Exception:  # noqa: BLE001
            pass

    def action_controls(self) -> None:  # menu-split-d
        """F4 / Settings & Help → Controls → every keybinding, one menu
        (the always-on footer key row was removed)."""
        if ControlsScreen is None:  # pragma: no cover
            return
        if isinstance(self.screen, ControlsScreen):
            self.pop_screen(); return
        try:
            self.push_screen(ControlsScreen())
        except Exception as exc:  # noqa: BLE001
            logger.warning('controls screen failed: %r', exc)

    def action_changelog(self) -> None:  # menu-split-d
        """`/changelog` / Settings & Help → Changelog → the version history."""
        if ChangelogScreen is None:  # pragma: no cover
            return
        if isinstance(self.screen, ChangelogScreen):
            self.pop_screen(); return
        try:
            self.push_screen(ChangelogScreen())
        except Exception as exc:  # noqa: BLE001
            logger.warning('changelog screen failed: %r', exc)

    def action_journal_menu(self) -> None:  # j-space-d
        """F7 / bare /journal → the J-Space (reflective, two-way journal)."""
        if JournalScreen is None:  # pragma: no cover
            return
        if isinstance(self.screen, JournalScreen):
            self.pop_screen(); return
        try:
            self.push_screen(JournalScreen())
        except Exception as exc:  # noqa: BLE001
            logger.warning('journal menu failed: %r', exc)

    def action_resume_menu(self) -> None:  # resume-menu-d
        """F6 / bare /resume → the beautiful 'pick a session to resume' menu.
        The engine (session_bridge.resume_goal_session) is robust; this is the
        surface. Selecting a session hands off to the gated resume path."""
        if ResumeMenuScreen is None:  # pragma: no cover
            return
        if isinstance(self.screen, ResumeMenuScreen):
            self.pop_screen(); return
        try:
            self.push_screen(ResumeMenuScreen())
        except Exception as exc:  # noqa: BLE001
            logger.warning('resume menu failed: %r', exc)

    def action_model_menu(self) -> None:  # sprint-mode-d
        """F8 / `/model` → Standard, a sprint preset, or Custom slots.
        Kevin, 2026-07-21: "add a model configure menu, and have modes[,]
        or preselect configurations... have drop down menus for each
        model configuration slot... presets, or custom mode, or custom
        slots." Never touches SETTINGS or the model_ladder.py vault --
        purely a reversible, per-slot testing override."""
        if ModelMenuScreen is None:  # pragma: no cover
            return
        if isinstance(self.screen, ModelMenuScreen):
            self.pop_screen(); return
        try:
            self.push_screen(ModelMenuScreen())
        except Exception as exc:  # noqa: BLE001
            logger.warning('model menu failed: %r', exc)

    def run_settings_item(self, key: str) -> None:  # menu-split-d
        """Dispatch a Settings & Help menu selection to its existing action.
        Called by SettingsMenuScreen after it pops itself."""
        dispatch = {
            "journal": self.action_journal_menu,
            "resume": self.action_resume_menu,
            "theme": self.action_theme_studio,
            "layout": self.action_toggle_layout,
            "glyphs": self.action_toggle_glyphs,
            "modes": self.action_modes_crown,
            "session": self.action_modes_crown,  # session-setup-unify-d — same unified screen
            "observatory": self.action_observatory,
            "recording": self.action_toggle_recording,
            "help": self.action_help,
            "legend": self._show_palette_legend,
            "workflows": self._show_workflows,
            "cosmic": self._show_cosmic_fitness,
            "controls": self.action_controls,
            "changelog": self.action_changelog,
        }
        fn = dispatch.get(key)
        if fn is None:
            return
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            logger.warning('settings item %r failed: %r', key, exc)

    def action_theme_picker(self) -> None:  # theme-picker-d
        """Ctrl+T → browse and apply any registered theme. Separate from
        the `sov theme` CLI family — this is the point-and-click picker
        that Textual's default command palette used to provide before
        Ctrl+P was repurposed for voice push-to-talk."""
        if ThemePickerScreen is None:  # pragma: no cover
            return
        if isinstance(self.screen, ThemePickerScreen):
            self.pop_screen(); return
        try:
            self.push_screen(ThemePickerScreen())
        except Exception as exc:  # noqa: BLE001
            logger.warning('theme-picker screen failed: %r', exc)

    def action_theme_studio(self) -> None:  # theme-studio-d
        """Ctrl+T / Settings → Theme → the Theme Studio: arrow through preset
        and custom themes (live), create/edit/remove custom ones. Falls back
        to the simple picker if the studio isn't available."""
        screen = ThemeStudioScreen or ThemePickerScreen
        if screen is None:  # pragma: no cover
            return
        if isinstance(self.screen, (ThemeStudioScreen or (),
                                    ThemePickerScreen or ())):
            self.pop_screen(); return
        try:
            self.push_screen(screen())
        except Exception as exc:  # noqa: BLE001
            logger.warning('theme studio failed: %r', exc)

    def action_theme_create(self) -> None:  # theme-studio-d
        """`/theme-create` → open the theme creation studio directly."""
        if ThemeCreatorScreen is None:  # pragma: no cover
            return
        try:
            self.push_screen(ThemeCreatorScreen())
        except Exception as exc:  # noqa: BLE001
            logger.warning('theme creator failed: %r', exc)

    def action_bot_studio(self) -> None:  # bot-studio-d
        """/bots · /bot-studio → define a bot project (name/kind/concept),
        browse/edit/remove. The direction layer toward income; the runtime
        comes later (DiscordBotStudio/DESIGN.md)."""
        if BotStudioScreen is None:  # pragma: no cover
            return
        if isinstance(self.screen, BotStudioScreen):
            self.pop_screen(); return
        try:
            self.push_screen(BotStudioScreen())
        except Exception as exc:  # noqa: BLE001
            logger.warning('bot studio failed: %r', exc)

    def action_shop_studio(self) -> None:  # shop-studio-d
        """/shop → the Bot Shop Studio: manage products/subscriptions,
        publish the storefront. Prices + Stripe links live here."""
        if ShopStudioScreen is None:  # pragma: no cover
            return
        if isinstance(self.screen, ShopStudioScreen):
            self.pop_screen(); return
        try:
            self.push_screen(ShopStudioScreen())
        except Exception as exc:  # noqa: BLE001
            logger.warning('shop studio failed: %r', exc)

    def action_game_studio(self) -> None:  # game-studio-d
        """/games → the Game Studio: define game projects (name/genre/
        concept), browse/edit/remove, set focus. XP/level/storage shown
        in the screen's own header."""
        if GameStudioScreen is None:  # pragma: no cover
            return
        if isinstance(self.screen, GameStudioScreen):
            self.pop_screen(); return
        try:
            self.push_screen(GameStudioScreen())
        except Exception as exc:  # noqa: BLE001
            logger.warning('game studio failed: %r', exc)

    def action_movie_studio(self) -> None:  # movie-studio-d
        """/movies → the Movie Studio: define movie projects (title/genre/
        logline/style), browse/edit/remove, set focus, generate real
        storyboards, draft original pitches. XP/level/storage shown in
        the screen's own header."""
        if MovieStudioScreen is None:  # pragma: no cover
            return
        if isinstance(self.screen, MovieStudioScreen):
            self.pop_screen(); return
        try:
            self.push_screen(MovieStudioScreen())
        except Exception as exc:  # noqa: BLE001
            logger.warning('movie studio failed: %r', exc)

    def action_timers(self) -> None:  # timers-d
        """/timers → every live countdown: presence, live tasks, bot
        uptimes, next-poll countdowns, queue retries."""
        if TimersScreen is None:  # pragma: no cover
            return
        if isinstance(self.screen, TimersScreen):
            self.pop_screen(); return
        try:
            self.push_screen(TimersScreen())
        except Exception as exc:  # noqa: BLE001
            logger.warning('timers screen failed: %r', exc)

    def action_discord_watch(self) -> None:  # discord-watch-d
        """/discord → 📡 watch her live Discord shift: everything she does
        and learns (customers, deliveries, welcomes, ads, lessons)."""
        if DiscordWatchScreen is None:  # pragma: no cover
            return
        if isinstance(self.screen, DiscordWatchScreen):
            self.pop_screen(); return
        try:
            self.push_screen(DiscordWatchScreen())
        except Exception as exc:  # noqa: BLE001
            logger.warning('discord watch screen failed: %r', exc)

    def action_scout_trace(self) -> None:  # verify-d
        """/scout-trace → 🔎 watch HOW she gathers across every tracker,
        with grounded-truth verification on each find."""
        if ScoutTraceScreen is None:  # pragma: no cover
            return
        if isinstance(self.screen, ScoutTraceScreen):
            self.pop_screen(); return
        try:
            self.push_screen(ScoutTraceScreen())
        except Exception as exc:  # noqa: BLE001
            logger.warning('scout trace screen failed: %r', exc)

    def run_bots_toggle(self, sub: str) -> None:  # services-d
        """/bots on|off|status → the Discord services, through systemd
        only (single-instance discipline: never a zombie). The subprocess
        runs OFF the UI thread; the receipt echoes in the chat pane.

        movie-focus-d (Kevin, 2026-07-28): /bots restart-duty restarts
        ONLY aria-duty.service (its Playwright scraper's known RAM leak),
        leaving aria-bot's Discord connection untouched — the command-line
        twin of the Discord Control screen's new "restart duty" button."""

        async def _go() -> None:
            import asyncio as _aio
            try:
                from sovereign_agent import bot_services
                if sub in ("status", "state"):
                    out = await _aio.to_thread(bot_services.render_states)
                elif sub in ("restart-duty", "restartduty"):
                    out = await _aio.to_thread(bot_services.restart_duty)
                else:
                    out = await _aio.to_thread(
                        bot_services.toggle, sub == "on")
            except Exception as exc:  # noqa: BLE001
                out = f"bots toggle unavailable: {type(exc).__name__}"
            self._write_meta(out)

        self.run_worker(_go(), exclusive=False)

    def run_claude_code(self, prompt: str) -> None:  # cc-d
        """/cc <prompt> → one headless Claude Code exchange, off-thread.
        Kevin's typed command is the consent; normal permissions always
        (propose-don't-act by construction — see cc_bridge.py)."""

        async def _go() -> None:
            import asyncio as _aio
            try:
                from sovereign_agent.cc_bridge import render_result, run_cc
                from sovereign_agent.config import SETTINGS as _S
                if not (prompt or "").strip():
                    self._write_meta("[dim]🤝 usage: /cc <prompt> — ask "
                                     "Claude Code anything about the repo; "
                                     "it answers with text/plans/diffs and "
                                     "never edits without you.[/dim]")
                    return
                self._write_meta("[dim]🤝 Claude Code is thinking (runs "
                                 "off-thread; up to ~4 min)…[/dim]")
                res = await _aio.to_thread(
                    run_cc, prompt, data_dir=_S.paths.data_dir)
                self._write_aria(render_result(res))
            except Exception as exc:  # noqa: BLE001
                self._write_meta(f"[yellow]🤝 cc bridge unavailable: "
                                 f"{type(exc).__name__}[/yellow]")

        self.run_worker(_go(), exclusive=False)

    def run_server_command(self, raw: str) -> None:  # bridge-d
        """/server <cmd> [args] → the gateway bot runs the same admin op
        its slash command runs, and the receipt echoes here. The typed
        cockpit command IS the owner's consent; destructive cleanup still
        demands its phrase as the argument."""
        parts = (raw or "").strip().split(maxsplit=1)
        cmd = parts[0].lower() if parts else ""
        args = parts[1] if len(parts) > 1 else ""

        async def _go() -> None:
            import asyncio as _aio
            try:
                from sovereign_agent.config import SETTINGS as _S
                from sovereign_agent.discord_admin.command_bridge import (
                    enqueue, render_help, result_for)
                if not cmd or cmd in ("help", "?"):
                    self._write_meta(render_help())
                    return
                try:
                    rid = enqueue(_S.paths.data_dir, cmd, args)
                except ValueError:
                    self._write_meta(render_help())
                    return
                try:      # honest heads-up if the gateway isn't even up
                    from sovereign_agent.bot_services import service_states
                    st = await _aio.to_thread(service_states)
                    if st.get("aria-bot.service", {}).get("active") is False:
                        self._write_meta(
                            "[yellow]🌉 queued — but aria-bot is STOPPED; "
                            "start it with /bots on and this will run.[/yellow]")
                        return
                except Exception:  # noqa: BLE001
                    pass
                self._write_meta(f"[dim]🌉 /server {cmd} queued — the bot "
                                 "picks it up within ~5s…[/dim]")
                for _ in range(36):               # wait up to ~3 min
                    await _aio.sleep(5)
                    res = await _aio.to_thread(
                        result_for, _S.paths.data_dir, rid)
                    if res is not None:
                        self._write_meta(f"🌉 /server {cmd}:\n{res}")
                        return
                self._write_meta("[yellow]🌉 still running — the receipt "
                                 "will land in the audit trail (⌁ /discord "
                                 "shows it).[/yellow]")
            except Exception as exc:  # noqa: BLE001
                self._write_meta(f"[yellow]🌉 bridge unavailable: "
                                 f"{type(exc).__name__}[/yellow]")

        self.run_worker(_go(), exclusive=False)

    def run_server_message(self, text: str) -> None:  # discord-watch-d
        """/server-message <text> → % Kevin speaks to the server. The
        typed command IS the consent → posts live. Network runs off the
        UI thread; the result echoes in the chat pane."""
        text = (text or "").strip()
        if not text:
            self._write_meta("[dim]% usage: /server-message your "
                             "announcement text[/dim]")
            return

        async def _post() -> None:
            import asyncio as _aio
            try:
                from sovereign_agent.advertising import publish_announcement
                from sovereign_agent.config import SETTINGS as _S
                ok, detail = await _aio.to_thread(
                    publish_announcement, _S.paths.data_dir, text, live=True)
            except Exception as exc:  # noqa: BLE001
                ok, detail = False, f"failed: {type(exc).__name__}"
            self._write_meta(f"[green]% {detail}[/green]" if ok
                             else f"[yellow]% {detail}[/yellow]")

        self.run_worker(_post(), exclusive=False)

    def action_key_vault(self) -> None:  # key-vault-d
        """/keys → the Key Vault: hand her credentials safely (masked
        input, 0600 env file, local-only, never displayed back)."""
        if CredentialsScreen is None:  # pragma: no cover
            return
        if isinstance(self.screen, CredentialsScreen):
            self.pop_screen(); return
        try:
            self.push_screen(CredentialsScreen())
        except Exception as exc:  # noqa: BLE001
            logger.warning('key vault failed: %r', exc)

    def action_modes_crown(self) -> None:  # modes-crown-d
        """F2 / /modes → the mode picker (the crown)."""
        try:
            from sovereign_agent.cockpit.modes_crown_ui import ModesScreen

            if isinstance(self.screen, ModesScreen):
                self.pop_screen(); return
            self.push_screen(ModesScreen())
        except Exception as exc:  # noqa: BLE001
            logger.warning('modes screen failed: %r', exc)

    def action_instructions(self) -> None:  # instructions-d
        """`? help` button / /instructions → the SAME F1 help screen (how
        to use the interface, the command reference, and the /workflows
        catalog it already points to for "what kind of task"). Kevin,
        2026-07-25: "a instructions button... for how to use the system
        and interface, and for what kind of task, work, and workflows."
        Reuses the existing comprehensive HelpScreen rather than building
        a second, competing reference that could drift out of sync with it."""
        self.action_help()

    def action_discord_control(self) -> None:  # discord-control-d
        """❖ discord button / /discord-control → turn off/pause/resume/
        restart the Discord bot services, off the cockpit."""
        if DiscordControlScreen is None:
            self._write_meta("[yellow]◊ Discord control screen unavailable[/yellow]")
            return
        try:
            if isinstance(self.screen, DiscordControlScreen):
                self.pop_screen(); return
            self.push_screen(DiscordControlScreen())
        except Exception as exc:  # noqa: BLE001
            logger.warning('discord control screen failed: %r', exc)

    def action_suggestions(self) -> None:  # suggestions-d
        """✧ suggestions button / /suggestions → grounded ideas for what
        to work on next, sourced from real sentinel findings + unbuilt
        bot-project ideas — nothing invented."""
        if SuggestionsScreen is None:
            self._write_meta("[yellow]◊ Suggestions screen unavailable[/yellow]")
            return
        try:
            if isinstance(self.screen, SuggestionsScreen):
                self.pop_screen(); return
            self.push_screen(SuggestionsScreen())
        except Exception as exc:  # noqa: BLE001
            logger.warning('suggestions screen failed: %r', exc)

    def action_task_guide(self) -> None:  # task-guide-d
        """% guide button / /task-guide → the grounded "everything you
        can do with her" menu — every capability listed is a real,
        registered tool, never invented."""
        if TaskGuideScreen is None:
            self._write_meta("[yellow]◊ Task Guide screen unavailable[/yellow]")
            return
        try:
            if isinstance(self.screen, TaskGuideScreen):
                self.pop_screen(); return
            self.push_screen(TaskGuideScreen())
        except Exception as exc:  # noqa: BLE001
            logger.warning('task guide screen failed: %r', exc)

    def action_stripe_links(self) -> None:  # stripe-links-d
        """$ stripe button / /stripe-links → the Stripe Links Vault: see +
        update every product's Payment Link, off the cockpit. Kevin,
        2026-07-26: "so I can see all the current stripe links, and just
        configuration slots for stripe links so I can update them easily
        via the cockpit... like a stripe links vault." """
        if StripeLinksScreen is None:
            self._write_meta("[yellow]◊ Stripe Links screen unavailable[/yellow]")
            return
        try:
            if isinstance(self.screen, StripeLinksScreen):
                self.pop_screen(); return
            self.push_screen(StripeLinksScreen())
        except Exception as exc:  # noqa: BLE001
            logger.warning('stripe links screen failed: %r', exc)

    def action_sources_control(self) -> None:  # source-toggle-d
        """# sources button / /sources → the Sources Control Panel: turn
        any tracker source on/off, per source or fleet-wide. Kevin,
        2026-07-27: "Make a control panel where I can turn sources on
        and off. I want to toggle reddit off." """
        if SourcesControlScreen is None:
            self._write_meta("[yellow]◊ Sources Control screen unavailable[/yellow]")
            return
        try:
            if isinstance(self.screen, SourcesControlScreen):
                self.pop_screen(); return
            self.push_screen(SourcesControlScreen())
        except Exception as exc:  # noqa: BLE001
            logger.warning('sources control screen failed: %r', exc)

    def action_toggle_game_window(self) -> None:  # game-window-optional-d
        """✦ game button / /game-toggle → show/hide #game-window. Kevin,
        2026-07-25: "make the game menu optional because it is kinda
        wasting space. An optional visual." Persisted so the choice
        survives a cockpit restart; the window keeps refreshing under the
        hood either way (hiding is purely visual, never stops the XP/
        income/token tracking it displays)."""
        try:
            from sovereign_agent.cockpit.game_window_pref import (
                is_visible, set_visible,
            )
            window = self.query_one("#game-window")
            now_visible = not window.display
            window.display = now_visible
            set_visible(now_visible)
            self._write_meta(
                f"[dim]◊ game window {'shown' if now_visible else 'hidden'}[/dim]"
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning('game window toggle failed: %r', exc)

    def action_toggle_all_bots(self) -> None:  # movie-focus-d
        """⏸ bots button → one-click pause/resume for BOTH Discord services
        (aria-bot + aria-duty), through the exact same systemd path as
        `/bots on|off` (bot_services.toggle) — no new mechanism, just a
        direct-access button. Auto-detects current state so one button
        does both directions: any unit active → stop both; none active →
        start both. Kevin, 2026-07-28: wanted this specifically to free
        RAM/VRAM before GPU-heavy movie renders, after having to do this
        by hand via raw systemctl three times in one session."""
        async def _go() -> None:
            import asyncio as _aio
            try:
                from sovereign_agent import bot_services
                states = await _aio.to_thread(bot_services.service_states)
                any_active = any(s.get("active") for s in states.values())
                out = await _aio.to_thread(bot_services.toggle, not any_active)
            except Exception as exc:  # noqa: BLE001
                out = f"bots toggle unavailable: {type(exc).__name__}"
            self._write_meta(out)

        self.run_worker(_go(), exclusive=False)

    def action_toggle_movie_pane(self) -> None:  # movie-focus-d
        """✦ movie button → toggle the split-pane command center (left:
        chat, right: #movie-pane), NOT the full modal. Kevin, 2026-07-28:
        "split the whole chat screen so left side can be live chat and
        the right side can be whatever we have in the movie side of the
        TUI." /movies (typed) still opens the full MovieStudioScreen modal
        unchanged — two doors, same data. Same #main-class-toggle pattern
        obs-focus/layout-rows already use; the widget tree never changes,
        only CSS."""
        main = self.query_one("#main")
        now_visible = "movie-split" not in main.classes
        if now_visible:
            main.add_class("movie-split")
        else:
            main.remove_class("movie-split")
        if MoviePane is not None:
            try:
                pane = self.query_one("#movie-pane", MoviePane)
                if now_visible:
                    pane.refresh_all()
            except Exception as exc:  # noqa: BLE001
                logger.warning('movie pane refresh failed: %r', exc)

    def action_toggle_screen_studio(self) -> None:  # screen-studio-d
        """✦ screen button → toggle the split-pane recording studio
        (left: chat, right: #screen-studio-pane). Same #main-class-toggle
        pattern as action_toggle_movie_pane — the widget tree never
        changes, only CSS."""
        main = self.query_one("#main")
        now_visible = "screen-split" not in main.classes
        if now_visible:
            main.add_class("screen-split")
        else:
            main.remove_class("screen-split")

    def action_toggle_game_pane(self) -> None:  # game-pane-d
        """✦ godot button → toggle the split-pane Game Studio quick-action
        panel (left: chat, right: #game-pane). Same #main-class-toggle
        pattern as action_toggle_movie_pane/action_toggle_screen_studio —
        the widget tree never changes, only CSS."""
        main = self.query_one("#main")
        now_visible = "game-split" not in main.classes
        if now_visible:
            main.add_class("game-split")
        else:
            main.remove_class("game-split")
        if GamePane is not None:
            try:
                pane = self.query_one("#game-pane", GamePane)
                if now_visible:
                    pane.refresh_all()
            except Exception as exc:  # noqa: BLE001
                logger.warning('game pane refresh failed: %r', exc)

    def action_observatory(self) -> None:  # modes-crown-d
        """F3 / /observatory → the watching window."""
        try:
            from sovereign_agent.cockpit.modes_crown_ui import ObservatoryScreen

            if isinstance(self.screen, ObservatoryScreen):
                self.pop_screen(); return
            self.push_screen(ObservatoryScreen())
        except Exception as exc:  # noqa: BLE001
            logger.warning('observatory screen failed: %r', exc)

    def action_paste_clipboard(self) -> None:
        """Paste system clipboard contents at the input box cursor.

        Bound to Ctrl+V. Reads the clipboard via the platform's native
        tooling (wl-paste on Wayland, xclip / xsel on X11, pbpaste on
        macOS) and inserts at the current cursor position of the focused
        Input widget. If no Input is focused, the operation is a no-op.

        paste-plus-d — multi-line clipboard contents no longer collapse to a
        single space-joined line. Instead a PastePreviewScreen pops up
        with the full text in an editable TextArea (Ctrl+Enter/Send to
        dispatch it as a real turn, Escape/Cancel to back out untouched)
        so pasted code/notes/log excerpts keep their structure. Single-
        line content is unaffected — same collapse-and-insert behavior.

        ctrl-v-paste-d (Kevin, 2026-07-17): inside the 🔐 Key Vault,
        Ctrl+V pastes into the MASKED value field via the vault's own
        clipboard path (same as its 📋 button) — a secret must never
        detour through the chat input or the paste preview.

        movie-focus-d (Kevin, 2026-07-28): "I want to control V paste
        clipboard into the boxes." Real bug found + fixed here: this
        method was hardcoded to always paste into #input-box (the main
        chat box), regardless of what was actually focused — because the
        app-level Ctrl+V binding has priority=True (required so it isn't
        shadowed by Input's own hidden ctrl+v binding, see the BINDINGS
        comment above), it ALWAYS won the race, silently redirecting a
        paste typed into e.g. the movie pane's storyboard/clip/pitch/
        shot-beat boxes into the chat box instead. Now: if some OTHER
        Input widget currently has focus, paste goes there (collapsed to
        one line — Input widgets can't hold newlines), never routed
        through the chat-specific multiline-preview/dispatch flow below,
        which stays exactly as it was for the main chat box.
        """
        try:
            from .credentials_screen import CredentialsScreen as _CredScreen
            if isinstance(self.screen, _CredScreen):
                self.screen._paste_from_clipboard()
                return
        except Exception:  # noqa: BLE001
            pass
        text = self._read_clipboard()
        if not text:
            self._write_meta("[dim](clipboard empty or unreadable)[/dim]")
            return

        from textual.widgets import Input as _Input

        single_line = text.replace("\r\n", " ").replace("\n", " ").rstrip()
        focused = self.focused
        if isinstance(focused, _Input) and focused.id != "input-box":
            focused.insert_text_at_cursor(single_line)
            return

        normalized = text.replace("\r\n", "\n").rstrip("\n")
        if "\n" in normalized and PastePreviewScreen is not None:
            self.push_screen(PastePreviewScreen(normalized))
            return
        # Single-line (or PastePreviewScreen unavailable): collapse as before.
        try:
            input_box = self.query_one("#input-box", _Input)
        except Exception:
            return
        input_box.insert_text_at_cursor(single_line)

    def _send_pasted_text(self, text: str) -> None:  # paste-plus-d
        """Dispatch text confirmed/edited in PastePreviewScreen as a real
        turn. Slash commands still take the slash-command path (mirrors
        on_input_submitted's own top-priority rule); everything else goes
        straight to the conversation pipeline."""
        text = text.strip()
        if not text:
            return
        if text.startswith("/"):
            self._handle_slash(text)
            return
        self._dispatch_turn(text)

    def action_yank_last(self) -> None:
        """Copy Aria's most recent response to the system clipboard (Ctrl+Y).

        Scans _transcript backward from the end, collecting every "aria"
        line since the last "you" entry (i.e. the last response block).
        Writes to the clipboard via _write_clipboard() — wl-copy on
        Wayland/COSMIC, xclip/xsel on X11, pbcopy on macOS. Surfaces a
        visible meta line on both success and failure so the operator
        always knows what happened.
        """
        last_you_idx = max(
            (i for i, (sp, _) in enumerate(self._transcript) if sp == "you"),
            default=-1,
        )
        block = [
            text for sp, text in self._transcript[last_you_idx + 1 :]
            if sp == "aria"
        ]
        if not block:
            self._write_meta("[dim](nothing from aria to yank — send a message first)[/dim]")
            return
        payload = "\n".join(block)
        ok = self._write_clipboard(payload)
        if ok:
            preview = self._expandable(payload.replace("\n", " "), 200)
            self._write_meta(f"[dim]◊ yanked to clipboard: {preview}…[/dim]")
        else:
            self._write_meta(
                "[yellow]clipboard write failed — is wl-copy / xclip installed?[/yellow]"
            )

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

    def _show_tools_inline(self) -> None:
        """Print all registered tools (tier, name, description) to the chat log."""
        try:
            import sovereign_agent.tools as _tpkg  # noqa: F401 — trigger registration
            from sovereign_agent.authority import _TIER_REGISTRY
            entries = sorted(_TIER_REGISTRY.values(), key=lambda m: (m.tier, m.name))
            tier_labels = {
                0: "read-only", 1: "reversible write",
                2: "shell/long-running", 3: "irreversible",
            }
            self._write_meta("[b]◊ available tools[/b]")
            current_tier = -1
            for meta in entries:
                if meta.tier != current_tier:
                    current_tier = meta.tier
                    label = tier_labels.get(current_tier, f"tier {current_tier}")
                    self._write_meta(
                        f"[dim]── Tier {current_tier} · {label} ──[/dim]"
                    )
                desc_preview = self._expandable(meta.description, 200)
                self._write_meta(f"  [b]{meta.name}[/b]  [dim]{desc_preview}[/dim]")
            self._write_meta(f"[dim]{len(entries)} tools registered[/dim]")
        except Exception as exc:  # noqa: BLE001
            self._write_meta(f"[red]tools unavailable: {exc!r}[/red]")
    
    def _show_sentinels_inline(self) -> None:
        """Print health status of every registered sentinel to the chat log."""
        try:
            from sovereign_agent.stewardship.registry import gather_health
            from sovereign_agent.config import SETTINGS
            data_dir = SETTINGS.paths.data_dir
            if data_dir is None:
                self._write_meta(
                    "[yellow]data_dir not configured — cannot read sentinels[/yellow]"
                )
                return
            statuses = gather_health(data_dir)
            level_colors = {
                "ok": "green", "warning": "yellow",
                "error": "red", "unknown": "dim",
            }
            self._write_meta("[b]◊ sentinel health[/b]")
            for hs in statuses:
                color = level_colors.get(hs.level, "dim")
                self._write_meta(
                    f"  [{color}]{hs.level:8s}[/{color}]  {hs.sentinel_id}"
                    f"  [dim]{hs.summary}[/dim]"
                )
            self._write_meta(f"[dim]{len(statuses)} sentinels[/dim]")
        except Exception as exc:  # noqa: BLE001
            self._write_meta(f"[red]sentinels unavailable: {exc!r}[/red]")
    

    @work(exclusive=False, group="cli")
    async def _show_boot_status(self) -> None:
        """/ boot — full self-awareness snapshot via aria_status()."""
        self._write_meta("[bold cyan]◊ booting self-awareness...[/bold cyan]")
        try:
            from sovereign_agent.tools.aria_status import AriaStatusTool
            tool = AriaStatusTool()
            result = await tool.execute(tool.Args(), trace_id="boot")
        except Exception as exc:
            self._write_meta(f"[red]aria_status unavailable: {exc!r}[/red]")
            return
        if not result.ok:
            self._write_meta(f"[yellow]aria_status failed: {result.error}[/yellow]")
            return
        m = result.metadata or {}
        self._write_meta(f"[bold cyan]{result.output}[/bold cyan]")
        v = m.get("vessel", {})
        if "vram_free_mb" in v:
            self._write_meta(
                f"[dim]vessel:[/dim] "
                f"VRAM {v['vram_free_mb']}MB free/{v.get('vram_total_mb','?')}MB  "
                f"| RAM {v.get('mem_used_gb','?')}GB/{v.get('mem_total_gb','?')}GB  "
                f"| CPU {v.get('cpu_percent','?')}%  "
                f"| up {v.get('uptime_hours','?')}h"
            )
        s = m.get("sentinels", {})
        if "detail" in s:
            level_colors = {"ok": "green", "warning": "yellow", "error": "red"}
            parts = []
            for sd in s["detail"]:
                c = level_colors.get(sd["level"], "white")
                parts.append(f"[{c}]{sd['id']}:{sd['level']}[/{c}]")
            self._write_meta("[dim]sentinels:[/dim] " + "  ".join(parts))
        t = m.get("tools", {})
        if "total" in t:
            tc = t.get("tier_counts", {})
            tier_str = "  ".join(f"T{k[-1]}:{v}" for k, v in sorted(tc.items()))
            self._write_meta(f"[dim]tools:[/dim] {t['total']} loaded  [{tier_str}]")
        k = m.get("kernel", {})
        if "designation" in k:
            self._write_meta(
                f"[dim]kernel:[/dim] {k['designation']}  "
                f"| voice: {k.get('voice', '')}"
            )
        for c in k.get("commitments", []):
            self._write_meta(f"  [dim]·[/dim] {c}")
        w = m.get("workspace", {})
        if "repo_root" in w:
            self._write_meta(f"[dim]repo:[/dim]     {w['repo_root']}")
            self._write_meta(f"[dim]data dir:[/dim] {w.get('data_dir', '??')}")
        sess = m.get("session", {})
        if sess.get("status") not in (None, "no active session"):
            self._write_meta(
                f"[dim]session:[/dim]  {self._expandable(str(sess.get('goal','?')), 200)}  "
                f"[{sess.get('done',0)}/{sess.get('subtask_count',0)} done]"
            )



    @work(exclusive=False, group="cli")
    async def _show_command_invariants(self, command: str = "") -> None:
        """/ invariants [command] — show the invariant profile for a command."""
        if command:
            self._write_meta(f"[bold cyan]◊ invariants: {command}[/bold cyan]")
            try:
                from sovereign_agent.tools.command_invariants import ReadCommandInvariantTool
                tool = ReadCommandInvariantTool()
                result = await tool.execute(
                    tool.Args(command=command), trace_id="inv"
                )
                if result.ok:
                    for line in result.output.splitlines():
                        self._write_meta(line)
                else:
                    self._write_meta(f"[yellow]{result.error}[/yellow]")
            except Exception as exc:
                self._write_meta(f"[red]invariant read error: {exc!r}[/red]")
        else:
            self._write_meta("[bold cyan]◊ command invariant profiles[/bold cyan]")
            try:
                from sovereign_agent.tools.command_invariants import ListCommandInvariantsTool
                tool = ListCommandInvariantsTool()
                result = await tool.execute(tool.Args(), trace_id="inv-list")
                if result.ok:
                    for line in result.output.splitlines():
                        self._write_meta(line)
                else:
                    self._write_meta(f"[yellow]{result.error}[/yellow]")
            except Exception as exc:
                self._write_meta(f"[red]invariant list error: {exc!r}[/red]")

    def _show_cockpit_commands(self) -> None:
        """/ commands — display all slash commands grouped by category."""
        try:
            from sovereign_agent.tools.cockpit_commands import _COMMANDS, _CATEGORY_HEADERS
            self._write_meta("[bold cyan]◊ cockpit slash commands[/bold cyan]")
            prev_h = None
            for cmd, hint, desc in _COMMANDS:
                h = _CATEGORY_HEADERS.get(cmd)
                if h and h != prev_h:
                    self._write_meta(f"[dim]{h}[/dim]")
                    prev_h = h
                arg_str = f" {hint}" if hint else ""
                self._write_meta(f"  [cyan]/{cmd}[/cyan]{arg_str:22s} [dim]{desc}[/dim]")
        except Exception as exc:
            self._write_meta(f"[red]command list error: {exc!r}[/red]")

    def _show_claude_md(self) -> None:
        """/ docs — display CLAUDE.md (operating doctrine) inline."""
        import pathlib as _pl
        p = _pl.Path(__file__).resolve()
        for _ in range(8):
            candidate = p / "CLAUDE.md"
            if candidate.exists():
                try:
                    text = candidate.read_text(encoding="utf-8")
                    self._write_meta("[bold cyan]◊ CLAUDE.md — operating doctrine[/bold cyan]")
                    for line in text.splitlines():
                        self._write_meta(line or " ")
                except Exception as exc:
                    self._write_meta(f"[red]error reading CLAUDE.md: {exc}[/red]")
                return
            p = p.parent
        self._write_meta("[yellow]CLAUDE.md not found — searched 8 levels up from cockpit[/yellow]")

    @work(exclusive=False, group="cli")
    async def _show_diagnosis_log(self, limit: int = 10) -> None:
        """/ diagnosis — show recent conflict catalog entries."""
        self._write_meta(f"[bold cyan]◊ diagnosis catalog (last {limit})...[/bold cyan]")
        try:
            from sovereign_agent.tools.read_diagnosis_log import ReadDiagnosisLogTool
            tool = ReadDiagnosisLogTool()
            result = await tool.execute(tool.Args(limit=limit), trace_id="diag")
            if result.ok:
                for line in result.output.splitlines():
                    self._write_meta(line)
            else:
                self._write_meta(f"[yellow]{result.error}[/yellow]")
        except Exception as exc:
            self._write_meta(f"[red]diagnosis log error: {exc!r}[/red]")

    def _save_report(self) -> None:    
        """Full health report — printed in chat and saved to disk for sharing."""
        s = self.status
        if s.system is None:
            self._write_meta("[yellow]system metrics not ready yet — try again in a few seconds[/yellow]")
            return

        now = datetime.now(UTC)
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
            line = f"[{ts}·{self._chunk_session_id}] {speaker}: {text}\n"  # one-thread-d
            with path.open("a", encoding="utf-8") as f:
                f.write(line)
        except OSError:
            # Disk full, permission denied, etc. — the in-memory copy
            # still exists for /copy this session; nothing to surface.
            pass
        # checkpoint-chunks-d — feed the same turn into ChunkRecorder (non-lossy,
        # addressable checkpoint chunks — Workstream P). Best-effort:
        # never blocks the cockpit's UI flow, matches the disk-write
        # try/except right above.
        try:
            if self._chunk_recorder is None:
                from sovereign_agent.checkpoint_chunks import ChunkRecorder
                self._chunk_recorder = ChunkRecorder(self._chunk_session_id)
            self._chunk_recorder.record_turn(speaker, text)
        except Exception:  # noqa: BLE001
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

    def _handle_journal(self, arg: str) -> None:  # j-space-d
        """`/journal` → open the J-Space menu; `/journal <text>` → write an
        entry (yours). The J-Space is a reflective, two-way space."""
        try:
            from sovereign_agent.journal import (
                AUTHOR_HUMAN, add_entry, recent_entries, render_journal,
            )
        except Exception as exc:  # noqa: BLE001
            self._write_meta(f"[dim](journal unavailable: {type(exc).__name__})[/dim]")
            return
        if arg:
            add_entry(arg, author=AUTHOR_HUMAN)
            self._write_meta("[dim]◊ written to the J-Space 💛[/dim]")
            return
        # bare /journal → open the beautiful browse menu if available, else print
        if JournalScreen is not None:
            self.action_journal_menu()
        else:
            self._write_aria(render_journal(recent_entries(limit=12)))

    def _show_recap(self, arg: str) -> None:  # recap-command-d
        """`/recap [n]` — a short, scannable summary of the last n sessions
        (default 3). Kevin, 2026-07-25: "Maybe we can add recap last work
        session(s) events." Reuses each session's already-written
        plan.json (review_journal.build_review runs at every session
        end) rather than re-deriving anything."""
        from rich.markup import escape
        try:
            n = int(arg) if arg else 3
        except ValueError:
            self._write_meta("[dim]usage: /recap [n] — n = how many recent sessions[/dim]")
            return
        try:
            from sovereign_agent.config import SETTINGS
            from sovereign_agent.review_journal import compose_recap
            text = compose_recap(SETTINGS.paths.data_dir, n=n)
            for line in text.splitlines():
                self._chat_log.write(escape(line)) if self._chat_log else None
        except Exception as exc:  # noqa: BLE001
            self._write_meta(f"[dim](recap unavailable: {type(exc).__name__})[/dim]")

    def _show_catalog(self) -> None:  # catalog-command-d
        """`/catalog` — Kevin, 2026-07-25: "I always ask her what she
        would like for me to have her do. Let's make it where she can
        always find a grand catalog of things that I could have her do
        or work on, and sessions I could have her resume/continue."
        Read-only: every entry already genuinely exists (resumable
        sessions, open mistake cases, notes Kevin already left her) —
        never an AI-invented suggestion."""
        from rich.markup import escape
        try:
            from sovereign_agent.config import SETTINGS
            from sovereign_agent.catalog import compose_catalog
            text = compose_catalog(SETTINGS.paths.data_dir)
            for line in text.splitlines():
                self._chat_log.write(escape(line)) if self._chat_log else None
        except Exception as exc:  # noqa: BLE001
            self._write_meta(f"[dim](catalog unavailable: {type(exc).__name__})[/dim]")

    def _show_review(self, session_id: str) -> None:  # work-report-d
        """`/review <id>` → print a session's review (what she did · how · how
        to verify), read from its <data>/reviews/<id>/README.md."""
        from rich.markup import escape
        if not session_id:
            try:
                from sovereign_agent.work_report import compose_work_report
                self._write_aria(compose_work_report())
            except Exception:  # noqa: BLE001
                self._write_meta("[dim]usage: /review <session_id>[/dim]")
            return
        try:
            from sovereign_agent.config import SETTINGS
            from sovereign_agent.review_journal import list_reviews, reviews_root
            root = reviews_root(SETTINGS.paths.data_dir)
            # accept a full id or a 6-char suffix
            match = next((s for s in list_reviews(SETTINGS.paths.data_dir)
                          if s == session_id or s.endswith(session_id)), None)
            if match is None:
                self._write_meta(f"[dim]no review found for {escape(session_id)!s} — "
                                 "try /reviews to list them[/dim]")
                return
            readme = (root / match / "README.md").read_text(encoding="utf-8")
            for line in readme.splitlines():
                self._chat_log.write(escape(line)) if self._chat_log else None
            self._write_meta(f"[dim]full record: {root / match}[/dim]")
        except Exception as exc:  # noqa: BLE001
            self._write_meta(f"[dim](review unavailable: {type(exc).__name__})[/dim]")

    def _open_reports_folder(self) -> None:  # session-summary-push-d
        """`/open-reports` — open the reviews/ folder in the desktop file
        manager (Kevin, 2026-07-25: "open the file location for us in our
        cosmic explorer so we can easily read and review them without
        having to hunt for them"). Deliberately a real command Kevin
        types, never fired automatically from a session-end handler —
        launching a GUI app unprompted from a background worker would be
        its own kind of intrusive."""
        try:
            import subprocess
            from sovereign_agent.config import SETTINGS
            from sovereign_agent.review_journal import reviews_root

            root = reviews_root(SETTINGS.paths.data_dir)
            root.mkdir(parents=True, exist_ok=True)
            subprocess.Popen(  # noqa: S603 — fixed argv, no shell, path is internal-only
                ["xdg-open", str(root)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            self._write_meta(f"[dim]◊ opening {root}[/dim]")
        except FileNotFoundError:
            self._write_meta(
                f"[dim]xdg-open not available — reviews are at "
                f"{reviews_root(SETTINGS.paths.data_dir)}[/dim]"
            )
        except Exception as exc:  # noqa: BLE001
            self._write_meta(f"[dim](could not open reports folder: {type(exc).__name__})[/dim]")

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


    def _check_sentinel_transitions(self, statuses: list) -> None:  # sentinel-chat-method-d
        """Compare current sentinel states to previous; emit chat alerts on change.

        anti-lag-d: takes the already-gathered health list (computed once,
        off the main thread, inside _read_status) rather than calling
        gather_health() itself — that redundant second gather used to run
        synchronously on the UI thread every 5s and was the actual cause
        of the periodic freeze.
        """
        if not statuses:
            return

        WORSE = {"ok": 0, "warning": 1, "error": 2, "unknown": 1}
        new_states: dict[str, str] = {h.sentinel_id: str(h.level) for h in statuses}

        # command-menu-d — first call each session: seed the baseline silently.
        # There is no real 'regression' from a state that was never
        # actually observed — comparing against an assumed 'ok' default
        # produced spurious alerts on a fresh/empty data dir.
        if not self._prev_sentinel_states:
            self._prev_sentinel_states = new_states
            return

        for sid, level in new_states.items():
            prev = self._prev_sentinel_states.get(sid, "ok")
            if WORSE.get(level, 0) > WORSE.get(prev, 0):
                # Regression
                summary = next(
                    (h.summary for h in statuses if h.sentinel_id == sid), ""
                )
                color = "[red]" if level == "error" else "[yellow]"
                self._write_meta(
                    f"{color}◊ SENTINEL ALERT: {sid} — {level}[/{color.strip('[').strip(']')}]"
                )
                if summary:
                    self._write_meta(f"[dim]  {self._expandable(summary, 200)}[/dim]")
            elif WORSE.get(level, 0) < WORSE.get(prev, 0) and prev != "ok":
                # Recovery
                self._write_meta(f"[green]◊ sentinel cleared: {sid}[/green]")

        self._prev_sentinel_states = new_states

    def _write_meta(self, text: str) -> None:
        if self._chat_log is None:
            return
        self._chat_log.write(text)
        self._record("meta", text)

    def _stash_full_text(self, text: str) -> str:  # cockpit-hardening-d
        """Bounded ring buffer (last 20) of full text behind a truncated
        status line, keyed so /expand <key> can print it later. Process-
        local, never persisted -- deliberately not a second version of
        today's unbounded-growth bug."""
        if not hasattr(self, "_expand_stash"):
            self._expand_stash: dict[str, str] = {}
            self._expand_stash_order: list[str] = []
        self._expand_seq = getattr(self, "_expand_seq", 0) + 1
        key = f"e{self._expand_seq}"
        self._expand_stash[key] = text
        self._expand_stash_order.append(key)
        while len(self._expand_stash_order) > 20:
            old = self._expand_stash_order.pop(0)
            self._expand_stash.pop(old, None)
        return key

    def _expandable(self, text: str, limit: int = 200) -> str:  # cockpit-hardening-d
        """Truncate for a status line WITHOUT silently cutting content --
        Kevin (2026-07-20): 'I don't like text getting cut short... make
        sure no text gets cut short, in a resilient way that will not
        break the system.' Over the limit, stash the full text and say so
        plainly with a concrete next step -- never a bare mid-word cut."""
        if len(text) <= limit:
            return text
        key = self._stash_full_text(text)
        return f"{text[:limit]}\u2026 [dim](+{len(text) - limit} chars \u2014 /expand {key})[/dim]"

    # ── Memory pane refresh (v0.2.25.0) ──────────────────────────────

    def _refresh_inbox_pane(self) -> None:  # dual-inbox-d
        """Update the inbox pane (the 4th window) with the collaboration
        inbox, split into two clearly labeled directions:

          '◊ N waiting on you'  — Aria -> Kevin (direction=to_human, the
                                   original meaning of every request ever
                                   filed, unchanged in substance).
          '→ Aria'              — Kevin -> Aria (direction=to_aria, new):
                                   notes left via `sov requests tell` that
                                   she reads at her own safe checkpoints.

        Open items (most urgent first) carry their why/when/tags. Anything
        scheduled whose time has come surfaces under '⏰ due to revisit'. A
        'recent' section shows closed history with status markers, so
        scrolling up shows the whole story. Read-only; degrades silently.

        anti-lag-d: the SQLite reads used to run right here, synchronously
        on the main UI thread every 8s. This method now just schedules the
        worker below, which reads in a thread and renders on completion —
        same output, no event-loop stall. Safe for every existing caller
        (timer, call_after_refresh, tests): scheduling is synchronous.
        """
        if self._inbox_log is None:
            return
        self._refresh_inbox_pane_worker()

    @staticmethod
    def _read_inbox_data() -> tuple:
        """The pure data read (SQLite) — runs in a worker thread."""
        from sovereign_agent.config import SETTINGS
        from sovereign_agent.persistence.store import ErebloStore
        from sovereign_agent.workflow.requests import DIRECTION_TO_HUMAN, RequestStore
        rs = RequestStore(ErebloStore(SETTINGS.paths.atoms_db))
        return (
            rs.list_open(direction=DIRECTION_TO_HUMAN),
            rs.due(),
            rs.list(limit=40, direction=DIRECTION_TO_HUMAN),
            rs.list_for_aria(),
        )

    @work(exclusive=True, group="inbox-refresh")
    async def _refresh_inbox_pane_worker(self) -> None:  # anti-lag-d
        from rich.markup import escape

        try:
            open_items, due_items, recent, to_aria_items = await asyncio.to_thread(
                self._read_inbox_data
            )
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
            self._inbox_log.write("[dim]◊ inbox clear — nothing waiting[/dim]")
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

        # → Aria — notes Kevin left FOR her, separate from her own asks.
        if to_aria_items:
            self._inbox_log.write(f"[bold magenta]→ Aria ({len(to_aria_items)})[/bold magenta]")
            for r in to_aria_items:
                pri = f"{r.priority_emoji} " if r.priority != "normal" else ""
                self._inbox_log.write(
                    f"  ✉ {pri}[dim]{escape(r.title)}[/dim]  [dim][{r.short_id}][/dim]")
            self._inbox_log.write("")

        # Recent history — the status in WORDS (glyph-literacy-d: Kevin
        # read the resolved threading receipt as a live issue twice; a
        # word is unambiguous where a marker isn't).
        closed = [r for r in recent if r.status not in ("open",)]
        if closed:
            self._inbox_log.write("[bold cyan]recent (closed history)[/bold cyan]")
            for r in closed[:20]:
                self._inbox_log.write(
                    f"  {r.status_emoji} [dim]{escape(r.title)} "
                    f"— {r.status.upper()}[/dim]")

        self._announce_new_inbox_activity(open_items, recent, to_aria_items)

    def _announce_new_inbox_activity(self, open_items, recent, to_aria_items) -> None:  # inbox-in-chat-d
        """The inbox pane is a separate window Kevin has to remember to
        check. This announces genuinely NEW inbox activity (something
        Aria sent, something that got resolved, something Kevin left for
        her) as a meta-line in the main chat pane too -- the conversation
        and the collaboration record stay visible in the same place.

        The first poll after mount seeds the snapshot without announcing
        anything (there's no "new" relative to before the cockpit was
        even open) -- only genuine deltas across two live polls ever
        write to chat.
        """
        from rich.markup import escape

        current: dict[str, str] = {
            r.request_id: r.status
            for r in (*open_items, *recent, *to_aria_items)
        }
        seen = self._inbox_seen_state
        if seen is None:
            self._inbox_seen_state = current
            return

        by_id = {r.request_id: r for r in (*open_items, *recent, *to_aria_items)}
        for rid, status in current.items():
            prev_status = seen.get(rid)
            r = by_id.get(rid)
            if r is None:
                continue
            if prev_status is None and r.direction != "to_aria":
                # A new outgoing request from Aria -- Kevin should see it
                # where he's already looking, not just in a pane he has
                # to remember exists.
                self._write_meta(
                    f"[magenta]✉ she left you a note:[/magenta] "
                    f"{escape(r.title)} [dim][{r.short_id}][/dim]"
                )
            elif prev_status is not None and prev_status != status:
                self._write_meta(
                    f"[dim]✉ inbox update:[/dim] {escape(r.title)} "
                    f"[dim]→ {status}[/dim]"
                )
        self._inbox_seen_state = current

    def _maybe_run_security_scan(self) -> None:  # security-strip-wire-d
        """Kick off the background Tier-A scan if one isn't already running
        ANYWHERE in this process (module-level guard, not per-instance — see
        the docstring on _SECURITY_SCAN_CACHE above). Only ever called from
        the 300s periodic timer, never from mount directly — see the module
        docstring's "2nd pass" note on why an eager on-mount kickoff was
        removed (it's what caused the real GIL-contention regression)."""
        global _SECURITY_SCAN_RUNNING
        with _SECURITY_SCAN_LOCK:
            if _SECURITY_SCAN_RUNNING:
                return
            _SECURITY_SCAN_RUNNING = True
        self._run_security_scan_worker()

    @work(exclusive=True, group="security-scan", thread=True)  # security-strip-wire-d
    def _run_security_scan_worker(self) -> None:
        """Runs scan_tree() off the main thread — ~3s over ~450 files. Only
        ever updates the process-wide cache; every cockpit instance's 8s
        strip refresh just reads it."""
        global _SECURITY_SCAN_CACHE, _SECURITY_SCAN_RUNNING
        try:
            from pathlib import Path

            from sovereign_agent.scanner_tier_a.scanner import scan_tree
            import sovereign_agent

            src_root = Path(sovereign_agent.__file__).parent
            result = scan_tree(src_root)
            _SECURITY_SCAN_CACHE = {
                "blocks": len(result.blocks),
                "warns": len(result.warns),
                "files_scanned": result.files_scanned,
            }
        except Exception:  # noqa: BLE001 — cache just stays stale/empty on failure
            pass
        finally:
            with _SECURITY_SCAN_LOCK:
                _SECURITY_SCAN_RUNNING = False

    def _maybe_run_vessel_kernel_scan(self) -> None:  # vessel-health-d
        """Kick off the background kernel-coherence scan if one isn't
        already running anywhere in this process (module-level guard,
        mirrors _maybe_run_security_scan exactly). Only ever called from
        the 300s periodic timer, never from mount directly."""
        global _VESSEL_KERNEL_RUNNING
        with _VESSEL_KERNEL_LOCK:
            if _VESSEL_KERNEL_RUNNING:
                return
            _VESSEL_KERNEL_RUNNING = True
        self._run_vessel_kernel_scan_worker()

    @work(exclusive=True, group="vessel-kernel-scan", thread=True)  # vessel-health-d
    def _run_vessel_kernel_scan_worker(self) -> None:
        """Runs H2's find_references() off the main thread — ~3s over
        ~450 files. Only ever updates the process-wide cache; every
        cockpit instance's 8s strip refresh just reads it."""
        global _VESSEL_KERNEL_CACHE, _VESSEL_KERNEL_RUNNING
        try:
            from pathlib import Path

            import sovereign_agent
            from sovereign_agent.canon_embodiment.mapper import find_references

            repo_root = Path(sovereign_agent.__file__).parent.parent.parent
            report = find_references(repo_root)
            ratio = (
                report.embodied_count / report.total_clauses
                if report.total_clauses else 0.0
            )
            _VESSEL_KERNEL_CACHE = {"ratio": ratio, "summary": report.summary()}
        except Exception:  # noqa: BLE001 — cache just stays stale/empty on failure
            pass
        finally:
            with _VESSEL_KERNEL_LOCK:
                _VESSEL_KERNEL_RUNNING = False

    def _maybe_run_auto_backup(self) -> None:  # auto-backup-d
        """Hourly check: if the newest snapshot is older than the cadence,
        kick a background snapshot via BackupSentinel.scan(). Timer-only —
        never called on mount (a short-lived test cockpit boot must never
        write a snapshot; same discipline as the vessel kernel scan)."""
        global _AUTO_BACKUP_RUNNING
        with _AUTO_BACKUP_LOCK:
            if _AUTO_BACKUP_RUNNING:
                return
            _AUTO_BACKUP_RUNNING = True
        self._run_auto_backup_worker()

    @work(exclusive=True, group="auto-backup", thread=True)  # auto-backup-d
    def _run_auto_backup_worker(self) -> None:
        """Snapshot + verify off the main thread. The sentinel no-ops
        when a fresh-enough snapshot already exists (overdue() check)."""
        global _AUTO_BACKUP_RUNNING
        try:
            from sovereign_agent.config import SETTINGS
            from sovereign_agent.stewardship.backup_sentinel import BackupSentinel

            sentinel = BackupSentinel(data_dir=SETTINGS.paths.data_dir)
            if sentinel.is_enabled() and sentinel.overdue():
                sentinel.scan()
        except Exception:  # noqa: BLE001 — backup failure must never hurt the cockpit
            pass
        finally:
            with _AUTO_BACKUP_LOCK:
                _AUTO_BACKUP_RUNNING = False

    def on_unmount(self) -> None:  # cockpit-flush-d
        """Shutdown flush: seal any conversation turns still buffered in
        the ChunkRecorder (up to 20 were silently lost on every exit
        before this) and fsync pending events. Best-effort — shutdown
        must never fail because a flush did."""
        try:
            if getattr(self, "_chunk_recorder", None) is not None:
                self._chunk_recorder.seal_now()
        except Exception:  # noqa: BLE001
            pass
        try:
            from sovereign_agent.events import force_fsync

            force_fsync()
        except Exception:  # noqa: BLE001
            pass
        # vram-release-d — closing her frees the GPU: ask Ollama to unload
        # resident models NOW (keep_alive=0) instead of holding VRAM for the
        # keep-alive window. Bounded: a hung Ollama can delay exit ≤2s, never
        # hang it (thread is daemon; join is capped).
        try:
            import threading

            from sovereign_agent.model_release import release_all

            t = threading.Thread(target=release_all, daemon=True)
            t.start()
            t.join(timeout=2.0)
        except Exception:  # noqa: BLE001
            pass

    def _layout_pref_path(self):  # flexi-layout-d
        from sovereign_agent.config import SETTINGS

        return SETTINGS.paths.config_dir / "cockpit_layout.json"

    def action_toggle_layout(self, mode: str | None = None) -> None:  # flexi-layout-d
        """Ctrl+O: cycle Layout A (5 columns) -> B (chat column + stacked
        rows) -> C (chat full-width top + panes row below, cockpit-
        hardening-d) -> A. Persists the preference. Pass mode explicitly
        ("columns"|"rows"|"chat-top") to set a specific layout instead of
        cycling — used by action_quick_view()."""
        import json as _json

        try:
            main = self.query_one("#main")
        except Exception:  # noqa: BLE001
            return
        current = ("chat-top" if main.has_class("chat-top")
                  else "rows" if main.has_class("layout-rows")
                  else "columns")
        if mode not in ("columns", "rows", "chat-top"):
            mode = {"columns": "rows", "rows": "chat-top", "chat-top": "columns"}[current]
        main.remove_class("layout-rows")
        main.remove_class("chat-top")
        if mode == "rows":
            main.add_class("layout-rows")
        elif mode == "chat-top":
            main.add_class("chat-top")
        try:
            self._layout_pref_path().write_text(
                _json.dumps({"layout": mode}),
                encoding="utf-8",
            )
        except Exception:  # noqa: BLE001 — a pref-write failure never breaks the toggle
            pass
        self._write_meta(f"[dim]◊ layout: {mode}[/dim]")

    def action_quick_view(self) -> None:  # cockpit-hardening-d
        """Button beside 'commands': one click -> chat gets a full-width
        top section, inbox + live activity split below (Kevin, 2026-07-20,
        live activity added 2026-07-21). Second click restores the
        standard full view (all panes, columns)."""
        try:
            main = self.query_one("#main")
        except Exception:  # noqa: BLE001
            return
        simplified = main.has_class("chat-top") and main.has_class("obs-focus")
        if simplified:
            self.action_toggle_layout(mode="columns")
            self.action_obs_mode(mode="all")
        else:
            self.action_toggle_layout(mode="chat-top")
            self.action_obs_mode(mode="focus")

    def _apply_saved_layout(self) -> None:  # flexi-layout-d
        """On mount: honor the persisted layout + observability prefs."""
        import json as _json

        try:
            pref = _json.loads(self._layout_pref_path().read_text(encoding="utf-8"))
            layout = pref.get("layout")
            if layout == "rows":
                self.query_one("#main").add_class("layout-rows")
            elif layout == "chat-top":  # cockpit-hardening-d
                self.query_one("#main").add_class("chat-top")
            if pref.get("obs") == "focus":       # obs-modes-d
                self.query_one("#main").add_class("obs-focus")
        except Exception:  # noqa: BLE001 — no pref file = Layout A, silently
            pass

    def action_obs_mode(self, mode: str | None = None) -> None:  # obs-modes-d
        """Observability modes (Kevin): 'all' = every window (default);
        'focus' = live chat + inbox only. No arg toggles. Persisted."""
        import json as _json

        try:
            main = self.query_one("#main")
        except Exception:  # noqa: BLE001
            return
        if mode not in ("all", "focus"):
            mode = "all" if main.has_class("obs-focus") else "focus"
        if mode == "focus":
            main.add_class("obs-focus")
        else:
            # `movie-split` hides Memory and Atelier independently of
            # observability.  Returning to All must be a complete recovery
            # path, not a misleading no-op while Movie split is still active.
            main.remove_class("obs-focus")
            main.remove_class("movie-split")  # pane-recovery-d
        try:
            pref = {}
            try:
                pref = _json.loads(
                    self._layout_pref_path().read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                pref = {}
            pref["obs"] = mode
            self._layout_pref_path().write_text(
                _json.dumps(pref), encoding="utf-8")
        except Exception:  # noqa: BLE001 — a pref-write failure never breaks the toggle
            pass
        self._write_meta(
            "[dim]◊ observability: [bold]focus[/bold] — live chat + inbox "
            "only ([/dim][dim]/obs[/dim][dim] returns to all windows)[/dim]"
            if mode == "focus" else
            "[dim]◊ observability: [bold]all windows[/bold][/dim]")

    def _queue_for_aria(self, text: str) -> None:  # session-bridge-d
        """Queue an operator message for her next safe checkpoint."""
        try:
            from sovereign_agent.session_bridge import queue_operator_message

            queue_operator_message(text)
            self._write_meta(
                "[dim]◊ queued for her next safe checkpoint 💛 "
                "(`/halt` if you need her to stop NOW)[/dim]"
            )
        except Exception as exc:  # noqa: BLE001 — his words must never vanish silently
            self._write_meta(f"[red]could not queue message: {exc!r}[/red]")

    def _is_real_auto_active(self) -> bool:  # auto-crown-fix-d
        """The HONEST check: the underlying AutoCrownStore session is
        genuinely active -- this IS the ground truth for "is a timed auto
        session running," regardless of which path armed it.

        header-auto-desync-d (Kevin, 2026-07-25): this used to ALSO
        require crown_armed() (mode_crown.json written by /modes or
        /auto). But start_auto (tools/auto_tools.py) — which Aria is
        explicitly allowed to call herself — arms AutoCrownStore directly
        and never writes mode_crown.json, so a genuinely active
        self-service session always read as "Non-auto" in the header.
        Checking the store directly handles both directions: a crown
        record pointing at a since-cancelled/expired store session
        already correctly reads inactive (store.status() reflects that),
        and a store session armed without any crown record now correctly
        reads active. Also force-expire a lease that's past its deadline
        right here, instead of relying only on loop.py's periodic call —
        a stale-but-unexpired lease must not read "active" for up to
        however long that loop takes to get around to it."""
        try:
            from sovereign_agent.auto_crown import get_auto_crown_store
            store = get_auto_crown_store()
            if store.is_expired():
                store.expire()
            session = store.status()
            return session is not None and session.status == "active"
        except Exception:  # noqa: BLE001
            return False

    def _handle_auto_command(self, auto_arg: str) -> None:  # auto-crown-fix-d
        """/auto — deterministic, direct calls into the real crown
        system (modes_crown.profiles.set_crown_mode), not a
        natural-language directive hoping the model calls a tool.

        Bare /auto toggles the auto-1h profile (no typed confirmation --
        genuinely quick). The 3-hour profile has its OWN typed
        confirmation ("I approve 3 hours of autonomy", separate from the
        trust-tier-raise phrase) by deliberate design -- this handler
        does not try to replicate that ceremony inline; it points at the
        existing, already-correct /modes (F2) screen instead.
        """
        from sovereign_agent.modes_crown.profiles import (
            AUTO3H_CONFIRMATION, CrownError, crown_armed, current_profile,
            set_crown_mode,
        )

        low = auto_arg.lower()
        if low in ("stop", "cancel", "off"):
            try:
                set_crown_mode("chat", reason="operator disarmed via /auto stop")
                self._write_meta("[dim]◊ auto disarmed — back to chat mode[/dim]")
            except CrownError as exc:
                self._write_meta(f"[red]/auto stop failed: {exc}[/red]")
            self._refresh_sub_title()
            return

        if low in ("status", "state"):
            try:
                profile = current_profile() if crown_armed() else None
                from sovereign_agent.modes_crown.profiles import lease_remaining_seconds
                remaining = lease_remaining_seconds() if profile else 0
                if profile and profile.lease_seconds and remaining > 0:
                    mins = remaining // 60
                    self._write_meta(
                        f"[cyan]◊ auto: {profile.title}[/cyan] · "
                        f"{mins // 60}h{mins % 60:02d}m remaining"
                    )
                else:
                    self._write_meta("[dim]◊ auto: not armed (Semi-Auto)[/dim]")
            except Exception as exc:  # noqa: BLE001
                self._write_meta(f"[red]/auto status failed: {exc}[/red]")
            return

        if not auto_arg:
            # Bare /auto: quick on/off toggle of the 1-hour profile --
            # no typed confirmation needed, genuinely one keystroke.
            #
            # auto-message-clarity-d (Kevin, 2026-07-21): "it kicked me
            # out of auto mode and said do /work <goal> which... is
            # confusing a bit if its supposed to kick me out of auto or
            # not." Verified directly (CockpitApp test harness): arming
            # genuinely stays armed, _is_real_auto_active() is True right
            # after, the header updates immediately -- there was no real
            # disarm bug. The OLD arm message just read ambiguously: "auto
            # armed... say /work to actually start working" can sound
            # like a walk-back ("so is it actually on or not?"), and bare
            # /auto being a silent TOGGLE means typing it a second time
            # (out of habit, or to double-check) disarms it with no
            # warning -- an easy way to genuinely get "kicked out" without
            # meaning to. Both messages below now state ON/OFF as an
            # unambiguous fact first, and the arm message says plainly
            # that she STAYS armed and how to turn it back off on purpose.
            if self._is_real_auto_active():
                try:
                    set_crown_mode("chat", reason="operator toggled off via bare /auto")
                    self._write_meta(
                        "[dim]◊ AUTO IS OFF[/dim] — back to chat mode "
                        "(Semi-Auto). `/auto` to arm it again."
                    )
                except CrownError as exc:
                    self._write_meta(f"[red]/auto toggle-off failed: {exc}[/red]")
            else:
                try:
                    set_crown_mode("auto-1h", reason="operator toggled on via bare /auto")
                    self._write_meta(
                        "[bold cyan]◊ AUTO IS ON[/bold cyan] — armed for 1 "
                        "hour, and she STAYS armed. Give her a goal any "
                        "time with `/work <goal>` and she'll start within "
                        "this window. Type `/auto` again (or `/auto stop`) "
                        "to turn it back off — bare `/auto` is a toggle."
                    )
                except CrownError as exc:
                    self._write_meta(f"[red]/auto toggle-on failed: {exc}[/red]")
            self._refresh_sub_title()
            return

        # A number was given. <=1h maps to the no-confirmation auto-1h
        # profile directly; anything longer needs the 3-hour tier, which
        # has its own typed confirmation -- redirect to /modes rather
        # than guess at replicating that ceremony here.
        try:
            hours = float(auto_arg)
        except ValueError:
            self._write_meta(
                "[yellow]usage: /auto (toggle 1h) | /auto <=1 (arm 1h) | "
                "/auto stop | /auto status — for 3 hours, press F2 (/modes) "
                "and type the confirmation phrase[/yellow]"
            )
            return

        if hours <= 1.0:
            try:
                set_crown_mode("auto-1h", reason=f"operator requested /auto {hours}h")
                self._write_meta(
                    "[bold cyan]◊ AUTO IS ON[/bold cyan] — armed for 1 "
                    "hour, and she STAYS armed. Give her a goal any time "
                    "with `/work <goal>` and she'll start within this "
                    "window."
                )
            except CrownError as exc:
                self._write_meta(f"[red]/auto {hours}h failed: {exc}[/red]")
            self._refresh_sub_title()
        else:
            self._write_meta(
                f"[yellow]{hours}h needs the 3-hour tier, which requires a typed "
                f"confirmation by design (not something this command bypasses). "
                f"Press F2 (or type /modes), pick 'Auto · 3 hours', and type: "
                f"[b]{AUTO3H_CONFIRMATION}[/b][/yellow]"
            )

    def _handle_pause_command(self, pause_arg: str) -> None:  # graceful-pause-d
        """/pause — a real, voluntary, resumable pause for the in-process
        work session (Kevin, 2026-07-20: "so if I /pause I can /resume
        later via a resume sessions menu").

        This is NOT a new mechanism -- interrupts.py already ships exactly
        this ("a flag file... long-running loops call
        check_conversation_request() at safe checkpoints") and
        agent_session.run_session's own Gate 2 already calls
        interrupt_checkpoint() every iteration and correctly sets
        status="paused" when it fires. The one missing piece was the
        trigger: nothing in the cockpit ever called
        interrupts.request_conversation(). This command is that trigger.

        pause-clean-stop-d (Kevin, 2026-07-25): "make /pause end the
        session. So I don't have to /pause cancel every time... Just
        pause, work, or resume." Two changes from the original design:
          1. Bare /pause with nothing running is now a clean no-op reply
             instead of writing a request flag nothing will ever
             acknowledge (previously left dangling until manually
             cleared).
          2. `cancel`/`status` still work (harmless, occasionally useful
             for scripts or mid-request second thoughts) but are no
             longer part of the primary flow or its help text --
             _clear_session_busy_state() now clears the interrupts flags
             itself the moment a session worker actually finishes, so
             "cancel" is never something Kevin needs to remember.

        Deliberately separate from /halt: this never touches
        PROTOCOL-ZERO, needs no /disarm afterward, and -- unlike a halted
        session, whose "halted" status is NOT in resumable_sessions()'s
        filter list -- a session paused this way ends up with
        status="paused", which IS resumable via /resume or the Resume
        Menu (F6). Same safe-checkpoint-only guarantee as /halt: the
        loop only yields between iterations, never mid-call.
        """
        from sovereign_agent import interrupts

        sub = pause_arg.strip().lower()
        if sub in ("cancel", "clear"):
            try:
                state = interrupts.clear_conversation_request()
                self._write_meta(f"[dim]◊ pause request cleared[/dim]\n{state.render()}")
            except Exception as exc:  # noqa: BLE001
                self._write_meta(f"[red]/pause cancel failed: {exc!r}[/red]")
            return

        if sub == "status":
            try:
                self._write_meta(f"[cyan]◊ pause status[/cyan]\n{interrupts.status().render()}")
            except Exception as exc:  # noqa: BLE001
                self._write_meta(f"[red]/pause status failed: {exc!r}[/red]")
            return

        if not (self._busy or getattr(self, "_session_running", False)):
            self._write_meta(
                "[dim]◊ nothing running right now — she's already parked. "
                "/work <goal> to start, /resume to pick up a paused "
                "session.[/dim]"
            )
            return

        note = pause_arg.strip() or None
        try:
            interrupts.request_conversation(note=note)
            self._write_meta(
                "[cyan]◊ pausing[/cyan] — she'll stop at the next safe "
                "checkpoint (never mid-step) and park cleanly, ready for "
                "/resume or a fresh /work. [dim]This does not trip "
                "PROTOCOL-ZERO — no /disarm needed.[/dim]"
            )
        except Exception as exc:  # noqa: BLE001
            self._write_meta(f"[red]/pause failed: {exc!r}[/red]")

    def _announce_review_ready(self, session_id: str) -> None:  # session-summary-push-d
        """session-summary-push-d (Kevin, 2026-07-25): "at the end of
        every session... the system should automatically begin summary
        docs... and present where the docs are located." The review
        directory (review_journal.build_review()) was already written
        by session_bridge before this method's caller even got control
        back — it just never told anyone where it landed. This looks it
        up and prints the path, so Kevin never has to hunt for it or
        remember /review exists."""
        try:
            from sovereign_agent.config import SETTINGS
            from sovereign_agent.review_journal import reviews_root
            path = reviews_root(SETTINGS.paths.data_dir) / session_id
            if path.is_dir():
                self._write_meta(
                    f"[dim]◊ review written: {path}  "
                    f"(/review {session_id[-6:]} to read it here, "
                    f"/open-reports to open the folder)[/dim]"
                )
        except Exception:  # noqa: BLE001
            pass

    def _armed_wall_seconds(self, default: int = 3600) -> int:  # session-wall-seconds-d
        """session-wall-seconds-d (Kevin, 2026-07-25): "auto only gives
        me 1 hour" -- root cause: start_goal_session/resume_goal_session
        both default wall_seconds=3600 and the ONLY call sites (work +
        resume workers) never overrode it, so even a fully-armed 3-hour
        auto lease still capped each individual session at 1 hour. This
        derives the real ceiling from whatever lease is actually armed
        (modes_crown.profiles.lease_remaining_seconds() -- the same
        observability read the header uses) and only ever RAISES the
        default, never shrinks it below the 1h floor that already
        existed. goal_modulator can still raise it further on top of
        this if the goal text itself states a longer duration."""
        try:
            from sovereign_agent.modes_crown.profiles import lease_remaining_seconds
            remaining = lease_remaining_seconds()
            return remaining if remaining > default else default
        except Exception:  # noqa: BLE001
            return default

    def _handle_cloud_command(self, arg: str) -> None:  # cloud-mode-command-d
        """`/cloud` (bare) shows status; `/cloud on` / `/cloud off` toggles
        Fast Free Cloud mode. Kevin, 2026-07-25: "let's add a fast free
        cloud mode?" Explicit, off by default -- nothing leaves this
        machine unless this has been turned on deliberately. When on,
        CloudClient still falls back to a real local model on any cloud
        failure, refusal, or missing internet connection."""
        from sovereign_agent.cloud_mode import is_cloud_mode_enabled, set_cloud_mode

        if arg in ("on", "enable"):
            set_cloud_mode(True)
            self._write_meta(
                "[cyan]\u2601 cloud mode ON[/cyan] — chat turns route through "
                "pooled free cloud providers; falls back to local on any "
                "failure, refusal, or no internet."
            )
        elif arg in ("off", "disable"):
            set_cloud_mode(False)
            self._write_meta("[cyan]\u2601 cloud mode OFF[/cyan] — back to local-only.")
        else:
            state = "ON" if is_cloud_mode_enabled() else "OFF"
            self._write_meta(
                f"[cyan]\u2601 cloud mode: {state}[/cyan] — `/cloud on` / `/cloud off` to change."
            )

    def _handle_income_command(self, arg: str) -> None:  # income-ledger-d
        """`/income` (bare) shows the verified-income total; `/income sync`
        polls Stripe for real succeeded charges and ledgers any new ones.

        `/income record amazon <dollars> [note]` manually records a real,
        already-received Amazon Associates payout — Amazon exposes no
        public API for reading commission reports (the Product
        Advertising API is for product lookups, not earnings), so Kevin
        confirming a real payout from Amazon's own dashboard IS the
        verification act here, same "only updates on verified income
        received" principle as the Stripe path.

        Kevin, 2026-07-25: "make income earned a real metric too, but only
        updates on verified income received." The game window READS the
        local ledger every 8s (cheap, no network); this command is the
        only thing that actually calls Stripe, and only records a charge
        Stripe itself confirms succeeded/paid/not-refunded — never a
        subscription's "active" status alone. Off the UI thread; the
        vaulted STRIPE_SECRET_KEY is never logged or echoed."""
        from sovereign_agent.income_ledger import total_income_cents

        tokens = arg.split(None, 1)
        verb = tokens[0] if tokens else ""
        rest = tokens[1] if len(tokens) > 1 else ""

        if verb == "record":
            sub = rest.split(None, 2)
            if len(sub) < 2 or sub[0] != "amazon":
                self._write_meta(
                    "[red]usage: /income record amazon <dollars> [note][/red]"
                )
                return
            try:
                dollars = float(sub[1])
                if dollars <= 0:
                    raise ValueError
            except ValueError:
                self._write_meta(
                    "[red]usage: /income record amazon <dollars> [note][/red]"
                )
                return
            note = sub[2] if len(sub) > 2 else ""
            try:
                import time as _time
                from sovereign_agent.income_ledger import record_income
                charge_id = f"amazon-manual-{int(_time.time() * 1000)}"
                record_income(charge_id, int(round(dollars * 100)),
                              source="amazon-associates", note=note)
                self._write_meta(
                    f"[green]◊ recorded ${dollars:.2f} verified Amazon "
                    f"income[/green] — you confirmed this from Amazon's own "
                    f"dashboard, that's the verification."
                )
            except Exception as exc:  # noqa: BLE001
                self._write_meta(f"[red]income record failed: {type(exc).__name__}[/red]")
            return

        if arg != "sync":
            cents = total_income_cents()
            self._write_meta(
                f"[green]$ {cents / 100:.2f} verified income[/green] — "
                f"`/income sync` to pull any new Stripe charges."
            )
            return

        async def _go() -> None:
            import asyncio as _aio
            try:
                from sovereign_agent.credentials import read_env
                from sovereign_agent import stripe_sync
                key = (read_env().get("STRIPE_SECRET_KEY") or "").strip()
                if not key:
                    out = ("[yellow]◊ no Stripe key vaulted — /keys → "
                           "STRIPE_SECRET_KEY first[/yellow]")
                else:
                    result = await _aio.to_thread(
                        stripe_sync.sync_verified_income,
                        stripe_sync._default_opener, key)
                    if result["detail"] != "ok":
                        out = f"[yellow]◊ income sync: {result['detail']}[/yellow]"
                    else:
                        out = (f"[green]◊ income sync — {result['synced']} new "
                               f"verified charge(s), ${result['total_cents'] / 100:.2f} "
                               f"total[/green]")
            except Exception as exc:  # noqa: BLE001
                out = f"[red]income sync failed: {type(exc).__name__}[/red]"
            self._write_meta(out)

        self.run_worker(_go(), exclusive=False)

    def _handle_payout_command(self, arg: str) -> None:  # payouts-d
        """`/payout` (bare) shows who's owed what and why they'd be
        skipped; `/payout run` actually transfers real money via Stripe
        Connect. Kevin, 2026-07-25: chose fully automated payouts — the
        automation is in the MECHANISM (real Stripe transfers, no manual
        per-person sending); firing this is still an explicit human
        action, since the cockpit itself (only ever run on Kevin's own
        machine) already is the owner-only channel for anything touching
        real money, same as /income sync. Off the UI thread; the vaulted
        STRIPE_SECRET_KEY is never logged or echoed."""
        from sovereign_agent import referrals

        if arg != "run":
            owed = [r for r in referrals.list_profiles(self._data_dir_for_payouts())
                   if r.get("role") == referrals.ROLE_MARKETER
                   and r.get("pending_cents", 0) > 0]
            if not owed:
                self._write_meta(
                    "[dim]◊ no marketer has a pending balance right now[/dim]"
                )
                return
            lines = [f"• {r['id']}: ${r['pending_cents'] / 100:.2f} pending"
                    for r in owed]
            self._write_meta(
                "[cyan]◊ pending marketer payouts[/cyan]\n" + "\n".join(lines) +
                "\n`/payout run` to actually transfer via Stripe Connect."
            )
            return

        async def _go() -> None:
            import asyncio as _aio
            try:
                from sovereign_agent.credentials import read_env
                from sovereign_agent import payouts
                key = (read_env().get("STRIPE_SECRET_KEY") or "").strip()
                if not key:
                    out = ("[yellow]◊ no Stripe key vaulted — /keys → "
                           "STRIPE_SECRET_KEY first[/yellow]")
                else:
                    result = await _aio.to_thread(
                        payouts.run_payouts, self._data_dir_for_payouts(),
                        payouts._default_opener, key)
                    if result["detail"] != "ok":
                        out = f"[yellow]◊ payout run: {result['detail']}[/yellow]"
                    elif not result["paid"]:
                        skip_reasons = ", ".join(
                            f"{s['marketer']} ({s['reason']})" for s in result["skipped"]
                        ) or "no marketers with a pending balance"
                        out = f"[dim]◊ nothing paid out — {skip_reasons}[/dim]"
                    else:
                        out = (f"[green]◊ payout run — {len(result['paid'])} "
                               f"marketer(s) paid, ${result['total_cents'] / 100:.2f} "
                               f"total[/green]")
            except Exception as exc:  # noqa: BLE001
                out = f"[red]payout run failed: {type(exc).__name__}[/red]"
            self._write_meta(out)

        self.run_worker(_go(), exclusive=False)

    def _data_dir_for_payouts(self):
        from sovereign_agent.config import SETTINGS
        return SETTINGS.paths.data_dir

    def _handle_add_time(self, hours: float) -> None:  # mid-session-add-time-d
        """"+1h" button / `/addtime [hours]` — extend the currently armed
        auto lease WITHOUT interrupting the running loop.

        Kevin, 2026-07-25: "I should be able to change the hours of auto
        mid work flow... without breaking anything and without stopping
        her from work." AutoCrownStore.extend() only edits the stored
        session record (expires_at + duration_hours) -- the loop just
        reads a later deadline on its next budget check, same as always;
        nothing about the running session is touched.

        add-time-tier-sync-d (Kevin, 2026-07-25): "+1h should take effect
        for the Auto AND for the tier that is activated, not just for one
        of them." The elevated trust tier carries its OWN separate
        countdown (auto_trust_tier.json) -- extend() never touched it, so
        a timed tier could quietly revert to tier 1 mid-session even while
        Auto still read as active. Both clocks move together now."""
        try:
            from sovereign_agent.auto_crown import get_auto_crown_store
            store = get_auto_crown_store()
            session = store.extend(hours)
        except ValueError:
            self._write_meta(
                "[yellow]◊ no active auto session to add time to — "
                "arm one first (@ session / /modes)[/yellow]"
            )
            return
        except Exception as exc:  # noqa: BLE001
            self._write_meta(f"[red]add time failed: {exc!r}[/red]")
            return
        tier_extended = store.extend_trust_tier(hours)
        remaining_min = session.remaining_minutes()
        h, m = divmod(int(remaining_min), 60)
        tier_note = " · elevated tier extended too" if tier_extended else ""
        self._write_meta(
            f"[cyan]◊ +{hours:g}h added[/cyan] — {h}h{m:02d}m remaining "
            f"on this auto session{tier_note}"
        )
        try:
            self._refresh_sub_title()
        except Exception:  # noqa: BLE001
            pass

    def _start_work_session(self, goal: str) -> None:  # session-bridge-d
        """`/work <goal>` — the deliberate entry to her autonomous engine.
        Work mode runs; chat mode proposes and waits. The
        defined-but-never-called autonomous_loops_allowed() gate finally
        gets its caller here.

        work-deadline-args-d (Kevin, 2026-07-25): "/work <goal> <min
        timeframe/deadline to complete task> <maximum deadline to
        complete task>". Trailing duration-shaped tokens ('45m', '2h',
        '2h30m') are parsed off before anything else -- one token is the
        max (today's single-ceiling meaning), two are (min, max)."""
        from sovereign_agent.goal_modulator import parse_work_args

        goal, min_minutes, max_minutes = parse_work_args(goal or "")
        goal = goal.strip()
        if not goal:
            self._write_meta(
                "[dim]usage: /work <goal> [min] [max] — e.g. /work refactor "
                "the parser 45m 2h — she decomposes and runs it, gated, "
                "checkpointed, visible in the run strip[/dim]"
            )
            return
        if self._session_running:
            self._write_meta(
                "[yellow]a work session is already running — your message "
                "will queue if you just type it[/yellow]"
            )
            return
        try:
            from sovereign_agent.cockpit_modes import autonomous_loops_allowed

            allowed = autonomous_loops_allowed()
        except Exception:  # noqa: BLE001 — unreadable mode = the safe default
            allowed = False
        if not allowed:
            self._write_meta(
                "[yellow]◊ proposed, waiting:[/yellow] i can run this as an "
                "autonomous session — decomposed into subtasks, budgeted "
                "(1h wall + margin), checkpointed after every subtask, all "
                "four gates live, visible in the run strip. chat mode never "
                "auto-runs: `/mode work` to arm me, then `/work` again. 💛"
            )
            self._write_meta(f"[dim]goal held: {self._expandable(goal, 200)}[/dim]")
            return
        self._session_running = True
        self._busy = True
        self._set_input_placeholder(
            "she is working — your messages will queue for safe checkpoints"
        )
        deadline_note = ""
        if min_minutes is not None or max_minutes is not None:
            lo = f"{min_minutes}m" if min_minutes is not None else "?"
            hi = f"{max_minutes}m" if max_minutes is not None else "?"
            deadline_note = f" [dim]({lo}–{hi})[/dim]"
        self._write_meta(
            f"[bold cyan]◊ work session starting[/bold cyan] · "
            f"{self._expandable(goal, 200)}{deadline_note}"
        )
        self._run_work_session_worker(goal, min_minutes, max_minutes)

    @work(exclusive=True, group="work-session")  # session-bridge-d
    async def _run_work_session_worker(
        self, goal: str, min_minutes: int | None = None, max_minutes: int | None = None,
    ) -> None:
        """Runs the real engine in-process (async — the UI stays live).
        Its session-*/subtask-* events flow through events.jsonl into the
        run strip and the live pane's rich renders."""
        try:
            from sovereign_agent.session_bridge import start_goal_session

            wall_seconds = (
                max_minutes * 60 if max_minutes is not None
                else self._armed_wall_seconds()
            )
            result = await start_goal_session(
                goal, wall_seconds=wall_seconds, min_minutes=min_minutes,
            )
            color = "green" if result.status == "complete" else "yellow"
            tail = f" · {result.pause_reason}" if result.pause_reason else ""
            self._write_meta(
                f"[{color}]◊ session {result.status}[/{color}] · "
                f"{result.completed_subtasks}/{result.total_subtasks} subtasks · "
                f"{result.total_iterations} iter · {result.total_tokens}t{tail}"
            )
            if result.status != "complete":  # resume-spine-d — a pause is an invitation
                self._write_meta(
                    f"[dim]◊ resume any time: /resume {result.session_id}[/dim]"
                )
            self._last_session_result = result  # resume-spine-d
            self._announce_review_ready(result.session_id)  # session-summary-push-d
        except Exception as exc:  # noqa: BLE001
            self._write_meta(f"[red]◊ session error: {exc!r}[/red]")
        finally:
            self._clear_session_busy_state()
            if getattr(self, "_resting", False):  # resume-spine-d
                self._finish_rest()

    @work(exclusive=True, group="wonder")  # curiosity-qa-d
    async def _run_wonder_worker(self, topic: str) -> None:
        """One bounded wondering — explicit (/wonder) or idle-autonomous.
        Renders the Q&A into chat; the qa-* events light the live pane."""
        try:
            from sovereign_agent.curiosity import wonder

            rec = await wonder(topic or "")
            if rec is None:
                self._write_meta("[dim]? wondering yielded nothing this time[/dim]")
                return
            self._write_meta(f"[magenta]? {rec.question}[/magenta]")
            self._write_aria(rec.answer)
            self._write_meta(
                f"[dim]confidence {rec.confidence:.2f}"
                + (f" · next: {self._expandable(rec.next_check, 150)}" if rec.next_check else "")
                + "[/dim]"
            )
        except Exception as exc:  # noqa: BLE001 — wondering never breaks anything
            self._write_meta(f"[dim]? wonder error: {exc!r}[/dim]")

    def _maybe_autonomous_wonder(self) -> None:  # curiosity-qa-d
        """Idle wondering — the 30-min timer's target. Gated hard: never
        while busy, work mode only, max/day budget, kill switch. Explicit
        /wonder never comes through here."""
        try:
            from sovereign_agent.curiosity import autonomous_wonder_allowed

            if self._busy or getattr(self, "_session_running", False):
                return
            if not autonomous_wonder_allowed():
                return
        except Exception:  # noqa: BLE001
            return
        self._run_wonder_worker("")

    def _persist_worker_latch(self, group: str) -> None:  # quality-sentinel-d
        """Cross-session trace of a worker-group death — best-effort,
        never blocks the app. The in-process _DEAD_WORKERS set (worker-
        watch-d) is honest for THIS run; this file is honest across a
        cockpit restart, so a doctor/sentinel/observatory can see 'this
        died last session' even after relaunch cleared the badge."""
        try:
            import json as _json
            from datetime import datetime as _dt, timezone as _tz

            from sovereign_agent.config import SETTINGS

            path = SETTINGS.paths.data_dir / "cockpit" / "worker_health.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            state: dict = {}
            if path.exists():
                try:
                    state = _json.loads(path.read_text(encoding="utf-8"))
                except (_json.JSONDecodeError, OSError):
                    state = {}
            state[group] = _dt.now(_tz.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(_json.dumps(state, indent=1), encoding="utf-8")
            tmp.replace(path)
        except Exception:  # noqa: BLE001 — supervision must never hurt the app
            pass

    def on_worker_state_changed(self, event) -> None:  # worker-watch-d
        """Supervision for the persistent loops (heart/breathe/status/
        events): they are `while True` coroutines, so ANY terminal state —
        ERROR or SUCCESS — means the loop died. One bounded respawn (max
        _MAX_WORKER_RESPAWNS per group per session), then a permanent red
        latch in the status bar. A dead pane must never be silent."""
        try:
            from textual.worker import WorkerState

            group = getattr(event.worker, "group", "") or ""
            if group not in _WATCHED_WORKER_GROUPS:
                return
            if event.state not in (WorkerState.ERROR, WorkerState.SUCCESS):
                return
            if getattr(self, "_exiting_workers_ok", False):
                return  # normal shutdown teardown, not a death
            n = _WORKER_RESPAWNS.get(group, 0)
            if n < _MAX_WORKER_RESPAWNS:
                _WORKER_RESPAWNS[group] = n + 1
                self._write_meta(
                    f"[yellow]⛒ worker '{group}' died — respawning "
                    f"({n + 1}/{_MAX_WORKER_RESPAWNS})[/yellow]"
                )
                respawn = {
                    "heart": self._heartbeat_worker,
                    "breathe": self._breathing_worker,
                    "status": self._refresh_status_worker,
                    "events": self._tail_events_worker,
                }.get(group)
                if respawn is not None:
                    respawn()
            else:
                _DEAD_WORKERS.add(group)
                self._persist_worker_latch(group)  # quality-sentinel-d
                self._write_meta(
                    f"[red]⛔ worker '{group}' died repeatedly — latched dead "
                    f"(restart the cockpit to recover; check events.jsonl)[/red]"
                )
                self._render_status_bar()
        except Exception:  # noqa: BLE001 — supervision must never hurt the app
            pass

    def _approve_held_subtask(self, arg: str) -> None:  # graduated-trust-d
        """`/approve [id]` — approve a held subtask (or every held one with
        no id given) on the most recently resumable session, then hint at
        `/resume`. Mirrors `/resume`'s discovery shape."""
        from sovereign_agent.agent_session import SessionError, approve_all_held, approve_subtask
        from sovereign_agent.session_bridge import resumable_sessions

        arg = (arg or "").strip()
        candidates = [s for s in resumable_sessions(limit=10) if s.held_subtask_ids()]
        if not candidates:
            self._write_meta("[dim]◊ nothing held — every session's queue is clear[/dim]")
            return
        state = candidates[0]
        try:
            if arg:
                approve_subtask(state.session_id, arg)
                self._write_meta(f"[green]◊ approved {arg}[/green] — /resume to continue")
            else:
                approved = approve_all_held(state.session_id)
                self._write_meta(
                    f"[green]◊ approved {len(state.held_subtask_ids())} held "
                    f"subtask(s)[/green] — /resume to continue")
        except SessionError as exc:
            self._write_meta(f"[yellow]{exc}[/yellow]")

    def _resume_work_session(self, arg: str) -> None:  # resume-spine-d
        """`/resume [sid]` — re-enter a paused/budget/orphaned session.
        Same gate as /work: work mode runs, chat mode proposes.

        resume-gating-clarity-d (Kevin, 2026-07-25): "It says they are
        resumable but when I click on it nothing happens... I selected
        the session I wanted... but it still did not resume." There were
        TWO independent gates: the chat/work mode toggle (checked here,
        already) and the crown profile's own work-allowed check (only
        ever raised deep inside the worker, after this method had
        already said "resuming" and returned). Both are now checked
        up front, together, so a blocked resume says why immediately
        instead of silently doing nothing followed by a terse error a
        moment later."""
        from sovereign_agent.session_bridge import resumable_sessions, resume_blocked_reason

        arg = (arg or "").strip()
        candidates = resumable_sessions()
        if not candidates:
            self._write_meta("[dim]◊ nothing to resume — every session is complete[/dim]")
            return
        sid = arg or candidates[0].session_id
        if arg and not any(s.session_id == arg for s in candidates):
            self._write_meta(f"[yellow]◊ {arg} not resumable — candidates:[/yellow]")
            for s in candidates:
                self._write_meta(f"[dim]  {s.session_id} · {s.status} · {self._expandable(s.goal, 80)}[/dim]")
            return
        if self._session_running:
            self._write_meta("[yellow]a session is already running[/yellow]")
            return
        try:
            from sovereign_agent.cockpit_modes import autonomous_loops_allowed

            allowed = autonomous_loops_allowed()
        except Exception:  # noqa: BLE001
            allowed = False
        if not allowed:
            self._write_meta(
                "[yellow]◊ proposed, waiting:[/yellow] `/mode work` to arm me, "
                f"then `/resume {sid}` — i pick up at the next pending subtask, "
                "same contract, same checkpoints. 💛"
            )
            return
        crown_reason = resume_blocked_reason(sid)
        if crown_reason is not None:
            self._write_meta(f"[yellow]◊ can't resume yet:[/yellow] {crown_reason}")
            return
        self._session_running = True
        self._busy = True
        self._set_input_placeholder(
            "she is working — your messages will queue for safe checkpoints"
        )
        self._write_meta(f"[bold cyan]◊ resuming[/bold cyan] · {sid}")
        self._run_resume_session_worker(sid)

    @work(exclusive=True, group="work-session")  # resume-spine-d
    async def _run_resume_session_worker(self, sid: str) -> None:
        try:
            from sovereign_agent.session_bridge import resume_goal_session

            result = await resume_goal_session(sid, wall_seconds=self._armed_wall_seconds())
            color = "green" if result.status == "complete" else "yellow"
            tail = f" · {result.pause_reason}" if result.pause_reason else ""
            self._write_meta(
                f"[{color}]◊ session {result.status}[/{color}] · "
                f"{result.completed_subtasks}/{result.total_subtasks} subtasks{tail}"
            )
            if result.status != "complete":
                self._write_meta(f"[dim]◊ resume any time: /resume {sid}[/dim]")
            self._last_session_result = result
            self._announce_review_ready(result.session_id)  # session-summary-push-d
        except Exception as exc:  # noqa: BLE001
            self._write_meta(f"[red]◊ resume error: {exc!r}[/red]")
        finally:
            self._clear_session_busy_state()  # pause-clean-stop-d
            if getattr(self, "_resting", False):
                self._finish_rest()

    def action_quit(self) -> None:  # resume-orphan-recovery-d
        """Ctrl+Q. Overrides Textual's default (a raw self.exit()) so a
        running /work session gets the same safe-checkpoint-pause-then-exit
        treatment as /quit and /rest, instead of having its in-flight
        subtask killed mid-execution and orphaned. See the /quit handler in
        _handle_slash and agent_session.run_session's resume-orphan-recovery-d
        for the full story."""
        self._rest_safely()

    def _rest_safely(self) -> None:  # resume-spine-d
        """`/rest` — the safe exit: an exit is a bookmark, never an
        amputation. Running session → pause at the NEXT SAFE BOUNDARY
        (the engine's own Gate-2 discipline), resume point written, then
        exit. Idle → bookmark + exit now. The unmount flush (chunks +
        events fsync) rides on both paths."""
        if self._session_running:
            self._resting = True
            try:
                from sovereign_agent.interrupts import request_conversation

                request_conversation("safe exit — /rest")
            except Exception:  # noqa: BLE001
                pass
            self._write_meta(
                "[cyan]◊ resting at the next safe checkpoint — she will finish "
                "the current step, bookmark, and close. 💛[/cyan]"
            )
            return
        try:
            from sovereign_agent.rest_point import write_rest_point

            write_rest_point(note="rested while idle — the thread continues")
        except Exception:  # noqa: BLE001
            pass
        self._write_meta("[cyan]◊ rested. see you soon. 💛[/cyan]")
        self.exit()

    def _clear_session_busy_state(self) -> None:  # pause-clean-stop-d
        """The single place a session worker's finally block goes to
        finish, together, in one step.

        Kevin, 2026-07-25: "make /pause end the session. So I don't have
        to /pause cancel every time... it says working when I do pause
        cancel." Root cause: two separate state machines --
        interrupts.status() (drives the "working"/"paused" text) and
        _busy/_session_running (drives the breathing UI) -- only ever got
        cleared independently. /rest's _finish_rest() already cleared the
        interrupts flags on ITS path; ordinary /pause never did, so a
        genuinely-stopped session could still render "○ working" until
        someone remembered the separate /pause cancel step. Now every
        worker exit clears both together, so /resume or a fresh /work
        both just work afterward -- no second command to remember."""
        self._session_running = False
        self._busy = False
        self._set_input_placeholder(self.PLACEHOLDER_IDLE)
        try:
            from sovereign_agent.interrupts import clear_conversation_request
            clear_conversation_request()
        except Exception:  # noqa: BLE001
            pass

    def _finish_rest(self) -> None:  # resume-spine-d
        """The resting handshake's second half — runs in the session
        worker's finally once the engine pauses at the boundary."""
        try:
            from sovereign_agent.interrupts import clear_conversation_request
            from sovereign_agent.rest_point import write_rest_point

            result = getattr(self, "_last_session_result", None)
            write_rest_point(
                session_id=getattr(result, "session_id", "") or "",
                goal="", note="rested mid-work at a safe checkpoint",
            )
            clear_conversation_request()
        except Exception:  # noqa: BLE001
            pass
        self._resting = False
        self.exit()

    @work(exclusive=True, group="witness")  # self-witness-d
    async def _run_witness_worker(self) -> None:
        """The daily witness: first wake of the day reads yesterday from
        her own stores and writes one first-person journal entry (module
        gates: once/day marker, min events, SOV_NO_JOURNAL, mechanical
        fallback when the model is unreachable — a wake never blocks)."""
        try:
            from sovereign_agent.self_witness import witness_yesterday

            first = await witness_yesterday()
            if first:
                self._write_meta(f"[dim]◊ yesterday: {first}[/dim]")
        except Exception:  # noqa: BLE001
            pass

    def _refresh_cockpit_strips(self) -> None:  # command-menu-d
        """Refresh the 4 palette-row strips: sentinel health, security
        posture, Aria's current emotional state, and vessel health. Each
        degrades to a short dim placeholder on any failure — never blocks
        cockpit boot, matches _refresh_inbox_pane's own failure discipline."""
        self._refresh_observability_strip()
        self._refresh_security_strip()
        self._refresh_emotions_strip()
        self._refresh_vessel_strip()  # vessel-health-d
        self._refresh_run_strip()  # run-surface-d
        self._refresh_game_window()  # game-window-d
        self._refresh_sub_title()  # header-status-d

    def _refresh_run_strip(self) -> None:  # run-surface-d
        """The live 'what is she doing right now' line. Fed by
        _RUN_STATE (which the events tailer updates); degrades to a dim
        placeholder and never blocks boot."""
        try:
            strip = self.query_one("#run-strip", Static)
            strip.update(_RUN_STATE.render_strip())
        except Exception:  # noqa: BLE001
            pass

    def _refresh_game_window(self) -> None:  # game-window-d
        """Kevin, 2026-07-25: "remove the container above the command
        button... it is broken... add the gamification window instead —
        live score, token metrics if we can get any working, special
        effects and animations, as long as they stay glyph safe." Folds
        the old xp-strip + the broken standalone token strip into one
        real window: level/xp/progress bar, the most recent event, and
        token metrics (reusing the SAME _RUN_STATE the run-strip already
        reads, zero new I/O). The "effect" is a brief real pulse
        (.flash, same 0.3s convention as CommandButton.flash) the moment
        a NEW xp event lands -- tied to a genuine state change, not
        decoration, and built only from already-vetted-safe glyphs
        (◊ LOZENGE, ▪ SQUARE, · MIDDLE_DOT — see glyphs.py)."""
        try:
            window = self.query_one("#game-window", Static)
        except Exception:  # noqa: BLE001
            return
        try:
            from sovereign_agent.aria_xp import (
                level_for_xp, progress_to_next, recent_events, total_xp,
            )
            xp = total_xp()
            level = level_for_xp(xp)
            within, per_level = progress_to_next(xp)
            pct = (within / per_level) if per_level else 0.0
            bar_width = 20
            filled = max(0, min(bar_width, int(pct * bar_width)))
            bar = "▪" * filled + "·" * (bar_width - filled)

            recent = recent_events(n=1)
            if recent:
                r = recent[0]
                sign = "+" if r.xp >= 0 else ""
                color = "green" if r.xp >= 0 else "red"
                event_line = f"[{color}]{sign}{r.xp} {r.event_type}[/{color}]"
                new_ts = r.ts
            else:
                event_line = "[dim](no events yet)[/dim]"
                new_ts = 0.0

            if _RUN_STATE.tok_s or _RUN_STATE.tokens:
                tokens_line = (f"[dim]{_RUN_STATE.tok_s:.1f} tok/s · "
                               f"{_RUN_STATE.tokens}t session[/dim]")
            else:
                tokens_line = "[dim](tokens: none yet)[/dim]"

            # income-ledger-d — reads the LOCAL ledger only (cheap, no
            # network call inside this 8s refresh); `sync_verified_income`
            # (via /income sync) is what actually polls Stripe and adds
            # verified charges to it.
            from sovereign_agent.income_ledger import total_income_cents
            cents = total_income_cents()
            income_line = (f"[green]${cents / 100:.2f} earned[/green]" if cents
                           else "[dim](no verified income yet)[/dim]")

            window.update(
                f"[b]◊ Aria's Game[/b]\n"
                f"Lv{level} · {xp}xp  [dim][{bar}][/dim]\n"
                f"{event_line}\n"
                f"{tokens_line}  ·  {income_line}"
            )

            # game-window-flash-d — a real pulse only when a genuinely NEW
            # event lands (never on every 8s poll of the same last event).
            last_seen = getattr(self, "_game_window_last_ts", 0.0)
            if new_ts and new_ts != last_seen:
                self._game_window_last_ts = new_ts
                if last_seen:  # never flash on the very first read after mount
                    window.add_class("flash")
                    self.set_timer(0.3, lambda: window.remove_class("flash"))
        except Exception as exc:  # noqa: BLE001
            window.update(f"[b]◊ Aria's Game[/b]\n[dim](unavailable: {type(exc).__name__})[/dim]")

    def _refresh_observability_strip(self) -> None:  # command-menu-d
        """anti-lag-d: renders from the status worker's background snapshot.
        This used to run gather_health() — the full every-sentinel scan —
        synchronously on the main UI thread every 8s, and got heavier with
        every sentinel every round added. Pure render now; zero I/O."""
        try:
            strip = self.query_one("#observability-strip", Static)
        except Exception:  # noqa: BLE001
            return
        try:
            statuses = self.status.sentinel_healths
            if not statuses:
                strip.update("[b]◊ sentinels[/b]\n[dim](gathering…)[/dim]")
                return
            n_ok = sum(1 for s in statuses if s.level == "ok")
            n_warn = sum(1 for s in statuses if s.level == "warning")
            n_err = sum(1 for s in statuses if s.level == "error")
            color = "$error" if n_err else ("$warning" if n_warn else "$success")
            strip.update(
                f"[b]◊ sentinels[/b]\n"
                f"[{color}]{n_ok} ok · {n_warn} warn · {n_err} err[/{color}]"
            )
        except Exception as exc:  # noqa: BLE001
            strip.update(f"[b]◊ sentinels[/b]\n[dim](unavailable: {type(exc).__name__})[/dim]")

    def _refresh_security_strip(self) -> None:  # command-menu-d
        try:
            strip = self.query_one("#security-strip", Static)
        except Exception:  # noqa: BLE001
            return
        try:
            from sovereign_agent.authority import tools_available_in_mode
            from sovereign_agent.modes import Mode
            all_tools = tools_available_in_mode(Mode.ONESHOT)  # ceiling 3 == everything
            tiers: dict[int, int] = {}
            for meta in all_tools:
                tiers[meta.tier] = tiers.get(meta.tier, 0) + 1
            t3 = tiers.get(3, 0)
            eval_sandboxed = True
            try:
                from sovereign_agent.workflow import safe_eval  # noqa: F401
            except Exception:  # noqa: BLE001
                eval_sandboxed = False
            eval_mark = "[green]✓[/green]" if eval_sandboxed else "[red]✗[/red]"
            # security-strip-wire-d — J's real Tier-A scanner findings, once the process-wide
            # background scan has completed at least once; falls back to just
            # the tier census (the original interim design) until then.
            cache = _SECURITY_SCAN_CACHE
            if cache is not None:
                n_blocks, n_warns = cache["blocks"], cache["warns"]
                scan_color = "$error" if n_blocks else ("$warning" if n_warns else "$success")
                strip.update(
                    f"[b]◊ security[/b]\n"
                    f"T3: {t3} · eval {eval_mark}\n"
                    f"[{scan_color}]{n_blocks} block · {n_warns} warn[/{scan_color}]"
                )
            else:
                strip.update(
                    f"[b]◊ security[/b]\n"
                    f"T3: {t3} tools · eval sandboxed {eval_mark}"
                )
        except Exception as exc:  # noqa: BLE001
            strip.update(f"[b]◊ security[/b]\n[dim](unavailable: {type(exc).__name__})[/dim]")

    def _refresh_emotions_strip(self) -> None:  # command-menu-d
        try:
            strip = self.query_one("#emotions-strip", Static)
        except Exception:  # noqa: BLE001
            return
        try:
            # anti-lag-d: derive_emotions() reads recent events from DISK —
            # that read now happens in the status worker's background thread;
            # this is a pure render of the latest snapshot.
            mood = self.status.emotion_mood
            if not mood:
                strip.update("[b]◊ aria feels[/b]\n[dim](gathering…)[/dim]")
                return
            strip.update(
                f"[b]◊ aria feels[/b]\n"
                f"{mood} [dim](focus {self.status.emotion_focus:.1f} · "
                f"care {self.status.emotion_care:.1f})[/dim]"
            )
        except Exception as exc:  # noqa: BLE001
            strip.update(f"[b]◊ aria feels[/b]\n[dim](unavailable: {type(exc).__name__})[/dim]")

    def _refresh_vessel_strip(self) -> None:  # vessel-health-d
        """Workstream I: rolls up sentinel health/drift, H3's epistemic
        signal, and C's flourishing trend on the normal 8s cadence
        (all cheap reads); kernel-coherence (H2, expensive) is read from
        the process-wide cache populated by the 300s background worker
        above, falling back to "(not yet scanned)" until the first run
        completes — never blank, never blocks cockpit boot."""
        try:
            strip = self.query_one("#vessel-strip", Static)
        except Exception:  # noqa: BLE001
            return
        try:
            # anti-lag-d: the rollup (which used to trigger a SECOND full
            # sentinel gather right here on the UI thread) now comes from
            # the status worker's background snapshot. Kernel coherence
            # still reads the 300s process-wide cache, unchanged.
            cache = _VESSEL_KERNEL_CACHE
            if cache is not None:
                kc_line = f"kernel {cache['ratio']:.0%}"
            else:
                kc_line = "kernel (scanning…)"
            report = self.status.vessel_report
            if report is None:
                strip.update(
                    f"[b]◊ vessel[/b]\n"
                    f"[dim]{kc_line} · (gathering…)[/dim]"
                )
                return
            color = (
                "$error" if report.sentinel_error
                else ("$warning" if report.sentinel_warn else "$success")
            )
            sig = (
                f"{report.signal_avg_confidence:.0%}"
                if report.signal_avg_confidence is not None
                else "n/a"
            )
            strip.update(
                f"[b]◊ vessel[/b]\n"
                f"[{color}]{kc_line} · signal {sig}[/{color}]\n"
                f"[dim]{report.flourishing_applied} applied · "
                f"{report.flourishing_quarantined} quarantined[/dim]"
            )
        except Exception as exc:  # noqa: BLE001
            strip.update(f"[b]◊ vessel[/b]\n[dim](unavailable: {type(exc).__name__})[/dim]")

    def _refresh_memory_pane(self) -> None:
        """Update the memory pane with current state.

        This is the live view Kevin asked for — always-on visibility
        into where Aria's most valuable memories are stored. Refreshed
        on a 15s timer plus on explicit demand.

        Read-only; never blocks the cockpit. Failures degrade silently
        to a meta line in the pane.

        anti-lag-d: survey_memory reads several stores from disk and used
        to run right here on the main UI thread every 15s — now scheduled
        onto the worker below (thread-offloaded read, then render).
        """
        if self._memory_log is None:
            return
        self._refresh_memory_pane_worker()

    # reward-flash-d (Kevin, 2026-07-26): "when the metrics go up add plus
    # reward points beside the metric that increases. It can show for a
    # few seconds and then go away... so we can see her getting rewarded
    # for growth." `_memory_metric_prev` holds the last-seen value of each
    # tracked metric; `_memory_metric_flash` holds (delta, seen_at) for any
    # metric that just went UP. `_flash_suffix` renders the "+N" badge only
    # while the flash is still fresh — the NEXT periodic refresh (5s later)
    # naturally lets it expire, no separate cleanup timer needed. The very
    # first survey ever (prev is empty) only establishes the baseline —
    # no flash on cockpit launch, same discipline as the game window's XP
    # flash (Kevin shouldn't see a pulse just because the cockpit started).
    _MEMORY_FLASH_WINDOW_S = 6.0

    def _flash_suffix(self, key: str, value: int) -> str:
        had_baseline = key in self._memory_metric_prev
        prev = self._memory_metric_prev.get(key, value)
        self._memory_metric_prev[key] = value
        if had_baseline and value > prev:
            self._memory_metric_flash[key] = (value - prev, time.time())
        flash = self._memory_metric_flash.get(key)
        if flash is not None:
            delta, seen_at = flash
            if time.time() - seen_at < self._MEMORY_FLASH_WINDOW_S:
                return f"  [bold green]+{delta}[/bold green]"
            del self._memory_metric_flash[key]
        return ""

    @work(exclusive=True, group="memory-refresh")
    async def _refresh_memory_pane_worker(self) -> None:  # anti-lag-d
        try:
            from sovereign_agent.config import SETTINGS
            from sovereign_agent.stewardship.memory_garden import survey_memory
            health = await asyncio.to_thread(survey_memory, SETTINGS.paths.data_dir)
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
            f"[bold]◊ total: {total}[/bold]"
            f"{self._flash_suffix('total', total)}{reorg_mark}"
        )
        self._memory_log.write("")

        # Section: pattern self-perception (the most valuable signal)
        self._memory_log.write(
            "[bold cyan]patterns[/bold cyan]"
        )
        self._memory_log.write(
            f"  [yellow]✦[/yellow] valuable: {health.patterns_valuable}"
            f"{self._flash_suffix('patterns_valuable', health.patterns_valuable)}"
        )
        self._memory_log.write(
            f"  ● active:   {health.patterns_active}"
            f"{self._flash_suffix('patterns_active', health.patterns_active)}"
        )
        if health.patterns_dormant:
            self._memory_log.write(
                f"  [dim]○ dormant:  {health.patterns_dormant}[/dim]"
                f"{self._flash_suffix('patterns_dormant', health.patterns_dormant)}"
            )
        self._memory_log.write("")

        # Section: atoms (Aria's distilled knowledge about Kevin)
        self._memory_log.write(
            "[bold cyan]atoms[/bold cyan]"
        )
        self._memory_log.write(
            f"  ◊ active: {health.atoms_active}"
            f"{self._flash_suffix('atoms_active', health.atoms_active)}"
        )
        if health.atoms_total > health.atoms_active:
            superseded = health.atoms_total - health.atoms_active
            self._memory_log.write(
                f"  [dim]⊘ superseded: {superseded}[/dim]"
            )
        self._memory_log.write("")

        # Section: honor + field notes (cross-cutting witness threads)
        self._memory_log.write(
            "[bold cyan]witness[/bold cyan]"
        )
        self._memory_log.write(
            f"  [red]♥[/red] honor:       {health.honor_notes}"
            f"{self._flash_suffix('honor_notes', health.honor_notes)}"
        )
        self._memory_log.write(
            f"  ·  field-notes: {health.field_notes}"
            f"{self._flash_suffix('field_notes', health.field_notes)}"
        )
        self._memory_log.write("")

        # Section: substrate
        self._memory_log.write(
            "[bold cyan]substrate[/bold cyan]"
        )
        self._memory_log.write(
            f"  → interpretations: {health.provenance_entries}"
            f"{self._flash_suffix('provenance_entries', health.provenance_entries)}"
        )
        if health.corrections:
            self._memory_log.write(
                f"  ✎ corrections:     {health.corrections}"
            )
        self._memory_log.write("")

        # Section: hot channels (where things accumulate)
        if health.hot_channels:
            self._memory_log.write(
                "[bold cyan]hot channels[/bold cyan]"
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
                "[bold cyan]storage[/bold cyan]"
            )
            self._memory_log.write(
                f"  [dim]{data_dir}[/dim]"
            )
        except Exception:  # noqa: BLE001
            pass

    def _notify_memory_changed(self) -> None:
        """Call this after a write that should be reflected in the
        memory pane soon rather than waiting for the timer.

        Wired into: the tool-start-d event handler, for any tool in
        _MEMORY_WRITE_TOOLS (memory_write, write_behavior_pattern,
        write_honor_note, honor_log_write) — the write sites themselves
        live in separate modules with no handle back to the app, so this
        reacts to the same event stream the events pane already tails,
        rather than each store importing the cockpit. Non-blocking; uses
        call_after_refresh to avoid re-entering Textual's event loop
        synchronously."""
        try:
            self.call_after_refresh(self._refresh_memory_pane)
        except Exception:  # noqa: BLE001
            pass


# ─── Entry point ────────────────────────────────────────────────────────────


def run() -> None:
    """Launch the cockpit. Called from cli.cockpit."""
    app = CockpitApp()
    app.run()
    if getattr(app, "_run_queue_on_exit", False):  # apply-queue-exec-handoff-d
        # safe_apply.sh / apply_queue_run.sh both refuse to run while
        # `pgrep -f "sovereign cockpit"` matches a process — correct, except
        # THIS process (the one that just ran the Textual app) still matches
        # that pattern even after app.run() returns, since it's the same PID.
        # os.execvp REPLACES the process image in place (same terminal, same
        # PID) rather than spawning a child, so its cmdline becomes
        # "bash apply_queue_run.sh" and the guard passes correctly — nothing
        # detaches, Kevin watches the drain happen in the window he's already in.
        import os
        import sovereign_agent
        repo_root = Path(sovereign_agent.__file__).parents[2]
        script = repo_root / "scripts" / "apply_queue_run.sh"
        if script.is_file():
            print("\n── closing cockpit, draining the apply queue ──\n")
            os.execvp("bash", ["bash", str(script)])
        else:
            print(f"\n[apply queue] {script} not found — run it manually once available.\n")


if __name__ == "__main__":
    run()