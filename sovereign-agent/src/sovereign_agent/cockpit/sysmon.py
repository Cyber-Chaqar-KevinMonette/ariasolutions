"""
╔══════════════════════════════════════════════════════════════════════════╗
║  cockpit/sysmon.py — system monitoring for the cockpit                   ║
║  v0.2.15.3 · Aria-Sovereign-V1                                            ║
║                                                                            ║
║  Reads CPU, RAM, swap, disk, load average, and uptime from /proc and     ║
║  os.statvfs. No external dependencies. Linux-only (sovereign-agent       ║
║  already requires systemd --user so this is consistent).                 ║
║                                                                            ║
║  The CPU sample maintains state across calls — the first call returns    ║
║  0.0 because there's no prior reading to diff against. The status        ║
║  worker calls SystemMonitor.read() once every 5 seconds, so by the       ║
║  second tick the user sees a meaningful number.                          ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ── Data shapes ─────────────────────────────────────────────────────────────


@dataclass
class SystemSnapshot:
    """A single moment of system health, suitable for status bars and reports."""
    # CPU
    cpu_percent: float = 0.0
    cpu_temp_c: Optional[float] = None  # None if /sys/class/thermal unavailable
    load_1m: float = 0.0
    load_5m: float = 0.0
    load_15m: float = 0.0
    cpu_count: int = 0

    # Memory (bytes)
    mem_total: int = 0
    mem_available: int = 0
    mem_used: int = 0
    mem_percent: float = 0.0

    # Swap (bytes)
    swap_total: int = 0
    swap_used: int = 0
    swap_percent: float = 0.0

    # Disk for data_dir (bytes)
    disk_total: int = 0
    disk_free: int = 0
    disk_used: int = 0
    disk_percent: float = 0.0
    disk_path: str = ""

    # Uptime
    uptime_seconds: float = 0.0

    # Did we read OK? Empty string means yes; otherwise an error message.
    error: str = ""


# ── Formatting helpers ──────────────────────────────────────────────────────


def fmt_bytes(n: int) -> str:
    """1.2 GB / 768 MB / 42 KB / 17 B — short, human-readable."""
    if n < 1024:
        return f"{n} B"
    for unit in ("KB", "MB", "GB", "TB", "PB"):
        n /= 1024.0
        if n < 1024:
            if n >= 100:
                return f"{n:.0f} {unit}"
            if n >= 10:
                return f"{n:.1f} {unit}"
            return f"{n:.2f} {unit}"
    return f"{n:.1f} EB"


def fmt_duration(seconds: float) -> str:
    """17h 42m / 3d 4h / 42m 17s — short, human-readable."""
    s = int(seconds)
    days, s = divmod(s, 86400)
    hours, s = divmod(s, 3600)
    mins, s = divmod(s, 60)
    if days >= 1:
        return f"{days}d {hours}h"
    if hours >= 1:
        return f"{hours}h {mins}m"
    if mins >= 1:
        return f"{mins}m {s}s"
    return f"{s}s"


# ── The monitor ─────────────────────────────────────────────────────────────


class SystemMonitor:
    """Reads system metrics from /proc. Thread-safe for serial use.

    First call after construction returns cpu_percent=0.0 — the first
    /proc/stat read seeds the diff baseline. The second call returns a
    real number. The status worker runs every 5 seconds so the user
    sees CPU within ~5 seconds of cockpit launch.
    """

    def __init__(self, data_dir: Optional[Path] = None) -> None:
        self._disk_path = str(data_dir) if data_dir else os.path.expanduser("~")
        self._prev_total: Optional[int] = None
        self._prev_idle: Optional[int] = None
        # Cache cpu_count once.
        self._cpu_count = os.cpu_count() or 1

    # ── Public ──────────────────────────────────────────────────────────

    def read(self) -> SystemSnapshot:
        """One full snapshot. Catches all exceptions — never raises."""
        snap = SystemSnapshot(cpu_count=self._cpu_count)
        try:
            self._read_cpu(snap)
            self._read_cpu_temp(snap)
            self._read_loadavg(snap)
            self._read_meminfo(snap)
            self._read_uptime(snap)
            self._read_disk(snap)
        except Exception as exc:  # noqa: BLE001
            snap.error = f"{type(exc).__name__}: {exc}"
        return snap

    # ── Component readers ───────────────────────────────────────────────

    def _read_cpu_temp(self, snap: SystemSnapshot) -> None:
        """Read CPU temperature from /sys/class/thermal.

        On Linux, thermal_zone* directories expose `temp` in millidegrees C.
        Many systems have multiple zones (one per package, per core, plus
        chipset zones). We average over zones whose `type` contains "cpu",
        "x86", "coretemp", or "pkg" — that's a reasonable approximation of
        "the CPU temperature" on a heterogeneous machine.

        Returns silently if no thermal zones exist (containers, some VMs,
        unsupported hardware). snap.cpu_temp_c stays None.
        """
        from pathlib import Path as _P
        thermal_dir = _P("/sys/class/thermal")
        if not thermal_dir.exists():
            return
        temps: list[float] = []
        try:
            for zone in thermal_dir.glob("thermal_zone*"):
                tp = zone / "type"
                tv = zone / "temp"
                if not (tp.exists() and tv.exists()):
                    continue
                try:
                    zone_type = tp.read_text(errors="ignore").strip().lower()
                except OSError:
                    continue
                # Filter to CPU-like zones; skip wifi/battery/ambient zones.
                if not any(tag in zone_type for tag in
                           ("cpu", "x86", "coretemp", "pkg", "core")):
                    continue
                try:
                    millic = int(tv.read_text(errors="ignore").strip())
                except (OSError, ValueError):
                    continue
                temps.append(millic / 1000.0)
        except OSError:
            return
        if temps:
            snap.cpu_temp_c = sum(temps) / len(temps)

    def _read_cpu(self, snap: SystemSnapshot) -> None:
        """CPU% across all cores, computed as a diff vs the previous sample."""
        try:
            with open("/proc/stat") as f:
                line = f.readline()
        except OSError:
            return
        # Format: "cpu  user nice system idle iowait irq softirq steal guest guest_nice"
        fields = line.split()[1:]
        if len(fields) < 5:
            return
        vals = [int(x) for x in fields]
        idle = vals[3] + (vals[4] if len(vals) > 4 else 0)
        total = sum(vals)

        if self._prev_total is not None and self._prev_idle is not None:
            total_diff = total - self._prev_total
            idle_diff = idle - self._prev_idle
            if total_diff > 0:
                snap.cpu_percent = 100.0 * (total_diff - idle_diff) / total_diff
                snap.cpu_percent = max(0.0, min(100.0, snap.cpu_percent))

        self._prev_total = total
        self._prev_idle = idle

    def _read_loadavg(self, snap: SystemSnapshot) -> None:
        try:
            with open("/proc/loadavg") as f:
                parts = f.readline().split()
        except OSError:
            return
        if len(parts) >= 3:
            snap.load_1m = float(parts[0])
            snap.load_5m = float(parts[1])
            snap.load_15m = float(parts[2])

    def _read_meminfo(self, snap: SystemSnapshot) -> None:
        info: dict[str, int] = {}
        try:
            with open("/proc/meminfo") as f:
                for line in f:
                    key, _, rest = line.partition(":")
                    val = rest.strip().split()
                    if val:
                        # /proc/meminfo values are in kB by convention.
                        info[key] = int(val[0]) * 1024
        except OSError:
            return

        snap.mem_total = info.get("MemTotal", 0)
        # MemAvailable is the right "what's actually free" — it accounts for
        # reclaimable cache. Falling back to MemFree is too pessimistic.
        snap.mem_available = info.get("MemAvailable", info.get("MemFree", 0))
        snap.mem_used = max(0, snap.mem_total - snap.mem_available)
        if snap.mem_total > 0:
            snap.mem_percent = 100.0 * snap.mem_used / snap.mem_total

        snap.swap_total = info.get("SwapTotal", 0)
        snap.swap_used = max(0, snap.swap_total - info.get("SwapFree", 0))
        if snap.swap_total > 0:
            snap.swap_percent = 100.0 * snap.swap_used / snap.swap_total

    def _read_uptime(self, snap: SystemSnapshot) -> None:
        try:
            with open("/proc/uptime") as f:
                parts = f.readline().split()
        except OSError:
            return
        if parts:
            snap.uptime_seconds = float(parts[0])

    def _read_disk(self, snap: SystemSnapshot) -> None:
        try:
            s = os.statvfs(self._disk_path)
        except OSError:
            return
        snap.disk_path = self._disk_path
        snap.disk_total = s.f_blocks * s.f_frsize
        snap.disk_free = s.f_bavail * s.f_frsize
        snap.disk_used = max(0, snap.disk_total - snap.disk_free)
        if snap.disk_total > 0:
            snap.disk_percent = 100.0 * snap.disk_used / snap.disk_total


def read_gpu_temp() -> Optional[float]:
    """Best-effort GPU temperature in °C, or None if unavailable.

    Tries pynvml first (fast, library call), falls back to nvidia-smi
    (~50ms subprocess). Returns None for any error or non-nvidia setups.
    Symmetric to vram.read_vram() in scope — kept here so vram.py stays
    untouched. AMD/Intel GPU temps would land here as additional fallbacks.
    """
    # Try pynvml (fast)
    try:
        import pynvml  # type: ignore[import-not-found]
        pynvml.nvmlInit()
        h = pynvml.nvmlDeviceGetHandleByIndex(0)
        t = pynvml.nvmlDeviceGetTemperature(h, pynvml.NVML_TEMPERATURE_GPU)
        pynvml.nvmlShutdown()
        return float(t)
    except Exception:  # noqa: BLE001
        pass

    # Fall back to nvidia-smi (subprocess)
    import shutil, subprocess
    if not shutil.which("nvidia-smi"):
        return None
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=temperature.gpu",
             "--format=csv,noheader,nounits"],
            stderr=subprocess.DEVNULL, timeout=2,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    line = out.decode(errors="ignore").strip().splitlines()
    if not line:
        return None
    try:
        return float(line[0].strip())
    except ValueError:
        return None


# ── Reportable data — what a prospect would screenshot ──────────────────────


def render_compact_metrics(
    snap: SystemSnapshot,
    *,
    vram_percent: Optional[float] = None,
    vram_temp_c: Optional[float] = None,
) -> str:
    """One-line metrics for the status bar. Rich-markup ready.

    Format:  ram 20%  ·  cpu 12%@62°  ·  vram 26%@68°  ·  disk 28%
    The `ram` label is deliberate — what the OS calls "memory" is RAM,
    not VRAM. VRAM (GPU memory) is shown separately when a GPU is
    present and `vram_percent` is supplied; omitted otherwise to keep
    the bar short on narrow terminals.

    Temperatures are appended where they're meaningful and available:
        cpu_temp_c → from /sys/class/thermal/thermal_zone*
        vram_temp_c → from nvidia-smi (passed in by the caller)
    RAM and disk don't have meaningful single-value temperatures.

    Each percent is colour-coded by threshold:
        green   < 60%      healthy
        yellow  60–84%     warm
        red    ≥ 85%       hot
    Temperatures use a separate threshold:
        green   < 70°C     healthy
        yellow  70–84°C    warm
        red    ≥ 85°C      hot
    """
    parts = [
        _pct("ram", snap.mem_percent),
        _pct_with_temp("cpu", snap.cpu_percent, snap.cpu_temp_c),
    ]
    if vram_percent is not None:
        parts.append(_pct_with_temp("vram", vram_percent, vram_temp_c))
    parts.append(_pct("disk", snap.disk_percent))
    return "  ·  ".join(parts)


def _pct_with_temp(label: str, value: float, temp_c: Optional[float]) -> str:
    """Like _pct but appends an `@N°` suffix if temp_c is given."""
    base = _pct(label, value)
    if temp_c is None:
        return base
    if temp_c >= 85.0:
        tc = "red"
    elif temp_c >= 70.0:
        tc = "yellow"
    else:
        tc = "green"
    return f"{base}[dim]@[/dim][{tc}]{temp_c:.0f}°[/{tc}]"


def _pct(label: str, value: float) -> str:
    if value >= 85.0:
        colour = "red"
    elif value >= 60.0:
        colour = "yellow"
    else:
        colour = "green"
    return f"[dim]{label}[/dim] [{colour}]{value:.0f}%[/{colour}]"


def render_health_report(
    snap: SystemSnapshot,
    *,
    version: str,
    halt: bool,
    daemon_active: bool,
    ledger_ok: bool,
    ledger_rows: int,
    snapshot_age_seconds: Optional[float],
    snapshot_verify_ok: bool,
    vram_total_mb: Optional[int] = None,
    vram_used_mb: Optional[int] = None,
    vram_source: str = "",
    now_iso: str = "",
) -> str:
    """Full text report — what you'd screenshot for a client.

    Pure plain text (no Rich markup) so it copies cleanly into emails, PRs,
    Slack, and PDFs. The cockpit wraps this in a fenced block when it
    surfaces the report in the chat pane.
    """
    lines: list[str] = []
    width = 64
    rule = "─" * width

    lines.append(f"sovereign-agent · health report · {now_iso}")
    lines.append(rule)
    lines.append("")

    # Overview
    lines.append(f"  Version       {version}")
    lines.append(f"  Uptime        {fmt_duration(snap.uptime_seconds)}")
    daemon_str = "● active" if daemon_active else "○ inactive"
    lines.append(f"  Daemon        {daemon_str}")
    lines.append(f"  HALT          {'◊ TRIPPED' if halt else 'clear'}")
    lines.append("")

    # System
    lines.append("  System")
    lines.append(
        f"    CPU         {snap.cpu_percent:5.1f}%   "
        f"load {snap.load_1m:.2f} {snap.load_5m:.2f} {snap.load_15m:.2f}   "
        f"({snap.cpu_count} cores)"
    )
    lines.append(
        f"    Memory      {snap.mem_percent:5.1f}%   "
        f"{fmt_bytes(snap.mem_used)} used of {fmt_bytes(snap.mem_total)}   "
        f"({fmt_bytes(snap.mem_available)} available)"
    )
    if snap.swap_total > 0:
        lines.append(
            f"    Swap        {snap.swap_percent:5.1f}%   "
            f"{fmt_bytes(snap.swap_used)} used of {fmt_bytes(snap.swap_total)}"
        )
    lines.append(
        f"    Disk        {snap.disk_percent:5.1f}%   "
        f"{fmt_bytes(snap.disk_free)} free of {fmt_bytes(snap.disk_total)}"
    )
    if snap.disk_path:
        lines.append(f"                {snap.disk_path}")
    if vram_total_mb is not None and vram_used_mb is not None and vram_total_mb > 0:
        vram_pct = 100.0 * vram_used_mb / vram_total_mb
        src = f" ({vram_source})" if vram_source else ""
        lines.append(
            f"    VRAM        {vram_pct:5.1f}%   "
            f"{vram_used_mb} MB used of {vram_total_mb} MB{src}"
        )
    lines.append("")

    # Ledger
    lines.append("  Ledger")
    ledger_status = "✓ clean" if ledger_ok else "✗ discrepancy"
    lines.append(f"    Status      {ledger_status}")
    lines.append(f"    Rows        {ledger_rows}")
    lines.append("")

    # Backups
    lines.append("  Backups")
    if snapshot_age_seconds is None:
        lines.append("    Latest      (no snapshot)")
    else:
        verify = "✓ verified" if snapshot_verify_ok else "✗ verify failed"
        lines.append(
            f"    Latest      {fmt_duration(snapshot_age_seconds)} ago · {verify}"
        )
    lines.append("")

    if snap.error:
        lines.append(f"  ⚠ partial read: {snap.error}")
        lines.append("")

    lines.append(rule)
    return "\n".join(lines)
