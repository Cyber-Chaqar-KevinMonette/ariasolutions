"""patcher.py — anchored, idempotent patches for Workstream O (dual inbox).

Three targets, all span/anchor replacements against the CURRENT live text
rather than full-file replacements — cli.py (10,949 lines) and app.py
(4,894 lines) both evolve fast, so touching only the exact span that matters
avoids clobbering unrelated content added since any reference payload was
captured.

  patch_cli(text, new_block)     — replaces the self-contained `requests_app`
                                    typer sub-app span in cli.py.
  patch_app_inbox(text, new_block) — replaces the `_refresh_inbox_pane`
                                    method body in cockpit/app.py.
  patch_tools_init(text)         — adds the inbox_tools import + two
                                    __all__ entries to tools/__init__.py,
                                    anchored next to hyperintel_tool's
                                    entries (both import AND __all__ in one
                                    patch — the lesson from H4/L about
                                    missing __all__ exports being a real,
                                    recurring bug class).
"""
from __future__ import annotations

MARK = "dual-inbox-d"

CLI_START_ANCHOR = "requests_app = typer.Typer(\n"
CLI_END_ANCHOR = 'app.add_typer(requests_app, name="requests")\n'

APP_START_ANCHOR = "    def _refresh_inbox_pane(self) -> None:\n"
APP_END_ANCHOR = "    def _refresh_memory_pane(self) -> None:\n"

TOOLS_IMPORT_ANCHOR = "from .hyperintel_tool import HyperIntelTool  # hyperintel-import-d\n"
TOOLS_ALL_ANCHOR = '    "HyperIntelTool",  # hyperintel-all-d\n'


class PatchError(Exception):
    pass


def _span_replace(text: str, start_anchor: str, end_anchor: str, new_block: str,
                   *, keep_end_anchor: bool) -> str:
    if text.count(start_anchor) != 1:
        raise PatchError(f"expected exactly 1 occurrence of {start_anchor!r}, found {text.count(start_anchor)}")
    if text.count(end_anchor) != 1:
        raise PatchError(f"expected exactly 1 occurrence of {end_anchor!r}, found {text.count(end_anchor)}")
    start = text.index(start_anchor)
    end = text.index(end_anchor)
    if keep_end_anchor:
        pass  # end marks where new_block stops; end_anchor itself is preserved after it
    else:
        end += len(end_anchor)
    if end <= start:
        raise PatchError("end anchor precedes start anchor — refusing to patch")
    return text[:start] + new_block + text[end:]


def patch_cli(text: str, new_block: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    marked_block = new_block.rstrip("\n") + f"\n# {MARK}\n"
    new_text = _span_replace(text, CLI_START_ANCHOR, CLI_END_ANCHOR, marked_block,
                              keep_end_anchor=False)
    return new_text, True


def patch_app_inbox(text: str, new_block: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    # keep_end_anchor=True: new_block replaces everything from the start
    # anchor UP TO (not including) _refresh_memory_pane's def line, which
    # stays in place as the next method.
    marked_block = new_block.rstrip("\n") + "\n\n"
    new_text = _span_replace(text, APP_START_ANCHOR, APP_END_ANCHOR, marked_block,
                              keep_end_anchor=True)
    return new_text, True


def patch_tools_init(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    if TOOLS_IMPORT_ANCHOR not in text:
        raise PatchError("tools/__init__.py: hyperintel import anchor not found verbatim")
    if TOOLS_ALL_ANCHOR not in text:
        raise PatchError("tools/__init__.py: hyperintel __all__ anchor not found verbatim")
    new_import = (
        TOOLS_IMPORT_ANCHOR
        + f"from .inbox_tools import SendToHumanTool, ReadInboxTool  # {MARK}\n"
    )
    text = text.replace(TOOLS_IMPORT_ANCHOR, new_import, 1)
    new_all = (
        TOOLS_ALL_ANCHOR
        + f'    "SendToHumanTool",  # {MARK}\n'
        + '    "ReadInboxTool",\n'
    )
    text = text.replace(TOOLS_ALL_ANCHOR, new_all, 1)
    return text, True
