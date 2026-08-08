"""aria-grounding-gate — the calibration check. (Grounding round · G2)

`grounding/gate.py` is a brand-new submodule inside the already-live
`grounding/` package (G1 applied) — reachable pre-apply via path
extension. `grounding/__init__.py`'s export, `curiosity.py`'s calibration
hook, and `pre_apply_gate.sh`'s third call are all IN-PLACE patches —
patch-dependent, skip honestly pre-apply; the apply script re-runs this
file and requires zero skips.
"""
from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest


def _find_repo_root(start: Path) -> Path:
    """A fixed parents[N] count breaks depending on staged
    (aria-grounding-gate/tests/, 2 levels down) vs. promoted (tests/, 1
    level down) location — mirrors quality_gate.py's own walk-up."""
    for candidate in (start, *start.parents):
        if (candidate / "src" / "sovereign_agent" / "cockpit" / "app.py").is_file():
            return candidate
    raise RuntimeError(f"could not locate repo root from {start}")


REPO_ROOT = _find_repo_root(Path(__file__).resolve())

MOSTLY_MYSTICAL = (
    "The web bursts into web, and I name it stillness. Cosmic resonance "
    "vibrates through the infinite lattice of becoming, luminous and "
    "boundless, ascending toward pure presence."
)
MOSTLY_EVIDENCE = (
    "The test suite passed 412 of 412 tests after the fix in loader.py. "
    "Latency dropped from 220ms to 90ms, measured across 50 runs."
)
HONEST_HEDGE = (
    "I might be wrong here — I haven't verified this yet, but I suspect "
    "the cause could be a timing issue. Worth checking further."
)


def _patched(obj) -> bool:
    return "grounding-gate-d" in inspect.getsource(obj)


# ─── grounding/gate.py core ───────────────────────────────────────────────


def test_mystical_fog_text_blocks():
    from sovereign_agent.grounding.gate import gate

    verdict = gate(MOSTLY_MYSTICAL)
    assert verdict.verdict == "BLOCK"
    assert verdict.text_verdict == "ungrounded" or verdict.calibration_mismatch


def test_evidence_backed_text_passes():
    from sovereign_agent.grounding.gate import gate

    verdict = gate(MOSTLY_EVIDENCE)
    assert verdict.verdict == "PASS"
    assert verdict.text_verdict == "grounded"


def test_calibration_mismatch_blocks_even_though_text_alone_might_not():
    from sovereign_agent.grounding.gate import gate

    verdict = gate(MOSTLY_MYSTICAL, claimed_confidence=0.9)
    assert verdict.verdict == "BLOCK"
    assert verdict.calibration_mismatch is True


def test_honest_low_confidence_hedge_passes_unclamped():
    from sovereign_agent.grounding.gate import gate

    verdict = gate(HONEST_HEDGE, claimed_confidence=0.3)
    assert verdict.calibration_mismatch is False
    assert verdict.verdict in ("PASS", "WARN")


def test_empty_text_is_honest_pass_not_a_block():
    from sovereign_agent.grounding.gate import gate

    verdict = gate("")
    assert verdict.verdict == "PASS"
    assert verdict.text_verdict == ""


def test_kill_switch_degrades_to_pass(monkeypatch):
    from sovereign_agent.grounding.gate import gate

    monkeypatch.setenv("SOV_NO_GROUNDING_GATE", "1")
    verdict = gate(MOSTLY_MYSTICAL, claimed_confidence=0.9)
    assert verdict.verdict == "PASS"
    assert "kill-switched" in verdict.notes[0]


# ─── curiosity.py wiring (patch-dependent) ────────────────────────────────


class _FakeClient:
    def __init__(self, payload):
        self._payload = payload

    async def chat(self, **kwargs):
        return {"message": {"role": "assistant", "content": json.dumps(self._payload)}}


@pytest.mark.asyncio
async def test_wonder_clamps_confidence_on_calibration_mismatch():
    from sovereign_agent import curiosity

    if not _patched(curiosity):
        pytest.skip("pre-apply: curiosity.py not yet patched")

    rec = await curiosity.wonder(
        "a test topic",
        client=_FakeClient({
            "question": "what is the nature of becoming?",
            "answer": MOSTLY_MYSTICAL,
            "confidence": 0.9,
            "next_check": "meditate further",
        }),
    )
    assert rec is not None
    assert rec.confidence < curiosity.LOW_CONFIDENCE


@pytest.mark.asyncio
async def test_wonder_clamp_still_opens_the_uncertainty_the_low_confidence_branch_promises():
    from sovereign_agent import curiosity
    from sovereign_agent.epistemic_ledger.ledger import UncertaintyRegistry

    if not _patched(curiosity):
        pytest.skip("pre-apply: curiosity.py not yet patched")

    rec = await curiosity.wonder(
        "a test topic",
        client=_FakeClient({
            "question": "what is the nature of becoming, precisely?",
            "answer": MOSTLY_MYSTICAL,
            "confidence": 0.95,
            "next_check": "meditate further",
        }),
    )
    assert rec is not None
    open_qs = [u.question for u in UncertaintyRegistry().list_open()]
    assert rec.question in open_qs


@pytest.mark.asyncio
async def test_wonder_unaffected_when_text_and_confidence_already_agree():
    """A genuinely grounded, honestly-confident answer must be byte-
    identical to today — the gate only acts on a mismatch."""
    from sovereign_agent import curiosity

    if not _patched(curiosity):
        pytest.skip("pre-apply: curiosity.py not yet patched")

    rec = await curiosity.wonder(
        "a test topic",
        client=_FakeClient({
            "question": "does the fix hold under load?",
            "answer": MOSTLY_EVIDENCE,
            "confidence": 0.9,
            "next_check": "run it again tomorrow",
        }),
    )
    assert rec is not None
    assert rec.confidence == 0.9


# ─── grounding/__init__.py export + pre_apply_gate.sh (patch-dependent) ───


def test_grounding_init_exports_the_gate():
    import sovereign_agent.grounding as grounding_mod

    if not _patched(grounding_mod):
        pytest.skip("pre-apply: grounding/__init__.py not yet patched")
    assert hasattr(grounding_mod, "gate")
    assert hasattr(grounding_mod, "GroundingGateVerdict")


def test_pre_apply_gate_sh_calls_the_grounding_gate():
    text = (REPO_ROOT / "scripts" / "pre_apply_gate.sh").read_text(encoding="utf-8")
    if "grounding-gate-d" not in text:
        pytest.skip("pre-apply: pre_apply_gate.sh not yet patched")
    assert "grounding_gate.py" in text
