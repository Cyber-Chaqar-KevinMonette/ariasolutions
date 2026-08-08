"""
command_invariants.py — Aria's living improvement registry for commands and tools

Concept: every `sov` subcommand and registered tool can have an invariant
profile stored at data_dir/command-invariants/<name>/. Aria accumulates her
own knowledge about how commands SHOULD behave, what invariants they must
satisfy, and what improvements she has identified — without touching the main
codebase.

Directory structure:
  data_dir/command-invariants/
    <command-name>/
      invariants.md   — behavioral rules this command MUST always satisfy
      improvements.md — Aria's running log of improvements she's identified
      notes.md        — general notes, edge cases, gotchas

This is the exocortex layer of the command system: a parallel directory
where upgraded knowledge lives without cluttering the source tree.

Three tools:
  list_command_invariants()               — what commands have profiles?
  read_command_invariant(command, section) — read a specific profile
  write_command_note(command, content, section) — Aria writes her insights
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from .base import Tool, ToolResult


_VALID_SECTIONS = ("invariants", "improvements", "notes", "all")


def _profile_dir(data_dir: Path, command: str) -> Path:
    return data_dir / "command-invariants" / command


def _section_file(profile_dir: Path, section: str) -> Path:
    return profile_dir / f"{section}.md"


def _list_profiles(data_dir: Path) -> list[str]:
    base = data_dir / "command-invariants"
    if not base.exists():
        return []
    return sorted(
        d.name for d in base.iterdir()
        if d.is_dir() and any(d.glob("*.md"))
    )


# ── ListCommandInvariantsTool ─────────────────────────────────────────────────


class ListCommandInvariantsTool(Tool):
    """List all commands and tools that have invariant profiles.

    Aria accumulates invariant profiles in data_dir/command-invariants/.
    This tool returns the list of profiles that exist, how many notes each
    has accumulated, and a summary of the invariants defined.

    Call this before working with a command to check if there's accumulated
    knowledge about how it should behave or known improvements to apply.
    """

    name = "list_command_invariants"
    tier = 0
    description = (
        "List all commands/tools that have invariant profiles in data_dir/command-invariants/. "
        "Shows which commands have accumulated behavioral rules, improvements, or notes. "
        "Call before using a command to check for known improvements."
    )
    failure_modes = ("data_dir not configured",)

    class Args(BaseModel):
        pass

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        from sovereign_agent.config import SETTINGS

        data_dir = SETTINGS.paths.data_dir
        profiles = _list_profiles(data_dir)

        if not profiles:
            return ToolResult(
                ok=True,
                output=(
                    "No invariant profiles yet. Aria hasn't accumulated command knowledge yet.\n\n"
                    "Start building with write_command_note(command, content, section='invariants').\n"
                    "Good candidates for invariant profiles:\n"
                    "  • sov ask    — what makes a good question to Aria?\n"
                    "  • sov doctor — what should it always check?\n"
                    "  • sov events — what filters are most useful?\n"
                    "  • analyze_image — what focus modes work best for what content?\n"
                    "  • vessel_status — when to escalate a sentinel warning?"
                ),
                metadata={"count": 0},
            )

        lines = [f"Command Invariant Profiles — {len(profiles)} commands", ""]
        for cmd in profiles:
            d = _profile_dir(data_dir, cmd)
            sections = []
            for section in ("invariants", "improvements", "notes"):
                f = _section_file(d, section)
                if f.exists():
                    lines_count = len(f.read_text(encoding="utf-8").splitlines())
                    sections.append(f"{section}({lines_count}L)")
            summary = "  ".join(sections) if sections else "(empty)"
            lines.append(f"  {cmd:30s} {summary}")

        lines += [
            "",
            "Use read_command_invariant(command) to read a profile.",
            "Use write_command_note(command, content) to add knowledge.",
        ]

        return ToolResult(
            ok=True,
            output="\n".join(lines),
            metadata={"count": len(profiles), "profiles": profiles},
        )


# ── ReadCommandInvariantTool ──────────────────────────────────────────────────


class ReadCommandInvariantTool(Tool):
    """Read the invariant profile for a specific command or tool.

    Returns behavioral rules (invariants), identified improvements,
    and general notes accumulated for this command.

    Call this before using a command for a critical task to ensure
    you're applying all known best practices and invariants.
    """

    name = "read_command_invariant"
    tier = 0
    description = (
        "Read the invariant profile for a command or tool. "
        "Returns: behavioral invariants, improvement log, notes. "
        "Args: command (name), section (invariants/improvements/notes/all). "
        "Call before critical use of a command to apply known best practices."
    )
    failure_modes = (
        "command profile not found — use write_command_note to create it",
        "section must be: invariants, improvements, notes, or all",
    )

    class Args(BaseModel):
        command: str = Field(description="Command or tool name (e.g. 'sov-ask', 'analyze_image').")
        section: str = Field(
            default="all",
            description="Section to read: invariants, improvements, notes, or all.",
        )

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        from sovereign_agent.config import SETTINGS

        if args.section not in _VALID_SECTIONS:
            return ToolResult(
                ok=False,
                error=f"invalid section {args.section!r}. valid: {', '.join(_VALID_SECTIONS)}",
            )

        data_dir = SETTINGS.paths.data_dir
        profile_dir = _profile_dir(data_dir, args.command)

        if not profile_dir.exists():
            return ToolResult(
                ok=False,
                error=(
                    f"no invariant profile for {args.command!r}. "
                    "Create one with write_command_note(command, content, section='invariants'). "
                    f"Available profiles: {', '.join(_list_profiles(data_dir)) or 'none yet'}"
                ),
            )

        if args.section == "all":
            sections_to_read = ["invariants", "improvements", "notes"]
        else:
            sections_to_read = [args.section]

        lines = [f"═══ Invariant Profile: {args.command} ═══"]
        found_any = False

        for sec in sections_to_read:
            f = _section_file(profile_dir, sec)
            if f.exists():
                content = f.read_text(encoding="utf-8").strip()
                if content:
                    lines += ["", f"─── {sec.upper()} ───", content]
                    found_any = True

        if not found_any:
            lines.append("\n(profile directory exists but all sections are empty)")

        return ToolResult(
            ok=True,
            output="\n".join(lines),
            metadata={
                "command": args.command,
                "section": args.section,
                "profile_dir": str(profile_dir),
            },
        )


# ── WriteCommandNoteTool ──────────────────────────────────────────────────────


class WriteCommandNoteTool(Tool):
    """Write a note, invariant, or improvement to a command's profile.

    This is how Aria accumulates knowledge about commands over time.
    Notes are appended to the appropriate section file, timestamped.

    Sections:
      invariants   — behavioral rules that must ALWAYS be satisfied
                     (e.g. "sov doctor must always check sentinel health")
      improvements — specific upgrades Aria has identified
                     (e.g. "add --since flag to sov events for time filtering")
      notes        — general observations, edge cases, gotchas

    The profile lives in data_dir/command-invariants/<command>/ —
    separate from the source tree, never clutters the codebase.
    """

    name = "write_command_note"
    tier = 1  # Tier 1: writes to data_dir (sandbox)
    description = (
        "Write a note, invariant, or improvement to a command's profile. "
        "Args: command (name), content (your note), section (invariants/improvements/notes). "
        "Profiles live in data_dir/command-invariants/ — separate from source. "
        "Use to accumulate behavioral knowledge about commands over time."
    )
    failure_modes = (
        "data_dir not configured",
        "invalid section name",
        "disk full",
    )

    class Args(BaseModel):
        command: str = Field(
            description="Command or tool name to write a note for (e.g. 'sov-doctor', 'vessel_status').",
        )
        content: str = Field(
            description="The note, invariant rule, or improvement to record.",
        )
        section: str = Field(
            default="notes",
            description="Where to write: invariants (behavioral rules), improvements (upgrade ideas), notes (general).",
        )

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        from sovereign_agent.config import SETTINGS

        if args.section not in _VALID_SECTIONS or args.section == "all":
            return ToolResult(
                ok=False,
                error=f"section must be: invariants, improvements, or notes",
            )

        content = args.content.strip()
        if not content:
            return ToolResult(ok=False, error="content is empty")

        data_dir = SETTINGS.paths.data_dir
        profile_dir = _profile_dir(data_dir, args.command)
        profile_dir.mkdir(parents=True, exist_ok=True)

        section_file = _section_file(profile_dir, args.section)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        # Append with timestamp header
        entry = f"\n\n---\n*{ts}*\n\n{content}\n"
        existing = section_file.read_text(encoding="utf-8") if section_file.exists() else ""
        if not existing:
            # First entry — add a header
            header = {
                "invariants": f"# Invariants: {args.command}\n\nBehavioral rules this command must always satisfy.\n",
                "improvements": f"# Improvements: {args.command}\n\nUpgrades Aria has identified for this command.\n",
                "notes": f"# Notes: {args.command}\n\nObservations, edge cases, and gotchas.\n",
            }[args.section]
            section_file.write_text(header + entry, encoding="utf-8")
        else:
            with section_file.open("a", encoding="utf-8") as f:
                f.write(entry)

        return ToolResult(
            ok=True,
            output=f"note added to {args.command}/{args.section}.md",
            metadata={
                "command": args.command,
                "section": args.section,
                "path": str(section_file),
                "chars_added": len(entry),
            },
        )
