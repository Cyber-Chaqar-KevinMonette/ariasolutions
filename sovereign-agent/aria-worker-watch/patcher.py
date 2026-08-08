"""patcher.py — Fable round F5: aria-worker-watch.

Verified gap: the four persistent cockpit loops (heart/breathe/status/
events) self-heal per-pass, but a TERMINAL exit stays dead silently —
the pane freezes and nothing tells Kevin. Textual delivers
Worker.StateChanged to the creating node (the App), and app.py never
defined the handler.

Three anchored, idempotent patches to cockpit/app.py:
  1. Module state: respawn counters + the dead-worker latch set.
  2. `on_worker_state_changed`: a persistent-group worker reaching ERROR
     (or SUCCESS — these loops are `while True`, finishing IS a failure)
     gets ONE bounded respawn (max 2 per group per session), a chat meta
     line, and past the bound a permanent red latch. Supervision, not a
     crash loop.
  3. The status bar renders the latch: `⛔ <groups>` in red.
"""
from __future__ import annotations

MARK = "worker-watch-d"


class PatchError(Exception):
    pass


def _replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if text.count(old) != 1:
        raise PatchError(f"{label}: expected exactly 1 occurrence, found {text.count(old)}")
    return text.replace(old, new, 1)


STATE_ANCHOR = (
    "_AUTO_BACKUP_LOCK = threading.Lock()  # auto-backup-d\n"
    "_AUTO_BACKUP_RUNNING = False  # auto-backup-d\n"
)
STATE_NEW = (
    STATE_ANCHOR
    + f"# {MARK} — supervision state for the persistent cockpit loops.\n"
    "_WATCHED_WORKER_GROUPS = frozenset({\"heart\", \"breathe\", \"status\", \"events\"})\n"
    "_WORKER_RESPAWNS: dict[str, int] = {}\n"
    "_DEAD_WORKERS: set[str] = set()\n"
    "_MAX_WORKER_RESPAWNS = 2\n"
)

_HANDLER_BODY = '''    def on_worker_state_changed(self, event) -> None:  # MARKER
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
                self._write_meta(
                    f"[red]⛔ worker '{group}' died repeatedly — latched dead "
                    f"(restart the cockpit to recover; check events.jsonl)[/red]"
                )
                self._render_status_bar()
        except Exception:  # noqa: BLE001 — supervision must never hurt the app
            pass

    def _refresh_cockpit_strips(self) -> None:  # command-menu-d
'''

HANDLER_ANCHOR = (
    "    def _refresh_cockpit_strips(self) -> None:  # command-menu-d\n"
)
HANDLER_NEW = _HANDLER_BODY.replace("MARKER", MARK)

BAR_ANCHOR = (
    "        obs_parts: list[str] = []\n"
)
BAR_NEW = (
    "        obs_parts: list[str] = []\n"
    f"        if _DEAD_WORKERS:  # {MARK}\n"
    "            obs_parts.append(\n"
    '                f"[red]⛔ {\',\'.join(sorted(_DEAD_WORKERS))}[/red]"\n'
    "            )\n"
)


def patch_app(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    if "def on_worker_state_changed" in text:
        raise PatchError("app.py already defines on_worker_state_changed — would shadow")
    text = _replace_once(text, STATE_ANCHOR, STATE_NEW, label="state anchor")
    text = _replace_once(text, HANDLER_ANCHOR, HANDLER_NEW, label="handler anchor")
    text = _replace_once(text, BAR_ANCHOR, BAR_NEW, label="status-bar anchor")
    return text, True
