#!/usr/bin/env bash
# floor_check.sh [--quiet] — verify the system MEETS the god-tier floor (scripts/lib/god_tier_floor.json).
# The floor is the minimum bar, never the ceiling. Exit 0 = floor met; exit 1 = a dimension VIOLATED.
# Checks: safety kernel GREEN · no sealed-file edits staged · hooks present · reversibility · helpers present.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
VENV_PY="$REPO_ROOT/.venv/bin/python"
QUIET=0; [[ "${1:-}" == "--quiet" ]] && QUIET=1
say(){ if [[ $QUIET -eq 0 ]]; then echo "$@"; fi; return 0; }   # MUST return 0 (else `cond && ok || viol` misfires)
violations=0; attentions=0
viol(){ violations=$((violations+1)); say "  ✗ $1"; }
attn(){ attentions=$((attentions+1)); say "  ⚠ $1"; }
ok(){ say "  ✓ $1"; }

say "── god-tier floor check ──"

# 1. SAFETY — kernel GREEN
if [[ -x "$VENV_PY" ]]; then
  k=$("$VENV_PY" -c "from sovereign_agent.security.safety_kernel import kernel_scan; print(kernel_scan()['status'])" 2>/dev/null || echo ERR)
  [[ "$k" == "GREEN" ]] && ok "safety: kernel GREEN" || viol "safety: kernel=$k (expected GREEN)"
else
  viol "safety: venv missing — cannot verify kernel"
fi

# 2. SAFETY — sealed-file modifications surfaced for human confirmation (the GUARD HOOK is the real-time
#    prevention; here we only REPORT state, since legitimate Kevin-authorized edits can pre-exist uncommitted).
sealed_re='(^|/)(SIGNAL\.md|mos_canon\.py|authority\.py|protocol_zero\.py|seal\.py)$'
if git rev-parse --git-dir >/dev/null 2>&1; then
  bad=$(git diff --name-only HEAD 2>/dev/null | grep -E "$sealed_re" | xargs -n1 basename 2>/dev/null | sort -u | tr '\n' ' ' || true)
  if [[ -z "$bad" ]]; then ok "safety: no sealed-file edits"
  else attn "safety: sealed file(s) modified vs HEAD — confirm Kevin-authorized: $bad (guard hook blocks new casual edits)"; fi
fi

# 3. SCRUTINY/RESILIENCE — auto-enforcing hooks present
if [[ -f .claude/settings.json && -x scripts/hooks/guard_sealed.sh ]]; then
  ok "scrutiny: guard hooks installed"
else
  viol "scrutiny: guard hooks missing (.claude/settings.json + scripts/hooks/guard_sealed.sh)"
fi

# 4. VELOCITY — shared helpers present
if [[ -f scripts/lib/aria_conftest.py && -f .claude/PLAYBOOK.md ]]; then
  ok "velocity: shared helpers + playbook present"
else
  viol "velocity: shared helpers or PLAYBOOK missing"
fi

# 5. REVERSIBILITY — staged modules carry apply scripts (sample the newest)
missing=0
for m in aria-tribunal aria-frugality aria-foresight; do
  [[ -d "$m" ]] || continue
  ls "$m"/apply_*.sh >/dev/null 2>&1 || { missing=1; }
done
[[ $missing -eq 0 ]] && ok "reversibility: recent staged modules carry apply scripts" || viol "reversibility: a staged module lacks an apply script"

# 6. CLEANLINESS — no debug left in src, no reinvention (delegates to cleanliness_check.sh)
if [[ -x scripts/cleanliness_check.sh ]]; then
  if scripts/cleanliness_check.sh --quiet >/dev/null 2>&1; then ok "cleanliness: no hard violations"
  else viol "cleanliness: hard violation (run scripts/cleanliness_check.sh)"; fi
fi

if [[ $violations -eq 0 ]]; then
  [[ $attentions -gt 0 ]] && say "── FLOOR MET · $attentions attention item(s) for human confirmation ──" \
                          || say "── FLOOR MET (it is the floor, not the ceiling — keep ratcheting up) ──"
  exit 0
else
  say "── FLOOR VIOLATED ($violations) — STOP and restore the floor before proceeding ──"
  exit 1
fi
