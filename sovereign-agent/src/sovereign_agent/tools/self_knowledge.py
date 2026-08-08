"""
self_knowledge.py — Aria's self-introspection tools (v0.2.41.0)

Three Tier 0 tools that give Aria eyes on herself:

  read_self            — her kernel: commitments, voice, stance, current state
  list_available_tools — every tool registered in the authority tier matrix
  list_sov_commands    — every `sov` CLI subcommand she can propose

All are read-only, no sandbox restrictions, no approval needed.
"""
from __future__ import annotations

import shutil
import subprocess
from typing import Optional

from pydantic import BaseModel

from sovereign_agent import aria
from sovereign_agent.aria import (
    CORE_COMMITMENTS,
    CORE_DESIGNATION,
    CORE_STANCE,
    CORE_TAGLINE,
    CORE_VOICE,
    AriaState,
)
from sovereign_agent.config import SETTINGS

from .base import Tool, ToolResult


# ─── read_self ───────────────────────────────────────────────────────────────


class ReadSelfTool(Tool):
    """Return Aria's immutable kernel and current durable state.

    The kernel (commitments, voice, stance, tagline) never changes between
    sessions. The durable state (mood, focus, narrative) is read from the
    identity channel in atoms.db. Use this when you need to ground yourself,
    explain your values to the operator, or verify that your self-model is
    intact.
    """

    name = "read_self"
    tier = 0
    description = (
        "Return Aria's immutable kernel (commitments, voice, stance, tagline) "
        "and current durable state (mood, focus, narrative, goal/project counts). "
        "Use this to know yourself: who you are, what you stand for, and where "
        "you currently are in your work."
    )
    failure_modes = (
        "atoms.db missing or unreadable — kernel still returned, state fields default",
        "identity channel empty — state fields show defaults",
    )

    class Args(BaseModel):
        verbose: bool = False
        """If True, include full commitment text; if False, include numbered list."""

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        # Try to load durable state; fall back to kernel defaults
        state = AriaState()
        try:
            import sqlite3
            db = SETTINGS.paths.atoms_db
            if db.exists():
                with sqlite3.connect(str(db), timeout=5) as conn:
                    state = aria.load_state(conn)
        except Exception:
            pass  # kernel defaults are safe

        commitments = "\n".join(
            f"  {i}. {c}" for i, c in enumerate(CORE_COMMITMENTS, 1)
        )
        output = (
            f"# {CORE_DESIGNATION}\n"
            f"\n> {CORE_TAGLINE}\n"
            f"\n## Stance\n{CORE_STANCE}\n"
            f"\n## Voice\n{CORE_VOICE}\n"
            f"\n## Core commitments\n{commitments}\n"
        )
        if state.current_mood or state.current_focus or state.self_narrative:
            output += "\n## Current state\n"
            if state.current_focus:
                output += f"Focus: {state.current_focus}\n"
            if state.current_mood:
                output += f"Mood: {state.current_mood}\n"
            if state.self_narrative:
                output += f"\n{state.self_narrative}\n"
        output += (
            f"\n## Inventory\n"
            f"- {state.active_goals} active goal(s)\n"
            f"- {state.open_intentions} open intention(s)\n"
            f"- {state.tracked_projects} tracked project(s)\n"
        )
        return ToolResult(ok=True, output=output)


# ─── list_available_tools ────────────────────────────────────────────────────


class ListAvailableToolsTool(Tool):
    """List every tool currently registered in the authority tier matrix.

    Returns a structured table of: tool name, tier, and description. Use
    this to know your hands — what you can do — before planning a multi-step
    task. Tier 0 = read-only; Tier 1 = reversible write; Tier 2 = shell/
    long-running; Tier 3 = irreversible (requires approval).
    """

    name = "list_available_tools"
    tier = 0
    description = (
        "List every tool registered in the authority tier matrix, with name, "
        "tier level, and description. Call this when you want to know what "
        "actions you can take, before planning a multi-step task, or when "
        "you receive 'REFUSED: unknown tool' to understand what IS available."
    )
    failure_modes = (
        "tool registry empty — package import may have failed",
    )

    class Args(BaseModel):
        max_tier: Optional[int] = None
        """Filter to tools at or below this tier. None = show all tiers."""

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        from sovereign_agent.authority import _TIER_REGISTRY

        entries = sorted(_TIER_REGISTRY.values(), key=lambda m: (m.tier, m.name))
        if args.max_tier is not None:
            entries = [m for m in entries if m.tier <= args.max_tier]

        if not entries:
            return ToolResult(ok=False, error="tool registry is empty — check package imports")

        tier_labels = {0: "read-only", 1: "reversible write", 2: "shell/long", 3: "irreversible"}
        lines = ["# Available tools\n"]
        current_tier = -1
        for meta in entries:
            if meta.tier != current_tier:
                current_tier = meta.tier
                label = tier_labels.get(current_tier, f"tier {current_tier}")
                lines.append(f"\n## Tier {current_tier} — {label}\n")
            lines.append(f"  **{meta.name}**")
            lines.append(f"  {meta.description}\n")

        return ToolResult(ok=True, output="\n".join(lines), metadata={"count": len(entries)})


# ─── list_sov_commands ───────────────────────────────────────────────────────


class ListSovCommandsTool(Tool):
    """List every `sov` CLI subcommand available on this system.

    Runs `sovereign --help` and parses the output. Use this before
    proposing a `sov` command to verify it exists, or to discover what
    commands are available for a given task. When you propose a command
    and the router refuses it, call this to find the correct alternative.
    """

    name = "list_sov_commands"
    tier = 0
    description = (
        "List all available `sov` (sovereign) CLI subcommands by running "
        "`sovereign --help`. Use this before proposing a sov command to verify "
        "it exists, or when a proposed command is refused to find alternatives."
    )
    failure_modes = (
        "sovereign binary not on PATH — returns error",
        "help output format changes — parsing may be incomplete",
    )

    class Args(BaseModel):
        subcommand: Optional[str] = None
        """If provided, run `sovereign <subcommand> --help` for detailed options."""

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        binary = shutil.which("sovereign") or shutil.which("sov")
        if binary is None:
            return ToolResult(
                ok=False,
                error="sovereign/sov binary not found on PATH — is the venv active?",
            )

        argv = [binary]
        if args.subcommand:
            argv.extend(args.subcommand.split())
        argv.append("--help")

        try:
            proc = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=10,
            )
            output = proc.stdout or proc.stderr or "(no output)"
        except (subprocess.SubprocessError, OSError) as exc:
            return ToolResult(ok=False, error=f"failed to run {argv}: {exc}")

        return ToolResult(
            ok=True,
            output=output,
            metadata={"binary": binary, "subcommand": args.subcommand},
        )
