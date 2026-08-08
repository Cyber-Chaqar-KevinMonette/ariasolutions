"""tools/risk_tools.py — Risk Register read + propose tools (M57).

  risk_register_read()       T0 — parse RISK-NNN blocks from the markdown
  risk_register_propose()    T1 — write a risk-proposal atom (no markdown edits)
"""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from .base import Tool, ToolResult

try:
    from sovereign_agent.db import open_atoms_db
except ImportError:
    open_atoms_db = None  # type: ignore[assignment]

try:
    from sovereign_agent.memory import Atom, write_atom
except ImportError:
    Atom = None  # type: ignore[assignment]
    write_atom = None  # type: ignore[assignment]


def _register_path() -> Path:
    return Path(__file__).parents[3] / "docs" / "Aria_Weakness_Risk_Register.md"


# Maps section header glyph → severity label
_SECTION_GLYPHS = {
    "🔴": "critical",
    "🟡": "material",
    "🟢": "watch",
}

_SECTION_HEADER = re.compile(r"^###\s+(🔴|🟡|🟢)\s+(.+)$", re.MULTILINE)
_RISK_HEADER = re.compile(r"\*\*(RISK-\d{3})\s*[—–-]\s*(.+?)\.\*\*")
_STATUS_LINE = re.compile(
    r"`Category:\s*([^·`]+?)\s*·\s*Confidence:\s*([^·`]+?)\s*·\s*Status:\s*([^·`]+?)\s*·\s*Owner:\s*([^`]+?)\s*`"
)


def _parse_register(text: str) -> list[dict]:
    """Parse RISK-NNN entries from the register markdown.

    Returns a list of dicts with keys:
      id, title, category, confidence, status, owner, severity_glyph
    """
    # Build a map of line-position → severity glyph from section headers
    severity_by_pos: list[tuple[int, str]] = []
    for m in _SECTION_HEADER.finditer(text):
        glyph = m.group(1)
        severity_by_pos.append((m.start(), _SECTION_GLYPHS.get(glyph, "unknown")))

    def _severity_at(pos: int) -> str:
        label = "unknown"
        for start, sev in severity_by_pos:
            if start <= pos:
                label = sev
        return label

    results = []
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        hm = _RISK_HEADER.search(line)
        if hm:
            risk_id = hm.group(1)
            title = hm.group(2).strip()
            # Calculate approximate character position for severity lookup
            char_pos = len("\n".join(lines[:i]))

            # Look for status line in the next few lines
            entry: dict = {
                "id": risk_id,
                "title": title,
                "category": "?",
                "confidence": "?",
                "status": "?",
                "owner": "?",
                "severity": _severity_at(char_pos),
            }
            for j in range(i + 1, min(i + 5, len(lines))):
                sm = _STATUS_LINE.search(lines[j])
                if sm:
                    entry["category"] = sm.group(1).strip()
                    entry["confidence"] = sm.group(2).strip()
                    entry["status"] = sm.group(3).strip()
                    entry["owner"] = sm.group(4).strip()
                    break
            if entry["status"] != "?":  # skip references without a status line
                results.append(entry)
        i += 1
    return results


# ── RiskRegisterReadTool ──────────────────────────────────────────────────────

class _ReadArgs(BaseModel):
    status_filter: Optional[str] = Field(
        default=None,
        description="Filter by status: OPEN, MITIGATING, ACCEPTED, CLOSED, WATCH. None returns all.",
    )


class RiskRegisterReadTool(Tool[_ReadArgs]):
    name = "risk_register_read"
    tier = 0
    description = (
        "Read and parse Aria_Weakness_Risk_Register.md. Returns a list of all RISK-NNN entries "
        "with id, title, category, confidence, status, owner, and severity. "
        "Optional status_filter to narrow results."
    )
    failure_modes = ("register_missing",)
    Args = _ReadArgs

    async def execute(self, args: _ReadArgs, *, trace_id: str) -> ToolResult:
        path = _register_path()
        if not path.is_file():
            return ToolResult(ok=True, output={
                "risks": [],
                "total": 0,
                "note": f"Register not found at {path}",
            })

        text = path.read_text(encoding="utf-8")
        risks = _parse_register(text)

        if args.status_filter:
            target = args.status_filter.upper().strip()
            risks = [r for r in risks if r["status"].upper() == target]

        return ToolResult(ok=True, output={
            "risks": risks,
            "total": len(risks),
            "register_path": str(path),
        })


# ── RiskRegisterProposeTool ───────────────────────────────────────────────────

class _ProposeArgs(BaseModel):
    risk_id: str = Field(description="The RISK-NNN identifier (e.g., 'RISK-004').")
    current_status: str = Field(description="Current status as it appears in the register.")
    proposed_status: str = Field(description="Proposed new status: OPEN|MITIGATING|ACCEPTED|CLOSED.")
    rationale: str = Field(
        description="Non-empty explanation of why the status should change.",
        min_length=10,
    )
    mitigations_deployed: list[str] = Field(
        default_factory=list,
        description="List of module/milestone names that address this risk.",
    )


class RiskRegisterProposeTool(Tool[_ProposeArgs]):
    name = "risk_register_propose"
    tier = 1
    description = (
        "Write a risk-proposal atom to request a status change in the risk register. "
        "Does NOT edit Aria_Weakness_Risk_Register.md — Kevin reviews the proposal and "
        "applies it manually. Requires a non-empty rationale. T1 because it creates a "
        "persistent proposal record."
    )
    failure_modes = ("db_write_failed",)
    Args = _ProposeArgs

    async def execute(self, args: _ProposeArgs, *, trace_id: str) -> ToolResult:
        if open_atoms_db is None or Atom is None or write_atom is None:
            return ToolResult(ok=False, error="DB or Atom unavailable — cannot write proposal.")

        content = {
            "risk_id": args.risk_id,
            "current_status": args.current_status,
            "proposed_status": args.proposed_status,
            "rationale": args.rationale,
            "mitigations_deployed": args.mitigations_deployed,
        }
        atom = Atom(
            type="risk-proposal",
            summary=(
                f"[{args.risk_id}] propose {args.current_status} → {args.proposed_status}: "
                f"{args.rationale[:80]}"
            ),
            content_ref={"kind": "inline", "content": json.dumps(content)},
            claims=[],
            parents=[trace_id],
            confidence=0.9,
            created_by={"actor": "risk-register-crown", "version": "M57"},
            scope_tags=["risk-proposal", args.risk_id.lower(), args.proposed_status.lower()],
        )

        try:
            conn = open_atoms_db()
            atom_id = await asyncio.to_thread(write_atom, conn, atom)
            conn.commit()
            return ToolResult(ok=True, output={
                "atom_id": str(atom_id),
                "risk_id": args.risk_id,
                "proposed_status": args.proposed_status,
                "note": (
                    f"Proposal recorded. Kevin must edit Aria_Weakness_Risk_Register.md "
                    f"to flip {args.risk_id} from {args.current_status!r} to {args.proposed_status!r}."
                ),
            })
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"risk_register_propose failed: {e}")


__all__ = ["RiskRegisterReadTool", "RiskRegisterProposeTool"]
