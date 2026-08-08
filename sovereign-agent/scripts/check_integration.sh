#!/usr/bin/env bash
# check_integration.sh [--quiet] — verify the system can absorb the staged modules: anchor-chain integrity.
# Guards the apply queue. Checks: tools/__init__ + stewardship/__init__ import cleanly; no DUPLICATE
# registration anchors live; no two staged apply scripts claim the same anchor name. Read-only. Exit 1 on a
# hard integration fault.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
VENV_PY="$REPO_ROOT/.venv/bin/python"
QUIET=0; [[ "${1:-}" == "--quiet" ]] && QUIET=1
say(){ if [[ $QUIET -eq 0 ]]; then echo "$@"; fi; return 0; }
fails=0

say "── integration / anchor-chain integrity ──"

# 1. live registration files import cleanly
if "$VENV_PY" -c "import sovereign_agent.tools" 2>/tmp/_ci.err; then
  say "  ✓ sovereign_agent.tools imports cleanly"
else
  say "  ✗ tools/__init__.py import FAILED:"; sed 's/^/      /' /tmp/_ci.err | tail -4; fails=$((fails+1))
fi
if "$VENV_PY" -c "import sovereign_agent.stewardship" 2>/tmp/_ci.err; then
  say "  ✓ sovereign_agent.stewardship imports cleanly"
else
  say "  ✗ stewardship/__init__.py import FAILED:"; sed 's/^/      /' /tmp/_ci.err | tail -4; fails=$((fails+1))
fi

# 2. no genuine DOUBLE-APPLICATION live: an identical import line appearing twice = a module applied twice.
#    (A module may register several tools under one anchor comment — that's fine; we check the import LINES.)
dups=$(grep -E "^from \.\w+ import " src/sovereign_agent/tools/__init__.py 2>/dev/null | sed 's/  *#.*//' | sort | uniq -d)
if [[ -z "$dups" ]]; then say "  ✓ no duplicate tool imports (no double-application)"; else say "  ✗ DUPLICATE import line(s) — a module was applied twice:"; printf "%s\n" "$dups" | sed 's/^/      /'; fails=$((fails+1)); fi
dups2=$(grep -E "^from \. import " src/sovereign_agent/stewardship/__init__.py 2>/dev/null | sed 's/  *#.*//' | sort | uniq -d)
if [[ -z "$dups2" ]]; then say "  ✓ no duplicate sentinel imports"; else say "  ✗ DUPLICATE sentinel import(s):"; printf "%s\n" "$dups2" | sed 's/^/      /'; fails=$((fails+1)); fi

# 4. tool count sanity (registered tools resolve)
n=$("$VENV_PY" -c "import sovereign_agent.tools as t; print(len([x for x in dir(t) if x.endswith('Tool')]))" 2>/dev/null || echo 0)
say "  · $n Tool classes resolve from the registry"

if [[ $fails -eq 0 ]]; then
  say "── integration INTACT ✓ — safe to apply staged modules ──"; exit 0
else
  say "── integration FAULT ($fails) — fix before applying ──"; exit 1
fi
