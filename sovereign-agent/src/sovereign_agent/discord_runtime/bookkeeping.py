"""bookkeeping — per-bot ledgers, source-health telemetry, and timely
compaction. "Organized, clean, and timely" as code (R5).

Three responsibilities, all per-project under `<data>/bot_projects/<slug>/`:

  • **source_health.json** — the fetch-outcome telemetry (R5a). Every fetch
    records ok/error; consecutive failures accumulate, so a dead link (HTTP
    404 twelve polls in a row) is *distinguishable* from a merely quiet feed.
    `bot_health` reads this to say "link looks dead" with evidence.
  • **ledger.json** — one bot's book of record: created_at, lifetime alert /
    failure totals, last delivery, capabilities/API notes, last compaction.
    Small, human-readable, updated by compaction and (optionally) by hand.
  • **compact_runs()** — `runs.jsonl` grows forever without this. Lines older
    than `keep_days` are rolled up into ONE summary line per month (cycles /
    alerts / failures totals — audit truth preserved in aggregate, file stays
    small). Atomic rewrite. The fleet daemon calls `compact_all_projects()`
    once per day-boundary — timeliness is automated, not remembered.

Rollup lines carry `"rollup": true` and the ts of the newest line they
absorbed, so windowed stats (shop_stats, 30-day) naturally exclude them and
"last delivery age" stays truthful.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from sovereign_agent.bot_projects import projects_dir, slugify

__all__ = [
    "record_fetch_outcome",
    "read_source_health",
    "read_ledger",
    "update_ledger",
    "compact_runs",
    "compact_all_projects",
]

FAILING_THRESHOLD = 3        # consecutive failures before "link looks dead"


def _proj_dir(data_dir: Path, project_name: str) -> Path:
    d = projects_dir(data_dir) / slugify(project_name)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_json(path: Path, payload) -> None:
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                   encoding="utf-8")
    with open(tmp, "r+", encoding="utf-8") as fh:
        fh.flush()
        os.fsync(fh.fileno())
    tmp.replace(path)


def _read_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


# ── source health (R5a) ─────────────────────────────────────────────────────
def record_fetch_outcome(data_dir: Path, project_name: str, source_name: str,
                         ok: bool, detail: str = "", *,
                         now: float | None = None) -> None:
    """Record one fetch outcome. Never raises (called from the poll loop)."""
    try:
        now = time.time() if now is None else now
        path = _proj_dir(data_dir, project_name) / "source_health.json"
        health = _read_json(path)
        entry = health.get(source_name) or {
            "last_ok_ts": None, "last_error_ts": None, "last_error": "",
            "consecutive_failures": 0, "total_failures": 0, "total_ok": 0,
        }
        if ok:
            entry["last_ok_ts"] = now
            entry["consecutive_failures"] = 0
            entry["total_ok"] = int(entry.get("total_ok", 0)) + 1
        else:
            entry["last_error_ts"] = now
            entry["last_error"] = str(detail)[:120]
            entry["consecutive_failures"] = int(entry.get("consecutive_failures", 0)) + 1
            entry["total_failures"] = int(entry.get("total_failures", 0)) + 1
        health[source_name] = entry
        _write_json(path, health)
    except Exception:  # noqa: BLE001
        pass


def read_source_health(data_dir: Path, project_name: str) -> dict:
    return _read_json(projects_dir(data_dir) / slugify(project_name)
                      / "source_health.json")


def make_outcome_recorder(data_dir: Path, project_name: str):
    """The on_outcome hook build_runtime installs on real fetchers."""
    def recorder(source_name: str, ok: bool, detail: str) -> None:
        record_fetch_outcome(data_dir, project_name, source_name, ok, detail)
    return recorder


# ── the ledger ───────────────────────────────────────────────────────────────
def read_ledger(data_dir: Path, project_name: str) -> dict:
    return _read_json(_proj_dir(data_dir, project_name) / "ledger.json")


def update_ledger(data_dir: Path, project_name: str, **fields) -> dict:
    """Merge fields into the bot's ledger (numeric *_total fields add)."""
    path = _proj_dir(data_dir, project_name) / "ledger.json"
    ledger = _read_json(path)
    if not ledger:
        ledger = {"created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                  "lifetime_alerts": 0, "lifetime_failures": 0,
                  "last_delivery_ts": None, "last_compaction_ts": None,
                  "capabilities": {}, "notes": ""}
    for k, v in fields.items():
        if k in ("lifetime_alerts", "lifetime_failures") and isinstance(v, int):
            ledger[k] = int(ledger.get(k, 0)) + v          # totals accumulate
        elif k == "capabilities" and isinstance(v, dict):
            caps = ledger.get("capabilities") or {}
            caps.update(v)
            ledger["capabilities"] = caps
        else:
            ledger[k] = v
    ledger["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    _write_json(path, ledger)
    return ledger


# ── compaction (timeliness, automated) ───────────────────────────────────────
_DAY = 86400.0


def _month_of(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m")


def compact_runs(data_dir: Path, project_name: str, *, keep_days: int = 30,
                 now: float | None = None) -> dict:
    """Roll runs.jsonl lines older than keep_days into one summary line per
    month. Returns {"compacted": n, "kept": m}. Atomic; audit truth preserved
    in aggregate; lifetime totals flow into the ledger."""
    now = time.time() if now is None else now
    path = _proj_dir(data_dir, project_name) / "runs.jsonl"
    if not path.is_file():
        return {"compacted": 0, "kept": 0}
    cutoff = now - keep_days * _DAY
    months: dict[str, dict] = {}
    kept_lines: list[str] = []
    compacted = alerts = failures = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:  # noqa: BLE001 — torn line: drop during compaction
            continue
        ts = float(rec.get("ts", 0))
        if rec.get("rollup") or ts >= cutoff:
            kept_lines.append(json.dumps(rec, ensure_ascii=False))
            continue
        # roll this old line into its month
        m = months.setdefault(_month_of(ts), {
            "rollup": True, "month": _month_of(ts), "ts": ts,
            "cycles": 0, "alerts": 0, "failures": 0})
        m["ts"] = max(m["ts"], ts)              # rollup carries newest absorbed ts
        m["cycles"] += 1
        for d in rec.get("deliveries", []) or []:
            if d.get("sent") or d.get("dry_run"):
                m["alerts"] += 1
                alerts += 1
            else:
                m["failures"] += 1
                failures += 1
        compacted += 1
    if compacted == 0:
        return {"compacted": 0, "kept": len(kept_lines)}
    rollup_lines = [json.dumps(months[k], ensure_ascii=False) for k in sorted(months)]
    tmp = path.with_suffix(".jsonl.tmp")
    tmp.write_text("\n".join(rollup_lines + kept_lines) + "\n", encoding="utf-8")
    with open(tmp, "r+", encoding="utf-8") as fh:
        fh.flush()
        os.fsync(fh.fileno())
    tmp.replace(path)
    update_ledger(data_dir, project_name,
                  lifetime_alerts=alerts, lifetime_failures=failures,
                  last_compaction_ts=now)
    return {"compacted": compacted, "kept": len(kept_lines)}


def compact_all_projects(data_dir: Path, *, keep_days: int = 30,
                         now: float | None = None) -> dict[str, dict]:
    """Compact every defined bot. Called by the daemon at day boundaries."""
    from sovereign_agent.bot_projects import list_all
    out: dict[str, dict] = {}
    for p in list_all(data_dir):
        try:
            out[p.project_name] = compact_runs(data_dir, p.project_name,
                                               keep_days=keep_days, now=now)
        except Exception:  # noqa: BLE001 — one bot's books can't block the rest
            out[p.project_name] = {"error": True}
    return out
