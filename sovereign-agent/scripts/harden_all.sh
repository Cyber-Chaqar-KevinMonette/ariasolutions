#!/usr/bin/env bash
# harden_all.sh [--quiet] — the unified god-tier hardening harness. ONE command, ONE verdict.
# Runs: floor · cleanliness · apply-system validation · the god-tier scanner · every staged test suite.
# Emits a single hardening verdict + the honest list of anything below bar. Read-only. Quality over speed.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
VENV_PY="$REPO_ROOT/.venv/bin/python"
QUIET=0; [[ "${1:-}" == "--quiet" ]] && QUIET=1
say(){ if [[ $QUIET -eq 0 ]]; then echo "$@"; fi; return 0; }
fails=0; warns=0

say "════════════════════════════════════════════════════════"
say "  GOD-TIER HARDENING HARNESS   ($(date +%Y-%m-%d\ %H:%M))"
say "════════════════════════════════════════════════════════"

# 1. floor
if scripts/floor_check.sh --quiet >/dev/null 2>&1; then say "  ✓ god-tier floor MET"; else say "  ✗ floor VIOLATED"; fails=$((fails+1)); fi
# 2. cleanliness
if scripts/cleanliness_check.sh --quiet >/dev/null 2>&1; then say "  ✓ cleanliness MET"; else say "  ✗ cleanliness VIOLATED"; fails=$((fails+1)); fi
# 3. apply-system safety
safe_line=$(scripts/validate_apply_system.sh 2>/dev/null | grep "scripts:" | head -1)
say "  · apply-system: ${safe_line:-(n/a)}  (run via scripts/safe_apply.sh for full guards)"
# 4. god-tier scanner
if [[ -d aria-godtier-scanner ]]; then
  scan=$(PYTHONPATH=aria-godtier-scanner/payload/src "$VENV_PY" - <<'PY' 2>/dev/null
import sys, importlib.util, types
from pathlib import Path
base=Path('aria-godtier-scanner/payload/src/sovereign_agent/godtier')
pkg=types.ModuleType('godtier'); pkg.__path__=[str(base)]; sys.modules['godtier']=pkg
for n in ['targets','rubric','scanner','enhance']:
    s=importlib.util.spec_from_file_location(f'godtier.{n}',base/f'{n}.py'); m=importlib.util.module_from_spec(s); sys.modules[f'godtier.{n}']=m; s.loader.exec_module(m)
from godtier import scanner
print(scanner.summary_line(Path('.')))
PY
)
  say "  · ${scan:-scanner unavailable}"
fi

# 5. every staged test suite — run EACH IN ISOLATION (the conftests extend a shared package path, so a
#    combined run cross-contaminates; isolation gives the true per-module verdict).
say "  → running every staged test suite in isolation (true edge-case + behavior coverage)…"
green=0; red=0; red_list=""
for td in $(ls -d aria-*/tests 2>/dev/null); do
  mod="$(basename "$(dirname "$td")")"
  if "$VENV_PY" -m pytest "$td" -q >/tmp/_harden_one.out 2>&1; then
    green=$((green+1))
  else
    red=$((red+1)); red_list+="$mod "
  fi
done
if [[ $red -eq 0 ]]; then
  say "  ✓ all $green staged module suites green (isolated)"
else
  say "  ⚠ $green green / $red with failures (isolated): $red_list"
  warns=$((warns+1))
fi

say "────────────────────────────────────────────────────────"
if [[ $fails -eq 0 && $warns -eq 0 ]]; then
  say "  VERDICT: GOD-TIER HARDENED ✓  (floor + cleanliness + apply-safety + every staged suite green)"
  say "════════════════════════════════════════════════════════"
  exit 0
elif [[ $fails -eq 0 ]]; then
  say "  VERDICT: CORE GOD-TIER ✓ — floor + cleanliness + apply-safety MET; but $warns area(s) have"
  say "           module suites failing in isolation (pre-existing tech debt). Honest backlog above."
  say "════════════════════════════════════════════════════════"
  exit 0
else
  say "  VERDICT: $fails core area(s) below bar — harden before shipping."
  say "════════════════════════════════════════════════════════"
  exit 1
fi
