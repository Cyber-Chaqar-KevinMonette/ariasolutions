"""tools/quantum_consult_tool.py — Ask the non-classical council a question (T1).

Runs a question through the 13-node globe and returns a coherence-weighted disposition plus
each node's state-coupled voice (brain→mouth, Block 9.1). This is the "non-classical mode"
Kevin and Aria can consult. ADVISORY ONLY — the council offers a read; Kevin/Aria decide. It
never gates actions and never raises authority.

T1 (it runs an emulation step); no writes, no side effects on data stores.
FAILURE MODES: consult_error
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from .base import Tool, ToolResult


class QuantumConsultTool(Tool):
    """Consult the non-classical globe council on a question (advisory).

    Returns: disposition (0..1) + lean (yes/no/split), the advisory λ coherence mode,
    Aria's center synthesis, and 12 council voices whose tone emerges from their measured
    quantum state. Advisory only; never decides or acts.

    FAILURE MODES: consult_error
    """

    name = "quantum_consult"
    tier = 1
    description = (
        "Ask the non-classical globe council a yes/no-shaped question. Returns an advisory "
        "coherence-weighted disposition + lean, the λ coherence mode, Aria's center synthesis, "
        "and 12 state-coupled council voices. Advisory only — never gates actions or decides. "
        "FAILURE MODES: consult_error"
    )
    failure_modes = ("consult_error",)

    class Args(BaseModel):
        question: str = Field(description="The question to put to the council.")
        steps: int = Field(default=2, description="Coupling sweeps (1-5).")

    async def execute(self, args: Args, *, trace_id: str) -> ToolResult:
        if not args.question.strip():
            return ToolResult(ok=False, error="consult_error: empty question")
        try:
            from sovereign_agent.quantum.council import consult_council
            steps = max(1, min(5, args.steps))
            result = consult_council(args.question.strip(), steps=steps)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"consult_error: {exc!r}")

        # council-trust-log-d — log this consult so its outcome can be verified later
        try:
            from sovereign_agent.config import SETTINGS
            from sovereign_agent.quantum.trust import log_consult
            _logged = log_consult(SETTINGS.paths.data_dir, question=result["question"],
                                  lean=result["lean"], disposition=result["disposition"],
                                  coherence=result.get("self_coherence", 0.0))
            result["consult_id"] = _logged["consult_id"]
        except Exception:
            pass
        return ToolResult(ok=True, output=result, metadata={"source": "quantum_consult"})
