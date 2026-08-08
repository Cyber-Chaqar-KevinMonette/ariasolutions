"""cockpit/game_window_pref.py — the game window's optional-visual toggle.

Kevin, 2026-07-25: "make the game menu optional because it is kinda
wasting space. An optional visual." A tiny persisted boolean, same
read/write shape as every other small cockpit preference (cloud_mode.py)
— visible by default (the window is a real, useful feature, not hidden
until discovered), toggled off with one click when it's in the way.
"""
from __future__ import annotations

import json
from pathlib import Path


def _path(data_dir: Path | None = None) -> Path:
    if data_dir is None:
        from sovereign_agent.config import SETTINGS
        data_dir = SETTINGS.paths.data_dir
    return Path(data_dir) / "game_window_pref.json"


def is_visible(data_dir: Path | None = None) -> bool:
    """True (the default) unless explicitly turned off."""
    try:
        data = json.loads(_path(data_dir).read_text(encoding="utf-8"))
        return bool(data.get("visible", True))
    except Exception:  # noqa: BLE001
        return True


def set_visible(visible: bool, *, data_dir: Path | None = None) -> None:
    p = _path(data_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"visible": bool(visible)}, indent=2), encoding="utf-8")
    tmp.replace(p)


__all__ = ["is_visible", "set_visible"]
