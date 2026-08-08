"""cockpit/modes_crown_ui.py — the modes popup + the observatory window.
(FABLE II · M6 · modes-crown-d)

Two ModalScreens in the proven CommandPaletteScreen shape:

  ModesScreen        — F2 / `/modes`: every mode profile as a button;
                       auto-3h reveals a typed-confirmation input (the
                       Tier-3 spirit: deliberate, unambiguous).
  ObservatoryScreen  — F3 / `/observatory`: the watching window — mode +
                       lease countdown, stance trail, emotion surface,
                       mechanical load. Refreshes once a second; Esc
                       closes. Watching, never steering.
"""
from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Static

MARK = "modes-crown-d"


class ModesScreen(ModalScreen):
    """The mode picker: one button per profile; typed confirmation where a
    profile demands it; every change evented by set_crown_mode itself."""

    BINDINGS = [Binding("escape,q", "close_modes", "close")]

    CSS = """
    ModesScreen { align: center middle; }
    #modes-modal {
        width: 78; max-height: 80%;
        background: $surface; border: round $primary;
        padding: 1 2;
    }
    #modes-scroll { max-height: 24; }
    ModesScreen Button { width: 100%; margin-bottom: 0; }
    #modes-status { color: $warning; }
    #modes-confirm { display: none; }
    #modes-confirm.armed { display: block; }
    """

    def __init__(self) -> None:
        super().__init__()
        self._pending_mode: str = ""

    def action_close_modes(self) -> None:
        self.app.pop_screen()

    def on_key(self, event) -> None:
        if event.key in ("escape",):
            event.stop()
            event.prevent_default()
            self.app.pop_screen()

    def compose(self) -> ComposeResult:
        from sovereign_agent.modes_crown.profiles import PROFILES, current_profile

        active = current_profile().mode_id
        with Vertical(id="modes-modal"):
            yield Static(
                "[b]◈ Modes[/b]  [dim]the crown — pick how she works[/dim]",
                id="modes-title")
            with VerticalScroll(id="modes-scroll"):
                for profile in PROFILES.values():
                    marker = "●" if profile.mode_id == active else "○"
                    lease = (f" · lease {profile.lease_seconds // 3600}h"
                             if profile.lease_seconds else "")
                    yield Button(
                        f"{marker} {profile.title}{lease} — {profile.description}",
                        id=f"mode-{profile.mode_id}")
            yield Input(
                placeholder="type the confirmation phrase to arm, then Enter",
                id="modes-confirm")
            yield Static("", id="modes-status")

    def _set_mode(self, mode_id: str, confirm: str = "") -> None:
        from sovereign_agent.modes_crown.profiles import CrownError, set_crown_mode

        status = self.query_one("#modes-status", Static)
        try:
            profile = set_crown_mode(mode_id, confirm=confirm)
        except CrownError as exc:
            status.update(f"[yellow]{exc}[/yellow]")
            return
        try:
            self.app._write_meta(  # noqa: SLF001 — the cockpit's own meta line
                f"[bold magenta]◈ mode → {profile.mode_id}[/bold magenta] "
                f"[dim]{profile.description}[/dim]")
        except Exception:  # noqa: BLE001
            pass
        self.app.pop_screen()

    def on_button_pressed(self, event) -> None:
        event.stop()
        button_id = getattr(event.button, "id", "") or ""
        if not button_id.startswith("mode-"):
            self.app.pop_screen()
            return
        mode_id = button_id[len("mode-"):]
        from sovereign_agent.modes_crown.profiles import PROFILES

        profile = PROFILES.get(mode_id)
        if profile is None:
            return
        if profile.typed_confirmation:
            self._pending_mode = mode_id
            confirm = self.query_one("#modes-confirm", Input)
            confirm.add_class("armed")
            confirm.focus()
            self.query_one("#modes-status", Static).update(
                f"[yellow]{profile.title} arms only with the phrase: "
                f"[b]{profile.typed_confirmation}[/b][/yellow]")
            return
        self._set_mode(mode_id)

    def on_input_submitted(self, event) -> None:
        event.stop()
        if self._pending_mode:
            self._set_mode(self._pending_mode, confirm=event.value)


class ObservatoryScreen(ModalScreen):
    """The watching window: refreshed once a second, closes on Esc."""

    BINDINGS = [Binding("escape,q", "close_observatory", "close")]

    CSS = """
    ObservatoryScreen { align: center middle; }
    #observatory-modal {
        width: 84; max-height: 80%;
        background: $surface; border: round $accent;
        padding: 1 2;
    }
    """

    def action_close_observatory(self) -> None:
        self.app.pop_screen()

    def on_key(self, event) -> None:
        if event.key in ("escape", "q"):
            event.stop()
            event.prevent_default()
            self.app.pop_screen()

    def compose(self) -> ComposeResult:
        with Vertical(id="observatory-modal"):
            yield Static(
                "[b]🔭 Observatory[/b]  [dim]her modes, stance, emotion, "
                "load — watching, never steering[/dim]",
                id="observatory-title")
            yield Static("gathering…", id="observatory-body")

    def on_mount(self) -> None:
        self._refresh_body()
        self.set_interval(1.0, self._refresh_body)

    def _refresh_body(self) -> None:
        try:
            from sovereign_agent.modes_crown.observatory import (
                gather_observatory, render_observatory_text,
            )

            text = render_observatory_text(gather_observatory())
        except Exception as exc:  # noqa: BLE001 — the window shows what it can
            text = f"[dim]observatory unavailable: {exc!r}[/dim]"
        try:
            self.query_one("#observatory-body", Static).update(text)
        except Exception:  # noqa: BLE001
            pass
