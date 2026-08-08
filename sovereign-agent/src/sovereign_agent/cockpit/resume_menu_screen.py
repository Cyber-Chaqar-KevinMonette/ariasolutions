"""resume_menu_screen.py — a beautiful menu to resume a paused session.

Kevin's ask: "a resume session menu so users and myself can simply resume
our sessions via a beautiful menu." The resume ENGINE already exists and is
robust (session_bridge.resume_goal_session re-enters run_session at the next
pending subtask, scope contract + queued messages restored by construction);
this is the surface — a modal that lists every resumable session with its
goal, status, and progress, so you pick one with a click instead of typing
a session id.

Mirrors ThemePickerScreen's proven ModalScreen shape (Escape/q/✕ to close,
VerticalScroll body, click-to-act). Read-only listing; the actual resume
goes through the app's existing gated resume path (mode gate, one-session
guard, checkpoints) — nothing here bypasses a safety boundary.
"""
from __future__ import annotations

from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Static

# resume-menu-forget-d — "make the selection list scalable to a safe limit
# but large limit" (Kevin, 2026-07-21). VerticalScroll already handles the
# overflow; this just raises the offered count well past the old default
# of 12 without going unbounded.
_MAX_CANDIDATES = 50


class _HandoffButton(Button):
    """A button that fires an action and hands off (closes this modal),
    not a sustained focus target. Local copy of app.py's MenuTriggerButton
    (can't import it directly -- app.py imports THIS module, so importing
    back from .app would be a circular import). Same fix, same reason:
    without can_focus=False, Textual restores the focus ring here forever
    once the modal closes (feedback_cockpit_button_focus)."""
    can_focus = False


class ResumeSessionButton(_HandoffButton):
    """One resumable session. Carries its session_id for the click handler."""

    def __init__(self, session_id: str, label: str) -> None:
        safe_id = "resume-" + "".join(c if (c.isalnum() or c == "-") else "-" for c in session_id)[-24:]
        super().__init__(label, id=safe_id, classes="resume-choice-btn")
        self.session_id = session_id


class ForgetSessionButton(_HandoffButton):
    """resume-menu-forget-d — a per-row 'forget this session' button so
    Kevin can delete sessions he no longer needs straight from the menu,
    without ever touching the ones he didn't pick."""

    def __init__(self, session_id: str) -> None:
        safe_id = "forget-" + "".join(c if (c.isalnum() or c == "-") else "-" for c in session_id)[-24:]
        super().__init__("✕ forget", id=safe_id, classes="forget-choice-btn")
        self.session_id = session_id


class ResumeMenuScreen(ModalScreen):
    """↺ Resume → pick a paused session to continue. Esc / q / ✕ to close."""

    BINDINGS = [
        Binding("escape", "close", "close", show=False),
        Binding("q", "close", "close", show=False),
    ]

    def action_close(self) -> None:
        self.app.pop_screen()

    def on_key(self, event) -> None:
        if event.key in ("escape",):
            event.stop()
            event.prevent_default()
            self.app.pop_screen()

    def _candidates(self):
        try:
            from sovereign_agent.session_bridge import resumable_sessions
            return resumable_sessions(limit=_MAX_CANDIDATES)
        except Exception:  # noqa: BLE001
            return []

    def compose(self):
        with VerticalScroll(id="resume-modal"):
            yield _HandoffButton("✕ close", id="resume-exit-btn")
            candidates = self._candidates()
            yield Static(
                f"↺ Resume a session  [dim]({len(candidates)} resumable)[/dim]",
                id="resume-title",
            )
            if not candidates:
                yield Static(
                    "[dim]Nothing to resume — every session is complete. "
                    "Say /work <goal> to start a new one.[/dim]",
                    id="resume-empty",
                )
                return
            yield Static(
                "[dim]Click a session to continue exactly that one — I pick "
                "up at the next pending step, same contract, same "
                "checkpoints. ✕ forget removes a session you no longer "
                "need. Esc / q / ✕ to close.[/dim]",
                id="resume-help",
            )
            for s in candidates:
                done = sum(1 for st in s.subtasks if st.status in ("done", "skipped"))
                total = len(s.subtasks)
                goal = (s.goal or "(no goal)")[:60]
                label = f"{goal}\n  {s.status} · {done}/{total} steps · [{s.session_id[-6:]}]"
                row_id = "resume-row-" + "".join(
                    c if (c.isalnum() or c == "-") else "-" for c in s.session_id
                )[-24:]
                with Horizontal(id=row_id, classes="resume-row"):
                    yield ResumeSessionButton(s.session_id, label)
                    yield ForgetSessionButton(s.session_id)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == "resume-exit-btn":
            self.app.pop_screen()
            return
        if isinstance(event.button, ForgetSessionButton):
            # resume-menu-forget-d — deletes exactly the session on THIS
            # row, never the one that's currently running or any other
            # (Kevin, 2026-07-21: "it should resume the session I select").
            sid = event.button.session_id
            try:
                from sovereign_agent.session_bridge import forget_session
                forget_session(sid)
            except Exception:  # noqa: BLE001
                pass
            # Simplest correct refresh: reopen the menu so the list
            # reflects the deletion. Nothing here holds state across a
            # reopen (compose() re-reads candidates from disk each time).
            self.app.pop_screen()
            self.app.action_resume_menu()
            return
        sid = getattr(event.button, "session_id", None)
        if not sid:
            return
        # Close the menu, then hand off to the app's existing GATED resume
        # path (mode gate + one-session guard + checkpoints) — no bypass.
        # ALWAYS the session_id carried by the specific row clicked, never
        # an implicit "most recent" pick (Kevin, 2026-07-21: "it should
        # resume the session I select").
        self.app.pop_screen()
        try:
            self.app._resume_work_session(sid)
        except Exception:  # noqa: BLE001
            pass

    DEFAULT_CSS = """
    ResumeMenuScreen {
        align: center middle;
        background: $surface 60%;
    }
    #resume-modal {
        width: 72;
        height: 80%;
        padding: 1 2;
        border: thick $primary;
        background: $surface;
    }
    #resume-exit-btn { width: 100%; margin-bottom: 1; }
    #resume-title { text-style: bold; margin-bottom: 1; }
    #resume-help { height: 3; color: $text-muted; margin-bottom: 1; }
    #resume-empty { height: 3; color: $text-muted; }
    #resume-modal .resume-row {
        height: 4;
        margin-bottom: 1;
    }
    #resume-modal .resume-choice-btn {
        width: 5fr;
        height: 4;
    }
    #resume-modal .forget-choice-btn {
        width: 2fr;
        height: 4;
    }
    """
