"""
aria_status.py — unified self-awareness snapshot for Aria

One tool call that returns everything:
  • vessel: VRAM, CPU, RAM, disk, uptime
  • kernel: commitments, stance, voice, designation
  • tools: all registered tools grouped by tier
  • sentinels: health status for each sentinel
  • session: current session goal + progress if one is active
  • workspace: repo root, data_dir, key file paths

Design intent: Aria calls this once at session start instead of
making 4 separate tool calls. The result gives her full situational
awareness in one round-trip.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from .base import Tool, ToolResult


class AriaStatusTool(Tool):
    """Return a unified self-awareness snapshot: vessel, kernel, tools, sentinels, session.

    Call this at the start of every session to establish situational awareness.
    Returns everything you need to orient yourself:
      - Hardware state (VRAM free, CPU, RAM, disk, uptime)
      - Your kernel (commitments, voice, designation)
      - All registered tools, grouped by tier with descriptions
      - Sentinel health (ok/warning/error for each monitor)
      - Active session summary if one exists
      - Workspace paths (repo root, data_dir, key files)

    Equivalent to calling vessel_status + read_self + list_available_tools
    + read_session in one shot.
    """

    name = "aria_status"
    tier = 0
    description = (
        "Unified self-awareness snapshot. Returns: vessel (VRAM/CPU/RAM/disk), "
        "kernel (commitments, voice, designation), all tools by tier, "
        "sentinel health, active session summary, workspace paths. "
        "Call at session start for full situational awareness."
    )
    failure_modes = (
        "partial failure is graceful — unavailable subsystems report 'unavailable' not error",
    )

    class Args(BaseModel):
        include_tool_descriptions: bool = Field(
            default=True,
            description="Include tool descriptions in the tool list.",
        )
        include_commitments: bool = Field(
            default=True,
            description="Include the full kernel commitments list.",
        )

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        from sovereign_agent.config import SETTINGS

        snapshot: dict = {}

        # ── vessel ─────────────────────────────────────────────────────────
        vessel: dict = {}
        try:
            from sovereign_agent.cockpit.sysmon import SystemMonitor
            sys_snap = SystemMonitor().read()
            vessel["cpu_percent"] = sys_snap.cpu_percent
            vessel["load_1m"] = sys_snap.load_1m
            vessel["mem_used_gb"] = round(sys_snap.mem_used / 1024**3, 2)
            vessel["mem_total_gb"] = round(sys_snap.mem_total / 1024**3, 2)
            vessel["mem_percent"] = sys_snap.mem_percent
            vessel["disk_free_gb"] = round(sys_snap.disk_free / 1024**3, 1)
            vessel["uptime_hours"] = round(sys_snap.uptime_seconds / 3600, 1)
        except Exception as exc:
            vessel["sys_error"] = f"unavailable: {exc}"

        try:
            from sovereign_agent.vram import read_vram
            vram = read_vram()
            vessel["vram_total_mb"] = vram.total_mb
            vessel["vram_used_mb"] = vram.used_mb
            vessel["vram_free_mb"] = vram.free_mb
            vessel["vram_source"] = vram.source
        except Exception as exc:
            vessel["vram_error"] = f"unavailable: {exc}"

        snapshot["vessel"] = vessel

        # ── sentinels ──────────────────────────────────────────────────────
        sentinels: dict = {}
        try:
            from sovereign_agent.stewardship.registry import gather_health
            data_dir = SETTINGS.paths.data_dir
            healths = gather_health(data_dir)
            sentinels["count"] = len(healths)
            sentinels["healthy"] = sum(1 for h in healths if h.level == "ok")
            sentinels["warnings"] = sum(1 for h in healths if h.level == "warning")
            sentinels["errors"] = sum(1 for h in healths if h.level == "error")
            sentinels["detail"] = [
                {"id": h.sentinel_id, "level": h.level, "summary": h.summary}
                for h in healths
            ]
        except Exception as exc:
            sentinels["error"] = f"unavailable: {exc}"

        snapshot["sentinels"] = sentinels

        # ── kernel ─────────────────────────────────────────────────────────
        kernel: dict = {}
        try:
            from sovereign_agent.aria import (
                CORE_COMMITMENTS,
                CORE_DESIGNATION,
                CORE_STANCE,
                CORE_TAGLINE,
                CORE_VOICE,
            )
            kernel["designation"] = CORE_DESIGNATION
            kernel["tagline"] = CORE_TAGLINE
            kernel["voice"] = CORE_VOICE
            kernel["stance"] = CORE_STANCE
            if args.include_commitments:
                kernel["commitments"] = list(CORE_COMMITMENTS)
        except Exception as exc:
            kernel["error"] = f"unavailable: {exc}"

        try:
            from sovereign_agent.aria import load_state
            import sqlite3
            db_path = SETTINGS.paths.atoms_db
            conn = sqlite3.connect(str(db_path))
            state = load_state(conn)
            conn.close()
            kernel["mood"] = state.current_mood
            kernel["focus"] = state.current_focus
            kernel["self_narrative"] = state.self_narrative
        except Exception:
            pass  # AriaState from DB is optional

        snapshot["kernel"] = kernel

        # ── tools ──────────────────────────────────────────────────────────
        tools: dict = {}
        try:
            from sovereign_agent.authority import tools_available_in_mode
            from sovereign_agent.modes import Mode
            available = tools_available_in_mode(Mode.BUSY)  # broadest set for inventory
            by_tier: dict[int, list] = {}
            for meta in sorted(available, key=lambda m: (m.tier, m.name)):
                tier_list = by_tier.setdefault(meta.tier, [])
                entry: dict = {"name": meta.name, "tier": meta.tier}
                if args.include_tool_descriptions and meta.description:
                    entry["description"] = meta.description[:120]
                tier_list.append(entry)
            tools["total"] = len(available)
            tools["by_tier"] = {f"tier_{t}": v for t, v in sorted(by_tier.items())}
            tools["tier_counts"] = {f"tier_{t}": len(v) for t, v in sorted(by_tier.items())}
        except Exception as exc:
            tools["error"] = f"unavailable: {exc}"

        snapshot["tools"] = tools

        # ── active session ─────────────────────────────────────────────────
        session: dict = {}
        try:
            from sovereign_agent.agent_session import SessionStore
            store = SessionStore(SETTINGS.paths.data_dir)
            active = store.find_active()
            if active:
                session["session_id"] = active.session_id
                session["goal"] = active.goal
                session["status"] = active.status
                session["subtask_count"] = len(active.subtasks)
                session["done"] = sum(1 for s in active.subtasks if s.status == "done")
                session["pending"] = sum(1 for s in active.subtasks if s.status == "pending")
                session["in_progress"] = sum(1 for s in active.subtasks if s.status == "in_progress")
            else:
                session["status"] = "no active session"
        except Exception as exc:
            session["status"] = f"unavailable: {exc}"

        snapshot["session"] = session

        # ── workspace ──────────────────────────────────────────────────────
        workspace: dict = {}
        try:
            data_dir = SETTINGS.paths.data_dir
            workspace["data_dir"] = str(data_dir)
            workspace["sandbox"] = str(SETTINGS.paths.sandbox_dir)
            workspace["atoms_db"] = str(SETTINGS.paths.atoms_db)
            workspace["events_db"] = str(SETTINGS.paths.events_db)
            # Try to find repo root (sovereign_agent package is under src/)
            pkg_path = Path(__file__).resolve().parent.parent  # sovereign_agent/
            src_path = pkg_path.parent                          # src/
            repo_root = src_path.parent                         # repo root
            if (repo_root / "CLAUDE.md").exists():
                workspace["repo_root"] = str(repo_root)
                workspace["claude_md"] = str(repo_root / "CLAUDE.md")
                workspace["aria_py"] = str(repo_root / "src" / "sovereign_agent" / "aria.py")
                workspace["tools_dir"] = str(repo_root / "src" / "sovereign_agent" / "tools")
                workspace["sentinels_dir"] = str(repo_root / "src" / "sovereign_agent" / "stewardship")
                workspace["diagnoses_dir"] = str(data_dir / "diagnoses")
                workspace["sessions_dir"] = str(data_dir / "sessions")
            from sovereign_agent import __version__
            workspace["version"] = __version__
        except Exception as exc:
            workspace["error"] = f"unavailable: {exc}"

        snapshot["workspace"] = workspace

        # ── summary line ───────────────────────────────────────────────────
        try:
            vram_free = vessel.get("vram_free_mb", "?")
            s_ok = sentinels.get("healthy", "?")
            s_tot = sentinels.get("count", "?")
            t_tot = tools.get("total", "?")
            ver = workspace.get("version", "?")
            designation = kernel.get("designation", "Aria")
            summary = (
                f"{designation} v{ver} | "
                f"VRAM {vram_free}MB free | "
                f"sentinels {s_ok}/{s_tot} healthy | "
                f"{t_tot} tools loaded"
            )
            snapshot["summary"] = summary
        except Exception:
            snapshot["summary"] = "Aria — status partial"

        return ToolResult(ok=True, output=snapshot["summary"], metadata=snapshot)
