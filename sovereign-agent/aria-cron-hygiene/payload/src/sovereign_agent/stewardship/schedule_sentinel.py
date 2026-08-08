"""
╔══════════════════════════════════════════════════════════════════════════╗
║  stewardship/schedule_sentinel.py — schedule hygiene watchdog           ║
║                                                                           ║
║  RISK-008: append-only stores grow unbounded. schedule.yaml can         ║
║  accumulate duplicate entries, stale jobs, and invalid cron expressions ║
║  from autonomous sessions without any audit pass.                       ║
║                                                                           ║
║  Binding statements                                                       ║
║                                                                           ║
║    I. I detect duplicate schedule entry names.                           ║
║                                                                           ║
║   II. I detect invalid cron expressions (malformed fields).             ║
║                                                                           ║
║  III. I detect entries that have never fired (last_run empty + enabled). ║
║                                                                           ║
║   IV. I detect entries with empty directives (they are filtered by      ║
║       ScheduleStore.load() and never fire — silent dead weight).        ║
║                                                                           ║
║    V. I NEVER modify schedule.yaml. I propose; the operator decides.   ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .base import HealthStatus, Sentinel, SentinelReport
from .registry import register_sentinel


@dataclass
class ScheduleFinding:
    """One specific schedule issue."""
    kind: str       # 'duplicate', 'invalid-cron', 'never-fired', 'empty-directive'
    severity: str   # 'info' / 'warning' / 'error'
    summary: str
    detail: str = ""
    remediation: str = ""


@register_sentinel
class ScheduleSentinel(Sentinel):
    """Watches schedule.yaml for duplicates, invalid cron, and stale entries."""

    @property
    def id(self) -> str:
        return "schedule"

    @property
    def title(self) -> str:
        return "Schedule hygiene sentinel"

    @property
    def tier(self) -> int:
        return 1

    def articles(self) -> list[str]:
        return [
            "I detect duplicate schedule entry names.",
            "I detect invalid or malformed cron expressions.",
            "I detect enabled entries that have never fired.",
            "I detect entries with empty directives (silently filtered by ScheduleStore).",
            "I never modify schedule.yaml — I propose; the operator decides.",
        ]

    # ── Scanning ─────────────────────────────────────────────────────────

    def scan(self) -> SentinelReport:
        findings: list[ScheduleFinding] = []

        yaml_path = self._schedule_path()
        raw_entries = self._load_raw(yaml_path)

        if raw_entries is None:
            # File missing — clean state, not an error
            catalog = {
                "scanned_at": self._iso_now(),
                "schedule_path": str(yaml_path),
                "entries_found": 0,
                "findings": [],
                "counts": {"error": 0, "warning": 0, "info": 0},
            }
            catalog_path = self.save_catalog(catalog, name="default")
            return SentinelReport(
                sentinel_id=self.id,
                observed_at=self._iso_now(),
                catalog_name="default",
                findings_count=0,
                summary="no schedule.yaml found — clean start",
                catalog_path=str(catalog_path),
                details={"counts": catalog["counts"]},
            )

        findings.extend(self._check_duplicates(raw_entries))
        findings.extend(self._check_invalid_cron(raw_entries))
        findings.extend(self._check_never_fired(raw_entries))
        findings.extend(self._check_empty_directives(raw_entries))

        counts = {
            "error":   sum(1 for f in findings if f.severity == "error"),
            "warning": sum(1 for f in findings if f.severity == "warning"),
            "info":    sum(1 for f in findings if f.severity == "info"),
        }
        catalog = {
            "scanned_at": self._iso_now(),
            "schedule_path": str(yaml_path),
            "entries_found": len(raw_entries),
            "findings": [
                {"kind": f.kind, "severity": f.severity, "summary": f.summary,
                 "detail": f.detail, "remediation": f.remediation}
                for f in findings
            ],
            "counts": counts,
        }
        catalog_path = self.save_catalog(catalog, name="default")

        for f in findings:
            if f.severity == "error":
                self.notify(
                    severity="alert",
                    title=f.summary,
                    message=f.detail,
                    addressed_to="operator",
                    data={"kind": f.kind},
                )

        return SentinelReport(
            sentinel_id=self.id,
            observed_at=self._iso_now(),
            catalog_name="default",
            findings_count=len(findings),
            summary=(
                f"{counts['error']} error, {counts['warning']} warning, {counts['info']} info"
                f" — {len(raw_entries)} schedule entries"
            ),
            catalog_path=str(catalog_path),
            details={"counts": counts},
        )

    def health_status(self) -> HealthStatus:
        catalog = self.load_catalog("default")
        if catalog is None:
            return HealthStatus(
                sentinel_id=self.id, level="unknown",
                summary="never scanned",
            )
        counts = catalog.get("counts", {})
        n = catalog.get("entries_found", 0)
        if counts.get("error", 0) > 0:
            return HealthStatus(
                sentinel_id=self.id, level="error",
                summary=f"schedule has errors ({n} entries) — run `sov sentinels show schedule`",
            )
        if counts.get("warning", 0) > 0:
            return HealthStatus(
                sentinel_id=self.id, level="warning",
                summary=f"schedule has warnings ({n} entries)",
                detail=f"last scan {catalog.get('scanned_at', '?')}",
            )
        return HealthStatus(
            sentinel_id=self.id, level="ok",
            summary=f"schedule clean — {n} entries",
            detail=f"last scan {catalog.get('scanned_at', '?')}",
        )

    # ── Individual checks ─────────────────────────────────────────────────

    def _check_duplicates(self, entries: list[dict]) -> list[ScheduleFinding]:
        seen: dict[str, int] = {}
        for e in entries:
            name = e.get("name", "")
            seen[name] = seen.get(name, 0) + 1
        findings = []
        for name, count in seen.items():
            if count > 1:
                findings.append(ScheduleFinding(
                    kind="duplicate",
                    severity="error",
                    summary=f"Duplicate schedule name: '{name}' appears {count} times",
                    detail="ScheduleStore.add() replaces on name match, but raw YAML duplicates can confuse direct parsers.",
                    remediation=f"Remove duplicate entries named '{name}' from schedule.yaml, keeping the most recent.",
                ))
        return findings

    def _check_invalid_cron(self, entries: list[dict]) -> list[ScheduleFinding]:
        from sovereign_agent.schedule import cron_matches
        probe_dt = datetime(2026, 1, 5, 9, 0, tzinfo=timezone.utc)  # fixed Monday 09:00
        findings = []
        for e in entries:
            expr = e.get("cron", "")
            if not expr:
                continue
            try:
                cron_matches(expr, probe_dt)
            except Exception as exc:  # noqa: BLE001
                findings.append(ScheduleFinding(
                    kind="invalid-cron",
                    severity="warning",
                    summary=f"Invalid cron expression: '{expr}' for entry '{e.get('name', '?')}'",
                    detail=f"Error: {exc}",
                    remediation="Fix the cron expression to valid 5-field format (min hour dom month dow).",
                ))
            else:
                # Structural validation: must have exactly 5 space-separated fields
                parts = expr.strip().split()
                if len(parts) != 5:
                    findings.append(ScheduleFinding(
                        kind="invalid-cron",
                        severity="warning",
                        summary=f"Malformed cron for '{e.get('name', '?')}': '{expr}' has {len(parts)} fields (need 5)",
                        remediation="Cron must be 5 fields: min hour dom month dow",
                    ))
        return findings

    def _check_never_fired(self, entries: list[dict]) -> list[ScheduleFinding]:
        findings = []
        for e in entries:
            if not e.get("enabled", True):
                continue
            if e.get("last_run", ""):
                continue
            name = e.get("name", "?")
            findings.append(ScheduleFinding(
                kind="never-fired",
                severity="info",
                summary=f"Schedule entry '{name}' has never fired",
                detail="This entry is enabled but has no last_run timestamp. It may not have been due yet, or the busy loop may not have reached it.",
                remediation="No action needed unless this entry should have run by now.",
            ))
        return findings

    def _check_empty_directives(self, entries: list[dict]) -> list[ScheduleFinding]:
        findings = []
        for e in entries:
            if not e.get("directive", "").strip():
                name = e.get("name", "?")
                findings.append(ScheduleFinding(
                    kind="empty-directive",
                    severity="warning",
                    summary=f"Schedule entry '{name}' has empty directive — silently skipped by ScheduleStore",
                    detail="ScheduleStore.load() filters entries without directive; this entry never fires.",
                    remediation=f"Add a directive to '{name}' or remove the entry.",
                ))
        return findings

    # ── Helpers ──────────────────────────────────────────────────────────

    def _schedule_path(self) -> Path:
        try:
            from sovereign_agent.config import SETTINGS
            return SETTINGS.paths.config_dir / "schedule.yaml"
        except Exception:  # noqa: BLE001
            return Path.home() / ".config" / "sovereign-agent" / "schedule.yaml"

    def _load_raw(self, path: Path) -> list[dict] | None:
        """Load raw schedule entries from YAML. Returns None if file missing."""
        if not path.is_file():
            return None
        try:
            import yaml
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            return [e for e in data.get("schedules", []) if isinstance(e, dict)]
        except Exception:  # noqa: BLE001
            return []

    @staticmethod
    def _iso_now() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


__all__ = ["ScheduleSentinel", "ScheduleFinding"]
