"""lab_slot.py — a dedicated slot for whatever model is currently being
worked on, experimented with, fine-tuned, or bulked up — kept completely
separate from her 6 production roles.

Kevin, 2026-07-21: "add a new configuration slot called fine-tuned/
bulking slot. So we can keep our main working AIs but have a configured
slot for open sourced AIs we are working with... or working on or
experimenting on, fine tuning, bulking."

Deliberately NOT part of model_corps.bases.json (the 6 production roles:
orchestrator/coder/fast/reflector/interpreter/vision) and NOT part of
model_ladder.py's prove-then-promote system (which is specifically for
proving a BIGGER version of an EXISTING production role, then swapping
that role to it). This is simpler and more general: one free-standing
pointer to "whatever's in the lab right now" — a fine-tuned LoRA adapter,
a fresh pull you're evaluating, anything — that never touches or risks
the production roster no matter what state it's in.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LabSlot:
    model: str | None
    note: str
    set_at: str | None

    @property
    def is_set(self) -> bool:
        return self.model is not None


def _path() -> Path:
    from .config import SETTINGS
    return SETTINGS.paths.config_dir / "lab_slot.json"


def get_lab_slot() -> LabSlot:
    """Read the current lab slot. Safe to call any time — a missing or
    corrupt file just means the slot is empty, never an exception."""
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
        return LabSlot(
            model=data.get("model"), note=data.get("note", ""),
            set_at=data.get("set_at"),
        )
    except (OSError, ValueError):
        return LabSlot(model=None, note="", set_at=None)


def set_lab_slot(model: str, *, note: str = "") -> LabSlot:
    """Point the lab slot at a model — anything: an Ollama tag, a local
    adapter path, a HuggingFace repo id. Never touches production
    (bases.json, the vault's AGENT_<SLOT>_MODEL entries) — this is
    purely observational bookkeeping for what you're currently
    evaluating."""
    from datetime import datetime, timezone

    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"model": model, "note": note,
            "set_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(path)
    return get_lab_slot()


def clear_lab_slot() -> None:
    """Empty the slot — a harmless no-op if it was never set."""
    _path().unlink(missing_ok=True)


__all__ = ["LabSlot", "get_lab_slot", "set_lab_slot", "clear_lab_slot"]
