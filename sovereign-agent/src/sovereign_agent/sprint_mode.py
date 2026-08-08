"""sprint_mode.py — an ADDITIVE, per-slot model override for testing,
never a replacement for the main model configuration.

Kevin, 2026-07-21 (a rapid-fire design conversation, quoted in the order
it landed):
  "I want a sprint mode we can use for testing. Doesn't replace our main
  modes or functions. It only uses a different configurations of models.
  The fastest free and open source models we can use... So we don't
  replace old systems... I should be able to use sprint mode with all
  other modes... both reversable."
  "add a model configure menu, and have modes"
  "or preselect configurations"
  "have drop down menus for each model configuration slot, and have it
  show all of the ollama models downloaded on the system"
  "presets, or custom mode, or custom slots"

Root cause this exists for: `aria-orchestrator` (5.2GB) doesn't fully fit
in an 8GB GTX 1070's VRAM (measured live this session via `ollama ps`'s
PROCESSOR column: ~25-27%/73-75% GPU/CPU split), so most of its
computation runs on CPU — much slower. This gives Kevin a fast, fully
reversible way to swap in a smaller model per SLOT for quick iteration,
without ever touching SETTINGS or the model_ladder.py vault (that's the
DELIBERATE, proven-then-promoted path for a permanent change — this is
the opposite: instant, reversible, testing-only).

Two ways to use it, both landing in the same one state file:
  - PRESETS: one click sets the orchestrator slot to a known-good small
    model (every model listed was confirmed present via `ollama list`,
    never guessed).
  - Custom slots: any of model_ladder.py's own SLOTS
    (orchestrator/coder/fast/reflector/interpreter/vision) can be pointed
    at ANY locally-installed Ollama model, independently.

Same flag-file discipline as interrupts.py: a small JSON file under
config_dir; missing/corrupt file = every slot at its SETTINGS default,
the safe fallback; a read/write failure never crashes a caller.
"""
from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .config import SETTINGS

_STATE_FILE = "sprint_mode.json"

# Mirrors model_ladder.py's own slot list — the same six roles, so a
# custom slot override here composes with everything that module already
# knows about, rather than inventing a second taxonomy.
SLOTS = ("orchestrator", "coder", "fast", "reflector", "interpreter", "vision")

_SLOT_SETTINGS_ATTR = {
    "orchestrator": "orchestrator_model",
    "coder": "coder_model",
    "fast": "fast_model",
    "reflector": "reflector_model",
    "interpreter": "interpreter_model",
    "vision": "vision_model",
}


@dataclass(frozen=True)
class SprintPreset:
    key: str
    title: str
    model: str
    note: str


# Every model here was confirmed present via `ollama list` on Kevin's
# machine (2026-07-21) -- no guessing, no unpulled models offered.
# Smallest first: qwen3.5:2b is the fastest available; aria-fast is
# Aria's own small tuned model, kept last as the "closest to her voice"
# option rather than the raw speed champion.
PRESETS: dict[str, SprintPreset] = {
    "sprint-2b": SprintPreset(
        key="sprint-2b", title="Sprint · qwen3.5:2b",
        model="qwen3.5:2b",
        note="fastest — smallest footprint, fits VRAM easily",
    ),
    "sprint-4b": SprintPreset(
        key="sprint-4b", title="Sprint · qwen3.5:4b",
        model="qwen3.5:4b",
        note="a step up in quality, still small and fast",
    ),
    "sprint-phi4": SprintPreset(
        key="sprint-phi4", title="Sprint · phi4-mini:3.8b",
        model="phi4-mini:3.8b",
        note="Microsoft's small model — good instruction-following",
    ),
    "sprint-fast": SprintPreset(
        key="sprint-fast", title="Sprint · aria-fast",
        model="aria-fast:latest",
        note="Aria's own tuned fast model — closest to her usual voice",
    ),
}


def _state_path() -> Path:
    return SETTINGS.paths.config_dir / _STATE_FILE


def _read_state() -> dict:
    try:
        data = json.loads(_state_path().read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (OSError, ValueError):
        pass
    return {}


def _write_state(data: dict) -> None:
    d = SETTINGS.paths.config_dir
    d.mkdir(parents=True, exist_ok=True)
    _state_path().write_text(json.dumps(data, indent=2), encoding="utf-8")


def list_installed_models(timeout: float = 3.0) -> list[str]:
    """Every model Ollama actually has pulled, live — never a hardcoded
    guess. Degrades honestly: no Ollama reachable → empty list, not an
    exception (a picker screen shows 'no models found', it doesn't crash)."""
    try:
        url = f"{SETTINGS.ollama_host.rstrip('/')}/api/tags"
        with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310 — local ollama only
            data = json.loads(resp.read().decode("utf-8"))
        names = [m.get("name", "") for m in data.get("models", [])]
        return sorted(n for n in names if n)
    except Exception:  # noqa: BLE001
        return []


def status() -> dict:
    """The full picture: which preset (if any) is active, and every
    slot's effective model (override or SETTINGS default) plus whether
    that slot IS overridden."""
    state = _read_state()
    overrides = state.get("overrides", {})
    preset_key = state.get("preset")
    if preset_key not in PRESETS:
        preset_key = None
    slots = {}
    for slot in SLOTS:
        default = getattr(SETTINGS, _SLOT_SETTINGS_ATTR[slot])
        override = overrides.get(slot)
        slots[slot] = {
            "model": override or default,
            "default": default,
            "overridden": override is not None,
        }
    return {"active": bool(preset_key) or bool(overrides),
            "preset": preset_key, "slots": slots}


def activate_preset(preset_key: str) -> SprintPreset:
    """One click: the orchestrator slot (the one that drives /work
    sessions) points at a known-good small model. Raises KeyError with
    the valid choices listed if the preset doesn't exist -- never
    silently substitutes one the operator didn't ask for."""
    preset = PRESETS.get(preset_key)
    if preset is None:
        raise KeyError(
            f"unknown sprint preset {preset_key!r} — choices: "
            f"{', '.join(PRESETS)}"
        )
    state = _read_state()
    state["preset"] = preset_key
    overrides = dict(state.get("overrides", {}))
    overrides["orchestrator"] = preset.model
    state["overrides"] = overrides
    _write_state(state)
    return preset


def set_slot_override(slot: str, model: str) -> None:
    """Custom mode: point exactly one slot at exactly one installed
    model, independent of any preset."""
    if slot not in SLOTS:
        raise KeyError(f"unknown slot {slot!r} — choices: {', '.join(SLOTS)}")
    state = _read_state()
    overrides = dict(state.get("overrides", {}))
    overrides[slot] = model
    state["overrides"] = overrides
    state["preset"] = None  # a manual slot edit is no longer "just" a preset
    _write_state(state)


def clear_slot_override(slot: str) -> None:
    """Reset one slot back to its SETTINGS default. Harmless no-op if it
    was never overridden."""
    state = _read_state()
    overrides = dict(state.get("overrides", {}))
    overrides.pop(slot, None)
    state["overrides"] = overrides
    if slot == "orchestrator":
        state["preset"] = None
    _write_state(state)


def deactivate() -> None:
    """Turn everything off — every slot back to its SETTINGS default,
    the same reversible on/off as interrupts.py's
    clear_conversation_request()."""
    _state_path().unlink(missing_ok=True)


def model_override(slot: str = "orchestrator") -> str | None:
    """The one thing most callers actually need: None when that slot has
    no override (the overwhelming default case), else the model name to
    use INSTEAD of its SETTINGS default for this call. Never raises -- a
    caller mid-loop must never crash because of a testing convenience."""
    try:
        overrides = _read_state().get("overrides", {})
        return overrides.get(slot) or None
    except Exception:  # noqa: BLE001 — degrade honestly, never crash the loop
        return None
