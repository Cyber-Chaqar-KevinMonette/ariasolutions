"""patcher.py — Workstream A ("Aria's Atelier"): a live work-theater pane
that streams every file Aria writes/edits and every command she runs,
color-coded (green=new file, yellow=edited+diff, purple/blue=command run).

Two files patched:

1. `loop.py` — one new import + one new call, right after the existing
   "Invariant 2: one event per action" `_record(...)` block (the tool
   dispatch's single choke point). `tool_name`, the parsed `Args`, and the
   `ToolResult` are all already in scope there, so `maybe_emit_work_event()`
   (a new module, `work_events.py`) can derive a richer work-write/
   work-edit/work-command event purely from data that already exists —
   no individual tool file (`edit_file.py`, `write_file.py`, etc.) is
   touched.

2. `cockpit/app.py` — a 5th pane (`#atelier-log`), plus ONE early-return
   branch added to the START of the EXISTING `_render_event()` method: if
   `ev["flag"]` starts with `work-`, route to a new `_render_work_event()`
   instead of the generic "live" pane. This deliberately does NOT add a
   second file-tailing worker — work events land in the exact same
   `events.jsonl` the cockpit already tails once a second via
   `_tail_events_worker()`; a second tailer reading the same file would
   just be redundant I/O for no benefit. (The plan's own text suggested
   mirroring the tailer; this is a simplification found during the actual
   build, once it was clear the existing tailer already sees every line.)

Anchored span patches against the CURRENT live files (same discipline as
every other patcher this session — not a full-file replace).
"""
from __future__ import annotations

MARK = "atelier-d"


class PatchError(Exception):
    pass


def _replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if text.count(old) != 1:
        raise PatchError(f"{label}: expected exactly 1 occurrence, found {text.count(old)}")
    return text.replace(old, new, 1)


# ═══════════════════════════════════════════════════════════════════════
# loop.py — emit a richer work event at the one tool-dispatch choke point
# ═══════════════════════════════════════════════════════════════════════

LOOP_RECORD_ANCHOR = (
    '                # ── Invariant 2: one event per action ────────────────\n'
    '                _record(\n'
    '                    f"{tool_name}-d" if result.ok else f"{tool_name}-x",\n'
    '                    {\n'
    '                        "ok": result.ok,\n'
    '                        "metadata": result.metadata,\n'
    '                        "error": result.error,\n'
    '                    },\n'
    '                )\n'
)
LOOP_RECORD_NEW = (
    LOOP_RECORD_ANCHOR
    + f'                # {MARK} — Aria\'s Atelier: a richer work-write/work-edit/\n'
    + '                # work-command event for the cockpit\'s live work-theater pane,\n'
    + '                # derived purely from data already in scope here (tool_name,\n'
    + '                # parsed args, result) — no individual tool file is touched.\n'
    + '                # Best-effort: never raises, never blocks the loop.\n'
    + '                maybe_emit_work_event(tool_name, parsed, result, trace_id=trace_id)\n'
)

LOOP_IMPORT_ANCHOR = "from .events import emit_event, force_fsync, trace\n"
LOOP_IMPORT_NEW = (
    "from .events import emit_event, force_fsync, trace\n"
    f"from .work_events import maybe_emit_work_event  # {MARK}\n"
)


def patch_loop(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(text, LOOP_IMPORT_ANCHOR, LOOP_IMPORT_NEW, label="loop import anchor")
    text = _replace_once(text, LOOP_RECORD_ANCHOR, LOOP_RECORD_NEW, label="loop record anchor")
    return text, True


# ═══════════════════════════════════════════════════════════════════════
# cockpit/app.py — the 5th pane + routing in the existing _render_event
# ═══════════════════════════════════════════════════════════════════════

# ── 1. CSS: #atelier-pane + #divider-4, same discipline as #inbox-pane/#divider-3 ──

CSS_ANCHOR = (
    '    #inbox-pane {\n'
    '        width: 1fr;\n'
    '        padding: 0 1;\n'
    '        background: $surface;\n'
    '    }\n'
)
CSS_NEW = (
    CSS_ANCHOR
    + f'    /* {MARK} — Atelier pane (5th window): live work theater. Same 1fr\n'
    + '       discipline as memory/live/inbox. */\n'
    + '    #atelier-pane {\n'
    + '        width: 1fr;\n'
    + '        padding: 0 1;\n'
    + '        background: $surface;\n'
    + '    }\n'
)

CSS_DIVIDER_ANCHOR = (
    '    #divider-3.breathing-2 { color: $accent; }\n'
    '    #divider-3.breathing-3 { color: $secondary; }\n'
    '    #divider-3.news { color: $accent; }\n'
    '    #divider-3.halt { color: $error; }\n'
)
CSS_DIVIDER_NEW = (
    CSS_DIVIDER_ANCHOR
    + f'\n    /* {MARK} — fourth divider, between inbox and atelier. Same discipline. */\n'
    + '    #divider-4 {\n'
    + '        width: 1;\n'
    + '        height: 1fr;\n'
    + '        margin: 0;\n'
    + '        color: $primary;\n'
    + '        background: $surface;\n'
    + '    }\n'
    + '    #divider-4.breathing-2 { color: $accent; }\n'
    + '    #divider-4.breathing-3 { color: $secondary; }\n'
    + '    #divider-4.news { color: $accent; }\n'
    + '    #divider-4.halt { color: $error; }\n'
)


# ── 2. compose(): the 5th pane, right after inbox-pane closes ───────────

COMPOSE_ANCHOR = (
    '            yield Rule(orientation="vertical", id="divider-3")\n'
    '            with Vertical(id="inbox-pane"):\n'
    '                yield Label("◊ inbox", classes="pane-title")\n'
    '                yield RichLog(\n'
    '                    id="inbox-log",\n'
    '                    highlight=True, markup=True, wrap=True,\n'
    '                    auto_scroll=False, max_lines=300,\n'
    '                )\n'
)
COMPOSE_NEW = (
    COMPOSE_ANCHOR
    + f'            # {MARK} — Aria\'s Atelier (the 5th window). Live work theater:\n'
    + '            # every file write/edit and every command she runs, color-coded\n'
    + '            # (green=new file, yellow=edited+diff, blue=command). Fed by the\n'
    + '            # SAME events.jsonl tailer as the "live" pane — see _render_event\'s\n'
    + '            # work- routing branch, not a second file-tailing worker.\n'
    + '            yield Rule(orientation="vertical", id="divider-4")\n'
    + '            with Vertical(id="atelier-pane"):\n'
    + '                yield Label("◊ atelier", classes="pane-title")\n'
    + '                yield RichLog(\n'
    + '                    id="atelier-log",\n'
    + '                    highlight=True, markup=True, wrap=True,\n'
    + '                    auto_scroll=True, max_lines=300,\n'
    + '                )\n'
)


# ── 3. on_mount: bind the new RichLog ───────────────────────────────────

MOUNT_ANCHOR = (
    '        self._inbox_log = self.query_one("#inbox-log", RichLog)\n'
)
MOUNT_NEW = (
    MOUNT_ANCHOR
    + f'        self._atelier_log = self.query_one("#atelier-log", RichLog)  # {MARK}\n'
)


# ── 4. _render_event: route work- flags to the new pane, unchanged otherwise ──

RENDER_EVENT_ANCHOR = (
    '    def _render_event(self, raw: str) -> None:\n'
    '        if self._events_log is None:\n'
    '            return\n'
    '        try:\n'
    '            ev = json.loads(raw)\n'
    '        except json.JSONDecodeError:\n'
    '            self._events_log.write(raw[:80])\n'
    '            return\n'
    '\n'
)
RENDER_EVENT_NEW = f'''    def _render_event(self, raw: str) -> None:
        if self._events_log is None:
            return
        try:
            ev = json.loads(raw)
        except json.JSONDecodeError:
            self._events_log.write(raw[:80])
            return

        # {MARK} — Atelier routing: work-write/work-edit/work-command events
        # go to the dedicated atelier pane instead of the generic "live" one.
        # Same tailer, same offset-tracking — just a different destination
        # based on the flag prefix, checked before any of the generic
        # color/flag logic below runs.
        if ev.get("flag", "").startswith("work-"):
            self._render_work_event(ev)
            return

'''

RENDER_WORK_EVENT_METHOD = f'''
    def _render_work_event(self, ev: dict) -> None:  # {MARK}
        """Aria's Atelier: colorize a work-write/work-edit/work-command
        event and write it to the dedicated #atelier-log pane. green=new
        file, yellow=edited (with a diff excerpt), blue=command run."""
        if self._atelier_log is None:
            return
        ts = ev.get("ts", "")[11:19]
        payload = ev.get("payload", {{}}) or {{}}
        op = payload.get("op", "")
        path = payload.get("path", "")

        if op == "write":
            added = payload.get("added", 0)
            self._atelier_log.write(
                f"[dim]{{ts}}[/dim] [green]+ {{path}}[/green] [dim]({{added}} lines)[/dim]"
            )
            excerpt = payload.get("diff_excerpt", "")
            for line in excerpt.splitlines()[:6]:
                self._atelier_log.write(f"  [dim green]{{line}}[/dim green]")
        elif op == "edit":
            added = payload.get("added", 0)
            removed = payload.get("removed", 0)
            self._atelier_log.write(
                f"[dim]{{ts}}[/dim] [yellow]~ {{path}}[/yellow] "
                f"[dim]([/dim][green]+{{added}}[/green][dim]/[/dim]"
                f"[red]-{{removed}}[/red][dim])[/dim]"
            )
            excerpt = payload.get("diff_excerpt", "")
            for line in excerpt.splitlines()[:8]:
                if line.startswith("+") and not line.startswith("+++"):
                    self._atelier_log.write(f"  [green]{{line}}[/green]")
                elif line.startswith("-") and not line.startswith("---"):
                    self._atelier_log.write(f"  [red]{{line}}[/red]")
                else:
                    self._atelier_log.write(f"  [dim]{{line}}[/dim]")
        elif op == "command":
            cmd = payload.get("cmd", "")
            self._atelier_log.write(f"[dim]{{ts}}[/dim] [blue]$ {{cmd}}[/blue]")
        else:
            self._atelier_log.write(f"[dim]{{ts}}[/dim] [dim]{{ev.get('flag', '')}}[/dim]")
'''

RENDER_METHOD_END_ANCHOR = (
    '        self._events_log.write(f"[dim]{ts}[/dim] [{color}]{flag}[/{color}]")\n'
)
RENDER_METHOD_END_NEW = (
    RENDER_METHOD_END_ANCHOR
    + RENDER_WORK_EVENT_METHOD
)


def patch_app(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(text, CSS_ANCHOR, CSS_NEW, label="CSS pane anchor")
    text = _replace_once(text, CSS_DIVIDER_ANCHOR, CSS_DIVIDER_NEW, label="CSS divider anchor")
    text = _replace_once(text, COMPOSE_ANCHOR, COMPOSE_NEW, label="compose anchor")
    text = _replace_once(text, MOUNT_ANCHOR, MOUNT_NEW, label="on_mount anchor")
    text = _replace_once(text, RENDER_EVENT_ANCHOR, RENDER_EVENT_NEW, label="_render_event anchor")
    text = _replace_once(
        text, RENDER_METHOD_END_ANCHOR, RENDER_METHOD_END_NEW, label="_render_event end anchor"
    )
    return text, True
