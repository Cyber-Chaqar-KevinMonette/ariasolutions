"""patcher.py — Quality round Q2: wire qa/hardening into real gates.

Kevin: *"Quality gates perhaps?"* Today neither `pre_apply_gate.sh` nor
`safe_apply.sh`'s post-apply step calls anything in `qa/*`. This wires it
in with real teeth — auto-rollback on a hardening regression — reusing
the git snapshot `safe_apply.sh` already writes rather than inventing new
plumbing.

Patches:
  1. quality/__init__.py — export gate() + QualityGateVerdict (small,
     additive — Q1's exports untouched).
  2. scripts/pre_apply_gate.sh — a second call, quality_gate.py over the
     module's payload, worst-wins the exit code with scrutiny.py's.
  3. scripts/safe_apply.sh — after floor_check, before auto-rollback:
     git diff the already-written snapshot commit for the .py files THIS
     apply touched, gate them, fold a BLOCK into the existing `ok` var —
     rides the rollback path M9 already hardened, no new machinery.

Anchored transforms only; MARK-idempotent; a moved anchor raises loudly."""
from __future__ import annotations

MARK = "quality-gate-d"


class PatchError(Exception):
    pass


def _replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if text.count(old) != 1:
        raise PatchError(f"{label}: expected 1 anchor, found {text.count(old)}")
    return text.replace(old, new, 1)


# ── 1. quality/__init__.py — export the gate ─────────────────────────────

INIT_ANCHOR = '''from .ledger import (
    QualityPassResult, latest_quality, quality_trend, record_quality_pass,
)

__all__ = [
    "QualityPassResult", "latest_quality", "quality_trend",
    "record_quality_pass",
]
'''

INIT_NEW = f'''from .gate import QualityGateVerdict, gate  # {MARK}
from .ledger import (
    QualityPassResult, latest_quality, quality_trend, record_quality_pass,
)

__all__ = [
    "QualityPassResult", "latest_quality", "quality_trend",
    "record_quality_pass", "QualityGateVerdict", "gate",  # {MARK}
]
'''


def patch_quality_init(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    return _replace_once(text, INIT_ANCHOR, INIT_NEW, label="quality init"), True


# ── 2. scripts/pre_apply_gate.sh ──────────────────────────────────────────

GATE_SH_ANCHOR = '''echo "════════ PRE-APPLY GATE: $MOD ════════"
"$VENV_PY" "$REPO_ROOT/scripts/lib/scrutiny.py" --module "$MOD"
rc=$?
echo "──────────────────────────────────────"
[[ $rc -eq 0 ]] && echo "GATE: clear to apply (propose-only — Kevin decides)" || echo "GATE: a voice says STOP — review before applying"
exit $rc
'''

GATE_SH_NEW = f'''echo "════════ PRE-APPLY GATE: $MOD ════════"
"$VENV_PY" "$REPO_ROOT/scripts/lib/scrutiny.py" --module "$MOD"
rc=$?
# {MARK} — the quality gate: real hardening checks over the module's own
# payload, not just prose review. Worst-wins with the scrutiny rc above.
"$VENV_PY" "$REPO_ROOT/scripts/lib/quality_gate.py" --module "$MOD"
qrc=$?
[[ $qrc -ne 0 ]] && rc=$qrc
echo "──────────────────────────────────────"
[[ $rc -eq 0 ]] && echo "GATE: clear to apply (propose-only — Kevin decides)" || echo "GATE: a voice says STOP — review before applying"
exit $rc
'''


def patch_pre_apply_gate(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    return _replace_once(text, GATE_SH_ANCHOR, GATE_SH_NEW,
                         label="pre_apply_gate.sh"), True


# ── 3. scripts/safe_apply.sh — fold into the existing rollback path ──────

SAFE_APPLY_ANCHOR = '''if [[ -x scripts/floor_check.sh ]]; then
  scripts/floor_check.sh --quiet >/dev/null 2>&1 && echo "  ✓ floor still MET" || { echo "  ✗ floor regressed"; ok=0; }
fi

# 6. auto-rollback on any post-apply failure
'''

SAFE_APPLY_NEW = f'''if [[ -x scripts/floor_check.sh ]]; then
  scripts/floor_check.sh --quiet >/dev/null 2>&1 && echo "  ✓ floor still MET" || {{ echo "  ✗ floor regressed"; ok=0; }}
fi

# {MARK} — quality gate: the .py files THIS apply actually touched (via
# the snapshot commit already written in step 2), scored for real. Rides
# the SAME rollback path as every other post-apply check — no new
# machinery, just a new signal feeding the existing `ok` variable.
if [[ -f "$SNAP/snapshot_commit.txt" && -f "$REPO_ROOT/scripts/lib/quality_gate.py" ]]; then
  changed_py=$(git diff --name-only "$(cat "$SNAP/snapshot_commit.txt")" -- '*.py' 2>/dev/null || true)
  if [[ -n "$changed_py" ]]; then
    if "$VENV_PY" "$REPO_ROOT/scripts/lib/quality_gate.py" --paths $changed_py; then
      echo "  ✓ quality gate PASS/WARN"
    else
      echo "  ✗ quality gate BLOCK"; ok=0
    fi
  fi
fi

# 6. auto-rollback on any post-apply failure
'''


def patch_safe_apply(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    return _replace_once(text, SAFE_APPLY_ANCHOR, SAFE_APPLY_NEW,
                         label="safe_apply.sh"), True


ALL_PATCHES = {
    "quality/__init__.py": patch_quality_init,
}

SCRIPT_PATCHES = {
    "pre_apply_gate.sh": patch_pre_apply_gate,
    "safe_apply.sh": patch_safe_apply,
}
