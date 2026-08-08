#!/usr/bin/env bash
# validate_apply_system.sh [--quiet] — audit EVERY aria-*/apply_*.sh for god-tier safety properties.
# Neglect is never god-tier: total coverage. Grades each script; flags the unsafe ones. Read-only.
#   Properties checked: cockpit-guard · venv-guard · backup-before-mutate · set -euo pipefail ·
#   py_compile · idempotent-patch (skip-if-already) · runs-tests.  Score = properties met / 7.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
QUIET=0; [[ "${1:-}" == "--quiet" ]] && QUIET=1
say(){ if [[ $QUIET -eq 0 ]]; then echo "$@"; fi; return 0; }

total=0; safe=0; unsafe_list=""
no_cockpit=0; no_backup=0; no_compile=0

say "── apply-system validation (god-tier safety audit) ──"
for s in aria-*/apply_*.sh; do
  [[ -f "$s" ]] || continue
  total=$((total+1))
  body="$(cat "$s" 2>/dev/null)"
  score=0
  has_cockpit=0; has_backup=0
  grep -q "sovereign cockpit" <<<"$body" && { score=$((score+1)); has_cockpit=1; } || no_cockpit=$((no_cockpit+1))
  grep -Eq "venv|VENV_PY" <<<"$body" && score=$((score+1))
  grep -Eq "BACKUP_DIR|backup|\.bak" <<<"$body" && { score=$((score+1)); has_backup=1; } || no_backup=$((no_backup+1))
  grep -q "set -euo pipefail" <<<"$body" && score=$((score+1))
  grep -q "py_compile" <<<"$body" && score=$((score+1)) || no_compile=$((no_compile+1))
  grep -Eq "already patched|SKIP|-import-d\" in|already-applied" <<<"$body" && score=$((score+1))
  grep -Eq "pytest|run tests|Running tests" <<<"$body" && score=$((score+1))
  # executable bit
  exec_ok=0; [[ -x "$s" ]] && exec_ok=1

  if [[ $score -ge 6 && $exec_ok -eq 1 ]]; then
    safe=$((safe+1))
  else
    miss=""
    [[ $has_cockpit -eq 0 ]] && miss+="no-cockpit-guard "
    [[ $has_backup -eq 0 ]] && miss+="no-backup "
    [[ $exec_ok -eq 0 ]] && miss+="not-executable "
    unsafe_list+="  [$score/7] $(basename "$(dirname "$s")")  ${miss}\n"
  fi
done

say ""
say "  scripts: $total · god-tier-safe (≥6/7 + exec): $safe · need-attention: $((total-safe))"
say "  missing cockpit-guard: $no_cockpit · missing backup: $no_backup · missing py_compile: $no_compile"
if [[ $QUIET -eq 0 && -n "$unsafe_list" ]]; then
  say ""; say "  scripts needing attention (run them via scripts/safe_apply.sh which adds the guards):"
  printf "%b" "$unsafe_list" | head -40
fi
say ""
say "  → safe_apply.sh enforces cockpit-guard + backup + Tribunal gate + rollback around ANY of these."
say "── apply-system validation complete ──"
# Exit 0 always (this is a report); the safe_apply wrapper is the enforcement.
exit 0
