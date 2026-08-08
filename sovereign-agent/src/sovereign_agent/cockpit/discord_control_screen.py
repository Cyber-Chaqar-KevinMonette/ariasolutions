"""cockpit/discord_control_screen.py — control the Discord bot from here.

Kevin, 2026-07-25: "add a way for me to control the bot, turn off the
bot, pause the bot, resume the bot, and restart the discord bot." A
thin, audited UI over `bot_services.py`'s existing systemd-only toggle/
restart (the same no-zombie path `/bots on|off|status` already uses) —
"pause" and "turn off" are honestly the SAME real action (a systemd unit
has no genuine paused state to distinguish them), kept as two clearly
labeled buttons anyway since that's the mental model Kevin asked for;
"resume" and "restart" are the two real distinct actions (start vs. a
fresh process).

movie-focus-d (Kevin, 2026-07-28): "add a button and command for me to
restart it [aria-duty] ... put inside the bots menu, or discord menu, or
merge them into one menu." This IS already that one menu — pause/resume/
restart already act on both bot services together, so the merge is
adding a fifth, narrower button here rather than a whole new screen.
Directly motivated by a real, live-confirmed incident: aria-duty's
Playwright scraper leaked from ~5GB to ~10GB RSS over a few hours,
starving the movie-generation pipeline of the RAM it needs. "Restart
duty" targets ONLY aria-duty.service, reclaiming that RAM without
dropping aria-bot's live Discord gateway connection.
"""
from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static

MARK = "discord-control-d"


class DiscordControlScreen(ModalScreen):
    """❖ turn off / pause / resume / restart the Discord bot services."""

    BINDINGS = [Binding("escape,q", "close_discord_control", "close")]

    CSS = """
    DiscordControlScreen { align: center middle; }
    #discord-control-modal {
        width: 64; max-height: 80%;
        background: $surface; border: round $primary;
        padding: 1 2;
        /* scrollbar-d (Kevin, 2026-07-26): same defensive fix as the
           other cockpit modals — a short terminal must never be able to
           clip a button off with no way to reach it. */
        overflow-y: auto;
    }
    #discord-control-title { text-style: bold; margin-bottom: 1; }
    #discord-control-help { color: $text-muted; margin-bottom: 1; }
    DiscordControlScreen Button { width: 100%; margin-bottom: 1; }
    #discord-control-status { color: $text-muted; margin-top: 1; }
    """

    def action_close_discord_control(self) -> None:
        self.app.pop_screen()

    def on_key(self, event) -> None:
        if event.key == "escape":
            event.stop()
            event.prevent_default()
            self.app.pop_screen()

    def compose(self) -> ComposeResult:
        with Vertical(id="discord-control-modal"):
            yield Static("[b]❖ Discord Bot Control[/b]", id="discord-control-title")
            yield Static(
                "[dim]Turn off / pause = stop both services (systemd). "
                "Resume = start. Restart = a fresh process, picks up new "
                "code. Restart duty = aria-duty only (the scraper), for "
                "when its Playwright browser has leaked RAM — leaves "
                "aria-bot's Discord connection untouched.[/dim]",
                id="discord-control-help",
            )
            yield Button("▪ turn off", id="discord-off-btn", variant="error")
            yield Button("▪ pause", id="discord-pause-btn", variant="warning")
            yield Button("▸ resume", id="discord-resume-btn", variant="success")
            yield Button("↻ restart", id="discord-restart-btn", variant="primary")
            yield Button("↻ restart duty (scraper)", id="discord-restart-duty-btn")
            yield Static("", id="discord-control-status")

    def on_mount(self) -> None:
        self._refresh_status()

    def _refresh_status(self) -> None:
        try:
            from sovereign_agent import bot_services
            status = self.query_one("#discord-control-status", Static)
            status.update(bot_services.render_states())
        except Exception as exc:  # noqa: BLE001
            try:
                self.query_one("#discord-control-status", Static).update(
                    f"[dim]status unavailable: {type(exc).__name__}[/dim]")
            except Exception:  # noqa: BLE001
                pass

    def on_button_pressed(self, event) -> None:
        bid = getattr(event.button, "id", "") or ""
        action = {
            "discord-off-btn": "off",
            "discord-pause-btn": "pause",
            "discord-resume-btn": "resume",
            "discord-restart-btn": "restart",
            "discord-restart-duty-btn": "restart-duty",
        }.get(bid)
        if action is None:
            return
        self._run_action(action)

    def _run_action(self, action: str) -> None:
        status = self.query_one("#discord-control-status", Static)
        status.update("[dim]working…[/dim]")

        async def _go() -> None:
            import asyncio
            try:
                from sovereign_agent import bot_services
                if action == "restart":
                    out = await asyncio.to_thread(bot_services.restart)
                elif action == "restart-duty":
                    out = await asyncio.to_thread(bot_services.restart_duty)
                elif action == "resume":
                    out = await asyncio.to_thread(bot_services.toggle, True)
                else:  # "off" and "pause" are the same real action
                    out = await asyncio.to_thread(bot_services.toggle, False)
            except Exception as exc:  # noqa: BLE001
                out = f"action failed: {type(exc).__name__}"
            try:
                self.query_one("#discord-control-status", Static).update(out)
            except Exception:  # noqa: BLE001
                pass

        self.app.run_worker(_go(), exclusive=False)


__all__ = ["DiscordControlScreen"]
