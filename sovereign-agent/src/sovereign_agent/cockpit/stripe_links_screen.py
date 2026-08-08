"""stripe_links_screen.py — 🎟 the Stripe Links Vault: see + update every
product's Payment Link, from the cockpit.

Kevin, 2026-07-26: "add a button and menu for stripe control panel inside
the cockpit front end so I can see all the current stripe links, and
just configuration slots for stripe links so I can update them easily
via the cockpit... like a stripe links vault." Same shape as
credentials_screen.py's Key Vault, minus the masking — a Payment Link
URL is explicitly NOT a secret (shop.py's own docstring), so it's shown
in full here, unlike a credential.
"""
from __future__ import annotations

from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select, Static


class StripeLinksScreen(ModalScreen):
    """🎟 Stripe Links Vault — every product's Payment Link, plain (not a
    secret), editable. Esc to close."""

    BINDINGS = [Binding("escape", "close", "close", show=False)]

    def action_close(self) -> None:
        self.app.pop_screen()

    def on_key(self, event) -> None:
        if event.key == "escape":
            event.stop(); event.prevent_default(); self.app.pop_screen()

    def compose(self):
        with VerticalScroll(id="sl-modal"):
            with Horizontal(id="sl-top"):
                yield Button("✕ close", id="sl-exit-btn")
                yield Button("save link", id="sl-save-btn", variant="success")
            yield Static("Stripe Links Vault — every product's Payment Link",
                        id="sl-title")
            yield Static(
                "[dim]Payment Links aren't secrets (shop.py's own doctrine) — "
                "shown in full below. Pick a product, paste its Stripe "
                "Payment Link, save. Esc to close.[/dim]",
                id="sl-help")
            yield Label("Which product?")
            yield Select([("(no products yet)", "")], id="sl-which",
                        allow_blank=False)
            yield Static("", id="sl-info")
            yield Label("Stripe Payment Link")
            yield Input(id="sl-value", placeholder="https://buy.stripe.com/...")
            with Horizontal(id="sl-actions"):
                yield Button("paste from clipboard", id="sl-paste-btn",
                            variant="primary")
                yield Button("clear link", id="sl-clear-btn", variant="error")
            yield Static("[dim]— every product —[/dim]", id="sl-sep")
            yield Static("", id="sl-status")

    def on_mount(self) -> None:
        self._refresh_options()
        self._refresh_info()
        self._refresh_status()

    # ── data ──
    @staticmethod
    def _products():
        from sovereign_agent.config import SETTINGS
        from sovereign_agent.shop import list_all
        return list_all(SETTINGS.paths.data_dir)

    def _selected(self) -> str:
        try:
            return str(self.query_one("#sl-which", Select).value or "")
        except Exception:  # noqa: BLE001
            return ""

    def _refresh_options(self) -> None:
        try:
            products = self._products()
            sel = self.query_one("#sl-which", Select)
            if not products:
                sel.set_options([("(no products yet)", "")])
                return
            current = self._selected()
            options = [(f"{p.name} — {p.price_label()}", p.name) for p in products]
            sel.set_options(options)
            names = {p.name for p in products}
            sel.value = current if current in names else options[0][1]
        except Exception:  # noqa: BLE001
            pass

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "sl-which":
            self._refresh_info()

    def _refresh_info(self) -> None:
        try:
            info = self.query_one("#sl-info", Static)
            name = self._selected()
            product = next((p for p in self._products() if p.name == name), None)
            value_input = self.query_one("#sl-value", Input)
            if product is None:
                info.update("[dim]no product selected[/dim]")
                value_input.value = ""
                return
            link = product.stripe_url or "[dim]not set[/dim]"
            info.update(f"[b]{product.name}[/b] — {product.price_label()}  "
                        f"({product.billing})\ncurrent link: {link}")
            value_input.value = product.stripe_url or ""
        except Exception:  # noqa: BLE001
            pass

    # ── status board ──
    def _refresh_status(self) -> None:
        try:
            products = self._products()
            lines = []
            for p in products:
                icon = "✅" if p.stripe_url else "○"
                link = f"  {p.stripe_url}" if p.stripe_url else ""
                lines.append(f"{icon} {p.name} — {p.price_label()}{link}")
            configured = sum(1 for p in products if p.stripe_url)
            lines.append(f"[dim]{configured}/{len(products)} product(s) have "
                        "a link set[/dim]")
            self.query_one("#sl-status", Static).update("\n".join(lines))
        except Exception:  # noqa: BLE001
            pass

    # ── actions ──
    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "sl-exit-btn":
            self.app.pop_screen()
        elif bid == "sl-save-btn":
            self._save()
        elif bid == "sl-paste-btn":
            self._paste_from_clipboard()
        elif bid == "sl-clear-btn":
            self._clear()

    def _paste_from_clipboard(self, reader=None) -> None:
        try:
            from sovereign_agent.cockpit.clipboard import read_clipboard
            text, detail = (reader or read_clipboard)()
            value_input = self.query_one("#sl-value", Input)
            if text is None:
                self._toast(f"couldn't read the clipboard ({detail})")
                return
            value_input.value = text.strip()
            value_input.focus()
            self._toast(f"pasted {len(text.strip())} characters ({detail}) — "
                        "hit save link")
        except Exception:  # noqa: BLE001
            pass

    def _save(self) -> None:
        name = self._selected()
        if not name:
            self._toast("pick a product first")
            return
        try:
            value = self.query_one("#sl-value", Input).value.strip()
        except Exception:  # noqa: BLE001
            return
        if value and not value.startswith(("https://", "http://")):
            self._toast("must be a full https:// (or http://) link")
            return
        try:
            from sovereign_agent.config import SETTINGS
            from sovereign_agent.shop import load, save
            product = load(name, SETTINGS.paths.data_dir)
            if product is None:
                self._toast(f"{name!r} not found")
                return
            product.stripe_url = value
            save(product, SETTINGS.paths.data_dir)
        except Exception as exc:  # noqa: BLE001
            self._toast(f"not saved: {type(exc).__name__}: {exc}")
            return
        self._toast(f"saved the link for {name} 💛" if value
                    else f"cleared the link for {name}")
        self._refresh_info(); self._refresh_status()

    def _clear(self) -> None:
        try:
            self.query_one("#sl-value", Input).value = ""
        except Exception:  # noqa: BLE001
            pass
        self._save()

    def _toast(self, msg: str) -> None:
        try:
            self.query_one("#sl-help", Static).update(f"[dim]{msg}[/dim]")
        except Exception:  # noqa: BLE001
            pass

    DEFAULT_CSS = """
    StripeLinksScreen { align: center middle; background: $surface 60%; }
    #sl-modal {
        width: 84; height: 90%; padding: 1 2;
        border: thick $primary; background: $surface;
    }
    #sl-top { height: 3; margin-bottom: 1; }
    #sl-top Button { width: 1fr; margin-right: 1; }
    #sl-title { text-style: bold; margin-bottom: 1; }
    #sl-help { height: 3; color: $text-muted; margin-bottom: 1; }
    #sl-info { min-height: 3; margin-bottom: 1; color: $text; }
    StripeLinksScreen Input, StripeLinksScreen Select { width: 100%; margin-bottom: 1; }
    StripeLinksScreen Label { color: $text-muted; }
    #sl-actions { height: 3; margin-bottom: 1; }
    #sl-actions Button { width: 1fr; margin-right: 1; }
    #sl-status { margin-top: 1; }
    """


__all__ = ["StripeLinksScreen"]
