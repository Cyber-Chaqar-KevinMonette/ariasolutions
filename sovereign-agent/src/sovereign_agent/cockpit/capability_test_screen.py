"""capability_test_screen.py — ⚡ the capability test menu modal.

capability-test-menu-d (Kevin, 2026-07-28): "make a test button... So I can
see all the available tests I can run with her... a one shot run all button
that queues them all. And I can see the queue metrics live and watch her work
live." A quick-test button beside every real capability she has, a "Test All"
button that queues the whole ready set, and a live log + metrics readout
while it runs — rendered straight from workflow/catalog.py's
capability_testable_workflows() so this menu can never drift from what's
actually wired in workflow/capability_tests.py. Mirrors
apply_queue_screen.py's list+buttons+log shape.

Read-only against the running system by itself: pressing a button just asks
the app (CockpitApp) to start its own background worker
(_captest_start/_captest_request_stop) — this screen only renders state and
dispatches button presses.
"""
from __future__ import annotations

from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import Button, RichLog, Static

# Textual widget ids may not contain "." (BadIdentifier), but every workflow
# wid does (e.g. "create.image") — encode/decode losslessly through the one
# dot every wid has, rather than inventing a second id scheme to keep in sync.
_WID_SEP = "__"


def _wid_to_id(wid: str) -> str:
    return f"captest-run-{wid.replace('.', _WID_SEP)}"


def _id_to_wid(button_id: str) -> str:
    return button_id[len("captest-run-"):].replace(_WID_SEP, ".", 1)


class CapabilityTestScreen(ModalScreen):
    BINDINGS = [Binding("escape,q", "close", "close", show=False)]

    queued: reactive[int] = reactive(0)
    running_count: reactive[int] = reactive(0)
    passed: reactive[int] = reactive(0)
    failed: reactive[int] = reactive(0)
    skipped: reactive[int] = reactive(0)
    elapsed: reactive[float] = reactive(0.0)

    def action_close(self) -> None:
        self.app.pop_screen()

    def on_key(self, event) -> None:
        if event.key in ("escape", "q"):
            event.stop()
            event.prevent_default()
            self.app.pop_screen()

    def compose(self):
        from ..workflow import catalog as _catalog

        ready = _catalog.capability_testable_workflows()
        gated = [w for w in _catalog.gated_workflows() if w.category == "Generate & Create"]
        by_cat: dict[str, list] = {}
        for w in ready + gated:
            by_cat.setdefault(w.category, []).append(w)

        with Vertical(id="captest-modal"):
            yield Static(
                f"⚡ Capability Test Menu — {len(ready)} ready to test live "
                f"[dim]({len(gated)} gated)[/dim]",
                id="captest-title")
            yield Static(self._metrics_text(), id="captest-metrics")
            with VerticalScroll(id="captest-list"):
                for category, items in by_cat.items():
                    yield Static(f"[b]── {category} ──[/b]", classes="captest-cat")
                    for w in items:
                        if w.status == "ready":
                            with Horizontal(classes="captest-row"):
                                yield Button("▶ Test", id=_wid_to_id(w.wid),
                                            variant="success", classes="captest-btn")
                                yield Static(
                                    f"[b]{w.title}[/b]\n[dim]{w.summary}[/dim]\n"
                                    f"[dim]{w.safety}[/dim]",
                                    classes="captest-desc")
                        else:
                            yield Static(
                                f"[dim]· {w.title} — gated: {w.needs}[/dim]",
                                classes="captest-gated")
            yield RichLog(id="captest-log", markup=True, max_lines=500)
            with Horizontal(id="captest-footer"):
                yield Button("⚡ Test All", id="captest-run-all", variant="success")
                yield Button("■ Stop", id="captest-stop", variant="warning")
                yield Button("✕ Close (Esc)", id="captest-close", variant="primary")

    def _metrics_text(self) -> str:
        return (f"queued [b]{self.queued}[/b] · running [b]{self.running_count}[/b] · "
               f"passed [green]{self.passed}[/green] · failed [red]{self.failed}[/red] · "
               f"skipped [dim]{self.skipped}[/dim] · {self.elapsed:.0f}s elapsed")

    def _refresh_metrics(self) -> None:
        try:
            self.query_one("#captest-metrics", Static).update(self._metrics_text())
        except Exception:  # noqa: BLE001 — widget may not be mounted yet
            pass

    def watch_queued(self, _value: int) -> None:
        self._refresh_metrics()

    def watch_running_count(self, _value: int) -> None:
        self._refresh_metrics()

    def watch_passed(self, _value: int) -> None:
        self._refresh_metrics()

    def watch_failed(self, _value: int) -> None:
        self._refresh_metrics()

    def watch_skipped(self, _value: int) -> None:
        self._refresh_metrics()

    def watch_elapsed(self, _value: float) -> None:
        self._refresh_metrics()

    def log_line(self, text: str) -> None:
        try:
            self.query_one("#captest-log", RichLog).write(text)
        except Exception:  # noqa: BLE001 — a UI hiccup must never crash a real run
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        bid = event.button.id or ""
        app = self.app
        if bid == "captest-close":
            app.pop_screen()
        elif bid == "captest-run-all":
            if hasattr(app, "_captest_start"):
                app._captest_start(None)   # None = every ready test
        elif bid == "captest-stop":
            if hasattr(app, "_captest_request_stop"):
                app._captest_request_stop()
        elif bid.startswith("captest-run-"):
            wid = _id_to_wid(bid)
            if hasattr(app, "_captest_start"):
                app._captest_start([wid])

    DEFAULT_CSS = """
    CapabilityTestScreen {
        align: center middle;
        background: $surface 60%;
    }
    #captest-modal {
        width: 100;
        height: 90%;
        padding: 1 2;
        border: thick $primary;
        background: $surface;
    }
    #captest-title { text-style: bold; margin-bottom: 1; }
    #captest-metrics { height: 1; color: $text-muted; margin-bottom: 1; }
    #captest-list {
        height: 1fr;
        border: round $surface-lighten-2;
        margin-bottom: 1;
    }
    .captest-cat { text-style: bold; margin-top: 1; }
    .captest-row { height: auto; margin-bottom: 1; }
    .captest-btn { width: 12; margin-right: 1; }
    .captest-desc { width: 1fr; }
    .captest-gated { color: $text-muted; margin-left: 14; }
    #captest-log {
        height: 12;
        border: round $surface-lighten-2;
        padding: 0 1;
        margin-bottom: 1;
    }
    #captest-footer { height: 3; }
    #captest-run-all { width: 2fr; margin-right: 1; }
    #captest-stop { width: 1fr; margin-right: 1; }
    #captest-close { width: 1fr; }
    """


__all__ = ["CapabilityTestScreen"]
