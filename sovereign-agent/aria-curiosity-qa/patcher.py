"""patcher.py — Keys round K6: aria-curiosity-qa.

Three anchored, idempotent patches to cockpit/app.py:
  1. `/wonder [topic]` slash verb — the explicit invitation, any mode.
  2. `_run_wonder_worker` (async @work) + `_maybe_autonomous_wonder` —
     idle wondering, gated HARD: work mode only
     (autonomous_wonder_allowed → autonomous_loops_allowed), max 3/day,
     kill switch SOV_NO_WONDER, and never while she's busy.
  3. A 30-min idle timer (timer-only, never on mount — the standing
     discipline; short-lived test boots must never wonder).

curiosity.py itself is a NEW file (payload/), copied whole. The qa-start-d
/ qa-d events it emits already render richly — K1 shipped their renderers
ahead of this module.
"""
from __future__ import annotations

MARK = "curiosity-qa-d"


class PatchError(Exception):
    pass


def _replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if text.count(old) != 1:
        raise PatchError(f"{label}: expected exactly 1 occurrence, found {text.count(old)}")
    return text.replace(old, new, 1)


VERB_ANCHOR = (
    '        elif verb == "work":  # session-bridge-d\n'
    "            self._start_work_session(arg)\n"
)
VERB_NEW = (
    f'        elif verb == "wonder":  # {MARK}\n'
    "            self._write_meta(\n"
    '                "[magenta]? wondering…[/magenta] [dim](watch the live pane)[/dim]"\n'
    "            )\n"
    "            self._run_wonder_worker(arg)\n"
    '        elif verb == "work":  # session-bridge-d\n'
    "            self._start_work_session(arg)\n"
)

TIMER_ANCHOR = (
    "        self._apply_saved_layout()  # flexi-layout-d\n"
)
TIMER_NEW = (
    TIMER_ANCHOR
    + f"        self.set_interval(1800.0, self._maybe_autonomous_wonder)  # {MARK}\n"
)

_METHODS_BODY = '''    @work(exclusive=True, group="wonder")  # MARKER
    async def _run_wonder_worker(self, topic: str) -> None:
        """One bounded wondering — explicit (/wonder) or idle-autonomous.
        Renders the Q&A into chat; the qa-* events light the live pane."""
        try:
            from sovereign_agent.curiosity import wonder

            rec = await wonder(topic or "")
            if rec is None:
                self._write_meta("[dim]? wondering yielded nothing this time[/dim]")
                return
            self._write_meta(f"[magenta]? {rec.question}[/magenta]")
            self._write_aria(rec.answer)
            self._write_meta(
                f"[dim]confidence {rec.confidence:.2f}"
                + (f" · next: {rec.next_check[:60]}" if rec.next_check else "")
                + "[/dim]"
            )
        except Exception as exc:  # noqa: BLE001 — wondering never breaks anything
            self._write_meta(f"[dim]? wonder error: {exc!r}[/dim]")

    def _maybe_autonomous_wonder(self) -> None:  # MARKER
        """Idle wondering — the 30-min timer's target. Gated hard: never
        while busy, work mode only, max/day budget, kill switch. Explicit
        /wonder never comes through here."""
        try:
            from sovereign_agent.curiosity import autonomous_wonder_allowed

            if self._busy or getattr(self, "_session_running", False):
                return
            if not autonomous_wonder_allowed():
                return
        except Exception:  # noqa: BLE001
            return
        self._run_wonder_worker("")

    def _refresh_cockpit_strips(self) -> None:  # command-menu-d
'''

METHODS_ANCHOR = (
    "    def _refresh_cockpit_strips(self) -> None:  # command-menu-d\n"
)
METHODS_NEW = _METHODS_BODY.replace("MARKER", MARK)


def patch_app(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(text, VERB_ANCHOR, VERB_NEW, label="app verb anchor")
    text = _replace_once(text, TIMER_ANCHOR, TIMER_NEW, label="app timer anchor")
    text = _replace_once(text, METHODS_ANCHOR, METHODS_NEW, label="app methods anchor")
    return text, True
