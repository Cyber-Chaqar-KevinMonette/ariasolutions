"""cockpit/model_menu_screen.py — F8 / `/model`: pick a model configuration.

Kevin, 2026-07-21 (design conversation, in order):
  "add a model configure menu, and have modes[,] or preselect
  configurations." "have drop down menus for each model configuration
  slot, and have it show all of the ollama models downloaded on the
  system." "presets, or custom mode, or custom slots"

Three screens, same proven ModalScreen/list shape as ModesScreen
(modes_crown_ui.py) and the theme studio's list+picker
(theme_studio_screen.py):

  ModelMenuScreen      — top level: Standard, each sprint preset, or
                         "Custom slots...".
  ModelSlotsScreen     — one row per model_ladder.py SLOT
                         (orchestrator/coder/fast/reflector/interpreter/
                         vision) showing its current effective model.
  ModelSlotPickerScreen — the "dropdown": every Ollama model actually
                         installed on this machine (live via
                         sprint_mode.list_installed_models(), never a
                         hardcoded guess), pick one to override that slot.

Glyph safety: this session found "●"/"○" (U+25CF/U+25CB, both East-Asian-
Width=Ambiguous) genuinely unsafe and NOT on the de-facto-narrow
whitelist -- confirmed directly via unicodedata, not assumed from
modes_crown_ui.py's own (older, unfixed) use of the same pair. Every
"current selection" marker here uses glyphs.BULLET (•, confirmed safe)
for the active row and a plain space for every other row, matching the
convention theme_studio_screen.py already established when it fixed this
exact bug.
"""
from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Static

from sovereign_agent.glyphs import BULLET


class _HandoffButton(Button):
    """Fire-and-close button -- not a sustained focus target. Local copy
    of app.py's MenuTriggerButton; app.py imports this module, so
    importing back from .app would be circular (feedback_cockpit_button_focus)."""
    can_focus = False


class SlotButton(_HandoffButton):
    """One slot row on ModelSlotsScreen. Carries the slot name."""

    def __init__(self, slot: str, label: str) -> None:
        super().__init__(label, id=f"slot-{slot}", classes="slot-choice-btn")
        self.slot = slot


class ModelChoiceButton(_HandoffButton):
    """One installed model on ModelSlotPickerScreen. Carries the model name."""

    def __init__(self, slot: str, model: str, label: str) -> None:
        safe_id = "pick-" + "".join(
            c if (c.isalnum() or c == "-") else "-" for c in model
        )[-40:]
        super().__init__(label, id=safe_id, classes="model-choice-btn")
        self.slot = slot
        self.model = model


class ModelMenuScreen(ModalScreen):
    """◊ Model → Standard, a sprint preset, or Custom slots. Esc/q to close."""

    BINDINGS = [Binding("escape,q", "close_models", "close")]

    CSS = """
    ModelMenuScreen { align: center middle; }
    #model-modal {
        width: 78; max-height: 80%;
        background: $surface; border: round $primary;
        padding: 1 2;
    }
    #model-scroll { max-height: 24; }
    ModelMenuScreen Button { width: 100%; margin-bottom: 0; }
    """

    def action_close_models(self) -> None:
        self.app.pop_screen()

    def on_key(self, event) -> None:
        if event.key in ("escape",):
            event.stop()
            event.prevent_default()
            self.app.pop_screen()

    def compose(self) -> ComposeResult:
        from sovereign_agent.sprint_mode import PRESETS, status

        state = status()
        active_preset = state["preset"]
        any_override = state["active"]
        with Vertical(id="model-modal"):
            yield Static(
                "[b]◊ Model[/b]  [dim]testing configurations -- never "
                "replaces the standard setup[/dim]",
                id="model-title")
            with VerticalScroll(id="model-scroll"):
                marker = BULLET if not any_override else " "
                yield _HandoffButton(
                    f"{marker} Standard — every slot at its default",
                    id="model-standard")
                for preset in PRESETS.values():
                    marker = BULLET if preset.key == active_preset else " "
                    yield _HandoffButton(
                        f"{marker} {preset.title} — {preset.note}",
                        id=f"model-{preset.key}")
                marker = BULLET if (any_override and not active_preset) else " "
                yield _HandoffButton(
                    f"{marker} Custom slots… — pick a model per slot",
                    id="model-custom")

    def on_button_pressed(self, event) -> None:
        event.stop()
        button_id = getattr(event.button, "id", "") or ""
        from sovereign_agent.sprint_mode import PRESETS, activate_preset, deactivate

        if button_id == "model-standard":
            deactivate()
            self._confirm("Standard", "every slot at its default")
            return
        if button_id == "model-custom":
            self.app.pop_screen()
            self.app.push_screen(ModelSlotsScreen())
            return
        if button_id.startswith("model-"):
            key = button_id[len("model-"):]
            preset = PRESETS.get(key)
            if preset is None:
                return
            activate_preset(key)
            self._confirm(preset.title, preset.model)
            return
        self.app.pop_screen()

    def _confirm(self, title: str, detail: str) -> None:
        try:
            self.app._write_meta(  # noqa: SLF001 — the cockpit's own meta line
                f"[bold magenta]◊ model → {title}[/bold magenta] [dim]{detail}[/dim]")
        except Exception:  # noqa: BLE001
            pass
        self.app.pop_screen()


class ModelSlotsScreen(ModalScreen):
    """Custom mode: every slot, its current effective model, click to
    change it. Esc/q to close; "‹ back" returns to ModelMenuScreen."""

    BINDINGS = [Binding("escape,q", "close_slots", "close")]

    CSS = """
    ModelSlotsScreen { align: center middle; }
    #slots-modal {
        width: 84; max-height: 80%;
        background: $surface; border: round $primary;
        padding: 1 2;
    }
    #slots-scroll { max-height: 24; }
    ModelSlotsScreen Button { width: 100%; margin-bottom: 0; }
    """

    def action_close_slots(self) -> None:
        self.app.pop_screen()

    def on_key(self, event) -> None:
        if event.key in ("escape",):
            event.stop()
            event.prevent_default()
            self.app.pop_screen()

    def compose(self) -> ComposeResult:
        from sovereign_agent.sprint_mode import SLOTS, status

        state = status()
        with Vertical(id="slots-modal"):
            yield Static(
                "[b]◊ Custom slots[/b]  [dim]pick a model per role — "
                "click a slot to choose from every model installed here[/dim]",
                id="slots-title")
            with VerticalScroll(id="slots-scroll"):
                yield _HandoffButton("‹ back", id="slots-back")
                for slot in SLOTS:
                    info = state["slots"][slot]
                    tag = "[dim](overridden)[/dim]" if info["overridden"] else ""
                    yield SlotButton(slot, f"{slot}: {info['model']} {tag}")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == "slots-back":
            self.app.pop_screen()
            self.app.push_screen(ModelMenuScreen())
            return
        slot = getattr(event.button, "slot", None)
        if not slot:
            return
        self.app.pop_screen()
        self.app.push_screen(ModelSlotPickerScreen(slot))


class ModelSlotPickerScreen(ModalScreen):
    """The dropdown: every model Ollama actually has installed, for ONE
    slot. Esc/q to close (no change); "‹ back" returns to the slot list;
    "✕ reset to default" clears any override for this slot."""

    BINDINGS = [Binding("escape,q", "close_picker", "close")]

    CSS = """
    ModelSlotPickerScreen { align: center middle; }
    #picker-modal {
        width: 84; max-height: 80%;
        background: $surface; border: round $primary;
        padding: 1 2;
    }
    #picker-scroll { max-height: 24; }
    ModelSlotPickerScreen Button { width: 100%; margin-bottom: 0; }
    """

    def __init__(self, slot: str) -> None:
        super().__init__()
        self.slot = slot

    def action_close_picker(self) -> None:
        self.app.pop_screen()

    def on_key(self, event) -> None:
        if event.key in ("escape",):
            event.stop()
            event.prevent_default()
            self.app.pop_screen()

    def compose(self) -> ComposeResult:
        from sovereign_agent.sprint_mode import list_installed_models, status

        models = list_installed_models()
        state = status()
        current = state["slots"][self.slot]["model"]
        with Vertical(id="picker-modal"):
            yield Static(
                f"[b]◊ {self.slot}[/b]  [dim]choose an installed model "
                f"({len(models)} found)[/dim]",
                id="picker-title")
            with VerticalScroll(id="picker-scroll"):
                yield _HandoffButton("‹ back", id="picker-back")
                yield _HandoffButton("✕ reset to default", id="picker-reset")
                if not models:
                    yield Static(
                        "[dim]no models found — is Ollama running? "
                        "(`ollama list` on the host)[/dim]",
                        id="picker-empty")
                for model in models:
                    marker = BULLET if model == current else " "
                    yield ModelChoiceButton(self.slot, model, f"{marker} {model}")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == "picker-back":
            self.app.pop_screen()
            self.app.push_screen(ModelSlotsScreen())
            return
        from sovereign_agent.sprint_mode import clear_slot_override, set_slot_override

        if event.button.id == "picker-reset":
            clear_slot_override(self.slot)
            self._confirm(f"{self.slot} → default")
            return
        model = getattr(event.button, "model", None)
        if not model:
            return
        set_slot_override(self.slot, model)
        self._confirm(f"{self.slot} → {model}")

    def _confirm(self, detail: str) -> None:
        try:
            self.app._write_meta(f"[bold magenta]◊ model[/bold magenta] [dim]{detail}[/dim]")  # noqa: SLF001
        except Exception:  # noqa: BLE001
            pass
        self.app.pop_screen()
        self.app.push_screen(ModelSlotsScreen())
