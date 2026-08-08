"""credentials_screen.py — 🔐 the Key Vault: hand Aria her keys, safely.

Kevin picks a credential from the catalog (each explains what it is, which
feature needs it, and where to get it), types the value into a MASKED
password field, and she writes it to the private env file (0600, local,
never the repo). Stored values are only ever displayed masked — this screen
cannot show a full secret back, by construction.
"""
from __future__ import annotations

from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select, Static

from sovereign_agent.credentials import (
    CRED_CATALOG,
    env_path,
    remove_secret,
    set_secret,
    validate_value,
    vault_status,
)

_CUSTOM = "__custom__"


class CredentialsScreen(ModalScreen):
    """🔐 Key Vault — set/remove credentials; masked always. Esc to close."""

    BINDINGS = [Binding("escape", "close", "close", show=False)]

    def action_close(self) -> None:
        self.app.pop_screen()

    def on_key(self, event) -> None:
        if event.key == "escape":
            event.stop(); event.prevent_default(); self.app.pop_screen()
        # ctrl-v-paste-d (Kevin, 2026-07-17): plain Ctrl+V pastes into the
        # value field, same path as the 📋 button. Normally the APP's
        # priority ctrl+v binding intercepts first and routes here via
        # action_paste_clipboard's vault-awareness — this branch is the
        # fallback if that binding ever changes.
        elif event.key == "ctrl+v":
            event.stop(); event.prevent_default()
            self._paste_from_clipboard()

    def compose(self):
        options = [(f"{c.label}  ({c.name})", c.name) for c in CRED_CATALOG]
        options.append(("+ Custom key...", _CUSTOM))
        with VerticalScroll(id="kv-modal"):
            with Horizontal(id="kv-top"):
                yield Button("✕ close", id="kv-exit-btn")
                yield Button("save key", id="kv-save-btn", variant="success")
            yield Static("Key Vault — her credentials, kept local", id="kv-title")
            yield Static("[dim]Values go to your private env file (0600). I only "
                         "ever show them masked. Esc to close.[/dim]", id="kv-help")
            yield Label("Which key?")
            yield Select(options, value=CRED_CATALOG[0].name, id="kv-which",
                         allow_blank=False)
            yield Static("", id="kv-info")
            yield Label("Custom key name (only for '＋ Custom key…')")
            yield Input(id="kv-custom-name", placeholder="MY_API_KEY")
            yield Label("Secret value (typing is masked)")
            yield Input(id="kv-value", password=True, placeholder="paste the secret here")
            yield Static("[dim]reads your clipboard straight into the field "
                         "(stays masked). Ctrl+V works here too — or "
                         "Ctrl+Shift+V / right-click.[/dim]", id="kv-paste-hint")
            with Horizontal(id="kv-actions"):
                yield Button("paste from clipboard", id="kv-paste-btn",
                             variant="primary")
                yield Button("rotate this key", id="kv-rotate-btn",
                             variant="warning")
                yield Button("remove selected", id="kv-remove-btn", variant="error")
            yield Static("[dim]— vault status —[/dim]", id="kv-sep")
            yield Static("", id="kv-status")

    def on_mount(self) -> None:
        self._refresh_info()
        self._refresh_status()

    # ── selection info ──
    def _selected(self) -> str:
        try:
            return str(self.query_one("#kv-which", Select).value or "")
        except Exception:  # noqa: BLE001
            return ""

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "kv-which":
            self._refresh_info()

    def _refresh_info(self) -> None:
        try:
            info = self.query_one("#kv-info", Static)
            name = self._selected()
            if name == _CUSTOM:
                info.update("[dim]Any extra key/password a future bot needs — "
                            "name it above (UPPER_SNAKE), stored the same safe "
                            "way. Convention for per-bot keys: BOT_<SLUG>_… "
                            "e.g. BOT_RESTOCKS_WEBHOOK_URL. The vault scales — "
                            "hundreds of keys stay instant.[/dim]")
                return
            spec = next((c for c in CRED_CATALOG if c.name == name), None)
            if spec is None:
                info.update("")
                return
            row = next((r for r in vault_status() if r["name"] == name), None)
            state = (f"currently: [b]{row['masked']}[/b]" if row and row["set"]
                     else "currently: [dim]not set[/dim]")
            # last-set-timestamp-d (Kevin, 2026-07-25): "I want to know when
            # the last time a key was rotated or applied." — right next to
            # the set/empty state, not a separate lookup.
            last_set = f"  ·  last set: {row['last_set_relative']}" if row else ""
            info.update(f"[b]{spec.what}[/b]\n"
                        f"needed for: {spec.required_for}\n"
                        f"where to get it: {spec.where}\n"
                        f"format: {spec.hint}  ·  {state}{last_set}")
        except Exception:  # noqa: BLE001
            pass

    # ── status board ──
    def _refresh_status(self) -> None:
        try:
            rows = vault_status()
            catalog = [r for r in rows if not r["custom"]]
            custom = [r for r in rows if r["custom"]]
            lines = []
            for r in catalog:
                icon = "✅" if r["set"] else "○"
                masked = f"  {r['masked']}" if r["set"] else ""
                # last-set-timestamp-d — only worth showing once a key is
                # actually set; an unset key has never been "rotated".
                last_set = f"  [dim]· {r['last_set_relative']}[/dim]" if r["set"] else ""
                lines.append(f"{icon} {r['label']}{masked}{last_set}"
                             f"  [dim]({r['required_for']})[/dim]")
            # scale-safe render: the vault may hold ANY number of custom keys
            # (per-bot creds use BOT_<SLUG>_* names); show the first 20 + count
            for r in custom[:20]:
                lines.append(f"✅ {r['label']}  {r['masked']}  "
                             f"[dim]· {r['last_set_relative']} (custom)[/dim]")
            if len(custom) > 20:
                lines.append(f"[dim]… +{len(custom) - 20} more custom key(s) "
                             f"(all stored; `sov keys status` lists features)[/dim]")
            lines.append(f"[dim]vault file: {env_path()} · {len(rows)} key slot(s)[/dim]")
            self.query_one("#kv-status", Static).update("\n".join(lines))
        except Exception:  # noqa: BLE001
            pass

    # ── actions ──
    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "kv-exit-btn":
            self.app.pop_screen()
        elif bid == "kv-save-btn":
            self._save()
        elif bid == "kv-paste-btn":
            self._paste_from_clipboard()
        elif bid == "kv-rotate-btn":
            self._rotate_guide()
        elif bid == "kv-remove-btn":
            self._remove()

    def _paste_from_clipboard(self, reader=None) -> None:
        """Fill the (masked) value field from the system clipboard. The
        secret never appears on screen — only a masked length note."""
        try:
            from sovereign_agent.cockpit.clipboard import read_clipboard
            text, detail = (reader or read_clipboard)()
            value_input = self.query_one("#kv-value", Input)
            if text is None:
                self._toast(f"couldn't read the clipboard ({detail}) — "
                            "install wl-clipboard (Wayland) or xclip (X11), "
                            "or paste with Ctrl+Shift+V / right-click")
                return
            value = text.strip()
            value_input.value = value
            value_input.focus()
            self._toast(f"pasted {len(value)} characters ({detail}) — "
                        "masked; hit 💾 save key")
        except Exception:  # noqa: BLE001
            pass

    def _target_name(self) -> str:
        name = self._selected()
        if name == _CUSTOM:
            try:
                name = self.query_one("#kv-custom-name", Input).value.strip()
            except Exception:  # noqa: BLE001
                name = ""
        return name

    def _save(self) -> None:
        name = self._target_name()
        try:
            value_input = self.query_one("#kv-value", Input)
            value = value_input.value
        except Exception:  # noqa: BLE001
            return
        try:
            set_secret(name, value)
        except ValueError as exc:
            self._toast(f"not saved: {exc}")
            return
        value_input.value = ""            # never leave a secret sitting in the field
        warns = validate_value(name.upper(), value.strip())
        note = f" ⚠ {warns[0]}" if warns else ""
        self._toast(f"saved {name.upper()} — stored masked, live for new runs 💛{note}")
        self._refresh_info(); self._refresh_status()

    def _remove(self) -> None:
        name = self._target_name()
        if not name or name == _CUSTOM:
            self._toast("pick a key first")
            return
        ok = remove_secret(name)
        self._toast(f"removed {name.upper()}" if ok else f"{name.upper()} wasn't set")
        self._refresh_info(); self._refresh_status()

    def _rotate_guide(self) -> None:
        """🔄 rotate — the honest version: new secrets are minted in each
        service's OWN dashboard, so the button gives the exact per-key
        path, then arms this screen for the fresh paste (value cleared,
        field focused). For webhooks she can re-mint them herself."""
        name = self._target_name()
        if not name:
            self._toast("pick a key first, then rotate")
            return
        if name.endswith("WEBHOOK_URL"):
            guide = ("easiest: run /setup-webhooks in Discord — Aria "
                     "deletes nothing, re-uses or re-mints the webhook and "
                     "vaults the fresh URL herself. Manual: channel Settings "
                     "→ Integrations → Webhooks → delete + New Webhook → "
                     "Copy URL → paste here → 💾.")
        elif name == "DISCORD_BOT_TOKEN":
            guide = ("Discord dev portal → your app → Bot → Reset Token "
                     "→ copy → paste here → 💾 — then restart her: "
                     "sov discord-admin run. Old token dies the moment you "
                     "reset (~60s of downtime total).")
        elif name == "STRIPE_SECRET_KEY":
            guide = ("Stripe Dashboard → Developers → API keys → your "
                     "key → ⋯ Roll key (or Create restricted key: read-only "
                     "Subscriptions+Customers) → paste here → 💾 — then "
                     "prove it: sov keys check.")
        elif name in ("DISCORD_OWNER_ID", "DISCORD_GUILD_ID") or \
                name.startswith("DISCORD_ENABLE") or name == "DISCORD_ADS_AUTO":
            self._toast(f"{name} is an ID/switch, not a secret — "
                        "nothing to rotate 💛")
            return
        else:
            guide = (f"mint a fresh value for {name} wherever it was "
                     "created, paste here → 💾. The old value stays valid "
                     "until its service revokes it.")
        try:
            value_input = self.query_one("#kv-value", Input)
            value_input.value = ""
            value_input.focus()
        except Exception:  # noqa: BLE001
            pass
        try:
            self.query_one("#kv-info", Static).update(f"[yellow]{guide}[/yellow]")
        except Exception:  # noqa: BLE001
            pass
        self._toast("rotation armed — field cleared, paste the fresh secret")

    def _toast(self, msg: str) -> None:
        try:
            self.query_one("#kv-help", Static).update(f"[dim]{msg}[/dim]")
        except Exception:  # noqa: BLE001
            pass

    DEFAULT_CSS = """
    CredentialsScreen { align: center middle; background: $surface 60%; }
    #kv-modal {
        width: 76; height: 90%; padding: 1 2;
        border: thick $primary; background: $surface;
    }
    #kv-top { height: 3; margin-bottom: 1; }
    #kv-top Button { width: 1fr; margin-right: 1; }
    #kv-title { text-style: bold; margin-bottom: 1; }
    #kv-help { height: 3; color: $text-muted; margin-bottom: 1; }
    #kv-info { min-height: 4; margin-bottom: 1; color: $text; }
    CredentialsScreen Input, CredentialsScreen Select { width: 100%; margin-bottom: 1; }
    CredentialsScreen Label { color: $text-muted; }
    #kv-paste-hint { height: 3; color: $text-muted; margin-bottom: 1; }
    #kv-actions { height: 3; margin-bottom: 1; }
    #kv-actions Button { width: 1fr; margin-right: 1; }
    #kv-status { margin-top: 1; }
    """
