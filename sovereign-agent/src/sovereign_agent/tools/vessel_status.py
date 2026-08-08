"""
vessel_status.py — Aria's vessel and system awareness tool (v0.2.41.0)

One Tier 0 tool that gives Aria visibility into:
  - System metrics: CPU, RAM, swap, disk, uptime (via cockpit/sysmon.py)
  - VRAM: total/used/free, source (nvml/nvidia-smi/estimate)
  - Sentinel health: status of every registered stewardship sentinel
  - Package version: sovereign_agent.__version__

This is the tool that answers "how is my vessel doing?" Aria should call
it at the start of heavy workloads to understand resource constraints,
and when she suspects something is wrong with her environment.
"""
from __future__ import annotations

from pydantic import BaseModel

import sovereign_agent as _pkg
from sovereign_agent.cockpit.sysmon import SystemMonitor, fmt_bytes, fmt_duration
from sovereign_agent.config import SETTINGS
from sovereign_agent.stewardship.registry import gather_health
from sovereign_agent.vram import read_vram

from .base import Tool, ToolResult


class VesselStatusTool(Tool):
    """Report Aria's system metrics, VRAM, sentinel health, and version.

    Returns a structured snapshot of: CPU usage, load averages, RAM/swap,
    disk space, uptime, GPU VRAM (total/used/free), health status of every
    registered sentinel, and the installed package version.

    Call this before starting a memory-intensive or GPU-heavy task to
    understand available resources. Call it when something feels wrong
    to diagnose the environment.
    """

    name = "vessel_status"
    tier = 0
    description = (
        "Report Aria's vessel health: CPU, RAM, disk, uptime, VRAM "
        "(total/used/free), health status of every sentinel, and package "
        "version. Call this to understand available resources before a "
        "heavy task, or to diagnose why something isn't working."
    )
    failure_modes = (
        "sysmon read fails — returns partial metrics with error field set",
        "pynvml/nvidia-smi absent — VRAM reported as estimate only",
        "sentinel instantiation fails — that sentinel shown as error in output",
        "data_dir unset — sentinel health skipped",
    )

    class Args(BaseModel):
        include_sentinels: bool = True
        """Set False to skip sentinel health (faster if you only need metrics)."""

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        lines: list[str] = []
        errors: list[str] = []

        # ── Version ─────────────────────────────────────────────────────────
        version = getattr(_pkg, "__version__", "unknown")
        lines.append(f"# Vessel status — sovereign-agent {version}\n")

        # ── System metrics ───────────────────────────────────────────────────
        try:
            data_dir = SETTINGS.paths.data_dir if SETTINGS.paths.data_dir else None
            mon = SystemMonitor(data_dir=data_dir)
            snap = mon.read()
            if snap.error:
                errors.append(f"sysmon: {snap.error}")
            lines.append("## System")
            lines.append(
                f"  cpu: {snap.cpu_percent:.1f}%  "
                f"load: {snap.load_1m:.2f} {snap.load_5m:.2f} {snap.load_15m:.2f}  "
                f"({snap.cpu_count} cores)"
            )
            if snap.cpu_temp_c is not None:
                lines.append(f"  cpu temp: {snap.cpu_temp_c:.1f}°C")
            lines.append(
                f"  ram: {snap.mem_percent:.1f}%  "
                f"{fmt_bytes(snap.mem_used)} / {fmt_bytes(snap.mem_total)}"
            )
            if snap.swap_total:
                lines.append(
                    f"  swap: {snap.swap_percent:.1f}%  "
                    f"{fmt_bytes(snap.swap_used)} / {fmt_bytes(snap.swap_total)}"
                )
            lines.append(
                f"  disk: {snap.disk_percent:.1f}%  "
                f"{fmt_bytes(snap.disk_free)} free / {fmt_bytes(snap.disk_total)}"
            )
            lines.append(f"  uptime: {fmt_duration(snap.uptime_seconds)}")
        except Exception as exc:
            errors.append(f"sysmon failed: {exc!r}")
            lines.append("## System\n  (unavailable — see errors)")

        # ── VRAM ─────────────────────────────────────────────────────────────
        try:
            vram = read_vram()
            lines.append(f"\n## VRAM (source: {vram.source})")
            lines.append(f"  total: {vram.total_mb} MB")
            lines.append(f"  used:  {vram.used_mb} MB")
            lines.append(f"  free:  {vram.free_mb} MB")
            headroom = "ok" if vram.free_mb >= 500 else "low — avoid heavy tools"
            lines.append(f"  headroom: {headroom}")
        except Exception as exc:
            errors.append(f"vram read failed: {exc!r}")
            lines.append("\n## VRAM\n  (unavailable — see errors)")

        # ── Sentinel health ───────────────────────────────────────────────────
        if args.include_sentinels:
            try:
                data_dir = SETTINGS.paths.data_dir
                if data_dir is None:
                    lines.append("\n## Sentinels\n  (skipped — data_dir not configured)")
                else:
                    statuses = gather_health(data_dir)
                    lines.append(f"\n## Sentinels ({len(statuses)} registered)")
                    level_icons = {"ok": "✓", "warning": "⚠", "error": "✗", "unknown": "?"}
                    for hs in statuses:
                        icon = level_icons.get(hs.level, "?")
                        lines.append(f"  {icon} {hs.sentinel_id}: {hs.summary}")
            except Exception as exc:
                errors.append(f"sentinel health failed: {exc!r}")
                lines.append("\n## Sentinels\n  (unavailable — see errors)")

        if errors:
            lines.append(f"\n## Errors ({len(errors)})")
            for e in errors:
                lines.append(f"  ! {e}")

        return ToolResult(
            ok=not errors or len(errors) < 2,
            output="\n".join(lines),
            metadata={"error_count": len(errors)},
        )
