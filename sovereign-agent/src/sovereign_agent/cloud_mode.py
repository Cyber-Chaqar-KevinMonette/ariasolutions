"""cloud_mode.py — the "Fast Free Cloud" toggle.

Kevin, 2026-07-25: "let's add a fast free cloud mode?" A deliberate,
explicit switch (never automatic/silent) — the operator turns it on, and
until they turn it off Aria's chat turns route through pooled free-tier
cloud providers (via `cloud_client.CloudClient`) instead of the local
Ollama model, for speed. Off is the permanent default; nothing leaves this
machine unless the operator has explicitly opted in.

One JSON flag file, same read/write shape as every other small toggle in
this codebase (auto_crown.py's trust-tier file, mode_crown's crown file) —
no database, no daemon, just a fact on disk.
"""
from __future__ import annotations

import json
from pathlib import Path


def _path(data_dir: Path | None = None) -> Path:
    if data_dir is None:
        from sovereign_agent.config import SETTINGS
        data_dir = SETTINGS.paths.data_dir
    return Path(data_dir) / "cloud_mode.json"


def is_cloud_mode_enabled(data_dir: Path | None = None) -> bool:
    """False (local-only) unless explicitly turned on. Never raises — a
    missing/corrupt flag file just means "not enabled"."""
    try:
        data = json.loads(_path(data_dir).read_text(encoding="utf-8"))
        return bool(data.get("enabled", False))
    except Exception:  # noqa: BLE001
        return False


def set_cloud_mode(enabled: bool, *, data_dir: Path | None = None) -> None:
    """The operator's explicit on/off act. Atomic write (tmp + replace),
    same durability pattern as every other state file here."""
    p = _path(data_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"enabled": bool(enabled)}, indent=2), encoding="utf-8")
    tmp.replace(p)


__all__ = ["is_cloud_mode_enabled", "set_cloud_mode"]
