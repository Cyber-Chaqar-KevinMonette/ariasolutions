"""
stewardship/telemetry_sentinel.py — Watches the telemetry stream for anomalies
(aria-telemetry-sentinel, M27)

17k telemetry samples collected per day. Nobody watching them.
This sentinel reads the current day's JSONL stream and watches for:
  1. VRAM > 90% sustained >60s → warning; > 95% → error
  2. Disk free < 5 GB → warning; < 1 GB → error
  3. CPU > 90% sustained >120s → warning
  4. RAM > 90% sustained >60s → warning
  5. GPU temp > 80°C → warning; > 88°C → error

Design:
  - scan() reads last N samples from telemetry/sys-YYYYMMDD.jsonl
  - health_status() reads from catalog (so it's cheap — no fresh file read)
  - No heal() — propose only, like all sentinels
  - Kill switch: SOV_NO_TELEMETRY_SENTINEL=1

The 5-second refresh interval in the cockpit means 12 samples/minute, so
  60s → 12 samples; 120s → 24 samples. We read last 30 samples for all checks.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from sovereign_agent.stewardship.base import HealthStatus, Sentinel, SentinelReport
from sovereign_agent.stewardship.registry import register_sentinel


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _telemetry_dir(data_dir: Path) -> Path:
    return data_dir / "telemetry"


def _read_recent_samples(data_dir: Path, n: int = 30) -> list[dict]:
    """Read the last n telemetry samples from today's JSONL file."""
    today = datetime.now(tz=timezone.utc).strftime("%Y%m%d")
    path = _telemetry_dir(data_dir) / f"sys-{today}.jsonl"
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    samples: list[dict] = []
    for line in reversed(lines[-n * 2:]):  # read extra to compensate for parse failures
        line = line.strip()
        if not line:
            continue
        try:
            samples.append(json.loads(line))
        except json.JSONDecodeError:
            continue
        if len(samples) >= n:
            break
    return list(reversed(samples))  # chronological order


# Thresholds (constants for easy review and testing)
VRAM_WARN_PCT = 90.0
VRAM_ERR_PCT = 95.0
VRAM_WARN_SAMPLES = 12    # ~60s at 5s interval
DISK_WARN_MB = 5 * 1024   # 5 GB
DISK_ERR_MB = 1 * 1024    # 1 GB
CPU_WARN_PCT = 90.0
CPU_WARN_SAMPLES = 24     # ~120s at 5s interval
RAM_WARN_PCT = 90.0
RAM_WARN_SAMPLES = 12     # ~60s
GPU_TEMP_WARN_C = 80.0
GPU_TEMP_ERR_C = 88.0


def _analyze_samples(samples: list[dict]) -> dict:
    """Analyze samples; return a findings dict for catalog storage."""
    findings: list[str] = []
    level = "ok"

    if not samples:
        return {"level": "unknown", "findings": [], "summary": "no telemetry samples yet today"}

    latest = samples[-1]

    # ── Disk free (instantaneous, no sustain needed) ────────────────────
    disk_free_mb = latest.get("disk_free_mb")
    if disk_free_mb is not None:
        if disk_free_mb < DISK_ERR_MB:
            findings.append(f"disk critically low: {disk_free_mb // 1024:.1f} GB free (< 1 GB)")
            level = "error"
        elif disk_free_mb < DISK_WARN_MB:
            findings.append(f"disk low: {disk_free_mb // 1024:.1f} GB free (< 5 GB)")
            if level == "ok":
                level = "warning"

    # ── GPU temp (instantaneous) ─────────────────────────────────────────
    vram_temp = latest.get("vram_temp_c")
    if vram_temp is not None:
        if vram_temp >= GPU_TEMP_ERR_C:
            findings.append(f"GPU temp critical: {vram_temp:.0f}°C (≥ {GPU_TEMP_ERR_C}°C)")
            level = "error"
        elif vram_temp >= GPU_TEMP_WARN_C:
            findings.append(f"GPU temp high: {vram_temp:.0f}°C (≥ {GPU_TEMP_WARN_C}°C)")
            if level == "ok":
                level = "warning"

    # ── VRAM sustained (last VRAM_WARN_SAMPLES samples) ─────────────────
    vram_window = samples[-VRAM_WARN_SAMPLES:]
    vram_pcts = [s.get("vram_pct") for s in vram_window if s.get("vram_pct") is not None]
    if len(vram_pcts) >= max(1, VRAM_WARN_SAMPLES // 2):
        avg_vram = sum(vram_pcts) / len(vram_pcts)
        if avg_vram >= VRAM_ERR_PCT:
            findings.append(f"VRAM critical: {avg_vram:.0f}% sustained (≥ {VRAM_ERR_PCT}%)")
            level = "error"
        elif avg_vram >= VRAM_WARN_PCT:
            findings.append(f"VRAM high: {avg_vram:.0f}% sustained (≥ {VRAM_WARN_PCT}%)")
            if level == "ok":
                level = "warning"

    # ── CPU sustained ────────────────────────────────────────────────────
    cpu_window = samples[-CPU_WARN_SAMPLES:]
    cpu_pcts = [s.get("cpu_pct") for s in cpu_window if s.get("cpu_pct") is not None]
    if len(cpu_pcts) >= max(1, CPU_WARN_SAMPLES // 2):
        sustained_above = sum(1 for p in cpu_pcts if p >= CPU_WARN_PCT)
        if sustained_above >= CPU_WARN_SAMPLES * 0.75:
            avg_cpu = sum(cpu_pcts) / len(cpu_pcts)
            findings.append(f"CPU sustained high: {avg_cpu:.0f}% for ~{len(cpu_pcts) * 5}s")
            if level == "ok":
                level = "warning"

    # ── RAM sustained ────────────────────────────────────────────────────
    ram_window = samples[-RAM_WARN_SAMPLES:]
    ram_pcts = [s.get("ram_pct") for s in ram_window if s.get("ram_pct") is not None]
    if len(ram_pcts) >= max(1, RAM_WARN_SAMPLES // 2):
        avg_ram = sum(ram_pcts) / len(ram_pcts)
        if avg_ram >= RAM_WARN_PCT:
            findings.append(f"RAM high: {avg_ram:.0f}% sustained (≥ {RAM_WARN_PCT}%)")
            if level == "ok":
                level = "warning"

    summary = findings[0] if findings else f"system healthy ({len(samples)} samples)"
    return {
        "level": level,
        "findings": findings,
        "summary": summary,
        "samples_analyzed": len(samples),
        "scanned_at": _iso_now(),
        "latest_snapshot": {
            k: latest.get(k) for k in
            ("cpu_pct", "ram_pct", "disk_free_mb", "vram_pct", "vram_temp_c")
        },
    }


@register_sentinel
class TelemetrySentinel(Sentinel):
    """Watches the real-time telemetry stream for system health anomalies.

    Reads the last 30 telemetry samples (~2.5 minutes) from today's
    sys-YYYYMMDD.jsonl. Checks: VRAM sustained high, disk critically low,
    CPU sustained high, RAM sustained high, GPU temperature.
    """

    @property
    def id(self) -> str:
        return "telemetry"

    @property
    def title(self) -> str:
        return "Telemetry stream sentinel"

    @property
    def tier(self) -> int:
        return 1

    def articles(self) -> list[str]:
        return [
            f"I alert when VRAM > {VRAM_WARN_PCT}% sustained for >{VRAM_WARN_SAMPLES * 5}s.",
            f"I alert when VRAM > {VRAM_ERR_PCT}% (error level — OOM risk).",
            f"I alert when disk free < {DISK_WARN_MB // 1024} GB (warning) or < {DISK_ERR_MB // 1024} GB (error).",
            f"I alert when CPU > {CPU_WARN_PCT}% sustained for >{CPU_WARN_SAMPLES * 5}s.",
            f"I alert when RAM > {RAM_WARN_PCT}% sustained for >{RAM_WARN_SAMPLES * 5}s.",
            f"I alert when GPU temp > {GPU_TEMP_WARN_C}°C (warning) or > {GPU_TEMP_ERR_C}°C (error).",
            "I never intervene automatically — I propose; the operator decides.",
            "I read from today's telemetry JSONL file; no data = unknown, not error.",
        ]

    def scan(self) -> SentinelReport:
        samples = _read_recent_samples(self._data_dir, n=30)
        analysis = _analyze_samples(samples)
        self.save_catalog(analysis, name="default")

        findings_text = "; ".join(analysis["findings"]) if analysis["findings"] else "none"
        return SentinelReport(
            sentinel_id=self.id,
            scanned_at=_iso_now(),
            findings=[{"text": f, "level": analysis["level"]} for f in analysis["findings"]],
            summary=analysis["summary"],
        )

    def health_status(self) -> HealthStatus:
        catalog = self.load_catalog("default")
        if catalog is None:
            return HealthStatus(
                sentinel_id=self.id,
                level="unknown",
                summary="not yet scanned — run `sov sentinels scan telemetry`",
            )
        level = catalog.get("level", "unknown")
        summary = catalog.get("summary", "no summary")
        detail = ""
        findings = catalog.get("findings", [])
        if len(findings) > 1:
            detail = "\n".join(f"  • {f}" for f in findings)
        return HealthStatus(
            sentinel_id=self.id,
            level=level,
            summary=summary,
            detail=detail,
        )
