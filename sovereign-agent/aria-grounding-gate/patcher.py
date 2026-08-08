"""patcher.py — Grounding round G2: the calibration check.

Today `curiosity.py`'s wonder loop trusts the model's self-reported
confidence with nothing checking it against the answer's own grounding
texture. This wires G1's classifier composition into a real gate with
real teeth: a confidently-claimed answer that doesn't actually verify as
grounded gets its confidence clamped BEFORE it's recorded — the existing
`if rec.confidence < LOW_CONFIDENCE:` uncertainty-registry branch then
fires exactly as originally designed, now honestly.

Patches:
  1. grounding/__init__.py — export gate() + GroundingGateVerdict (small,
     additive — G1's exports untouched).
  2. curiosity.py — the calibration hook, right after `rec` is validated
     and before it's recorded.
  3. scripts/pre_apply_gate.sh — a third call, grounding_gate.py over the
     module's own README, worst-wins the exit code with the two already
     there.

Anchored transforms only; MARK-idempotent; a moved anchor raises loudly."""
from __future__ import annotations

MARK = "grounding-gate-d"


class PatchError(Exception):
    pass


def _replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if text.count(old) != 1:
        raise PatchError(f"{label}: expected 1 anchor, found {text.count(old)}")
    return text.replace(old, new, 1)


# ── 1. grounding/__init__.py — export the gate ───────────────────────────

INIT_ANCHOR = '''from .ledger import (
    GroundingPassResult, latest_grounding, grounding_trend,
    record_grounding_pass,
)

__all__ = [
    "GroundingPassResult", "latest_grounding", "grounding_trend",
    "record_grounding_pass",
]
'''

INIT_NEW = f'''from .gate import GroundingGateVerdict, gate  # {MARK}
from .ledger import (
    GroundingPassResult, latest_grounding, grounding_trend,
    record_grounding_pass,
)

__all__ = [
    "GroundingPassResult", "latest_grounding", "grounding_trend",
    "record_grounding_pass", "GroundingGateVerdict", "gate",  # {MARK}
]
'''


def patch_grounding_init(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    return _replace_once(text, INIT_ANCHOR, INIT_NEW, label="grounding init"), True


# ── 2. curiosity.py — the calibration hook ────────────────────────────────

CURIOSITY_ANCHOR = '''    if not rec.question:
        emit_event("qa-x", plane="control", trace_id=trace,
                   payload={"error": "empty question"})
        return None
    record_qa(rec, data_dir)
'''

CURIOSITY_NEW = f'''    if not rec.question:
        emit_event("qa-x", plane="control", trace_id=trace,
                   payload={{"error": "empty question"}})
        return None
    try:  # {MARK} — the calibration hook: an intended extension point,
        # not dead code — does the claimed confidence actually match the
        # answer's own grounding texture? A mismatch clamps confidence
        # below LOW_CONFIDENCE so the branch just below fires honestly.
        from sovereign_agent.grounding.gate import gate as _grounding_gate

        _verdict = _grounding_gate(rec.answer, claimed_confidence=rec.confidence)
        if _verdict.calibration_mismatch:
            rec.confidence = min(rec.confidence, LOW_CONFIDENCE - 0.01)
    except Exception:  # noqa: BLE001 — grounding not applied → nothing to gate
        pass
    record_qa(rec, data_dir)
'''


def patch_curiosity(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    return _replace_once(text, CURIOSITY_ANCHOR, CURIOSITY_NEW,
                         label="curiosity.py calibration hook"), True


# ── 3. scripts/pre_apply_gate.sh — a third gate call ──────────────────────

GATE_SH_ANCHOR = '''# quality-gate-d — the quality gate: real hardening checks over the module's own
# payload, not just prose review. Worst-wins with the scrutiny rc above.
"$VENV_PY" "$REPO_ROOT/scripts/lib/quality_gate.py" --module "$MOD"
qrc=$?
[[ $qrc -ne 0 ]] && rc=$qrc
echo "──────────────────────────────────────"
'''

GATE_SH_NEW = f'''# quality-gate-d — the quality gate: real hardening checks over the module's own
# payload, not just prose review. Worst-wins with the scrutiny rc above.
"$VENV_PY" "$REPO_ROOT/scripts/lib/quality_gate.py" --module "$MOD"
qrc=$?
[[ $qrc -ne 0 ]] && rc=$qrc
# {MARK} — the grounding gate: does the module's own README prose hold up?
# Worst-wins with the two rc's above.
"$VENV_PY" "$REPO_ROOT/scripts/lib/grounding_gate.py" --module "$MOD"
grc=$?
[[ $grc -ne 0 ]] && rc=$grc
echo "──────────────────────────────────────"
'''


def patch_pre_apply_gate(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    return _replace_once(text, GATE_SH_ANCHOR, GATE_SH_NEW,
                         label="pre_apply_gate.sh"), True


ALL_PATCHES = {
    "grounding/__init__.py": patch_grounding_init,
    "curiosity.py": patch_curiosity,
}

SCRIPT_PATCHES = {
    "pre_apply_gate.sh": patch_pre_apply_gate,
}
