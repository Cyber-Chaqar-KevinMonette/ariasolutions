"""patcher.py — Timeout round T2: the standing gate.

Patches:
  1. timeouts/__init__.py — export gate() + TimeoutGateVerdict (small,
     additive — T1's exports untouched).
  2. scripts/pre_apply_gate.sh — a fifth call, timeout_gate.py checking
     the shared event log (not a per-module target like the other four
     gates), worst-wins the exit code with the four already there.

Anchored transforms only; MARK-idempotent; a moved anchor raises loudly."""
from __future__ import annotations

MARK = "timeout-gate-d"


class PatchError(Exception):
    pass


def _replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if text.count(old) != 1:
        raise PatchError(f"{label}: expected 1 anchor, found {text.count(old)}")
    return text.replace(old, new, 1)


# ── 1. timeouts/__init__.py — export the gate ────────────────────────────

INIT_ANCHOR = '''from .ledger import (
    TIMEOUT_CATALOG,
    TimeoutEvent,
    TimeoutScanResult,
    latest_timeout_scan,
    record_timeout_scan,
    timeout_trend,
)

__all__ = [
    "TIMEOUT_CATALOG", "TimeoutEvent", "TimeoutScanResult",
    "record_timeout_scan", "latest_timeout_scan", "timeout_trend",
]
'''

INIT_NEW = f'''from .gate import TimeoutGateVerdict, gate  # {MARK}
from .ledger import (
    TIMEOUT_CATALOG,
    TimeoutEvent,
    TimeoutScanResult,
    latest_timeout_scan,
    record_timeout_scan,
    timeout_trend,
)

__all__ = [
    "TIMEOUT_CATALOG", "TimeoutEvent", "TimeoutScanResult",
    "record_timeout_scan", "latest_timeout_scan", "timeout_trend",
    "TimeoutGateVerdict", "gate",  # {MARK}
]
'''


def patch_timeouts_init(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    return _replace_once(text, INIT_ANCHOR, INIT_NEW, label="timeouts init"), True


# ── 2. scripts/pre_apply_gate.sh — a fifth gate call ──────────────────────

GATE_SH_ANCHOR = '''# integrity-gate-d — the integrity gate: composite anti-misleading check over the
# module's own README. Worst-wins with the three rc's above.
"$VENV_PY" "$REPO_ROOT/scripts/lib/integrity_gate.py" --module "$MOD"
irc=$?
[[ $irc -ne 0 ]] && rc=$irc
echo "──────────────────────────────────────"
'''

GATE_SH_NEW = f'''# integrity-gate-d — the integrity gate: composite anti-misleading check over the
# module's own README. Worst-wins with the three rc's above.
"$VENV_PY" "$REPO_ROOT/scripts/lib/integrity_gate.py" --module "$MOD"
irc=$?
[[ $irc -ne 0 ]] && rc=$irc
# {MARK} — the timeout gate: checks the shared event log for recurring
# unexplained timeouts (not per-module — the same check every apply
# shares). Worst-wins with the four rc's above.
"$VENV_PY" "$REPO_ROOT/scripts/lib/timeout_gate.py"
trc=$?
[[ $trc -ne 0 ]] && rc=$trc
echo "──────────────────────────────────────"
'''


def patch_pre_apply_gate(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    return _replace_once(text, GATE_SH_ANCHOR, GATE_SH_NEW,
                         label="pre_apply_gate.sh"), True


ALL_PATCHES = {
    "timeouts/__init__.py": patch_timeouts_init,
}

SCRIPT_PATCHES = {
    "pre_apply_gate.sh": patch_pre_apply_gate,
}
