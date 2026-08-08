"""theme_creator_screen.py — a theme CREATION studio with per-area dropdowns.

Kevin's ask: a menu to build custom themes — a section per theme area, each
with a dropdown of color options, and (effectively) no cap on how many
custom themes you can save.

Design:
  • Builds ON the existing `user_themes` layer (UserTheme + save/validate/
    list) — this is only the UI.
  • One labeled `Select` (dropdown) per color slot, options drawn from a
    broad, spectrum-covering palette. The current value is always a valid
    option (prepended if not in the palette), so editing an existing theme
    round-trips.
  • Live preview: every change rebuilds the theme, registers it, and applies
    it — you SEE the theme as you build it.
  • Save → validate → persist (user_themes.save, force overwrite when
    editing) → keep it active.

The color/build logic is pure (`COLOR_PALETTE`, `SLOTS`,
`theme_from_selections`) so it is trivially testable without a running app.
"""
from __future__ import annotations

from typing import Any

from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select, Static

# A broad, spectrum-covering palette. (name, #RRGGBB). Kept as data so it's
# easy to extend; every entry is a valid slot value.
COLOR_PALETTE: list[tuple[str, str]] = [
    ("near-black", "#0A0E14"), ("ink", "#0C141F"), ("charcoal", "#1A1A22"),
    ("slate", "#232734"), ("dim-gray", "#3A3F4B"), ("gray", "#6B7280"),
    ("silver", "#9CA3AF"), ("light-gray", "#CBD1DA"), ("off-white", "#E0E6ED"),
    ("white", "#F5F7FA"),
    ("crimson", "#DC143C"), ("red", "#EF4444"), ("rose", "#FB7185"),
    ("pink", "#F472B6"), ("magenta", "#E879F9"),
    ("coral", "#FB923C"), ("orange", "#F97316"), ("amber", "#FBBF24"),
    ("gold", "#F5C542"), ("yellow", "#FDE047"),
    ("lime", "#A3E635"), ("green", "#4ADE80"), ("emerald", "#34D399"),
    ("mint", "#86EFAC"), ("teal", "#2DD4BF"),
    ("cyan", "#22D3EE"), ("sky", "#38BDF8"), ("azure", "#5EEAD4"),
    ("blue", "#60A5FA"), ("indigo", "#818CF8"),
    ("violet", "#A78BFA"), ("purple", "#C084FC"), ("lavender", "#D8B4FE"),
    ("plum", "#9D4EDD"), ("deep-teal", "#0D9488"), ("deep-blue", "#1E3A8A"),
]

# The color slots the user edits, in a sensible top-to-bottom order.
SLOTS: list[tuple[str, str]] = [
    ("background", "Background — the deepest layer"),
    ("surface", "Surface — panes / cards"),
    ("panel", "Panel — raised areas"),
    ("primary", "Primary — the signature accent"),
    ("accent", "Accent — secondary highlight"),
    ("secondary", "Secondary — tertiary highlight"),
    ("success", "Success — good / green"),
    ("warning", "Warning — caution / amber"),
    ("error", "Error — danger / red"),
    ("foreground", "Foreground — the main text"),
]

_FAMILIES = ["custom", "warm", "cool", "nature", "mono"]

# A sensible dark starting point (all values are palette members).
_DEFAULT_SEED = {
    "background": "#0A0E14", "surface": "#0C141F", "panel": "#1A1A22",
    "primary": "#2DD4BF", "accent": "#A78BFA", "secondary": "#86EFAC",
    "success": "#4ADE80", "warning": "#FBBF24", "error": "#FB7185",
    "foreground": "#E0E6ED",
}


def theme_from_selections(
    name: str, family: str, dark: bool, slots: dict[str, str],
    *, mood: str = "a custom theme"
):
    """Pure: build a UserTheme from the creator's current selections."""
    from sovereign_agent.cockpit.user_themes import UserTheme
    def g(slot: str) -> str:
        return slots.get(slot) or _DEFAULT_SEED.get(slot, "#000000")
    return UserTheme(
        name=name or "my-theme", family=family if family in _FAMILIES else "custom",
        mood=mood, dark=bool(dark),
        background=g("background"), surface=g("surface"), panel=g("panel"),
        primary=g("primary"), accent=g("accent"), secondary=g("secondary"),
        success=g("success"), warning=g("warning"), error=g("error"),
        foreground=g("foreground"), created_by="operator",
    )


def _options_for(current: str) -> list[tuple[str, str]]:
    """Palette options, with `current` guaranteed present (prepended)."""
    opts = [(f"{name}  {hexv}", hexv) for name, hexv in COLOR_PALETTE]
    if current and current not in {h for _, h in COLOR_PALETTE}:
        opts.insert(0, (f"current  {current}", current))
    return opts


class ThemeCreatorScreen(ModalScreen):
    """✎ Create a theme — dropdowns per area, live preview, save. Esc to close."""

    BINDINGS = [
        Binding("escape", "close", "close", show=False),
    ]

    def __init__(self, seed: dict[str, str] | None = None, edit_name: str = "") -> None:
        super().__init__()
        self._slots: dict[str, str] = dict(_DEFAULT_SEED)
        if seed:
            self._slots.update({k: v for k, v in seed.items() if k in self._slots})
        self._edit_name = edit_name

    def action_close(self) -> None:
        self.app.pop_screen()

    def on_key(self, event) -> None:
        if event.key == "escape":
            event.stop(); event.prevent_default(); self.app.pop_screen()

    def compose(self):
        with VerticalScroll(id="creator-modal"):
            with Horizontal(id="creator-top"):
                yield Button("✕ close", id="creator-exit-btn")
                yield Button("save theme", id="creator-save-btn", variant="success")
            yield Static("Create a theme", id="creator-title")
            yield Static("[dim]Pick a color for each area — the theme previews live "
                         "as you go. Name it and save. Esc to close.[/dim]",
                         id="creator-help")
            yield Label("Name")
            yield Input(value=self._edit_name or "my-theme", id="creator-name",
                        placeholder="lowercase-with-hyphens")
            with Horizontal(id="creator-meta"):
                yield Select([(f, f) for f in _FAMILIES], value="custom",
                             id="creator-family", allow_blank=False)
                yield Select([("dark", "dark"), ("light", "light")], value="dark",
                             id="creator-dark", allow_blank=False)
            for slot, desc in SLOTS:
                yield Label(desc)
                yield Select(_options_for(self._slots.get(slot, "")),
                             value=self._slots.get(slot), id=f"slot-{slot}",
                             allow_blank=False)

    def on_mount(self) -> None:
        # apply the seed as the live preview immediately
        self._apply_preview()

    def _current_slots(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for slot, _ in SLOTS:
            try:
                sel = self.query_one(f"#slot-{slot}", Select)
                if sel.value not in (None, Select.BLANK):
                    out[slot] = str(sel.value)
            except Exception:  # noqa: BLE001
                pass
        return out or dict(self._slots)

    def _apply_preview(self) -> None:
        try:
            dark = True
            try:
                dark = self.query_one("#creator-dark", Select).value == "dark"
            except Exception:  # noqa: BLE001
                pass
            theme = theme_from_selections("__preview__", "custom", dark,
                                          self._current_slots())
            self.app.register_theme(theme.to_cockpit_theme().to_textual_theme())
            self.app.theme = "__preview__"
        except Exception:  # noqa: BLE001 — preview must never crash the creator
            pass

    def on_select_changed(self, event: Select.Changed) -> None:
        self._apply_preview()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "creator-exit-btn":
            self.app.pop_screen()
            return
        if event.button.id == "creator-save-btn":
            self._save()

    def _save(self) -> None:
        from sovereign_agent.cockpit import user_themes as ut
        from sovereign_agent.config import SETTINGS
        name = self.query_one("#creator-name", Input).value.strip()
        family = str(self.query_one("#creator-family", Select).value or "custom")
        dark = self.query_one("#creator-dark", Select).value == "dark"
        theme = theme_from_selections(name, family, dark, self._current_slots())
        errs = ut.validate(theme)
        if errs:
            self._notify(f"can't save: {errs[0]}")
            return
        try:
            ut.save(theme, SETTINGS.paths.data_dir, force=True)
            self.app.register_theme(theme.to_cockpit_theme().to_textual_theme())
            self.app.theme = theme.name
            ut.set_active_theme_name(theme.name, SETTINGS.paths.data_dir)
        except Exception as exc:  # noqa: BLE001
            self._notify(f"save failed: {type(exc).__name__}")
            return
        self._notify(f"saved & applied '{theme.name}' 💛")
        self.app.pop_screen()

    def _notify(self, msg: str) -> None:
        try:
            self.query_one("#creator-help", Static).update(f"[dim]{msg}[/dim]")
        except Exception:  # noqa: BLE001
            pass

    DEFAULT_CSS = """
    ThemeCreatorScreen { align: center middle; background: $surface 60%; }
    #creator-modal {
        width: 68; height: 90%; padding: 1 2;
        border: thick $primary; background: $surface;
    }
    #creator-top { height: 3; margin-bottom: 1; }
    #creator-exit-btn { width: 1fr; margin-right: 1; }
    #creator-save-btn { width: 1fr; }
    #creator-title { text-style: bold; margin-bottom: 1; }
    #creator-help { height: 3; color: $text-muted; margin-bottom: 1; }
    #creator-meta { height: 3; margin-bottom: 1; }
    #creator-meta Select { width: 1fr; margin-right: 1; }
    ThemeCreatorScreen Select { width: 100%; margin-bottom: 1; }
    ThemeCreatorScreen Label { color: $text-muted; }
    """
