#!/usr/bin/env bash
# cleanliness_check.sh [--quiet] — the god-tier cleanliness dimension, enforced.
# Neglect is never god-tier. Checks: no debug left in src · no orphan .bak · staged conftests use the
# shared helper (no reinvention) · TODO/FIXME awareness · docs present. Exit 1 on a HARD violation.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
QUIET=0; [[ "${1:-}" == "--quiet" ]] && QUIET=1
say(){ if [[ $QUIET -eq 0 ]]; then echo "$@"; fi; return 0; }   # MUST return 0 (else `cond && ok || hard` misfires)
viol=0; attn=0
hard(){ viol=$((viol+1)); say "  ✗ $1"; }
warn(){ attn=$((attn+1)); say "  ⚠ $1"; }
ok(){ say "  ✓ $1"; }

say "── god-tier cleanliness check ──"

# 1. HARD — no debugger left in shipped src. Match a debug STATEMENT (line-start), not a regex/string literal
#    (e.g. a scanner that defines r"...|import pdb\b" to detect debug elsewhere is not itself debug).
dbg=$(grep -rnE "^[[:space:]]*(breakpoint\(\)|pdb\.set_trace\(\)|import[[:space:]]+pdb([[:space:]]|$))" src/ 2>/dev/null | grep -v "\.pyc" | head -5 || true)
[[ -z "$dbg" ]] && ok "no debugger/breakpoint in src" || { hard "debugger left in src:"; say "$dbg" | sed 's/^/      /'; }

# 2. WARN — orphan .bak files in src (should be cleaned / live in module backups/)
baks=$(find src -name '*.bak*' 2>/dev/null | head -10 || true)
[[ -z "$baks" ]] && ok "no orphan .bak files in src" || { warn "orphan .bak files in src ($(echo "$baks" | wc -l | tr -d ' ')) — move to module backups/"; }

# 3. CLEANLINESS — staged conftests use the shared helper (no reinvention)
reinvented=0
for c in aria-*/tests/conftest.py; do
  [[ -f "$c" ]] || continue
  grep -q "aria_conftest" "$c" 2>/dev/null || { grep -q "extend_paths\|__path__" "$c" 2>/dev/null && reinvented=$((reinvented+1)); }
done
[[ $reinvented -eq 0 ]] && ok "staged conftests use the shared helper (no reinvention)" || warn "$reinvented conftest(s) reinvent the path-shim — use scripts/lib/aria_conftest"

# 4. AWARENESS — TODO/FIXME/HACK/XXX count in src (not a failure; transparency)
todos=$(grep -rn -- "TODO\|FIXME\|HACK\|XXX" src/ 2>/dev/null | grep -v "\.pyc" | wc -l | tr -d ' ')
say "  · $todos TODO/FIXME/HACK markers in src (awareness)"

# 5. DOCS — the load-bearing docs present
for d in CLAUDE.md .claude/PLAYBOOK.md GOD_TIER_STANDARD.md; do
  [[ -f "$d" ]] || warn "missing doc: $d"
done
[[ -f CLAUDE.md && -f .claude/PLAYBOOK.md ]] && ok "load-bearing docs present"

if [[ $viol -eq 0 ]]; then
  [[ $attn -gt 0 ]] && say "── CLEANLINESS MET · $attn attention item(s) ──" || say "── CLEANLINESS MET ──"
  exit 0
else
  say "── CLEANLINESS VIOLATED ($viol) ──"; exit 1
fi
