"""tools/session_portrait_tool.py — Cross-session context transfer bundle (M83).

T0 tool. Returns a structured JSON bundle for session-start warm-up:
recent session-close atoms, Kevin's care signals, high-confidence hot atoms,
and the current PEIG state. Call this at the start of a new session to carry
forward the thread from the previous one.

The bundle is advisory — Aria reads it to warm up context, not to commit.
Kevin can always redirect. Nothing is auto-applied; the portrait is an
invitation to remember.

FAILURE MODES: read_error
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from .base import Tool, ToolResult


class SessionPortraitTool(Tool):
    """Return a cross-session context transfer bundle.

    Includes: recent session-close atoms, Kevin's care signals (most recent
    first), 5 highest-confidence active atoms, and PEIG state. Call at
    session start for maximum continuity and warmth.

    FAILURE MODES: read_error
    """

    name = "session_portrait"
    tier = 0
    description = (
        "Return a session-start context bundle: recent session-close atoms, "
        "Kevin's care signals, hot atoms (highest confidence), and PEIG state. "
        "Call at session start for cross-session continuity. "
        "FAILURE MODES: read_error"
    )
    failure_modes = ("read_error",)

    class Args(BaseModel):
        n_atoms: int = Field(
            default=5, ge=1, le=20,
            description="Number of hot atoms to include (highest confidence).",
        )
        n_care: int = Field(
            default=5, ge=0, le=20,
            description="Number of care signals from Kevin to include.",
        )
        n_sessions: int = Field(
            default=3, ge=1, le=10,
            description="Number of recent session-close atoms to include.",
        )

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        from sovereign_agent.config import SETTINGS
        data_dir = SETTINGS.paths.data_dir
        portrait: dict = {}

        # ── PEIG state ────────────────────────────────────────────────────────
        try:
            from sovereign_agent.stewardship.peig_sentinel import measure_peig
            state = measure_peig(data_dir)
            portrait["peig_state"] = state.as_dict()
        except Exception as exc:
            portrait["peig_state"] = {"error": repr(exc)}

        # ── Recent session-close atoms ─────────────────────────────────────────
        try:
            from sovereign_agent.stewardship.atoms import AtomStore
            store = AtomStore(data_dir / "atoms.ndjson")
            session_atoms = store.search(tag="session-close")
            portrait["last_sessions"] = [
                {
                    "atom_id": a.atom_id[:8],
                    "title":   a.title,
                    "claim":   a.claim,
                    "ts":      a.ts_updated,
                }
                for a in session_atoms[: args.n_sessions]
            ]
        except Exception as exc:
            portrait["last_sessions"] = {"error": repr(exc)}

        # ── Kevin's care signals ───────────────────────────────────────────────
        try:
            from sovereign_agent.stewardship.honor import HonorDirection, HonorLedger
            honor_path = data_dir / "honor" / "ledger.jsonl"
            if honor_path.exists():
                ledger = HonorLedger(honor_path)
                care = ledger.search(
                    direction=HonorDirection.KEVIN_TO_ARIA, tag="reaction"
                )
                portrait["care_signals"] = [
                    {
                        "note_id": n.note_id[:8],
                        "text":    n.text,
                        "tags":    [t for t in n.tags if t != "reaction"],
                        "ts":      n.ts,
                    }
                    for n in care[: args.n_care]
                ]
            else:
                portrait["care_signals"] = []
        except Exception as exc:
            portrait["care_signals"] = {"error": repr(exc)}

        # ── Hot atoms (highest-confidence active atoms) ────────────────────────
        try:
            from sovereign_agent.stewardship.atoms import AtomStore
            store = AtomStore(data_dir / "atoms.ndjson")
            active = store.active()
            hot = sorted(active, key=lambda a: a.confidence, reverse=True)[: args.n_atoms]
            portrait["hot_atoms"] = [
                {
                    "atom_id":    a.atom_id[:8],
                    "title":      a.title,
                    "kind":       a.kind.value if hasattr(a.kind, "value") else str(a.kind),
                    "claim":      a.claim,
                    "confidence": round(a.confidence, 3),
                    "tags":       a.tags[:5],
                }
                for a in hot
            ]
        except Exception as exc:
            portrait["hot_atoms"] = {"error": repr(exc)}

        return ToolResult(
            ok=True,
            output=portrait,
            metadata={"source": "session_portrait"},
        )
