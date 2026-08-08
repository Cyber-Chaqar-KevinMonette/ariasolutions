"""patcher.py — Keys round K1: aria-run-surface.

Six anchored, idempotent patches to cockpit/app.py:
  1. Module import + process-wide RunState (fed by the existing 1s tailer).
  2. `_render_event` routing: feed RunState + payload-aware rich renders
     for the session/subtask/workflow-step/diet/qa families — unknown
     flags fall through to the generic renderer byte-for-byte as before.
  3. Any flag ending `-x` renders RED (failures currently scroll past
     WHITE — the color chain never checked the suffix).
  4. A 5th palette-row strip (#run-strip) — the live "what is she doing
     right now" line (goal · subtasks done/seen · current · tokens ·
     breaker). The multi-line run PANE arrives with K2's layout rows.
  5. `_refresh_cockpit_strips` includes the run strip + the new
     `_refresh_run_strip` method (same graceful-degrade discipline).
  6. Status bar gains the ACTIVE MODE field (chat dim / work bold magenta
     — the "am I autonomous right now" signal, previously invisible) and
     a red breaker badge when RunState saw a circuit-open-x.

run_surface.py itself is a NEW file (payload/), copied whole.
"""
from __future__ import annotations

MARK = "run-surface-d"


class PatchError(Exception):
    pass


def _replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if text.count(old) != 1:
        raise PatchError(f"{label}: expected exactly 1 occurrence, found {text.count(old)}")
    return text.replace(old, new, 1)


# 1. import + module state
STATE_ANCHOR = (
    "_AUTO_BACKUP_LOCK = threading.Lock()  # auto-backup-d\n"
    "_AUTO_BACKUP_RUNNING = False  # auto-backup-d\n"
)
STATE_NEW = (
    STATE_ANCHOR
    + f"from . import run_surface as _run_surface  # {MARK}\n"
    f"_RUN_STATE = _run_surface.RunState()  # {MARK}\n"
)

# 2. routing + rich renders in _render_event
ROUTE_ANCHOR = (
    '        if ev.get("flag", "").startswith("work-"):\n'
    "            self._render_work_event(ev)\n"
    "            return\n"
    "\n"
    '        ts = ev.get("ts", "")[11:19]  # HH:MM:SS slice\n'
    '        flag = ev.get("flag", "?")\n'
)
ROUTE_NEW = (
    '        if ev.get("flag", "").startswith("work-"):\n'
    "            self._render_work_event(ev)\n"
    "            return\n"
    "\n"
    f"        # {MARK} — feed the live run tracker, then try a payload-aware\n"
    "        # rich render for the session/subtask/workflow/diet/qa families.\n"
    "        # Unknown flags fall through to the generic renderer unchanged.\n"
    "        _RUN_STATE.ingest(ev)\n"
    "        self._refresh_run_strip()\n"
    '        ts = ev.get("ts", "")[11:19]  # HH:MM:SS slice\n'
    "        _rich = _run_surface.render_rich_event(ev)\n"
    "        if _rich is not None:\n"
    '            self._events_log.write(f"[dim]{ts}[/dim] {_rich}")\n'
    "            return\n"
    '        flag = ev.get("flag", "?")\n'
)

# 3. -x renders red
COLOR_ANCHOR = (
    "        # Color by event kind\n"
    '        if "end" in flag:\n'
)
COLOR_NEW = (
    "        # Color by event kind\n"
    f'        if flag.endswith("-x"):  # {MARK} — failures are RED, always\n'
    '            color = "red"\n'
    '        elif "end" in flag:\n'
)

# 4. the 5th strip
STRIP_ANCHOR = (
    '            yield Static("", id="vessel-strip", classes="cockpit-strip")  # vessel-health-d\n'
)
STRIP_NEW = (
    STRIP_ANCHOR
    + f'            yield Static("", id="run-strip", classes="cockpit-strip")  # {MARK}\n'
)

# 5. refresh wiring + method
REFRESH_ANCHOR = (
    "        self._refresh_observability_strip()\n"
    "        self._refresh_security_strip()\n"
    "        self._refresh_emotions_strip()\n"
    "        self._refresh_vessel_strip()  # vessel-health-d\n"
)
REFRESH_NEW = (
    "        self._refresh_observability_strip()\n"
    "        self._refresh_security_strip()\n"
    "        self._refresh_emotions_strip()\n"
    "        self._refresh_vessel_strip()  # vessel-health-d\n"
    f"        self._refresh_run_strip()  # {MARK}\n"
)

METHOD_ANCHOR = (
    "    def _refresh_observability_strip(self) -> None:  # command-menu-d\n"
)
METHOD_NEW = (
    f"    def _refresh_run_strip(self) -> None:  # {MARK}\n"
    '        """The live \'what is she doing right now\' line. Fed by\n'
    "        _RUN_STATE (which the events tailer updates); degrades to a dim\n"
    '        placeholder and never blocks boot."""\n'
    "        try:\n"
    '            strip = self.query_one("#run-strip", Static)\n'
    "            strip.update(_RUN_STATE.render_strip())\n"
    "        except Exception:  # noqa: BLE001\n"
    "            pass\n"
    "\n"
    "    def _refresh_observability_strip(self) -> None:  # command-menu-d\n"
)

# 6. status bar: mode + breaker badge
STATUSBAR_ANCHOR = (
    "        obs_parts: list[str] = []\n"
    "        if self._session_tokens > 0:\n"
)
STATUSBAR_NEW = (
    "        obs_parts: list[str] = []\n"
    f"        try:  # {MARK} — ACTIVE MODE: the 'am I autonomous right now' signal\n"
    "            from sovereign_agent.cockpit_modes import load_mode as _rs_load_mode\n"
    "\n"
    "            _rs_mode = _rs_load_mode().mode.value\n"
    "            obs_parts.append(\n"
    '                f"[bold magenta]◈ {_rs_mode}[/bold magenta]" if _rs_mode != "chat"\n'
    '                else "[dim]◈ chat[/dim]"\n'
    "            )\n"
    "        except Exception:  # noqa: BLE001\n"
    "            pass\n"
    "        if _RUN_STATE.breaker_open_tool:\n"
    '            obs_parts.append(f"[red]⛒ {_RUN_STATE.breaker_open_tool}[/red]")\n'
    "        if self._session_tokens > 0:\n"
)


def patch_app(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(text, STATE_ANCHOR, STATE_NEW, label="app module-state anchor")
    text = _replace_once(text, ROUTE_ANCHOR, ROUTE_NEW, label="app render-event routing anchor")
    text = _replace_once(text, COLOR_ANCHOR, COLOR_NEW, label="app color-chain anchor")
    text = _replace_once(text, STRIP_ANCHOR, STRIP_NEW, label="app strip anchor")
    text = _replace_once(text, REFRESH_ANCHOR, REFRESH_NEW, label="app refresh anchor")
    text = _replace_once(text, METHOD_ANCHOR, METHOD_NEW, label="app method anchor")
    text = _replace_once(text, STATUSBAR_ANCHOR, STATUSBAR_NEW, label="app statusbar anchor")
    return text, True
