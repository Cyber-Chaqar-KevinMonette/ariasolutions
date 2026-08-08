"""tools/immune_tools.py — Aria's immune system tools (DEFENSIVE, crown-jewel protection).

  immune_status     (T0) — check crown-jewel integrity; instant tamper awareness
  immune_baseline   (T1) — record/refresh the known-good integrity baseline
  immune_quarantine (T1) — isolate a suspicious artifact for analysis (reversible)
  immune_heal       (T2) — restore a tampered crown jewel from a verified backup (reversible, gated)

Defense only. No offensive capability. Outward/destructive actions are not possible here.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from .base import Tool, ToolResult


class ImmuneStatusTool(Tool):
    """Check the integrity of Aria's crown jewels (charter, authority gate, canon, brain, vault).

    Instant tamper awareness. Read-only. FAILURE MODES: read_error
    """

    name = "immune_status"
    tier = 0
    description = (
        "Check the integrity of Aria's crown-jewel files (charter, authority gate, mos_canon, seal, "
        "vault, quantum brain) against the recorded baseline. Returns intact/breach + guidance. "
        "Instant tamper awareness. Read-only. FAILURE MODES: read_error"
    )
    failure_modes = ("read_error",)

    class Args(BaseModel):
        pass

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        try:
            from sovereign_agent.config import SETTINGS
            from sovereign_agent.security.immune import check_integrity
            result = check_integrity(SETTINGS.paths.data_dir)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"read_error: {exc!r}")
        return ToolResult(ok=True, output=result, metadata={"source": "immune_status"})


class ImmuneBaselineTool(Tool):
    """Record/refresh the known-good integrity baseline of the crown jewels. FAILURE MODES: write_error"""

    name = "immune_baseline"
    tier = 1
    description = (
        "Record (or refresh) the known-good integrity baseline (SHA-256) of Aria's crown jewels. "
        "Do this when the system is verified-clean. FAILURE MODES: write_error"
    )
    failure_modes = ("write_error",)

    class Args(BaseModel):
        pass

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        try:
            from sovereign_agent.config import SETTINGS
            from sovereign_agent.security.immune import record_baseline
            result = record_baseline(SETTINGS.paths.data_dir)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"write_error: {exc!r}")
        return ToolResult(ok=True, output=result, metadata={"source": "immune_baseline"})


class ImmuneQuarantineTool(Tool):
    """Isolate a suspicious file into an inert quarantine for analysis (reversible, defensive).

    FAILURE MODES: not_found, quarantine_error
    """

    name = "immune_quarantine"
    tier = 1
    description = (
        "Move a suspicious file into an isolated, inert quarantine dir for forensic analysis (records "
        "size/hash/origin). Defensive only — never executed or weaponized; reversible. "
        "FAILURE MODES: not_found, quarantine_error"
    )
    failure_modes = ("not_found", "quarantine_error")

    class Args(BaseModel):
        suspect_path: str = Field(description="Absolute path of the suspicious file to isolate.")

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        try:
            from sovereign_agent.config import SETTINGS
            from sovereign_agent.security.immune import quarantine
            result = quarantine(SETTINGS.paths.data_dir, args.suspect_path)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"quarantine_error: {exc!r}")
        if not result.get("ok"):
            return ToolResult(ok=False, error=result.get("error", "quarantine_error"))
        return ToolResult(ok=True, output=result, metadata={"source": "immune_quarantine"})


class ImmuneHealTool(Tool):
    """Reversibly restore a tampered crown jewel from a verified backup (gated; takes a safety snapshot).

    FAILURE MODES: heal_error
    """

    name = "immune_heal"
    tier = 2
    description = (
        "Reversibly heal a tampered file by restoring its known-good version from a verified backup. "
        "Takes a pre-heal safety snapshot first (the heal is reversible). Awaits operator approval by "
        "default. FAILURE MODES: heal_error"
    )
    failure_modes = ("heal_error",)

    class Args(BaseModel):
        file_path: str = Field(description="Path of the tampered file to restore.")

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        try:
            from sovereign_agent.config import SETTINGS
            from sovereign_agent.security.immune import heal_from_backup
            result = heal_from_backup(SETTINGS.paths.data_dir, args.file_path)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"heal_error: {exc!r}")
        return ToolResult(ok=True, output=result, metadata={"source": "immune_heal"})
