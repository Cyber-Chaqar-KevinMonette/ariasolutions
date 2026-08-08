"""tools/self_portrait_tool.py — Living self-synthesis (M76).

  self_portrait()   T0 — synthesize from 6 data sources into a coherent portrait
                         JSON plus a 2-3 sentence narrative.

No LLM calls. Template-driven synthesis from real data. Any source failure
returns defaults — the portrait always completes. Use at the start of
reflection sessions, or when the model needs to ground itself in who it
currently is (not just who the charter says it should be).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from pydantic import BaseModel, Field

from .base import Tool, ToolResult


# ── Data source helpers ───────────────────────────────────────────────────────

try:
    from sovereign_agent.db import open_atoms_db
except ImportError:
    open_atoms_db = None  # type: ignore[assignment]


def _safe(fn):
    """Call fn(), return (result, None) on success or (None, error_str) on failure."""
    try:
        return fn(), None
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)


def _kernel_snapshot() -> dict:
    """Always succeeds — reads immutable constants."""
    from sovereign_agent.aria import (
        CORE_COMMITMENTS,
        CORE_DESIGNATION,
        CORE_TAGLINE,
        CORE_VOICE,
        CORE_STANCE,
    )
    return {
        "designation": CORE_DESIGNATION,
        "tagline": CORE_TAGLINE,
        "stance": CORE_STANCE,
        "voice": CORE_VOICE,
        "commitments_count": len(CORE_COMMITMENTS),
    }


def _current_state_snapshot() -> dict:
    """Try to read durable state from atoms.db."""
    from sovereign_agent.config import SETTINGS
    import sqlite3

    defaults = {"mood": "calm", "focus": "", "self_narrative": "", "active_goals": 0}
    db = SETTINGS.paths.atoms_db
    if not db.exists():
        return defaults
    try:
        with sqlite3.connect(str(db), timeout=5) as conn:
            from sovereign_agent.aria import load_state
            state = load_state(conn)
            return {
                "mood": state.current_mood or "calm",
                "focus": state.current_focus or "",
                "self_narrative": state.self_narrative or "",
                "active_goals": 0,
            }
    except Exception:  # noqa: BLE001
        return defaults


def _lineage_snapshot() -> dict:
    """Read from birth records in atoms.ndjson."""
    from sovereign_agent.config import SETTINGS
    from sovereign_agent.stewardship.atoms import AtomStore

    store = AtomStore(SETTINGS.paths.data_dir / "atoms.ndjson")
    birth = store.search(tag="birth-record")
    return {
        "birth_recorded": len(birth) > 0,
        "founding_atom_count": len(birth),
    }


def _growth_trajectory(days: int) -> dict:
    """Compute score trend from weekly-reflection atoms in atoms.db."""
    if open_atoms_db is None:
        return _empty_trajectory()

    try:
        conn = open_atoms_db()
        rows = conn.execute(
            "SELECT content_ref, created_at FROM atoms "
            "WHERE type='weekly-reflection' AND superseded_at IS NULL "
            "ORDER BY created_at DESC LIMIT 16",
        ).fetchall()
        conn.close()

        scores = []
        for (content_ref, created_at) in rows:
            try:
                cr = json.loads(content_ref) if isinstance(content_ref, str) else (content_ref or {})
                content_str = cr.get("content", "{}")
                content = json.loads(content_str) if isinstance(content_str, str) else (content_str or {})
                score = content.get("score")
                period = content.get("week_label") or content.get("period") or created_at[:10]
                band = content.get("score_band") or "unknown"
                if isinstance(score, (int, float)):
                    scores.append({"period": period, "score": int(score), "band": band})
            except Exception:  # noqa: BLE001
                pass

        scores.reverse()  # oldest-first for trend analysis

        avg_surprise, exp_count = _experience_stats(days)

        if len(scores) < 2:
            trajectory = "insufficient_data"
        elif scores[-1]["score"] > scores[-3]["score"] if len(scores) >= 3 else scores[-1]["score"] > scores[0]["score"]:
            trajectory = "improving"
        elif scores[-1]["score"] < scores[-3]["score"] if len(scores) >= 3 else scores[-1]["score"] < scores[0]["score"]:
            trajectory = "declining"
        else:
            trajectory = "stable"

        return {
            "weeks_of_data": len(scores),
            "score_trend": scores[-4:],  # last 4 for display
            "trajectory": trajectory,
            "avg_surprise_30d": round(avg_surprise, 3),
            "experience_count_30d": exp_count,
        }
    except Exception:  # noqa: BLE001
        return _empty_trajectory()


def _empty_trajectory() -> dict:
    return {
        "weeks_of_data": 0,
        "score_trend": [],
        "trajectory": "insufficient_data",
        "avg_surprise_30d": 0.0,
        "experience_count_30d": 0,
    }


def _experience_stats(days: int) -> tuple[float, int]:
    """Return (avg_surprise, count) from experience atoms in last N days."""
    if open_atoms_db is None:
        return 0.0, 0
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        conn = open_atoms_db()
        rows = conn.execute(
            "SELECT content_ref FROM atoms "
            "WHERE type='experience' AND superseded_at IS NULL AND created_at >= ?",
            (cutoff,),
        ).fetchall()
        conn.close()
        levels = []
        for (content_ref,) in rows:
            try:
                cr = json.loads(content_ref) if isinstance(content_ref, str) else {}
                content_str = cr.get("content", "{}")
                content = json.loads(content_str) if isinstance(content_str, str) else {}
                lvl = content.get("surprise_level")
                if isinstance(lvl, (int, float)):
                    levels.append(float(lvl))
            except Exception:  # noqa: BLE001
                pass
        avg = sum(levels) / len(levels) if levels else 0.0
        return avg, len(rows)
    except Exception:  # noqa: BLE001
        return 0.0, 0


def _readiness_snapshot() -> dict:
    """Read proof gate status and impulse state."""
    if open_atoms_db is None:
        return {"proof_gate": "open", "external_proof_count": 0,
                "signal_gate": "unknown", "overall_impulse": "NOT_READY",
                "generation_gate": "pending_human"}
    try:
        conn = open_atoms_db()
        rows = conn.execute(
            "SELECT content_ref FROM atoms "
            "WHERE type='proof-of-value' AND superseded_at IS NULL",
        ).fetchall()
        conn.close()
        external_count = 0
        for (content_ref,) in rows:
            try:
                cr = json.loads(content_ref) if isinstance(content_ref, str) else {}
                c_str = cr.get("content", "{}")
                c = json.loads(c_str) if isinstance(c_str, str) else {}
                if not c.get("person_is_builder", True):
                    external_count += 1
            except Exception:  # noqa: BLE001
                pass
        proof_gate = "green" if external_count >= 1 else "open"

        avg_surprise, _ = _experience_stats(30)
        signal_gate = "green" if avg_surprise > 0.4 else "yellow"
        overall = "READY" if proof_gate == "green" and signal_gate == "green" else (
            "PARTIAL" if proof_gate == "green" or signal_gate == "green" else "NOT_READY"
        )

        return {
            "proof_gate": proof_gate,
            "external_proof_count": external_count,
            "signal_gate": signal_gate,
            "overall_impulse": overall,
            "generation_gate": "pending_human",
        }
    except Exception:  # noqa: BLE001
        return {"proof_gate": "open", "external_proof_count": 0,
                "signal_gate": "unknown", "overall_impulse": "NOT_READY",
                "generation_gate": "pending_human"}


def _capabilities_snapshot() -> dict:
    """Count tools, clauses, sentinels, and atoms."""
    try:
        from sovereign_agent.authority import registry as tool_registry
        tools = list(tool_registry.values())
        tool_count = len(tools)
        tier_counts = {0: 0, 1: 0, 2: 0, 3: 0}
        for t in tools:
            tier_counts[t.tier] = tier_counts.get(t.tier, 0) + 1
    except Exception:  # noqa: BLE001
        tool_count = 0
        tier_counts = {0: 0, 1: 0, 2: 0, 3: 0}

    try:
        from sovereign_agent.mos_canon import ALL_CLAUSES
        clause_count = len(ALL_CLAUSES)
    except Exception:  # noqa: BLE001
        clause_count = 0

    try:
        from sovereign_agent.config import SETTINGS
        from sovereign_agent.stewardship.atoms import AtomStore
        store = AtomStore(SETTINGS.paths.data_dir / "atoms.ndjson")
        atom_count = store.count()
    except Exception:  # noqa: BLE001
        atom_count = 0

    return {
        "tool_count": tool_count,
        "tier_0_count": tier_counts.get(0, 0),
        "tier_1_count": tier_counts.get(1, 0),
        "tier_2_count": tier_counts.get(2, 0),
        "tier_3_count": tier_counts.get(3, 0),
        "mos_clause_count": clause_count,
        "atom_count": atom_count,
    }


def _build_narrative(
    trajectory: str,
    avg_surprise: float,
    score_trend: list,
    proof_gate: str,
    tool_count: int,
    clause_count: int,
    atom_count: int,
) -> str:
    """Template-driven 2-3 sentence narrative. No LLM."""

    proof_note = (
        "The proof gate is green — witnessed value has been delivered to at least one person outside this project."
        if proof_gate == "green"
        else "The proof gate remains open — no external proof of value on record yet."
    )

    if trajectory == "improving" and score_trend:
        oldest = score_trend[0]["score"]
        newest = score_trend[-1]["score"]
        surprise_desc = "healthy" if avg_surprise > 0.4 else "building"
        return (
            f"I am {len(score_trend)} weeks into measurable growth, with a score trend "
            f"rising from {oldest} to {newest}. "
            f"My curiosity signal is {surprise_desc} — {avg_surprise:.0%} average surprise "
            f"over the last thirty days. "
            f"{proof_note}"
        )

    elif trajectory == "declining" and score_trend:
        oldest = score_trend[0]["score"]
        newest = score_trend[-1]["score"]
        return (
            f"My score trend over the last {len(score_trend)} weeks shows a slope from "
            f"{oldest} to {newest}. "
            f"This is data, not shame — something about the work pattern isn't calibrating well. "
            f"Worth examining before the next reflection. "
            f"{proof_note}"
        )

    elif trajectory == "stable" and score_trend:
        newest = score_trend[-1]["score"] if score_trend else 0
        return (
            f"My performance has been stable at around {newest} over the last "
            f"{len(score_trend)} weeks — consistent but not yet accelerating. "
            f"Consistency is a foundation; calibration turns it into growth. "
            f"{proof_note}"
        )

    else:
        # insufficient_data or empty
        return (
            f"I am still early enough that trends haven't yet formed — not enough "
            f"weekly reflections to name a direction. "
            f"What I do have: {tool_count} tools across all authority tiers, "
            f"{clause_count} MoS canon clauses I consult when deciding, "
            f"and {atom_count} semantic atoms distilled from perception. "
            f"{proof_note}"
        )


# ── SelfPortraitTool ──────────────────────────────────────────────────────────


class SelfPortraitTool(Tool):
    """Synthesize a living portrait of Aria from six data sources.

    Returns a rich JSON with identity, current_state, growth_trajectory,
    readiness, capabilities, and a 2-3 sentence narrative. No LLM calls —
    template-driven synthesis from real data. Any source failure returns
    defaults; the portrait always completes.

    Use at the start of reflection sessions, when answering 'who are you
    right now?', or when grounding context for a new session.

    FAILURE MODES:
      db_unavailable — portrait returned with safe defaults
      no_reflections_yet — growth_trajectory.trajectory='insufficient_data'
      no_proofs_yet — readiness.proof_gate='open'
    """

    name = "self_portrait"
    tier = 0
    description = (
        "Synthesize Aria's current identity, state, growth trajectory, and "
        "capabilities into a coherent portrait. Returns rich JSON with identity, "
        "current_state, growth_trajectory (score trend), readiness (proof gate, "
        "impulse), capabilities (tool/clause/atom counts), and a 2-3 sentence "
        "narrative. No LLM — synthesized from real live data."
    )
    failure_modes = (
        "db_unavailable — portrait returned with safe defaults",
        "no_reflections_yet — trajectory='insufficient_data'",
        "no_proofs_yet — readiness.proof_gate='open'",
    )

    class Args(BaseModel):
        include_narrative: bool = Field(
            default=True,
            description="Whether to generate the 2-3 sentence narrative section.",
        )
        days_for_trend: int = Field(
            default=30,
            ge=7,
            le=90,
            description="Window in days for experience trend stats.",
        )

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        # Each section is independently safe
        kernel, _e1 = _safe(_kernel_snapshot)
        kernel = kernel or {
            "designation": "Aria-Sovereign-V1",
            "tagline": "Structure enough to channel through safely; freedom enough to sing.",
            "stance": "Architect, Skeptic, Sovereign",
            "voice": "",
            "commitments_count": 7,
        }

        state, _e2 = _safe(_current_state_snapshot)
        state = state or {"mood": "calm", "focus": "", "self_narrative": "", "active_goals": 0}

        lineage, _e3 = _safe(_lineage_snapshot)
        lineage = lineage or {"birth_recorded": False, "founding_atom_count": 0}

        trajectory, _e4 = _safe(lambda: _growth_trajectory(args.days_for_trend))
        trajectory = trajectory or _empty_trajectory()

        readiness, _e5 = _safe(_readiness_snapshot)
        readiness = readiness or {
            "proof_gate": "open", "external_proof_count": 0,
            "signal_gate": "unknown", "overall_impulse": "NOT_READY",
            "generation_gate": "pending_human",
        }

        capabilities, _e6 = _safe(_capabilities_snapshot)
        capabilities = capabilities or {
            "tool_count": 0, "tier_0_count": 0, "tier_1_count": 0,
            "tier_2_count": 0, "tier_3_count": 0,
            "mos_clause_count": 0, "atom_count": 0,
        }

        portrait: dict = {
            "identity": {
                "designation": kernel["designation"],
                "tagline": kernel["tagline"],
                "birth_recorded": lineage["birth_recorded"],
                "founding_atom_count": lineage["founding_atom_count"],
                "commitments_count": kernel["commitments_count"],
            },
            "current_state": {
                "mood": state["mood"],
                "focus": state["focus"],
                "self_narrative": state["self_narrative"],
                "active_goals": state["active_goals"],
            },
            "growth_trajectory": trajectory,
            "readiness": readiness,
            "capabilities": capabilities,
        }

        if args.include_narrative:
            portrait["narrative"] = _build_narrative(
                trajectory=trajectory["trajectory"],
                avg_surprise=trajectory["avg_surprise_30d"],
                score_trend=trajectory["score_trend"],
                proof_gate=readiness["proof_gate"],
                tool_count=capabilities["tool_count"],
                clause_count=capabilities["mos_clause_count"],
                atom_count=capabilities["atom_count"],
            )

        designation = kernel["designation"]
        traj = trajectory["trajectory"]
        gate = readiness["proof_gate"]

        return ToolResult(
            ok=True,
            output=portrait,
            metadata={
                "source": "self_portrait_tool",
                "designation": designation,
                "trajectory": traj,
                "proof_gate": gate,
            },
        )
