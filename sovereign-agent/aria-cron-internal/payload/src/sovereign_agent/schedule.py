"""
schedule.py — Internal cron scheduler for Aria (aria-cron-internal)

Stores named schedules in schedule.yaml (config_dir). On each busy loop
cycle, `check_and_inject_due()` fires any due entries into the backlog.

Cron format: standard 5-field "min hour dom mon dow" with support for:
  * (wildcard), */N (step), and exact values. No ranges, no lists —
  keep it simple for the operator's lifetime of use.

No external deps beyond stdlib + yaml (already in pyproject.toml).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml


# ─── Cron matching ───────────────────────────────────────────────────────────


def _field_matches(spec: str, value: int) -> bool:
    """Does cron field spec match value?

    Supports: *, */N, exact integer.
    Examples: "*" → always True; "*/15" → value % 15 == 0; "8" → value == 8.
    """
    spec = spec.strip()
    if spec == "*":
        return True
    if spec.startswith("*/"):
        try:
            step = int(spec[2:])
            return step > 0 and value % step == 0
        except ValueError:
            return False
    try:
        return int(spec) == value
    except ValueError:
        return False


def cron_matches(cron_expr: str, dt: datetime) -> bool:
    """True if the datetime matches the 5-field cron expression.

    Field order: min hour dom month dow (0=Sunday).
    """
    parts = cron_expr.strip().split()
    if len(parts) != 5:
        return False
    min_spec, hour_spec, dom_spec, mon_spec, dow_spec = parts
    # datetime.weekday(): 0=Monday; cron dow: 0=Sunday
    # Convert: cron_dow = (weekday + 1) % 7
    cron_dow = (dt.weekday() + 1) % 7
    return (
        _field_matches(min_spec, dt.minute)
        and _field_matches(hour_spec, dt.hour)
        and _field_matches(dom_spec, dt.day)
        and _field_matches(mon_spec, dt.month)
        and _field_matches(dow_spec, cron_dow)
    )


# ─── ScheduleEntry ───────────────────────────────────────────────────────────


@dataclass
class ScheduleEntry:
    """One scheduled directive."""

    name: str
    cron: str
    directive: str
    tier: int = 0
    description: str = ""
    enabled: bool = True
    last_run: str = ""       # ISO timestamp of last injection, or ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "cron": self.cron,
            "directive": self.directive,
            "tier": self.tier,
            "description": self.description,
            "enabled": self.enabled,
            "last_run": self.last_run,
        }


# ─── ScheduleStore ───────────────────────────────────────────────────────────


class ScheduleStore:
    """Read/write schedule.yaml atomically."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def load(self) -> list[ScheduleEntry]:
        if not self.path.exists():
            return []
        try:
            data = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            return []
        entries = []
        for item in data.get("schedules", []):
            if not item.get("name") or not item.get("cron") or not item.get("directive"):
                continue
            entries.append(ScheduleEntry(
                name=str(item["name"]),
                cron=str(item["cron"]),
                directive=str(item["directive"]),
                tier=int(item.get("tier", 0)),
                description=str(item.get("description", "")),
                enabled=bool(item.get("enabled", True)),
                last_run=str(item.get("last_run", "")),
            ))
        return entries

    def save(self, entries: list[ScheduleEntry]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"schedules": [e.to_dict() for e in entries]}
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True))
        tmp.replace(self.path)

    def add(self, entry: ScheduleEntry) -> None:
        entries = self.load()
        entries = [e for e in entries if e.name != entry.name]  # replace if exists
        entries.append(entry)
        self.save(entries)

    def remove(self, name: str) -> bool:
        entries = self.load()
        before = len(entries)
        entries = [e for e in entries if e.name != name]
        self.save(entries)
        return len(entries) < before


# ─── Due-check integration ───────────────────────────────────────────────────


def check_and_inject_due(
    store: ScheduleStore,
    *,
    now: datetime | None = None,
) -> list[str]:
    """Check each enabled schedule entry. If due, inject into backlog.

    Returns list of injected schedule names.
    Called from the busy loop on each _drain_iteration().
    """
    from sovereign_agent.mode_controller import add_task  # lazy to avoid circular import

    now = now or datetime.now(tz=timezone.utc)
    entries = store.load()
    injected: list[str] = []

    updated = False
    for entry in entries:
        if not entry.enabled:
            continue
        if not cron_matches(entry.cron, now):
            continue

        # Avoid duplicate injection within the same minute
        if entry.last_run:
            try:
                last = datetime.fromisoformat(entry.last_run)
                if (last.year, last.month, last.day, last.hour, last.minute) == (
                    now.year, now.month, now.day, now.hour, now.minute
                ):
                    continue
            except ValueError:
                pass

        try:
            add_task(
                goal=entry.directive,
                priority="medium",
                mode="oneshot",
                task_id=f"sched-{entry.name[:20].replace(' ', '-')}-{now.strftime('%Y%m%d%H%M')}",
            )
        except Exception:  # noqa: BLE001
            continue

        entry.last_run = now.isoformat(timespec="seconds")
        updated = True
        injected.append(entry.name)

    if updated:
        store.save(entries)

    return injected


def _schedule_path() -> Path:
    from sovereign_agent.config import SETTINGS
    return SETTINGS.paths.config_dir / "schedule.yaml"
