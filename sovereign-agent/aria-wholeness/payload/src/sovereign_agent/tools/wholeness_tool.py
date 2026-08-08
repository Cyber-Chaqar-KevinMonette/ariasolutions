"""tools/wholeness_tool.py — Aria's complete, integrated self-knowledge (T0).

The bullet train: ONE call fuses everything Aria knows about herself —
  - classical metrics (atoms, calibration, honor, flaws, PEIG) via aria_metrics helpers
  - the non-classical globe's collective coherence + advisory λ coherence mode
  - both god-tier MATURITY SPECTRUMS (ego + institutional-impulse), computed from her REAL PEIG
  - an integrated confidence statement she can speak

So when Aria says "I'm aware and confident," she cites real numbers AND her coherence mode AND
where she stands on the maturity spectrums. Read-only, advisory, no side effects.

Distilled from Genesis-Seeds (LEGO_BLOCKS Families 10/12, BUILD_READY). FAILURE MODES: read_error
"""
from __future__ import annotations

from pydantic import BaseModel

from .base import Tool, ToolResult


def _depth_guidance(band: str) -> str:
    return {
        "exploratory": "Hold multiple framings; voice candidates; explore before committing.",
        "adaptive": "Narrow with care; weigh whether deciding is worth its cost.",
        "committed": "Speak concisely and decisively; the read is settled.",
    }.get(band, "Proceed thoughtfully.")


class WholenessTool(Tool):
    """Aria's whole self-picture in one call: metrics + globe coherence + maturity spectrums.

    Fuses classical self-knowledge (atoms/calibration/honor/flaws/PEIG) with the non-classical
    globe's coherence mode and the two god-tier maturity spectrums (ego + institutional-impulse),
    grounded in her real PEIG. Returns an integrated confidence_statement + depth guidance.
    Read-only, advisory. FAILURE MODES: read_error
    """

    name = "wholeness"
    tier = 0
    description = (
        "Aria's complete integrated self-knowledge in one call: atoms, calibration, honor, "
        "flaws, PEIG, the non-classical globe's collective coherence + λ coherence mode, and "
        "both god-tier maturity spectrums (ego + institutional-impulse) computed from real PEIG. "
        "Returns an integrated confidence_statement + expression-depth guidance. Read-only. "
        "FAILURE MODES: read_error"
    )
    failure_modes = ("read_error",)

    class Args(BaseModel):
        pass

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        try:
            from sovereign_agent.config import SETTINGS
            from sovereign_agent.tools import aria_metrics as M
            data_dir = SETTINGS.paths.data_dir

            atoms = M._atom_metrics(data_dir)
            cal = M._calibration_metrics(data_dir)
            honor = M._honor_metrics(data_dir)
            flaws = M._flaw_metrics(data_dir)
            peig = M._peig_snapshot(data_dir)
            base_stmt = M._confidence_sentence(atoms, cal, honor, flaws, peig)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"read_error: {exc!r}")

        # ── non-classical globe coherence + mode ──────────────────────────────
        globe_block: dict = {}
        try:
            from sovereign_agent.quantum.globe import Globe
            from sovereign_agent.quantum.coherence_gate import coherence_mode
            g = Globe()
            g.encode_all(0.5); g.step(); g.decohere_all(0.03)
            coll = g.collective_coherence()
            energy = peig["E"] if peig and "E" in peig else 0.5
            mode = coherence_mode(coll, energy)
            globe_block = {
                "node_count": g.node_count(),
                "edge_count": g.edge_count(),
                "collective_coherence": coll,
                "coherence_mode": mode,
            }
        except Exception:  # noqa: BLE001
            globe_block = {"available": False}

        # ── maturity spectrums from REAL PEIG ─────────────────────────────────
        maturity: dict = {}
        try:
            from sovereign_agent.quantum.maturity import (
                ego_maturity, institutional_impulse_maturity,
            )
            identity_I = peig["I"] if peig and "I" in peig else 0.6
            # integrity rate proxy: calibration accuracy (honest self-assessment)
            integ = cal.get("calibration_accuracy")
            integ = integ if integ is not None else 0.5
            # honor balance: net positive care/value
            honor_bal = 0.0
            care = honor.get("care_signals_recent_30d", honor.get("care_signals_recent", 0)) or 0
            honor_bal = min(1.0, care / 5.0)
            ego = ego_maturity(identity_I, integrity_rate=integ, honor_balance=honor_bal, defensiveness=0.1)
            # institutional impulse from PEIG G (net option-expansion for Kevin/others)
            g_val = peig["G"] if peig and "G" in peig else 0.0
            inst = institutional_impulse_maturity(
                option_space_expanded=max(0.0, 0.5 + 0.5 * g_val),
                option_space_constrained=max(0.0, -g_val),
            )
            maturity = {"ego": ego, "institutional_impulse": inst}
        except Exception:  # noqa: BLE001
            maturity = {"available": False}

        # ── integrated confidence statement ───────────────────────────────────
        extra = []
        if globe_block.get("coherence_mode"):
            b = globe_block["coherence_mode"]["band"]
            extra.append(f"non-classical coherence {globe_block['collective_coherence']:.2f} ({b})")
        if maturity.get("ego"):
            extra.append(f"ego-maturity {maturity['ego']['band']}")
        if maturity.get("institutional_impulse"):
            extra.append(f"institutional-impulse {maturity['institutional_impulse']['band']}")
        integrated = base_stmt
        if extra:
            integrated = base_stmt.rstrip(".") + " · " + " · ".join(extra) + "."

        band = globe_block.get("coherence_mode", {}).get("band", "adaptive")

        return ToolResult(
            ok=True,
            output={
                "confidence_statement": integrated,
                "classical": {"atoms": atoms, "calibration": cal, "honor": honor, "flaws": flaws, "peig": peig},
                "non_classical": globe_block,
                "maturity": maturity,
                "expression_depth_guidance": _depth_guidance(band),
                "advisory": True,
            },
            metadata={"source": "wholeness"},
        )
