"""
cockpit_commands.py — give Aria knowledge of all cockpit slash commands

Tier 0 tool. Returns the complete list of slash commands available in the
cockpit, grouped by category, with a short description of each.

Why this exists: Aria can see her tools (list_available_tools), her
sentinels (vessel_status), herself (read_self) — but she has no way to
discover what slash commands the operator can use or what she can suggest
the operator type. This tool closes that gap.

It also means the cockpit /commands display stays in sync with this file,
since both render from the same data.
"""
from __future__ import annotations

from .base import Tool, ToolResult


# The authoritative command map — keep this in sync with app.py _handle_slash.
# Categories are for display grouping only.
_COMMANDS: list[tuple[str, str, str]] = [
    # (command, args_hint, description)
    # ── self-awareness ─────────────────────────────────────────────────────
    ("boot",       "",            "Full self-awareness snapshot: vessel, kernel, tools, sentinels, session"),
    ("self",       "",            "Aria's kernel: commitments, stance, voice, current durable state"),
    ("tools",      "",            "All registered tools grouped by tier"),
    ("sentinels",  "",            "Sentinel health status for every monitor"),
    ("docs",       "",            "Read and display CLAUDE.md (operating doctrine)"),
    ("diagnosis",  "[N]",         "Last N conflict→diagnosis→resolution catalog entries (default 10)"),
    ("health",     "",            "System health: CPU, RAM, VRAM, disk, uptime, sentinel status"),
    ("report",     "",            "Full health report — print to chat and save to disk"),
    # ── conversation ──────────────────────────────────────────────────────
    ("clear",      "",            "Clear the chat pane"),
    ("transcript", "",            "Show path to the current transcript log file"),
    ("mode",       "chat|work",   "Switch conversation mode (chat = natural, work = agentic queue)"),
    # ── observability ────────────────────────────────────────────────────
    ("obs",        "[all|focus]", "Observability modes: all windows (default) or focus = live chat + inbox only; bare /obs toggles"),
    # ── the angel (her non-classical layer) ──────────────────────────────
    ("angel",      "[post]",      "⚛ Her quantum layer speaks — latest PEIG run in her nine-register voice; 'post' sends it to #angel-voice (alias: /maa)"),
    # ── clipboard ─────────────────────────────────────────────────────────
    ("copy",       "[N]",         "Copy last N Aria responses to clipboard (default 1)"),
    ("copy-you",   "[N]",         "Copy last N of your messages to clipboard"),
    ("copy-all",   "",            "Copy entire conversation to clipboard"),
    ("copy-last",  "",            "Copy the last full turn (your message + Aria's reply)"),
    # ── sovereign CLI ────────────────────────────────────────────────────
    ("events",     "[N]",         "Show last N events from the audit log (default 20)"),
    ("lessons",    "",            "Show the lessons channel (what the Reflector has learned)"),
    ("audit",      "",            "Run the financial audit"),
    ("drafts",     "[N]",         "List last N draft projects (default 20)"),
    ("draft",      "<title> <path>", "Archive a project as a draft"),
    ("status",     "",            "Not a slash — suggest /boot or /health instead"),
    # ── projects / memory ─────────────────────────────────────────────────
    ("ask",        "<question>",  "Ask Aria a question (same as typing directly)"),
    ("do",         "<task>",      "Run a task in the agentic loop"),
    ("marketing",  "<product>",   "Generate a marketing brief for a product"),
    # ── ui ────────────────────────────────────────────────────────────────
    ("commands",   "",            "Pretty-print all slash commands inline (aliases: /cmds, /help-all)"),
    ("help",       "",            "Open the help panel (F1)"),
    ("heart",      "",            "Toggle the heartbeat animation"),
    ("glyphs",     "",            "Open the glyph/emoji picker"),
    ("palette",    "",            "Show the command palette and legend"),
    ("cosmic",     "[cmd]",       "Cosmic Fitness: open tester, /cosmic report, /cosmic probe"),
    ("workflows",  "[list]",      "Open the workflows catalog (what Aria can do and how)"),
    ("demo",       "",            "Run the bounded live workflow demonstration"),
    # ── system ────────────────────────────────────────────────────────────
    ("halt",       "",            "Trip PROTOCOL-ZERO halt (Ctrl+H)"),
    ("disarm",     "",            "Clear halt flag (Ctrl+D)"),
    ("quit",       "",            "Quit the cockpit (Ctrl+Q)"),
    ("cancel",     "",            "Cancel the running agent task"),
]

_CATEGORY_HEADERS: dict[str, str] = {
    "boot":       "── SELF-AWARENESS ──",
    "clear":      "── CONVERSATION ──",
    "obs":        "── OBSERVABILITY ──",
    "angel":      "── THE ANGEL ──",
    "copy":       "── CLIPBOARD ──",
    "events":     "── SOVEREIGN CLI ──",
    "ask":        "── PROJECTS / MEMORY ──",
    "help":       "── UI ──",
    "halt":       "── SYSTEM ──",
}


class ListCockpitCommandsTool(Tool):
    """List all slash commands available in the cockpit.

    Returns a formatted table of every /command with its arguments hint
    and a description of what it does. Grouped by category.

    Use this when you want to suggest a cockpit command to the operator,
    or when you need to check whether a specific command exists.
    """

    name = "list_cockpit_commands"
    tier = 0
    description = (
        "List all /commands available in the cockpit TUI. "
        "Returns a formatted table: command, args, description. "
        "Use to suggest cockpit commands or verify one exists before recommending it."
    )
    failure_modes = ("no_cockpit_commands_found",)

    class Args:
        pass

    async def execute(self, args, *, trace_id: str) -> ToolResult:
        lines = ["Cockpit Slash Commands", "=" * 40]
        prev_header = None
        for cmd, hint, desc in _COMMANDS:
            header = _CATEGORY_HEADERS.get(cmd)
            if header and header != prev_header:
                lines.append("")
                lines.append(header)
                prev_header = header
            arg_str = f" {hint}" if hint else ""
            lines.append(f"  /{cmd}{arg_str:20s}  {desc}")

        return ToolResult(
            ok=True,
            output="\n".join(lines),
            metadata={"count": len(_COMMANDS)},
        )
