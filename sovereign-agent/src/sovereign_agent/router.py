"""
╔══════════════════════════════════════════════════════════════════════════╗
║  router.py — Intent → side effects                                        ║
║  v0.2.19.0                                                                ║
║                                                                           ║
║  The interpreter produces typed Intent objects. The router turns them    ║
║  into actions: writing to memory channels, resolving projects, executing ║
║  vetted commands, asking focused clarifying questions, emitting events.  ║
║                                                                           ║
║  Authority model (MOS-UNIFIED-CANON):                                     ║
║                                                                           ║
║    Tier 0 — Read-only                                                    ║
║      sov status, sov projects list, sov channels show, sov events,       ║
║      sov drafts list, sov palace search, sov people fact (read),         ║
║      ls, cat, find, head, tail, wc                                       ║
║      → silent dispatch, no event needed                                  ║
║                                                                           ║
║    Tier 1 — Reversible writes                                            ║
║      sov projects scan/update, sov inventory, sov people fact (write),  ║
║      sov channels add, sov drafts archive, sov backup snapshot           ║
║      → silent dispatch, event emitted                                    ║
║                                                                           ║
║    Tier 2 — Persistent / external                                        ║
║      sov dream start, sov continue, anything that runs long-lived loops ║
║      → meta event in chat ("◊ running: <summary>"), event emitted        ║
║                                                                           ║
║    Tier 3 — Irreversible                                                 ║
║      Anything outside the allowlist; explicit deletes; reaching outside  ║
║      $HOME                                                                ║
║      → single-line confirm ("type 'ok' or /cancel"); event emitted       ║
║                                                                           ║
║    Tier 4 — Reserved                                                     ║
║      Cross-system orchestration; not produced by the interpreter         ║
║                                                                           ║
║  The router is the choke point. The interpreter's output is UNTRUSTED   ║
║  (it might be model hallucination). The allowlist is enforced here, not ║
║  upstream. A Work intent whose commands include "rm -rf" gets demoted to║
║  Ambiguous and surfaced as "I can't run that — did you mean X or Y?"   ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import asyncio
import logging
import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .intents import (
    Ambiguous,
    AuthorityTier,
    Conversation,
    Intent,
    ProjectRef,
    Recall,
    Slash,
    Work,
)

logger = logging.getLogger(__name__)


# ─── Allowlists ─────────────────────────────────────────────────────────────


# Tier 0 — read-only `sov` subcommands. The router auto-classifies any
# command that begins with one of these as tier 0 regardless of what the
# interpreter claimed.
TIER_0_SOV_SUBCOMMANDS: frozenset[str] = frozenset({
    # original commands
    "status", "version", "doctor",
    "events", "drafts",        # the read forms (list/show/get); routed below
    "projects",                # subcommand args inspected; only list is t0
    "channels",
    "people",                  # the read forms
    "palace",
    "config",
    "modes",
    # router-expand additions — read-only commands
    "honor",        # read: sov honor show, sov honor count
    "atoms",        # read: sov atoms show, sov atoms search, sov atoms list
    "behavior",     # read: sov behavior show, sov behavior patterns
    "gap",          # read: sov gap list
    "continuations",# read: sov continuations list
    "lessons",      # read: sov lessons list, sov lessons show
    "proposals",    # read: sov proposals list
    "cadence",      # read: sov cadence show
    "commitments",  # read: sov commitments list
    "telemetry",    # read: sov telemetry summary, sov telemetry tail
    "backlog",      # read: sov backlog list, sov backlog show
    "sessions",     # read: sov sessions list
    "interpret",    # read: sov interpret show
    "health",       # read: sov health check
    "stewards",     # read: sov stewards list, sov stewards scan
    "aria",         # read: sov aria (kernel snapshot)
    "info",         # read: sov info
    "financial",    # read: sov financial status
    "impact",       # read: sov impact show
    "reasoning",    # read: sov reasoning list
    "reward",       # read: sov reward show
    "episode",      # read: sov episode list
    "seal",         # read: sov seal (compute — non-mutating)
    "verify",       # read: sov verify (non-mutating)
    "insights",     # read: sov insights show
    "recall",       # read: sov recall list
    "personas",     # read: sov personas list
    "constitution", # read: sov constitution show
    "appendix",     # read: sov appendix list
    "capabilities", # read: sov capabilities list
    "edge-cases",   # read: sov edge-cases list
    "corrections",  # read: sov corrections list
    "field-notes",  # read: sov field-notes list
})  # # router-expand-t0-d

# Tier 1 — reversible writes
TIER_1_SOV_SUBCOMMANDS: frozenset[str] = frozenset({
    # original commands
    "inventory",
    "backup",
    "approval",
    # router-expand additions — reversible writes
    "gap",          # write: sov gap add (new capability gap entry)
    "backlog",      # write: sov backlog add (new task to queue)
    "commitments",  # write: sov commitments add
    "proposals",    # write: sov proposals add
    "memory",       # write: sov memory tend, sov memory write
    "atoms",        # write: sov atoms create
    "channels",     # write: sov channels add
    "field-notes",  # write: sov field-notes add
    "appendix",     # write: sov appendix add
    "corrections",  # write: sov corrections add
})  # # router-expand-t1-d

# Tier 2 — persistent / long-running
TIER_2_SOV_SUBCOMMANDS: frozenset[str] = frozenset({
    "dream",
    "continue",
    "do",                      # used as a sub-channel; routed specially below
})

# Non-sov commands allowed in tier 0. These are read-only system tools.
TIER_0_SYSTEM_COMMANDS: frozenset[str] = frozenset({
    "ls", "cat", "find", "head", "tail", "wc", "tree",
    "pwd", "echo", "stat", "file", "du",
})


# Commands that are *definitely* disallowed — the router NEVER runs these
# regardless of authority claim. A model hallucinating these gets demoted
# to Ambiguous with a clear refusal message.
BLOCKED_COMMAND_TOKENS: frozenset[str] = frozenset({
    "rm", "rmdir", "mv", "dd", "mkfs",
    "shutdown", "reboot", "poweroff", "halt",
    "kill", "killall", "pkill",
    "chmod", "chown", "sudo", "su", "doas",
    "curl", "wget", "ssh", "scp", "rsync",
    "git",        # writes to repos — needs explicit operator authorship
    "pip", "uv", "uvx", "npm", "cargo", "apt", "snap",
    ">", ">>", "&&", "||", ";",  # shell metachars — commands must be single-token-rooted
})


# ─── Result objects ─────────────────────────────────────────────────────────


@dataclass
class RouteResult:
    """The outcome of routing one Intent. Returned to the caller (cockpit
    or CLI) so the surface can decide what to print.

    Fields:
      kind: a label for the surface to render
      messages: lines to print in the chat pane (Aria's voice)
      events: structured events to emit (one per side effect)
      executed_commands: shell-form commands the router actually ran
      pending: if non-empty, the router is asking the operator a focused
        single-line question; the caller should display `pending.question`
        and route the next operator input to `pending.callback(text)`.
    """
    kind: str = ""
    messages: list[str] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)
    executed_commands: list[str] = field(default_factory=list)
    pending: PendingPrompt | None = None
    project: ProjectRef | None = None


@dataclass
class PendingPrompt:
    """A focused single-line follow-up the router is waiting on.

    Used ONLY for tier-3 irreversible confirms, and only when the
    interpreter / router decided execution requires explicit operator
    assent. The operator answers with "ok" / "yes" (executes) or
    "/cancel" / anything else (aborts and falls to Conversation).
    """
    question: str
    callback: Callable[[str], "RouteResult"]


# ─── Project resolution ─────────────────────────────────────────────────────


_PROJECT_NAME_SAFE = re.compile(r"^[A-Za-z0-9._-]+$")


def _safe_project_name(raw: str) -> str:
    """Coerce a hint into a filesystem-safe project name.

    Rules:
      - Strip everything outside [A-Za-z0-9._-]
      - Replace spaces with '-'
      - Truncate to 64 chars
      - Fall back to 'scratch' if empty
    """
    s = raw.strip().replace(" ", "-")
    s = re.sub(r"[^A-Za-z0-9._-]", "", s)
    s = s.strip(".-_")
    if not s:
        return "scratch"
    return s[:64]


def resolve_project(
    hint: str,
    store: Any,           # ProjectStore — typed as Any to avoid circular import
    *,
    fallback_text: str = "",
) -> ProjectRef:
    """Resolve a project hint into a concrete ProjectRef.

    Hint can be:
      - empty (use the fallback_text to derive a name)
      - a registered project name (return as-is, created=False)
      - a path (derive name from basename, create if not registered)
      - a free-form string (sanitize, create if not registered)

    Never blocks. Never asks. The point of v0.2.19.0 is that Aria
    NAMES projects, the operator never has to. If the operator wants
    a specific name, they say so in their original message.
    """
    raw = hint.strip()
    root = ""

    if not raw:
        # Use the first 4 words of fallback_text as a name hint.
        first_words = "-".join(fallback_text.split()[:4]) or "scratch"
        name = _safe_project_name(first_words.lower())
        if store.exists(name):
            return ProjectRef(name=name, root="", created=False)
        return ProjectRef(name=name, root="", created=True)

    # If the hint is a path
    if "/" in raw or raw.startswith("~"):
        p = Path(raw).expanduser()
        root = str(p)
        name = _safe_project_name(p.name or "scratch")
    else:
        name = _safe_project_name(raw)

    if store.exists(name):
        return ProjectRef(name=name, root=root, created=False)
    return ProjectRef(name=name, root=root, created=True)


# ─── Command validation ────────────────────────────────────────────────────


def validate_command(cmd: str) -> tuple[bool, str, int]:
    """Validate a single command from a Work intent.

    Returns (ok, reason, suggested_tier).

    Rules:
      1. Must be a non-empty string
      2. Must not contain shell metacharacters or blocked tokens
      3. Must start with `sov` or a tier-0 system command
      4. If `sov`, the subcommand must be in one of the tier lookups
      5. Path arguments must not escape $HOME

    On failure, reason is human-readable for the operator. The router
    surfaces this as an Ambiguous("can't run X — did you mean Y?").
    """
    cmd = cmd.strip()
    if not cmd:
        return False, "empty command", 0

    # Reject any shell metacharacters or blocked tokens BEFORE parsing.
    for tok in BLOCKED_COMMAND_TOKENS:
        # Exact token boundary check — "rm" must not flag "remove" in
        # a comment, but it must flag "rm -rf".
        if re.search(rf"(^|\s){re.escape(tok)}(\s|$)", cmd):
            return False, f"blocked token: {tok}", 3

    # Single-line, no chaining
    if any(meta in cmd for meta in ("&&", "||", ";", "|", ">", "<", "`", "$(")):
        return False, "command chaining / redirection not allowed", 3

    try:
        argv = shlex.split(cmd)
    except ValueError as exc:
        return False, f"unparseable: {exc}", 3

    if not argv:
        return False, "empty after parse", 0

    head = argv[0]

    # Path arguments must not escape $HOME for tier 0/1
    # v0.2.22.0: prior versions used `arg.startswith(home)` which is
    # vulnerable to a prefix attack — `/root-attacker/secret` starts with
    # `/root` lexically. The fix is to compare resolved Path objects via
    # is_relative_to(), which correctly distinguishes /root from /root-x.
    # Symlinks: we DO NOT resolve them, intentionally. A user-created
    # symlink inside $HOME pointing outside is the user's choice; we
    # block only the explicit case where the typed argument escapes.
    home_path = Path.home()
    tmp_path = Path("/tmp")
    for arg in argv[1:]:
        if not arg.startswith("/"):
            continue                  # relative path; allowed
        try:
            arg_path = Path(arg)
        except (TypeError, ValueError):
            return False, f"invalid path: {arg}", 3
        # is_relative_to: True iff arg_path is the same as or under root.
        # /root-attacker/x is NOT is_relative_to(/root) → blocked.
        inside_home = arg_path.is_relative_to(home_path)
        inside_tmp = arg_path.is_relative_to(tmp_path)
        if not (inside_home or inside_tmp):
            return False, f"path outside $HOME: {arg}", 3

    # System read-only commands
    if head in TIER_0_SYSTEM_COMMANDS:
        return True, "ok: system read-only", 0

    # `sov` subcommand
    if head != "sov" and head != "sovereign":
        return False, f"only `sov` and read-only system commands allowed (got: {head})", 3

    if len(argv) < 2:
        return False, "sov requires a subcommand", 3

    sub = argv[1]

    # `sov projects ...` — only `list`/`show` are tier 0; `scan`/`update` tier 1
    if sub == "projects":
        action = argv[2] if len(argv) > 2 else "list"
        if action in ("list", "show"):
            return True, "ok: projects read", 0
        if action in ("scan", "update"):
            return True, "ok: projects write", 1
        return False, f"unknown projects action: {action}", 1

    if sub == "channels":
        # `sov channels show <name>` is read; `add` is write
        action = argv[2] if len(argv) > 2 else "show"
        if action in ("show", "list"):
            return True, "ok: channel read", 0
        if action in ("add", "fact"):
            return True, "ok: channel write", 1
        return False, f"unknown channels action: {action}", 1

    if sub == "people":
        action = argv[2] if len(argv) > 2 else "show"
        if action in ("show", "list", "get"):
            return True, "ok: people read", 0
        if action in ("fact", "add", "set"):
            return True, "ok: people write", 1
        return False, f"unknown people action: {action}", 1

    if sub == "do":
        # `sov do` is the legacy v0.2.18.x entry — still allowed but the
        # router prefers to call its replacements directly. Treat as t2.
        return True, "ok: legacy do (tier 2)", 2

    if sub in TIER_0_SOV_SUBCOMMANDS:
        return True, "ok: tier 0", 0
    if sub in TIER_1_SOV_SUBCOMMANDS:
        return True, "ok: tier 1", 1
    if sub in TIER_2_SOV_SUBCOMMANDS:
        return True, "ok: tier 2", 2

    # ── _capability_gap_patched ──
    known = sorted(
        TIER_0_SOV_SUBCOMMANDS | TIER_1_SOV_SUBCOMMANDS | TIER_2_SOV_SUBCOMMANDS
    )
    known_str = ", ".join(known)
    return False, f"unknown sov subcommand: {sub!r}. known: {known_str}", 3


# ─── The router itself ──────────────────────────────────────────────────────


class Router:
    """Routes Intent objects to side effects.

    The router holds references to:
      - the project store (for project resolution)
      - the channel writer (for conversation save)
      - the event sink (for audit trail)
      - an executor (for running commands)

    These are passed in so the router is testable without a full
    sovereign environment.
    """

    def __init__(
        self,
        *,
        project_store: Any = None,
        channel_writer: Callable[[str, str], None] | None = None,
        event_sink: Callable[[dict], None] | None = None,
        executor: Callable[[list[str]], int] | None = None,
    ) -> None:
        self.project_store = project_store
        self.channel_writer = channel_writer or (lambda channel, text: None)
        self.event_sink = event_sink or (lambda evt: None)
        self.executor = executor or _default_subprocess_executor

    async def route(self, intent: Intent) -> RouteResult:
        """Dispatch one Intent. Returns a RouteResult.

        Never raises. Never asks yes/no. Tier-3 commands produce a
        PendingPrompt the caller can choose to surface.
        """
        try:
            if isinstance(intent, Conversation):
                return self._route_conversation(intent)
            if isinstance(intent, Recall):
                return await self._route_recall(intent)
            if isinstance(intent, Work):
                return await self._route_work(intent)
            if isinstance(intent, Ambiguous):
                return self._route_ambiguous(intent)
            if isinstance(intent, Slash):
                # Slash is handled by the cockpit/CLI before reaching
                # the router. If we see one here, treat it as no-op.
                return RouteResult(kind="slash", messages=[])
        except Exception as exc:  # noqa: BLE001
            logger.exception("router.route failed: %r", exc)
            return RouteResult(
                kind="error",
                messages=[
                    f"[red]router error: {type(exc).__name__}[/red] — "
                    "your message is safe; nothing was executed."
                ],
            )

        return RouteResult(kind="unknown")

    # ── Conversation ─────────────────────────────────────────────────

    def _route_conversation(self, intent: Conversation) -> RouteResult:
        for channel in intent.save_to:
            try:
                self.channel_writer(channel, intent.text)
            except Exception as exc:  # noqa: BLE001
                logger.warning("channel write failed [%s]: %r", channel, exc)

        # Aria's reply hint becomes the message back to the operator.
        # If the interpreter didn't supply one, we craft a minimal
        # acknowledgment by voice.
        reply = intent.reply_hint.strip() or _default_reply(intent)

        self.event_sink({
            "kind": "conversation",
            "channels": intent.save_to,
            "voice": intent.reply_voice,
        })
        return RouteResult(
            kind="conversation",
            messages=[reply] if reply else [],
        )

    # ── Recall ────────────────────────────────────────────────────────

    async def _route_recall(self, intent: Recall) -> RouteResult:
        # Recall always maps to a tier-0 command. We compose one based
        # on scope; the executor handles the actual search.
        scope = intent.scope
        query = intent.query.strip() or "*"

        if scope == "projects":
            cmd = ["sov", "projects", "list"]
        elif scope == "channels":
            # Generic channel grep; the channels CLI handles the query.
            cmd = ["sov", "channels", "search", query]
        elif scope == "events":
            cmd = ["sov", "events", "-n", "50"]
        else:
            # default: memory search
            cmd = ["sov", "palace", "search", query]

        rc = await asyncio.get_running_loop().run_in_executor(
            None, self.executor, cmd,
        )
        self.event_sink({
            "kind": "recall",
            "scope": scope,
            "query": query,
            "rc": rc,
        })
        return RouteResult(
            kind="recall",
            messages=[],
            executed_commands=[" ".join(cmd)],
        )

    # ── Work ─────────────────────────────────────────────────────────

    async def _route_work(self, intent: Work) -> RouteResult:
        # Validate every command. Demote to Ambiguous if any fail.
        validated: list[tuple[str, int]] = []
        for cmd in intent.commands:
            ok, reason, tier = validate_command(cmd)
            if not ok:
                # Emit a capability-gap event when an unknown sov subcommand
                # is encountered so the operator can audit what Aria tried.
                if "unknown sov subcommand" in reason:
                    self.event_sink({
                        "kind": "capability-gap-d",
                        "proposed_command": cmd,
                        "reason": reason,
                        "summary": intent.summary,
                        "note": (
                            "Aria proposed a sov command that doesn't exist. "
                            "Consider building it in aria-<name>/ staging folder."
                        ),
                    })
                return self._route_ambiguous(Ambiguous(
                    text=intent.summary,
                    question=(
                        f"I can't run `{cmd}` ({reason}). "
                        "Did you mean one of these instead? "
                        "(I've logged this as a capability gap in the event trail.)"
                    ),
                    options=_safe_alternatives(intent, cmd),
                    rationale=f"command-validation: {reason}",
                ))
            validated.append((cmd, tier))

        effective_tier = max((t for _, t in validated), default=0)

        # Resolve project once for the whole turn (if a hint exists).
        project = None
        if intent.project_hint and self.project_store is not None:
            project = resolve_project(
                intent.project_hint,
                self.project_store,
                fallback_text=intent.summary,
            )

        # Tier 3 — emit a PendingPrompt instead of executing
        if effective_tier >= AuthorityTier.IRREVERSIBLE:
            commands = [c for c, _ in validated]

            def _confirm_callback(answer: str) -> RouteResult:
                if answer.strip().lower() not in ("ok", "yes", "y", "do it"):
                    self.event_sink({
                        "kind": "work_cancelled",
                        "tier": effective_tier,
                        "summary": intent.summary,
                    })
                    return RouteResult(
                        kind="cancelled",
                        messages=["[yellow]◊ cancelled — nothing was run[/yellow]"],
                    )
                # Re-route as a tier-2 work (already confirmed)
                return asyncio.run(self._execute_commands(
                    intent, validated, project, confirmed=True,
                ))

            return RouteResult(
                kind="pending_confirm",
                messages=[
                    f"[yellow]◊ this is tier-{effective_tier} "
                    "(irreversible). Type `ok` to run, or `/cancel` "
                    "to abort.[/yellow]",
                    f"  [dim]summary:[/dim] {intent.summary}",
                    *(f"  [dim]→[/dim] {c}" for c, _ in validated),
                ],
                pending=PendingPrompt(
                    question="ok or /cancel?",
                    callback=_confirm_callback,
                ),
            )

        # Tier 0/1/2 — execute
        return await self._execute_commands(intent, validated, project)

    async def _execute_commands(
        self,
        intent: Work,
        validated: list[tuple[str, int]],
        project: ProjectRef | None,
        *,
        confirmed: bool = False,
    ) -> RouteResult:
        messages: list[str] = []
        events: list[dict] = []
        executed: list[str] = []

        if project and project.created:
            messages.append(
                f"[cyan]◊ creating project[/cyan] [bold]{project.name}[/bold]"
                + (f" → {project.root}" if project.root else "")
            )

        max_tier = max((t for _, t in validated), default=0)
        if max_tier >= AuthorityTier.PERSISTENT:
            messages.append(
                f"[cyan]◊ running:[/cyan] {intent.summary}"
            )

        for cmd, tier in validated:
            try:
                argv = shlex.split(cmd)
            except ValueError:
                continue

            rc = await asyncio.get_running_loop().run_in_executor(
                None, self.executor, argv,
            )
            executed.append(cmd)
            events.append({
                "kind": "work_exec",
                "command": cmd,
                "tier": tier,
                "rc": rc,
                "project": project.name if project else "",
                "confirmed": confirmed,
            })

        for evt in events:
            self.event_sink(evt)

        if max_tier <= AuthorityTier.REVERSIBLE and not messages:
            # Silent tier-0/1 still gets a tiny acknowledgment so the
            # operator sees something happened.
            messages.append(f"[dim]✓ {intent.summary}[/dim]")

        return RouteResult(
            kind="work",
            messages=messages,
            events=events,
            executed_commands=executed,
            project=project,
        )

    # ── Ambiguous ────────────────────────────────────────────────────

    def _route_ambiguous(self, intent: Ambiguous) -> RouteResult:
        lines = [f"[yellow]◊ {intent.question}[/yellow]"]
        for i, opt in enumerate(intent.options, 1):
            lines.append(f"  [dim]{i}.[/dim] {opt}")
        lines.append(
            "  [dim](or just keep talking — I'll save what you said)[/dim]"
        )
        self.event_sink({
            "kind": "ambiguous",
            "question": intent.question,
            "options": list(intent.options),
        })
        return RouteResult(kind="ambiguous", messages=lines)


# ─── Helpers ────────────────────────────────────────────────────────────────


def _default_reply(intent: Conversation) -> str:
    """Fallback reply when the interpreter didn't supply a reply_hint.

    Voice-aware, minimal, never sycophantic. The LLM-generated reply
    in the cockpit's responder pipeline will usually replace this; this
    only fires when there's no responder (offline / CLI mode).
    """
    voice = intent.reply_voice
    chans = ", ".join(intent.save_to)
    if voice == "quiet":
        return ""
    if voice == "playful":
        return f"[dim](saved to {chans})[/dim]"
    if voice == "thinking":
        return f"[dim]◯ noted — held in {chans}[/dim]"
    # warm (default)
    return f"[dim]◊ kept in {chans}[/dim]"


def _safe_alternatives(intent: Work, blocked_cmd: str) -> list[str]:
    """Suggest up to 3 safer alternatives when a command is rejected.

    Tries fuzzy-matching the blocked command against known sov subcommands
    using difflib so Aria gets real suggestions, not generic fallbacks.
    """
    import difflib, shlex as _shlex
    base: list[str] = []

    # Extract the attempted sov subcommand (if any) for fuzzy matching
    attempted_sub: str | None = None
    try:
        argv = _shlex.split(blocked_cmd)
        if len(argv) >= 2 and argv[0] in ("sov", "sovereign"):
            attempted_sub = argv[1]
    except ValueError:
        pass

    if attempted_sub:
        known = sorted(
            TIER_0_SOV_SUBCOMMANDS | TIER_1_SOV_SUBCOMMANDS | TIER_2_SOV_SUBCOMMANDS
        )
        close = difflib.get_close_matches(attempted_sub, known, n=3, cutoff=0.4)
        for match in close:
            base.append(f"sov {match}")

    if intent.project_hint:
        base.append(f"sov projects list (to see '{intent.project_hint}')")

    if not base:
        base = ["sov status", "sov projects list", "sov channels show context"]

    base.append(
        "build it: create aria-<name>/ staging folder with apply_<name>.sh"
    )
    return base[:4]


def _default_subprocess_executor(argv: list[str]) -> int:
    """Synchronous fallback executor — invoked when no executor is
    injected. Runs the command and returns its exit code. Used by tests
    and by the CLI; the cockpit injects its own asyncio-aware version.
    """
    import subprocess
    try:
        result = subprocess.run(
            argv,
            check=False,
            capture_output=True,
            text=True,
            timeout=300,
        )
        return result.returncode
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
        logger.warning("executor failed [%s]: %r", argv, exc)
        return 127


__all__ = [
    "Router",
    "RouteResult",
    "PendingPrompt",
    "resolve_project",
    "validate_command",
    "TIER_0_SOV_SUBCOMMANDS",
    "TIER_1_SOV_SUBCOMMANDS",
    "TIER_2_SOV_SUBCOMMANDS",
    "TIER_0_SYSTEM_COMMANDS",
    "BLOCKED_COMMAND_TOKENS",
]
