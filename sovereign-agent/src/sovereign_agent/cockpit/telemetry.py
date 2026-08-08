"""
╔══════════════════════════════════════════════════════════════════════════╗
║  cockpit/telemetry.py — daily-rotated system-metrics log                 ║
║  v0.2.15.3 · Aria-Sovereign-V1                                            ║
║                                                                            ║
║  Every status refresh in the cockpit writes one JSON line to              ║
║  <data_dir>/telemetry/sys-YYYYMMDD.jsonl. The file rotates daily by       ║
║  filename — no rename gymnastics required, no cron, no logrotate.        ║
║                                                                            ║
║  Why JSONL: greppable, jq-able, append-only, every line stands alone.    ║
║  A line corrupted mid-write at process kill costs you one sample, not    ║
║  the day's file.                                                          ║
║                                                                            ║
║  Why daily rotation: a single file would grow unbounded. ~12 lines/min ×  ║
║  60 × 24 ≈ 17k lines/day, ~3-5 MB depending on field set. Daily rotation ║
║  keeps each file readable in a single `less` pass and lets the operator  ║
║  delete old days with `rm sys-20260501.jsonl` if they don't want the     ║
║  history. No magic retention policy.                                     ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .sysmon import SystemSnapshot


# Module-level lock — the cockpit only has one status worker but better safe.
_LOCK = threading.Lock()


def _telemetry_dir() -> Path:
    """Resolve <data_dir>/telemetry, creating it if missing.

    Falls back to AGENT_DATA env var, then to ~/.local/share/sovereign-agent.
    The fallback chain exists so this module is importable and testable
    without the full agent config being set up.
    """
    try:
        from ..config import SETTINGS
        base = SETTINGS.paths.data_dir
    except Exception:  # noqa: BLE001
        base = Path(
            os.environ.get("AGENT_DATA",
                           str(Path.home() / ".local/share/sovereign-agent"))
        )
    d = base / "telemetry"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _file_for(ts: datetime) -> Path:
    """Today's file by UTC date. Use UTC so day boundaries are unambiguous."""
    return _telemetry_dir() / f"sys-{ts.strftime('%Y%m%d')}.jsonl"


def snapshot_to_record(
    snap: SystemSnapshot,
    *,
    ts: Optional[datetime] = None,
    vram_total_mb: Optional[int] = None,
    vram_used_mb: Optional[int] = None,
    vram_temp_c: Optional[float] = None,
    extra: Optional[dict] = None,
) -> dict:
    """Convert a SystemSnapshot (+ VRAM context) into a flat dict for JSONL.

    Flat keys, primitive values only — keeps JSONL records grep/jq-friendly
    and prevents any nested-object ambiguity. None values are dropped so
    older days' files don't have null columns from features that didn't
    exist yet.
    """
    ts = ts or datetime.now(timezone.utc)
    rec: dict = {
        "ts": ts.isoformat(timespec="seconds"),
        "cpu_pct": round(snap.cpu_percent, 1),
        "load_1m": round(snap.load_1m, 2),
        "load_5m": round(snap.load_5m, 2),
        "load_15m": round(snap.load_15m, 2),
        "cpu_count": snap.cpu_count,
        "ram_pct": round(snap.mem_percent, 1),
        "ram_used_mb": snap.mem_used // (1024 * 1024),
        "ram_total_mb": snap.mem_total // (1024 * 1024),
        "swap_pct": round(snap.swap_percent, 1),
        "disk_pct": round(snap.disk_percent, 1),
        "disk_free_mb": snap.disk_free // (1024 * 1024),
        "disk_total_mb": snap.disk_total // (1024 * 1024),
        "uptime_s": int(snap.uptime_seconds),
    }
    if snap.cpu_temp_c is not None:
        rec["cpu_temp_c"] = round(snap.cpu_temp_c, 1)
    if vram_total_mb is not None and vram_total_mb > 0:
        rec["vram_total_mb"] = int(vram_total_mb)
        if vram_used_mb is not None:
            rec["vram_used_mb"] = int(vram_used_mb)
            rec["vram_pct"] = round(100.0 * vram_used_mb / vram_total_mb, 1)
    if vram_temp_c is not None:
        rec["vram_temp_c"] = round(vram_temp_c, 1)
    if snap.error:
        rec["error"] = snap.error
    if extra:
        # `extra` is for the per-task context: continuation_id, task_label,
        # phase ("start"/"end"), Δvram, duration_s, etc.
        rec.update(extra)
    return rec


def write_sample(
    snap: SystemSnapshot,
    *,
    vram_total_mb: Optional[int] = None,
    vram_used_mb: Optional[int] = None,
    vram_temp_c: Optional[float] = None,
    extra: Optional[dict] = None,
) -> Optional[Path]:
    """Append one telemetry record. Returns the file path, or None on error.

    Never raises — telemetry must not break the cockpit. Errors during
    write are silently dropped (the next sample will succeed if the issue
    was transient; if it's persistent the operator's missing data will
    tell them). The status worker logs nothing.
    """
    try:
        ts = datetime.now(timezone.utc)
        rec = snapshot_to_record(
            snap, ts=ts,
            vram_total_mb=vram_total_mb,
            vram_used_mb=vram_used_mb,
            vram_temp_c=vram_temp_c,
            extra=extra,
        )
        path = _file_for(ts)
        with _LOCK:
            # Open-append-close per write — slow if there were thousands per
            # second, but at 5s cadence the overhead is irrelevant and we
            # avoid carrying an open file across the cockpit's lifetime.
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, separators=(",", ":")) + "\n")
        return path
    except Exception:  # noqa: BLE001
        return None


# ── Reading & summary helpers (used by `sov telemetry ...`) ────────────────


def tail_today(n: int = 50) -> list[dict]:
    """Return the last N records from today's telemetry file."""
    path = _file_for(datetime.now(timezone.utc))
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return []
    rows: list[dict] = []
    for line in lines[-n:]:
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def summarise(days: int = 1) -> dict:
    """Compute min/avg/max for headline metrics across the last N days.

    Returns a dict like:
        {
          "files_read": 3,
          "sample_count": 15021,
          "ts_first": "...",
          "ts_last": "...",
          "cpu_pct":  {"min": 0.5, "avg": 12.4, "max": 88.1},
          "ram_pct":  {...},
          "vram_pct": {...},
          "cpu_temp_c": {...},
          ...
        }
    """
    end = datetime.now(timezone.utc).date()
    metrics: dict[str, list[float]] = {}
    files_read = 0
    sample_count = 0
    ts_first: Optional[str] = None
    ts_last: Optional[str] = None

    from datetime import timedelta
    for delta in range(days):
        day = end - timedelta(days=delta)
        path = _telemetry_dir() / f"sys-{day.strftime('%Y%m%d')}.jsonl"
        if not path.exists():
            continue
        files_read += 1
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    sample_count += 1
                    ts = rec.get("ts", "")
                    if ts:
                        if ts_first is None or ts < ts_first:
                            ts_first = ts
                        if ts_last is None or ts > ts_last:
                            ts_last = ts
                    for key in ("cpu_pct", "cpu_temp_c", "ram_pct",
                                "vram_pct", "vram_temp_c", "disk_pct",
                                "load_1m", "swap_pct"):
                        v = rec.get(key)
                        if isinstance(v, (int, float)):
                            metrics.setdefault(key, []).append(float(v))
        except OSError:
            continue

    out: dict = {
        "files_read": files_read,
        "sample_count": sample_count,
        "ts_first": ts_first,
        "ts_last": ts_last,
    }
    for key, values in metrics.items():
        if values:
            out[key] = {
                "min": round(min(values), 1),
                "avg": round(sum(values) / len(values), 1),
                "max": round(max(values), 1),
                "n": len(values),
            }
    return out


def current_path() -> Path:
    """Return today's telemetry file path (whether or not it exists yet)."""
    return _file_for(datetime.now(timezone.utc))
