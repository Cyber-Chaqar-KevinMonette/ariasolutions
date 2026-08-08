"""rest_point.py — the safe-exit bookmark. (Fable round F7.)

Kevin: *"a safe exit command that sets a resume point for Aria — or a
better god tier version."* The god-tier version: an exit is a BOOKMARK,
never an amputation. `/rest` pauses any running session at the next safe
boundary (the engine's own Gate-2 discipline — never mid-tool-call),
writes this resume point, and only then exits; the next wake reads it and
offers `/resume` with a heart.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def _path(data_dir: Path | None = None) -> Path:
    if data_dir is None:
        from sovereign_agent.config import SETTINGS

        data_dir = SETTINGS.paths.data_dir
    return Path(data_dir) / "resume_point.json"


def write_rest_point(*, session_id: str = "", goal: str = "", note: str = "",
                     data_dir: Path | None = None) -> Path:
    path = _path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({
        "rested_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "session_id": session_id,
        "goal": goal[:200],
        "note": note[:300],
    }, indent=1), encoding="utf-8")
    tmp.replace(path)
    return path


def consume_rest_point(data_dir: Path | None = None) -> dict | None:
    """Read-and-clear: the wake greeting surfaces a rest point exactly once.
    None when there is nothing to surface. Never raises."""
    try:
        path = _path(data_dir)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        path.unlink(missing_ok=True)
        return data
    except Exception:  # noqa: BLE001
        return None
