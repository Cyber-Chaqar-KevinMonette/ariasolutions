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
        self._pending_tier_mode: str = ""  # modes-tier-unify-d
        self._pending_tier_hours: float | None = None  # session-setup-unify-d

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
                "[b]◊ Modes[/b]  [dim]the crown — pick how she works[/dim]",
                id="modes-title")
            with VerticalScroll(id="modes-scroll"):
                for profile in PROFILES.values():
                    marker = "●" if profile.mode_id == active else "○"
                    lease = (f" · lease {profile.lease_seconds // 3600}h"
                             if profile.lease_seconds else "")
                    yield Button(
                        f"{marker} {profile.title}{lease} — {profile.description}",
                        id=f"mode-{profile.mode_id}")
            # session-setup-unify-d (Kevin, 2026-07-25): "a drop down menu
            # for hours. Max 1-12." Not a separate screen from /modes and
            # /tiers -- this IS the unified one they asked for; the two
            # named auto-* buttons above stay as quick presets, this adds
            # any duration in between/beyond them, same tier ceremony.
            yield Static(
                "[dim]◊ or pick any custom auto duration (1-12h):[/dim]",
                id="modes-custom-hours-label")
            yield Input(
                placeholder="hours, e.g. 5 — then Enter",
                id="modes-custom-hours")
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
                f"[bold magenta]◊ mode → {profile.mode_id}[/bold magenta] "
                f"[dim]{profile.description}[/dim]")
        except Exception:  # noqa: BLE001
            pass
        # auto-message-clarity-d (Kevin, 2026-07-21): "I mean in the
        # header" -- arming via F2 changed the REAL state correctly, but
        # never force-refreshed the header (unlike /auto, which already
        # did). The header only caught up on the next periodic tick,
        # showing stale "Non-auto" in between -- genuinely looks like a
        # kick-out even though nothing was ever disarmed.
        try:
            self.app._refresh_sub_title()  # noqa: SLF001
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

        # modes-tier-unify-d (Kevin, 2026-07-25): "Modes should activate
        # auto and tiers at the same time I believe it says it does but
        # it does not actually do so." Root cause: set_crown_mode() would
        # fail with a CrownError when the profile needed a higher trust
        # tier than was currently approved -- pointing Kevin at the
        # SEPARATE F4 tier screen, which he then had to remember to come
        # back from. Checked here, proactively, BEFORE attempting to arm,
        # so the tier ceremony (same phrase tier_screen.py already uses --
        # not a new one) happens inline, in this same screen.
        if profile.trust_tier > 1:
            try:
                from sovereign_agent.auto_crown import AutoCrownStore
                current_tier = AutoCrownStore().get_max_trust_tier()
            except Exception:  # noqa: BLE001
                current_tier = 1
            if profile.trust_tier > current_tier:
                from .tier_screen import approval_phrase

                self._pending_tier_mode = mode_id
                self._pending_mode = ""
                confirm = self.query_one("#modes-confirm", Input)
                confirm.add_class("armed")
                confirm.focus()
                self.query_one("#modes-status", Static).update(
                    f"[yellow]{profile.title} needs trust tier "
                    f"{profile.trust_tier} (currently {current_tier}) — "
                    f"type: [b]{approval_phrase(profile.trust_tier)}[/b][/yellow]")
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
        input_id = getattr(event.input, "id", "") or ""
        if input_id == "modes-custom-hours":
            self._handle_custom_hours(event.value)
            return
        if self._pending_tier_mode or self._pending_tier_hours is not None:
            self._handle_tier_confirmation(event.value)
            return
        if self._pending_mode:
            self._set_mode(self._pending_mode, confirm=event.value)

    def _handle_custom_hours(self, value: str) -> None:  # session-setup-unify-d
        from sovereign_agent.modes_crown.profiles import custom_hours_trust_tier

        status = self.query_one("#modes-status", Static)
        try:
            hours = float(value.strip())
        except ValueError:
            status.update("[red]✗ enter a number of hours, e.g. 5[/red]")
            return
        if not (0.1 <= hours <= 12.0):
            status.update("[red]✗ hours must be between 1 and 12[/red]")
            return

        needed_tier = custom_hours_trust_tier(hours)
        try:
            from sovereign_agent.auto_crown import AutoCrownStore
            current_tier = AutoCrownStore().get_max_trust_tier()
        except Exception:  # noqa: BLE001
            current_tier = 1
        if needed_tier > current_tier:
            from .tier_screen import approval_phrase

            self._pending_tier_hours = hours
            self._pending_tier_mode = ""
            confirm = self.query_one("#modes-confirm", Input)
            confirm.add_class("armed")
            confirm.focus()
            status.update(
                f"[yellow]{hours:g}h needs trust tier {needed_tier} "
                f"(currently {current_tier}) — type: "
                f"[b]{approval_phrase(needed_tier)}[/b][/yellow]")
            return
        self._arm_custom(hours)

    def _arm_custom(self, hours: float) -> None:  # session-setup-unify-d
        from sovereign_agent.modes_crown.profiles import CrownError, arm_custom_hours

        status = self.query_one("#modes-status", Static)
        try:
            profile = arm_custom_hours(hours)
        except CrownError as exc:
            status.update(f"[yellow]{exc}[/yellow]")
            return
        try:
            self.app._write_meta(  # noqa: SLF001
                f"[bold magenta]◊ mode → auto · {hours:g}h[/bold magenta] "
                f"[dim]{profile.description}[/dim]")
        except Exception:  # noqa: BLE001
            pass
        try:
            self.app._refresh_sub_title()  # noqa: SLF001 — auto-message-clarity-d
        except Exception:  # noqa: BLE001
            pass
        self.app.pop_screen()

    def _handle_tier_confirmation(self, value: str) -> None:  # modes-tier-unify-d
        from .tier_screen import approval_phrase
        from sovereign_agent.auto_crown import AutoCrownStore
        from sovereign_agent.modes_crown.profiles import (
            PROFILES, custom_hours_trust_tier,
        )

        status = self.query_one("#modes-status", Static)

        # session-setup-unify-d — the custom-hours branch
        if self._pending_tier_hours is not None:
            hours = self._pending_tier_hours
            needed_tier = custom_hours_trust_tier(hours)
            if value.strip() != approval_phrase(needed_tier):
                status.update(
                    f"[red]✗ phrase mismatch — type exactly:[/red] "
                    f"[b]{approval_phrase(needed_tier)}[/b]")
                return
            try:
                # tier-auto-duration-sync-d: raises the ceiling so the arm
                # below won't be refused. The DURATION match (Kevin, 2026-07-
                # 25: "tier is 4 hours and auto is 3 hours, they need to
                # match") is enforced once, centrally, in _arm_lease() right
                # after this — whatever value lands here gets overwritten
                # there to the lease's own hours, so every arming path (this
                # one, or tier-already-sufficient with no raise at all) ends
                # up synced the same way.
                AutoCrownStore().set_trust_tier(needed_tier)
            except Exception as exc:  # noqa: BLE001
                status.update(f"[red]tier raise failed: {exc}[/red]")
                return
            self._pending_tier_hours = None
            self._arm_custom(hours)
            return

        mode_id = self._pending_tier_mode
        profile = PROFILES.get(mode_id)
        if profile is None:
            self._pending_tier_mode = ""
            return
        if value.strip() != approval_phrase(profile.trust_tier):
            status.update(
                f"[red]✗ phrase mismatch — type exactly:[/red] "
                f"[b]{approval_phrase(profile.trust_tier)}[/b]")
            return
        try:
            # tier-auto-duration-sync-d — raises the ceiling only; the
            # duration match happens centrally in _arm_lease() (see note
            # in the custom-hours branch above).
            AutoCrownStore().set_trust_tier(profile.trust_tier)
        except Exception as exc:  # noqa: BLE001
            status.update(f"[red]tier raise failed: {exc}[/red]")
            return
        self._pending_tier_mode = ""
        confirm = self.query_one("#modes-confirm", Input)
        confirm.value = ""
        # Tier approved -- proceed exactly as if the profile were picked
        # fresh. It may still need its OWN typed confirmation (e.g.
        # auto-3h's separate "I approve N hours" phrase) -- a distinct,
        # deliberate ceremony, not something this collapses away.
        if profile.typed_confirmation:
            self._pending_mode = mode_id
            status.update(
                f"[green]✔ tier {profile.trust_tier} approved.[/green] "
                f"[yellow]{profile.title} arms only with the phrase: "
                f"[b]{profile.typed_confirmation}[/b][/yellow]")
            confirm.focus()
            return
        self._set_mode(mode_id)


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
                "[b]Observatory[/b]  [dim]her modes, stance, emotion, "
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
