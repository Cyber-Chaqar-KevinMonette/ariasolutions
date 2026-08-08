"""apply_queue_screen.py — Ctrl+Shift+A cockpit modal: SELECT modules to apply.

This is the cockpit-driven half of aria-apply-queue. You can't apply while the
cockpit runs (that would mutate live ``src/`` beneath it), so here you only
*select*: a multi-select list of every pending staged module. "Queue selected"
writes the durable, dependency-sequenced queue (``ApplyQueueStore``). Then close
the cockpit and run ``./scripts/apply_queue_run.sh`` to drain it safely — each
module through ``safe_apply.sh`` (guarded + auto-rollback), successes leaving the
queue, rollbacks routed to quarantine.

Read-only against the running system: it writes the queue file only, never src/.
"""
from __future__ import annotations

from pathlib import Path

from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, RichLog, SelectionList, Static
from textual.widgets.selection_list import Selection

from sovereign_agent.staged_status import pending_modules as _pending_modules


class ApplyQueueScreen(ModalScreen):
    """Ctrl+Shift+A → multi-select staged modules → write the durable apply queue."""

    BINDINGS = [
        Binding("escape", "close", "close", show=False),
        Binding("q", "close", "close", show=False),
    ]

    def __init__(self, repo_root: Path) -> None:
        super().__init__()
        self._repo_root = Path(repo_root)

    def action_close(self) -> None:
        self.app.pop_screen()

    def on_key(self, event) -> None:
        if event.key in ("escape",):
            event.stop()
            event.prevent_default()
            self.app.pop_screen()

    def compose(self):
        pending = _pending_modules(self._repo_root)
        with Vertical(id="aq-modal"):
            yield Static(
                f"Apply Queue — select modules to apply  "
                f"[dim]({len(pending)} pending)[/dim]",
                id="aq-title",
            )
            yield Static(
                "[dim]Space toggles · Enter on a row toggles · then “Queue selected”. "
                "Close the cockpit and run ./scripts/apply_queue_run.sh to apply.[/dim]",
                id="aq-help",
            )
            if pending:
                yield SelectionList(
                    *[Selection(name, name) for name in pending],
                    id="aq-list",
                )
            else:
                yield Static("[green]No pending modules — queue is clear. 💛[/green]")
            yield RichLog(id="aq-log", markup=True, max_lines=200)
            with Horizontal(id="aq-footer"):
                yield Button("Queue selected", id="aq-queue", variant="success")
                yield Button("Queue & Quit", id="aq-queue-quit", variant="success")  # apply-queue-quit-btn-d
                yield Button("Clear queue", id="aq-clear", variant="warning")
                yield Button("Close (Esc)", id="aq-close", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        bid = event.button.id or ""
        log = self.query_one("#aq-log", RichLog)
        if bid == "aq-close":
            self.app.pop_screen()
        elif bid == "aq-queue":
            self._queue_selected(log)
        elif bid == "aq-queue-quit":  # apply-queue-quit-btn-d
            if self._queue_selected(log):
                log.write("[cyan bold]Closing the cockpit — the apply queue will drain "
                          "right here in this terminal.[/cyan bold]")
                self.app._run_queue_on_exit = True  # noqa: SLF001 — same-module cockpit handoff flag
                self.app.exit()
        elif bid == "aq-clear":
            self._clear_queue(log)

    # ── queue actions (write the durable file only) ─────────────────────────

    def _store(self):
        # imported lazily so the cockpit still loads if the package isn't applied
        from sovereign_agent.apply_queue.store import ApplyQueueStore
        return ApplyQueueStore()

    def _queue_selected(self, log: RichLog) -> bool:
        """Write the selection to the durable queue. Returns True iff something
        was actually queued (so the Quit button can refuse to close the cockpit
        over an empty/failed enqueue — quitting with nothing queued would just
        strand Kevin with a closed cockpit and no work scheduled)."""
        try:
            sel = self.query_one("#aq-list", SelectionList).selected
        except Exception:  # noqa: BLE001
            sel = []
        if not sel:
            log.write("[yellow]Nothing selected — pick at least one module.[/yellow]")
            return False
        try:
            store = self._store()
            store.enqueue(list(sel))
            active = store.active()
            log.write(f"[green]✓ queued {len(sel)} module(s).[/green] "
                      f"Active queue ({len(active)}):")
            for it in active:
                log.write(f"  [{it.seq:>2}] {it.slug}")
            log.write("[cyan]Now close the cockpit and run "
                      "./scripts/apply_queue_run.sh[/cyan]")
            return True
        except Exception as exc:  # noqa: BLE001
            log.write(f"[red]could not write queue: {exc!r}[/red]")
            return False

    def _clear_queue(self, log: RichLog) -> None:
        try:
            self._store().clear()
            log.write("[yellow]queue cleared (log archived).[/yellow]")
        except Exception as exc:  # noqa: BLE001
            log.write(f"[red]could not clear queue: {exc!r}[/red]")

    DEFAULT_CSS = """
    ApplyQueueScreen {
        align: center middle;
        background: $surface 60%;
    }
    #aq-modal {
        width: 96;
        height: 88%;
        padding: 1 2;
        border: thick $primary;
        background: $surface;
    }
    #aq-title { text-style: bold; margin-bottom: 1; }
    #aq-help { height: 2; color: $text-muted; }
    #aq-list {
        height: 1fr;
        border: round $surface-lighten-2;
        margin-top: 1;
    }
    #aq-log {
        height: 10;
        border: round $surface-lighten-2;
        padding: 0 1;
        margin-top: 1;
    }
    #aq-footer { height: 3; margin-top: 1; dock: bottom; }
    #aq-queue { width: 2fr; margin-right: 1; }
    #aq-queue-quit { width: 2fr; margin-right: 1; }
    #aq-clear { width: 1fr; margin-right: 1; }
    #aq-close { width: 1fr; }
    """
