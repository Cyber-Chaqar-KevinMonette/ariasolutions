"""task_guide — the real, grounded menu of what Aria can do.

Kevin, 2026-07-26: "Create a menu for things she can do... Create a task
guide button on the frontend so I can see everything I can do with her
and so I can test everything following the guide."

Every entry below names REAL, REGISTERED tools — `test_task_guide.py`
asserts every `tool_names` entry actually exists in the live tool
registry (`authority.all_tools()`), so a renamed or removed tool fails
that test immediately instead of the guide quietly drifting into
fiction. This is a curated highlight reel of the practical, testable
capabilities — not an auto-dump of the full 200+-tool registry (most of
which is internal self-improvement/architecture machinery, not
something Kevin was ever meant to poke at directly). `total_tool_count()`
still surfaces the real total so nothing is hidden, just organized.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class GuideEntry:
    label: str
    example: str                       # literally type/paste this to test it
    tool_names: tuple[str, ...] = ()    # real registered tool(s) behind it
    note: str = ""


@dataclass(frozen=True)
class GuideCategory:
    title: str
    entries: tuple[GuideEntry, ...]


CATEGORIES: tuple[GuideCategory, ...] = (
    GuideCategory("Files & Code", (
        GuideEntry("Write or edit a file",
                  "create a script at scripts/hello.py that prints hi",
                  ("write_file", "edit_file")),
        GuideEntry("Run code, shell commands, or the test suite",
                  "run the tests for verticals.py",
                  ("run_code", "run_shell", "run_tests")),
        GuideEntry("Check git status", "what's the current git status?",
                  ("git_status",)),
    )),
    GuideCategory("Images", (
        GuideEntry("Generate an image",
                  "generate an image of a red fox in the snow, digital art style",
                  ("generate_image",),
                  note="local FLUX.1-schnell diffusion, ~20-40s on the GTX 1070"),
        GuideEntry("Edit or inpaint an existing image",
                  "take that last image and make it black and white",
                  ("edit_image", "inpaint_image")),
        GuideEntry("Analyze, caption, or OCR an image",
                  "what's in this image?",
                  ("analyze_image", "image_caption", "extract_text_from_image")),
    )),
    GuideCategory("Audio & Voice", (
        GuideEntry("Text to speech", "say this out loud: welcome to the shop",
                  ("synthesize_speech",),
                  note="piper-tts, CPU-only — no GPU/VRAM needed"),
        GuideEntry("Transcribe audio", "transcribe this recording for me",
                  ("transcribe_audio",),
                  note="faster-whisper, CPU-only"),
    )),
    GuideCategory("Research & Web", (
        GuideEntry("Search + research a topic",
                  "research the current state of X and summarize with sources",
                  ("web_search", "web_fetch", "web_research"),
                  note="web_fetch is allowlist-limited — not an open crawler"),
    )),
    GuideCategory("Discord & Community", (
        GuideEntry("Control the Discord bot", "open the ❖ discord button in the cockpit",
                  ()),
        GuideEntry("Per-user subscribe panel (mobile-friendly)",
                  "/my-panel in Discord", ()),
        GuideEntry("Reply to / resolve her inbox requests",
                  "open the & my inbox button in the cockpit, or /my-inbox in Discord",
                  ("read_inbox", "send_to_human", "acknowledge_inbox_note")),
        GuideEntry("Turn one tracker on/off fleet-wide",
                  "/tracker <slug> on|off in Discord (owner only)", ()),
    )),
    GuideCategory("Memory & Self-Knowledge", (
        GuideEntry("Ask what she remembers",
                  "what do you remember about the shop's pricing?",
                  ("memory_search", "memory_write")),
        GuideEntry("Ask what she's learned",
                  "what have you learned recently?",
                  ("read_lessons", "read_behavior_patterns")),
    )),
    GuideCategory("Sessions, Work & Suggestions", (
        GuideEntry("Start a bounded work session", "/work <goal>", ()),
        GuideEntry("Ask what's worth doing next",
                  "open the ✧ suggestions button, or ask: what should you work on?",
                  ()),
        GuideEntry("Resume a paused session",
                  "open the resume menu in the cockpit",
                  ("session_resume_audit",)),
    )),
    GuideCategory("Game Development", (
        GuideEntry("Check a Godot project for errors",
                  "check the <project> game project for errors",
                  ("godot_check",)),
        GuideEntry("Open the Godot editor",
                  "open <project> in the Godot editor",
                  ("godot_open",)),
        GuideEntry("Scaffold game docs",
                  "write the game brief for <project>",
                  ("scaffold_game_docs",)),
    )),
)


def all_referenced_tool_names() -> set[str]:
    """Every real tool name this guide claims exists — the set the test
    suite checks against the live registry."""
    return {n for cat in CATEGORIES for e in cat.entries for n in e.tool_names}


def total_tool_count() -> int:
    """The REAL total registered tool count, so the guide can honestly
    say 'and N more' instead of pretending this curated list is
    everything."""
    import sovereign_agent.tools  # noqa: F401 — import side-effect: registers every tool
    from sovereign_agent.authority import all_tools
    return len(all_tools())


__all__ = ["GuideEntry", "GuideCategory", "CATEGORIES",
           "all_referenced_tool_names", "total_tool_count"]
