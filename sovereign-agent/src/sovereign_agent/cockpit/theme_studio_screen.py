"""theme_studio_screen.py — the Theme Studio: browse, preview, create, edit, remove.

Redesigned (Kevin, 2026-07-20): "the arrows idea is cool. But make that an
optional way to switch through themes. But the main way is the list. I
want a list where I can select and maybe preview themes. Redesign the
theme picker system worldclass and with seriousness."

Primary interaction is now a real list (Textual's OptionList): Presets and
Custom themes each under their own (non-selectable) header, every row
carrying a small live color swatch from the theme's own palette. Moving
the highlight — arrow keys, mouse, OR the optional prev/next buttons below,
all driving the same cursor — applies that theme LIVE as a preview, the
same instant feedback the old arrow-only carousel gave, just reachable by
browsing a real list instead of only stepping one-by-one. Closing without
choosing (Esc/✕) reverts to whatever theme was active when the screen
opened; pressing Enter or clicking a row COMMITS it (persisted, matching
the original behavior). This is the same propose-vs-commit shape as
VSCode's own theme picker — a genuinely proven, serious design to model,
not a novel invention.

The arrow buttons are kept exactly as Kevin asked — an OPTIONAL secondary
way to move through the SAME list cursor, not a second parallel mechanism.

Glyph safety (Kevin: "4 unsafe glyphs inside theme picker" — confirmed via
sovereign_agent.glyphs.is_emoji_risk() + a direct unicodedata check, not
guessed): ◀ (U+25C0) and ▶ (U+25B6) are both East-Asian-Width=Ambiguous —
genuinely unsafe, not a false alarm — replaced with glyphs.ARROW_LEFT/
ARROW_RIGHT (◂/▸, U+25C2/U+25B8, both confirmed EAW=Neutral). ✎ (pencil)
and 🗑 (wastebasket) are both emoji-range and confirmed emoji-risk by this
session's own hardened check — replaced with plain text labels, no icon,
matching the deliberate choice already made for the tier3/game-studio
button work earlier this session. ＋ (FULLWIDTH PLUS SIGN, U+FF0B) is
EAW=Fullwidth, also genuinely unsafe — replaced with a plain ASCII "+".

Caught one more while building this redesign, not in Kevin's original
report: the "current theme" marker (● BLACK CIRCLE, U+25CF) copied from
the older theme_picker_screen.py's own convention is ALSO East-Asian-
Width=Ambiguous and not on the de-facto-narrow whitelist — genuinely
unsafe, confirmed the same way as the other five. Replaced with
glyphs.BULLET (•, U+2022), already an established safe constant. Not
fixed in theme_picker_screen.py itself — that screen wasn't part of what
was asked, named here so it isn't lost.
"""
from __future__ import annotations

from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Label, OptionList, Static
from textual.widgets.option_list import Option

from sovereign_agent.glyphs import ARROW_LEFT, ARROW_RIGHT, BULLET, CROSS
from .theme_creator_screen import SLOTS, ThemeCreatorScreen

_HEADER_PRESETS = "header-presets"
_HEADER_CUSTOM = "header-custom"
_SWATCH_SLOTS = ("primary", "accent", "success")  # a compact 3-color preview


def cycle_index(current: int, count: int, step: int) -> int:
    """Wrap an index by step within [0, count) -- safe when count is 0
    (an empty theme list has no index to land on)."""
    if count <= 0:
        return 0
    return (current + step) % count


def _swatch(obj) -> str:
    """A small inline color-preview strip from a theme's own palette --
    the 'maybe preview themes' ask, made real rather than a plain name."""
    chips = []
    for slot in _SWATCH_SLOTS:
        color = getattr(obj, slot, None)
        if color:
            chips.append(f"[on {color}]  [/]")
    return "".join(chips)


class ThemeStudioScreen(ModalScreen):
    """◊ Theme Studio — a real list to browse + preview (Enter/click to
    apply, Esc reverts), arrows as an optional secondary way to step
    through the same list, plus create/edit/remove for custom themes."""

    BINDINGS = [
        Binding("escape", "close", "close", show=False),
        Binding("q", "close", "close", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._presets: list[str] = []
        self._customs: list[str] = []
        self._original_theme: str | None = None
        self._committed = False

    # ── data ──
    def _load(self) -> None:
        try:
            from sovereign_agent.cockpit.themes import CURATED_THEMES
            self._preset_objs = list(CURATED_THEMES)
            self._presets = [t.name for t in CURATED_THEMES]
        except Exception:  # noqa: BLE001
            self._preset_objs = []
            self._presets = []
        try:
            from sovereign_agent.cockpit import user_themes as ut
            from sovereign_agent.config import SETTINGS
            self._custom_objs = list(ut.list_all(SETTINGS.paths.data_dir))
            self._customs = [t.name for t in self._custom_objs]
        except Exception:  # noqa: BLE001
            self._custom_objs = []
            self._customs = []

    def action_close(self) -> None:
        self._revert_if_uncommitted()
        self.app.pop_screen()

    def on_key(self, event) -> None:
        if event.key in ("escape",):
            event.stop(); event.prevent_default()
            self._revert_if_uncommitted()
            self.app.pop_screen()

    def _revert_if_uncommitted(self) -> None:
        """Esc/✕ without choosing anything restores the theme that was
        active when the Studio opened -- browsing/previewing must be
        risk-free, matching VSCode's own theme-picker behavior."""
        if not self._committed and self._original_theme is not None:
            try:
                self.app.theme = self._original_theme
            except Exception:  # noqa: BLE001
                pass

    # ── layout ──
    def compose(self):
        self._load()
        self._original_theme = getattr(self.app, "theme", None)
        with VerticalScroll(id="studio-modal"):
            yield Button(f"{CROSS} close", id="studio-exit-btn")
            yield Static(
                f"◊ Theme Studio  [dim]({len(self._presets)} presets · "
                f"{len(self._customs)} custom)[/dim]",
                id="studio-title",
            )
            yield Static(
                "[dim]Browse the list below — moving the highlight previews "
                "a theme live. Enter/click applies it. Esc reverts. Arrows "
                "step the same list if you prefer them. Esc / q / ✕ to "
                "close.[/dim]",
                id="studio-help",
            )

            option_list = OptionList(id="theme-list")
            yield option_list

            with Horizontal(classes="carousel"):
                yield Button(ARROW_LEFT, id="theme-prev")
                yield Static("[dim]optional: step the list above[/dim]",
                             classes="carousel-label")
                yield Button(ARROW_RIGHT, id="theme-next")

            with Horizontal(id="custom-actions"):
                yield Button("edit", id="custom-edit")
                yield Button("remove", id="custom-remove", variant="error")

            yield Button("+ create new theme", id="studio-create", variant="success")

    def on_mount(self) -> None:
        self._populate_list()

    def _populate_list(self) -> None:
        try:
            option_list = self.query_one("#theme-list", OptionList)
        except Exception:  # noqa: BLE001
            return
        option_list.clear_options()
        active = getattr(self.app, "theme", None)

        # Kevin (2026-07-20): "space them all to line up" -- pad every name
        # to the widest one so every row's swatch starts in the same column,
        # a real aligned column rather than a ragged inline afterthought.
        name_width = max([len(n) for n in (*self._presets, *self._customs)], default=0)

        option_list.add_option(Option("[b]Presets[/b]", id=_HEADER_PRESETS, disabled=True))
        for name, obj in zip(self._presets, self._preset_objs):
            marker = BULLET if name == active else " "
            option_list.add_option(Option(
                f"{marker} {name:<{name_width}}  {_swatch(obj)}", id=f"theme-preset::{name}",
            ))

        option_list.add_option(Option("[b]Custom[/b]", id=_HEADER_CUSTOM, disabled=True))
        if self._customs:
            for name, obj in zip(self._customs, self._custom_objs):
                marker = BULLET if name == active else " "
                option_list.add_option(Option(
                    f"{marker} {name:<{name_width}}  {_swatch(obj)}", id=f"theme-custom::{name}",
                ))
        else:
            option_list.add_option(Option(
                "[dim](no custom themes yet — create one below)[/dim]",
                id="no-customs", disabled=True,
            ))

        # Start the cursor on the active theme if it's in the list.
        for candidate_id in (f"theme-preset::{active}", f"theme-custom::{active}"):
            try:
                option_list.highlighted = option_list.get_option_index(candidate_id)
                break
            except Exception:  # noqa: BLE001 — not found under that id, try the next
                continue

    def _theme_name_from_option_id(self, option_id: str | None) -> str | None:
        if not option_id or option_id in (_HEADER_PRESETS, _HEADER_CUSTOM, "no-customs"):
            return None
        if "::" in option_id:
            return option_id.split("::", 1)[1]
        return None

    # ── preview / commit ──
    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        name = self._theme_name_from_option_id(
            event.option.id if event.option else None
        )
        if name is None:
            return
        try:
            self.app.theme = name
        except Exception:  # noqa: BLE001
            pass

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        name = self._theme_name_from_option_id(
            event.option.id if event.option else None
        )
        if name is None:
            return
        self._commit(name)

    def _commit(self, name: str) -> None:
        try:
            self.app.theme = name
            from sovereign_agent.cockpit import user_themes as ut
            from sovereign_agent.config import SETTINGS
            ut.set_active_theme_name(name, SETTINGS.paths.data_dir)
        except Exception:  # noqa: BLE001
            pass
        self._committed = True
        self.app.pop_screen()

    # ── interaction ──
    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "studio-exit-btn":
            self._revert_if_uncommitted()
            self.app.pop_screen(); return
        if bid == "theme-prev":
            self.query_one("#theme-list", OptionList).action_cursor_up()
        elif bid == "theme-next":
            self.query_one("#theme-list", OptionList).action_cursor_down()
        elif bid == "studio-create":
            self._committed = True  # opening the creator is a deliberate move on, not a revert
            self.app.pop_screen()
            self.app.push_screen(ThemeCreatorScreen())
        elif bid == "custom-edit":
            self._edit_current_custom()
        elif bid == "custom-remove":
            self._remove_current_custom()

    def _highlighted_custom_name(self) -> str | None:
        try:
            option_list = self.query_one("#theme-list", OptionList)
            option = option_list.get_option_at_index(option_list.highlighted)
        except Exception:  # noqa: BLE001
            return None
        name = self._theme_name_from_option_id(option.id if option else None)
        return name if name in self._customs else None

    def _current_custom_seed(self, name: str):
        try:
            from sovereign_agent.cockpit import user_themes as ut
            from sovereign_agent.config import SETTINGS
            t = ut.load(name, SETTINGS.paths.data_dir)
            if t is None:
                return None
            seed = {slot: getattr(t, slot, None) for slot, _ in SLOTS}
            return {k: v for k, v in seed.items() if v}
        except Exception:  # noqa: BLE001
            return None

    def _edit_current_custom(self) -> None:
        name = self._highlighted_custom_name()
        if name is None:
            self._toast("select a custom theme in the list first to edit it")
            return
        seed = self._current_custom_seed(name)
        self._committed = True
        self.app.pop_screen()
        self.app.push_screen(ThemeCreatorScreen(seed=seed, edit_name=name))

    def _remove_current_custom(self) -> None:
        name = self._highlighted_custom_name()
        if name is None:
            self._toast("select a custom theme in the list first to remove it")
            return
        try:
            from sovereign_agent.cockpit import user_themes as ut
            from sovereign_agent.config import SETTINGS
            ut.delete(name, SETTINGS.paths.data_dir)
        except Exception:  # noqa: BLE001
            pass
        if self._presets:
            try:
                self.app.theme = self._presets[0]
            except Exception:  # noqa: BLE001
                pass
        self._load()
        self._populate_list()
        self._toast(f"removed '{name}'")

    def _toast(self, msg: str) -> None:
        try:
            self.query_one("#studio-help", Static).update(f"[dim]{msg}[/dim]")
        except Exception:  # noqa: BLE001
            pass

    DEFAULT_CSS = """
    ThemeStudioScreen { align: center middle; background: $surface 60%; }
    #studio-modal {
        width: 68; height: 85%; padding: 1 2;
        border: thick $primary; background: $surface;
    }
    #studio-exit-btn { width: 100%; margin-bottom: 1; }
    #studio-title { text-style: bold; margin-bottom: 1; }
    #studio-help { height: 4; color: $text-muted; margin-bottom: 1; }
    #theme-list { height: 16; margin-bottom: 1; border: round $primary; }
    .carousel { height: 3; margin-bottom: 1; }
    .carousel Button { width: 6; }
    .carousel-label { width: 1fr; content-align: center middle; color: $text-muted; }
    #custom-actions { height: 3; margin-bottom: 1; }
    #custom-actions Button { width: 1fr; margin-right: 1; }
    ThemeStudioScreen Label { color: $text-muted; }
    #studio-create { width: 100%; }
    """
