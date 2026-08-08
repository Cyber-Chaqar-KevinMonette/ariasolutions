"""bot_studio_screen.py — the Bot Project Studio: define bot projects.

Kevin's ask: a studio where he names the project, names the bot, selects the
kind (from a list + Other), and writes a description of the concept — plus
browse / edit / remove existing projects. Same clean shape as the Theme
Studio. This defines the DIRECTION; the bot runtime is a later build.
"""
from __future__ import annotations

from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select, Static

from sovereign_agent.bot_projects import BOT_KINDS, BotProject, save, validate


def cycle_index(idx: int, n: int, delta: int) -> int:
    if n <= 0:
        return 0
    return (idx + delta) % n


class BotStudioScreen(ModalScreen):
    """🤖 Bot Studio — define a bot project, browse/edit/remove. Esc to close."""

    BINDINGS = [
        Binding("escape", "close", "close", show=False),
    ]

    def __init__(self, edit: BotProject | None = None) -> None:
        super().__init__()
        self._projects: list[BotProject] = []
        self._pi = 0
        self._edit = edit

    def action_close(self) -> None:
        self.app.pop_screen()

    def on_key(self, event) -> None:
        if event.key == "escape":
            event.stop(); event.prevent_default(); self.app.pop_screen()

    def _load_projects(self) -> None:
        try:
            from sovereign_agent.bot_projects import list_all
            from sovereign_agent.config import SETTINGS
            self._projects = list_all(SETTINGS.paths.data_dir)
        except Exception:  # noqa: BLE001
            self._projects = []

    def compose(self):
        self._load_projects()
        e = self._edit
        with VerticalScroll(id="bot-modal"):
            with Horizontal(id="bot-top"):
                yield Button("✕ close", id="bot-exit-btn")
                yield Button("save project", id="bot-save-btn", variant="success")
            yield Static("Bot Studio — define a project", id="bot-title")
            yield Static("[dim]Name it, pick a kind, write the concept so you and "
                         "Aria know where you're heading. Save. Esc to close.[/dim]",
                         id="bot-help")

            yield Label("Project name")
            yield Input(value=(e.project_name if e else ""), id="bot-project-name",
                        placeholder="e.g. pokemon-restock-alerts")
            yield Label("Bot name")
            yield Input(value=(e.bot_name if e else ""), id="bot-bot-name",
                        placeholder="e.g. StockScout")
            yield Label("Kind")
            yield Select([(label, key) for key, label in BOT_KINDS],
                         value=(e.kind if e else "restock-alert"),
                         id="bot-kind", allow_blank=False)
            yield Label("If 'Other', name the kind")
            yield Input(value=(e.kind_other if e else ""), id="bot-kind-other",
                        placeholder="only if kind = Other")
            yield Label("Concept / direction — what is this bot for?")
            yield Input(value=(e.description if e else ""), id="bot-description",
                        placeholder="the idea, the goal, who it helps")
            yield Label("Audience (optional)")
            yield Input(value=(e.audience if e else ""), id="bot-audience")
            yield Label("Monetization idea (optional)")
            yield Input(value=(e.monetization if e else ""), id="bot-monetization")
            yield Label("Sources to monitor (optional)")
            yield Input(value=(e.sources if e else ""), id="bot-sources")
            yield Label("Notes (optional)")
            yield Input(value=(e.notes if e else ""), id="bot-notes")

            # ── browse existing projects ──
            yield Static("[dim]— your bot projects —[/dim]", id="bot-browse-sep")
            with Horizontal(classes="bot-carousel"):
                yield Button("◂", id="bot-prev")
                yield Static("", id="bot-project-label", classes="bot-carousel-label")
                yield Button("▸", id="bot-next")
            with Horizontal(id="bot-actions"):
                yield Button("edit", id="bot-edit")
                yield Button("▸ dry-run", id="bot-dryrun")
                yield Button("remove", id="bot-remove", variant="error")

    def on_mount(self) -> None:
        self._refresh_browse()

    def _refresh_browse(self) -> None:
        try:
            lbl = self.query_one("#bot-project-label", Static)
            if self._projects:
                p = self._projects[self._pi]
                lbl.update(f"[b]{p.project_name}[/b] — {p.kind_label} · {p.status}  "
                           f"[dim]({self._pi + 1}/{len(self._projects)})[/dim]")
            else:
                lbl.update("[dim](no projects yet — fill the form above and save)[/dim]")
        except Exception:  # noqa: BLE001
            pass

    def _collect(self) -> BotProject:
        def v(wid: str) -> str:
            try:
                return self.query_one(f"#{wid}", Input).value.strip()
            except Exception:  # noqa: BLE001
                return ""
        kind = "restock-alert"
        try:
            kind = str(self.query_one("#bot-kind", Select).value or "restock-alert")
        except Exception:  # noqa: BLE001
            pass
        return BotProject(
            project_name=v("bot-project-name"), bot_name=v("bot-bot-name"),
            kind=kind, kind_other=v("bot-kind-other"),
            description=v("bot-description"), audience=v("bot-audience"),
            monetization=v("bot-monetization"), sources=v("bot-sources"),
            notes=v("bot-notes"),
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "bot-exit-btn":
            self.app.pop_screen(); return
        if bid == "bot-save-btn":
            self._save(); return
        if bid == "bot-prev" and self._projects:
            self._pi = cycle_index(self._pi, len(self._projects), -1); self._refresh_browse()
        elif bid == "bot-next" and self._projects:
            self._pi = cycle_index(self._pi, len(self._projects), +1); self._refresh_browse()
        elif bid == "bot-edit" and self._projects:
            self.app.pop_screen()
            self.app.push_screen(BotStudioScreen(edit=self._projects[self._pi]))
        elif bid == "bot-dryrun" and self._projects:
            self._dry_run_current()
        elif bid == "bot-remove" and self._projects:
            self._remove_current()

    def _save(self) -> None:
        from sovereign_agent.bot_projects import save as _save
        from sovereign_agent.config import SETTINGS
        proj = self._collect()
        errs = validate(proj)
        if errs:
            self._toast(f"can't save: {errs[0]}"); return
        try:
            _save(proj, SETTINGS.paths.data_dir)
        except Exception as exc:  # noqa: BLE001
            self._toast(f"save failed: {type(exc).__name__}"); return
        self._toast(f"saved '{proj.project_name}' 💛")
        self._load_projects(); self._refresh_browse()

    def _remove_current(self) -> None:
        from sovereign_agent.bot_projects import delete
        from sovereign_agent.config import SETTINGS
        name = self._projects[self._pi].project_name
        try:
            delete(name, SETTINGS.paths.data_dir)
        except Exception:  # noqa: BLE001
            pass
        self._load_projects()
        self._pi = min(self._pi, max(0, len(self._projects) - 1))
        self._refresh_browse()
        self._toast(f"removed '{name}'")

    def _dry_run_current(self) -> None:
        """Run ONE safe dry-run cycle for the browsed project — sends nothing."""
        from sovereign_agent.config import SETTINGS
        proj = self._projects[self._pi]
        try:
            from sovereign_agent.discord_runtime.runtime import build_runtime
            rt = build_runtime(proj, SETTINGS.paths.data_dir, live=False)
            if not rt.sources:
                self._toast(f"'{proj.project_name}': no sources yet — "
                            "add one via `sov bots add-source`.")
                return
            rep = rt.poll_once()
            self._toast(f"dry-run · {rep.summary()} (nothing sent)")
        except Exception as exc:  # noqa: BLE001
            self._toast(f"dry-run failed: {type(exc).__name__}: {exc}")

    def _toast(self, msg: str) -> None:
        try:
            self.query_one("#bot-help", Static).update(f"[dim]{msg}[/dim]")
        except Exception:  # noqa: BLE001
            pass

    DEFAULT_CSS = """
    BotStudioScreen { align: center middle; background: $surface 60%; }
    #bot-modal {
        width: 72; height: 90%; padding: 1 2;
        border: thick $primary; background: $surface;
    }
    #bot-top { height: 3; margin-bottom: 1; }
    #bot-exit-btn { width: 1fr; margin-right: 1; }
    #bot-save-btn { width: 1fr; }
    #bot-title { text-style: bold; margin-bottom: 1; }
    #bot-help { height: 3; color: $text-muted; margin-bottom: 1; }
    BotStudioScreen Input, BotStudioScreen Select { width: 100%; margin-bottom: 1; }
    BotStudioScreen Label { color: $text-muted; }
    #bot-browse-sep { margin-top: 1; }
    .bot-carousel { height: 3; margin-bottom: 1; }
    .bot-carousel Button { width: 6; }
    .bot-carousel-label { width: 1fr; content-align: center middle; }
    #bot-actions { height: 3; }
    #bot-actions Button { width: 1fr; margin-right: 1; }
    """
