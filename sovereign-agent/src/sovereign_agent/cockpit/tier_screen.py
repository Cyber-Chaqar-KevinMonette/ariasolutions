"""tier_screen.py — ◊ the trust-tier menu + kill switch (F4, Kevin 2026-07-19).

Kevin: "I keep getting stuck at approve tier 3 — make the solution
simple, easy, and immersive. A menu with buttons showing which tiers are
approved. And make tier three toggleable, to act as a kill switch."

The ceremony asymmetry IS the safety design:
  • RAISING trust requires typing the approval phrase ("I approve tier N")
    — the human ceremony the T3 tool always demanded, now discoverable.
  • LOWERING trust is INSTANT — one click on "[!] kill switch → tier 1"
    drops the ceiling immediately, no typing, no confirmation. Cutting
    power must always be easier than granting it.

State is AutoCrownStore's `auto_trust_tier.json` — the same file the
`set_auto_trust_tier` T3 tool writes; this screen is the owner's hands.
"""
from __future__ import annotations

from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Static

TIERS: tuple[tuple[int, str, str], ...] = (
    (1, "1h", "the default — short bounded sessions"),
    (2, "2h", "double shift"),
    (3, "4h", "unlocks auto-3h (the deep-work mode)"),
    (4, "12h", "the full overnight watch"),  # duration-ceiling-raise-d — was 8h
)


def approval_phrase(tier: int) -> str:
    return f"I approve tier {tier}"


class TierScreen(ModalScreen):
    """◊ Trust tiers → see what's approved; raise with the phrase;
    kill instantly."""

    BINDINGS = [
        Binding("escape", "close", "close", show=False),
        Binding("q", "close", "close", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._pending_tier: int | None = None

    # -- state ---------------------------------------------------------
    def _store(self):
        from sovereign_agent.auto_crown import AutoCrownStore
        return AutoCrownStore()

    def _current(self) -> int:
        try:
            return self._store().get_max_trust_tier()
        except Exception:  # noqa: BLE001
            return 1

    # -- lifecycle -----------------------------------------------------
    def action_close(self) -> None:
        self.app.pop_screen()

    def on_key(self, event) -> None:
        if event.key == "escape":
            event.stop()
            event.prevent_default()
            self.app.pop_screen()

    def _remaining_note(self) -> str:  # tier-expiry-d
        """Kevin, 2026-07-21: "have a timer show when elevated tiers
        end." Empty string at tier 1 (permanent, no timer)."""
        try:
            remaining = self._store().trust_tier_remaining_seconds()
        except Exception:  # noqa: BLE001
            return ""
        if remaining <= 0:
            return ""
        h, rem = divmod(remaining, 3600)
        m = rem // 60
        countdown = f"{h}h {m:02d}m" if h else f"{m}m"
        return f" — reverts to tier 1 in {countdown}"

    def compose(self):
        current = self._current()
        with VerticalScroll(id="tier-modal"):
            yield Button("✕ close", id="tier-exit-btn")
            yield Static("◊ Trust tiers — auto-session ceiling",  # tier3-glyph-fix-d
                         id="tier-title")
            yield Static(
                f"[bold]Currently approved: tier {current}[/bold] "
                f"(max {dict((t, h) for t, h, _ in TIERS)[current]} per "
                f"auto session){self._remaining_note()}", id="tier-current")
            yield Button(  # tier3-quick-toggle-d
                "\u25b8 Activate Tier 3" if current < 3 else "\u2714 Tier 3 active",  # theme-studio-redesign-d
                id="tier3-activate-btn",
                variant="primary" if current < 3 else "success")
            yield Button(
                "\u2717 Deactivate Tier 3" if current >= 3 else "\u00b7 Tier 3 not active",
                id="tier3-deactivate-btn",
                variant="error" if current >= 3 else "default")
            for tier, hours, desc in TIERS:
                mark = "✔" if tier <= current else "·"
                label = f"{mark} Tier {tier} — {hours} · {desc}"
                yield Button(label, id=f"tier-btn-{tier}",
                             variant="success" if tier <= current
                             else "default")
            yield Static(
                "[dim]Raise = type the phrase below (your ceremony). "
                "Lower = instant, no typing — cutting power is always "
                "one click.[/dim]", id="tier-help")
            yield Button("[!] KILL SWITCH — drop to tier 1 now",
                         id="tier-kill-btn", variant="error")
            yield Input(placeholder="type the approval phrase here…",
                        id="tier-phrase")
            yield Static("", id="tier-status")

    # -- interactions --------------------------------------------------
    def _set_tier(self, tier: int) -> None:
        try:
            self._store().set_trust_tier(tier)
            self._refresh_view(f"✔ trust tier is now {tier}")
        except Exception as e:  # noqa: BLE001
            self._status(f"✗ {e}")

    def _refresh_view(self, msg: str) -> None:
        # simplest honest refresh: re-open the screen with fresh state
        self.app.pop_screen()
        self.app.push_screen(TierScreen())
        try:
            self.app.notify(msg)
        except Exception:  # noqa: BLE001
            pass

    def _status(self, text: str) -> None:
        try:
            self.query_one("#tier-status", Static).update(text)
        except Exception:  # noqa: BLE001
            pass

    def _activate_tier3(self) -> None:  # tier3-quick-toggle-d
        """Same ceremony the per-tier raise buttons already use -- this
        is a dedicated entry point into it, never a bypass."""
        current = self._current()
        if current >= 3:
            self._status("\u2714 tier 3 is already active")
            return
        self._pending_tier = 3
        self._status(
            f"to activate tier 3, type exactly: "
            f"[bold]{approval_phrase(3)}[/bold]  \u23ce")
        try:
            self.query_one("#tier-phrase", Input).focus()
        except Exception:  # noqa: BLE001
            pass

    def _deactivate_tier3(self) -> None:  # tier3-quick-toggle-d
        """Instant, no typing -- the same shape as the existing kill
        switch. Cutting power is always easier than granting it."""
        current = self._current()
        if current < 3:
            self._status("\u00b7 tier 3 is not active")
            return
        self._set_tier(1)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        event.stop()
        if bid == "tier-exit-btn":
            self.app.pop_screen()
            return
        if bid == "tier3-activate-btn":  # tier3-quick-toggle-d
            self._activate_tier3()
            return
        if bid == "tier3-deactivate-btn":
            self._deactivate_tier3()
            return
        if bid == "tier-kill-btn":
            self._set_tier(1)                      # instant — the kill switch
            return
        if bid.startswith("tier-btn-"):
            tier = int(bid.rsplit("-", 1)[1])
            current = self._current()
            if tier <= current:
                self._set_tier(tier)               # lowering: instant
            else:
                self._pending_tier = tier          # raising: the ceremony
                self._status(
                    f"to approve tier {tier}, type exactly: "
                    f"[bold]{approval_phrase(tier)}[/bold]  ⏎")
                try:
                    self.query_one("#tier-phrase", Input).focus()
                except Exception:  # noqa: BLE001
                    pass

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        tier = self._pending_tier
        if tier is None:
            self._status("pick a tier button first")
            return
        if event.value.strip() == approval_phrase(tier):
            self._pending_tier = None
            self._set_tier(tier)
        else:
            self._status(
                f"✗ phrase mismatch — type exactly: "
                f"[bold]{approval_phrase(tier)}[/bold]")

    DEFAULT_CSS = """
    TierScreen {
        align: center middle;
        background: $surface 60%;
    }
    #tier-modal {
        width: 64;
        height: 80%;
        padding: 1 2;
        border: thick $primary;
        background: $surface;
    }
    #tier-exit-btn { width: 100%; margin-bottom: 1; }
    #tier-title { text-style: bold; margin-bottom: 1; }
    #tier-current { margin-bottom: 1; }
    #tier-help { margin: 1 0; color: $text-muted; }
    #tier-kill-btn { width: 100%; margin: 1 0; }
    #tier-phrase { margin-top: 1; }
    """
