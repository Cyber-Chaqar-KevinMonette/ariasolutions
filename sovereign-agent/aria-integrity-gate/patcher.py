"""patcher.py — Integrity round I2: the standing gate.

Patches:
  1. integrity/__init__.py — export gate() + IntegrityGateVerdict (small,
     additive — I1's exports untouched).
  2. scripts/pre_apply_gate.sh — a fourth call, integrity_gate.py over the
     module's own README, worst-wins the exit code with the three already
     there (scrutiny, quality, grounding).

Anchored transforms only; MARK-idempotent; a moved anchor raises loudly."""
from __future__ import annotations

MARK = "integrity-gate-d"


class PatchError(Exception):
    pass


def _replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if text.count(old) != 1:
        raise PatchError(f"{label}: expected 1 anchor, found {text.count(old)}")
    return text.replace(old, new, 1)


# ── 1. integrity/__init__.py — export the gate ───────────────────────────

INIT_ANCHOR = '''from .ledger import (
    IntegrityPassResult,
    IntegritySignal,
    calibration_sensitivity,
    integrity_trend,
    latest_integrity,
    record_integrity_pass,
)

__all__ = [
    "IntegritySignal", "IntegrityPassResult", "record_integrity_pass",
    "latest_integrity", "integrity_trend", "calibration_sensitivity",
]
'''

INIT_NEW = f'''from .gate import IntegrityGateVerdict, gate  # {MARK}
from .ledger import (
    IntegrityPassResult,
    IntegritySignal,
    calibration_sensitivity,
    integrity_trend,
    latest_integrity,
    record_integrity_pass,
)

__all__ = [
    "IntegritySignal", "IntegrityPassResult", "record_integrity_pass",
    "latest_integrity", "integrity_trend", "calibration_sensitivity",
    "IntegrityGateVerdict", "gate",  # {MARK}
]
'''


def patch_integrity_init(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    return _replace_once(text, INIT_ANCHOR, INIT_NEW, label="integrity init"), True


# ── 2. scripts/pre_apply_gate.sh — a fourth gate call ─────────────────────

GATE_SH_ANCHOR = '''# grounding-gate-d — the grounding gate: does the module's own README prose hold up?
# Worst-wins with the two rc's above.
"$VENV_PY" "$REPO_ROOT/scripts/lib/grounding_gate.py" --module "$MOD"
grc=$?
[[ $grc -ne 0 ]] && rc=$grc
echo "──────────────────────────────────────"
'''

GATE_SH_NEW = f'''# grounding-gate-d — the grounding gate: does the module's own README prose hold up?
# Worst-wins with the two rc's above.
"$VENV_PY" "$REPO_ROOT/scripts/lib/grounding_gate.py" --module "$MOD"
grc=$?
[[ $grc -ne 0 ]] && rc=$grc
# {MARK} — the integrity gate: composite anti-misleading check over the
# module's own README. Worst-wins with the three rc's above.
"$VENV_PY" "$REPO_ROOT/scripts/lib/integrity_gate.py" --module "$MOD"
irc=$?
[[ $irc -ne 0 ]] && rc=$irc
echo "──────────────────────────────────────"
'''


def patch_pre_apply_gate(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    return _replace_once(text, GATE_SH_ANCHOR, GATE_SH_NEW,
                         label="pre_apply_gate.sh"), True


ALL_PATCHES = {
    "integrity/__init__.py": patch_integrity_init,
}

SCRIPT_PATCHES = {
    "pre_apply_gate.sh": patch_pre_apply_gate,
}
