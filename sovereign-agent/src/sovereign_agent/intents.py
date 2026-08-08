"""
╔══════════════════════════════════════════════════════════════════════════╗
║  intents.py — Typed intent objects for the natural-conversation layer    ║
║  v0.2.19.0                                                                ║
║                                                                           ║
║  Every operator message resolves to ONE intent. The interpreter produces ║
║  these; the router consumes them. The cockpit displays them.             ║
║                                                                           ║
║  Inversion from v0.2.18.x:                                               ║
║                                                                           ║
║    Old default: text → keyword-matched Directive → input("?") → confirm  ║
║    New default: text → Conversation (saved to memory, responded to)      ║
║                                                                           ║
║    Work is dispatched only when the interpreter is confident the         ║
║    operator requested it. Ambiguity is surfaced explicitly (ONE          ║
║    question, up to 3 options) and falls back to conversation, never to   ║
║    a confirm trap.                                                        ║
║                                                                           ║
║  Authority tiers (from MOS canon):                                       ║
║    0 — read-only, no side effects        → silent dispatch                ║
║    1 — reversible writes, bounded scope  → silent + logged                ║
║    2 — persistent changes, external calls→ surfaced meta event            ║
║    3 — irreversible, financial, PII      → "type 'ok' or /cancel"         ║
║    4 — cross-system, multi-agent          → PROTOCOL-ZERO armed           ║
║                                                                           ║
║  Tier 3 is the ONLY tier in the chat path that asks for confirmation,    ║
║  and the prompt is a single-word check, not yes/no. The operator's       ║
║  free-form prose is never the answer to a y/n question. That was the     ║
║  v0.2.18.x trap. It does not exist in v0.2.19.0.                          ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Literal


class AuthorityTier(IntEnum):
    """Authority tiers for agentic work — see MOS Architect-Auditor skill."""
    READ_ONLY = 0
    REVERSIBLE = 1
    PERSISTENT = 2
    IRREVERSIBLE = 3
    CROSS_SYSTEM = 4


# In v0.2.20.x this was a closed allowlist. v0.2.21.0 opens it: Aria
# chooses channel names by reasoning about the message, and may invent
# new ones. The channel writer creates channels on demand. The list
# below is a HINT of common channels for tooling (e.g. `sov channels
# list` ordering), not a constraint on what's writable.
CONVERSATION_CHANNELS: tuple[str, ...] = (
    "context",        # default — uncategorized observations
    "people",         # facts about people in operator's world
    "identity",       # operator-stated identity claims
    "intention",      # what the operator wants / values
    "emotions",       # operator's emotional state
    "humor",          # jokes, riffs, warmth
    "lessons",        # things learned together
    "intuition",      # operator's hunches, half-formed ideas
    "ritual",         # repeated patterns, practices
    "trust",          # trust-building moments
    "insights",       # synthesized realizations
    "reasoning",      # explicit reasoning shared by operator
    "specialist",     # technical/domain claims worth versioning
)


# ─── The Intent algebra ─────────────────────────────────────────────────────


@dataclass
class Conversation:
    """The operator said something that does not request work.

    Aria's response: save the text to one or more memory channels, then
    reply in her voice. No subprocess, no command execution, no confirm.

    Examples:
        "good morning" → save to context, reply warmly
        "my back is killing me today" → save to emotions+people, reply
            with care, suggest gentle pacing
        "I think coherence is more about phase than energy" → save to
            specialist+insights, reply with engagement
        "Meeting Kevin with confidence, joy, love, family vibes..."
            → save to identity+intention+ritual, reply welcomingly
    """
    kind: Literal["conversation"] = "conversation"
    text: str = ""
    save_to: list[str] = field(default_factory=lambda: ["context"])
    reply_voice: Literal["warm", "thinking", "playful", "quiet"] = "warm"
    # Aria's *suggested* reply, surfaced as a hint to the responder. The
    # responder is free to ignore it and generate its own. Surfacing it
    # here makes the interpreter's reasoning auditable.
    reply_hint: str = ""

    def __post_init__(self) -> None:
        # v0.2.21.0: channel names are open — Aria chooses by reasoning,
        # not by matching a fixed list. We only sanitize whitespace/
        # empty strings here; the filesystem-safety coercion happens
        # in the interpreter and the channel writer.
        self.save_to = [c.strip() for c in self.save_to if c and c.strip()]
        if not self.save_to:
            self.save_to = ["context"]


@dataclass
class ProjectRef:
    """Reference to a named project — existing or newly-created.

    The router resolves these. The interpreter only ever specifies a
    *hint* (name or path); resolution is the router's job because the
    project store is not a pure function of the message.
    """
    name: str = ""
    root: str = ""                # may be empty; router fills it
    created: bool = False         # True if router created this project


@dataclass
class Work:
    """The operator requested an action Aria should execute.

    The interpreter populates `summary`, `commands`, `authority_tier`,
    and `project_hint` (name OR path, optional). The router resolves the
    project and validates each command against the allowlist before
    execution.

    Commands are ALWAYS `sov <subcommand> ...` form, or one of a small
    explicitly-whitelisted set of read-only system commands (ls, cat,
    find, head, tail, wc). Anything else is rejected by the router as a
    tier violation.

    Why this constraint:
        Aria writes commands; she is the commander. But "commander"
        does not mean "arbitrary shell access" — it means "authorship
        within the vocabulary the system exposes." The vocabulary is
        the `sov` CLI plus a tiny read-only system fringe. Everything
        else requires explicit tier-3 escalation.
    """
    kind: Literal["work"] = "work"
    summary: str = ""              # one-line human description
    commands: list[str] = field(default_factory=list)  # `sov ...` invocations
    authority_tier: int = 1        # default: reversible
    project_hint: str = ""         # name or path or empty
    # Why Aria chose this — visible to the operator. Builds trust by
    # making the interpreter's logic legible.
    rationale: str = ""


@dataclass
class Recall:
    """The operator wants to look something up — not execute work.

    Examples:
        "what do I have on quantum coherence?" → search memory
        "show me my projects"                  → list projects
        "what did we decide about back braces?" → channel search
    """
    kind: Literal["recall"] = "recall"
    query: str = ""
    scope: Literal["memory", "projects", "channels", "events", "all"] = "all"
    rationale: str = ""


@dataclass
class Slash:
    """A slash command — direct verb → action, no LLM in the loop.

    Slash commands are recognized BEFORE the interpreter runs. They are
    the operator's escape hatch and their syntax is intentionally
    machine-readable (no ambiguity, no LLM interpretation).

    The router maps verb+arg to a fixed handler set.
    """
    kind: Literal["slash"] = "slash"
    verb: str = ""
    arg: str = ""


@dataclass
class Ambiguous:
    """Aria could not classify the message with confidence.

    Surface ONE focused question with up to 3 options. If the operator
    doesn't answer in `timeout_seconds`, fall back to Conversation.
    NEVER block the operator on a yes/no confirm.

    Why three options max:
        More options is noise. If there are genuinely more than three
        reasonable interpretations, the right move is "save as
        conversation; revisit later" — not "force-rank the four
        possibilities into a menu."
    """
    kind: Literal["ambiguous"] = "ambiguous"
    text: str = ""
    question: str = ""
    options: list[str] = field(default_factory=list)
    timeout_seconds: int = 30
    rationale: str = ""

    def __post_init__(self) -> None:
        # Cap options at 3 — see docstring.
        self.options = self.options[:3]


# Union type — every intent the conversation layer can produce.
Intent = Conversation | Work | Recall | Slash | Ambiguous


# ─── Context passed to the interpreter ───────────────────────────────────────


@dataclass
class ConversationContext:
    """Side-channel context the interpreter consults when classifying.

    The interpreter does NOT mutate this; it is read-only. Routing-side
    effects (project creation, memory writes) happen downstream.

    Why pass these in explicitly:
        The interpreter is testable as a pure function of (text,
        context). No global state. No "and also Aria's mood today."
        If a classification is wrong, the inputs are reproducible.
    """
    # Project names the operator has registered. Used to resolve "I
    # updated <name>" or "the X project" without searching the file
    # system.
    known_project_names: tuple[str, ...] = ()
    # Recent operator messages — gives the LLM continuity. Trimmed to
    # the last N turns by the caller.
    recent_turns: tuple[str, ...] = ()
    # The operator's current location in the conversation. Cockpit sets
    # this from its state. CLI sets it to "cli".
    surface: Literal["cockpit", "cli", "test"] = "cli"
    # Whether the operator has a live subprocess waiting for input. If
    # True, the router prefers Conversation-with-no-side-effects so we
    # don't fire a second worker.
    busy: bool = False


__all__ = [
    "AuthorityTier",
    "CONVERSATION_CHANNELS",
    "Conversation",
    "ProjectRef",
    "Work",
    "Recall",
    "Slash",
    "Ambiguous",
    "Intent",
    "ConversationContext",
]
