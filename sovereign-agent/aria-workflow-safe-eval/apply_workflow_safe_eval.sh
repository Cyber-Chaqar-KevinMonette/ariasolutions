#!/usr/bin/env bash
# apply_workflow_safe_eval.sh — close the eval() sandbox-escape hole in workflow/god_engine.py.
#
# THE BUG (found during a full-system security scan, 2026-07-02): `verify_step()` evaluated
# operator/model-supplied `criteria` strings with `eval(criteria, {"__builtins__": {}}, ns)`.
# Emptying `__builtins__` is a well-known INCOMPLETE sandbox — attribute-traversal gadget chains
# (e.g. `().__class__.__bases__[0].__subclasses__()`) reach arbitrary classes without ever
# touching a builtin name. Reachable via `WorkflowCheckpointTool` (tools/god_workflow_tools.py),
# a Tier-0 tool whose docstring claims "zero side effects" and whose `failure_modes` never
# mention code-execution risk.
#
# THE FIX: workflow/safe_eval.py — a restricted AST-walking evaluator. Only boolean ops,
# comparisons, name lookups (restricted to the fixed verify_step namespace), literals, lists, and
# tuples are permitted; Call/Attribute/Subscript/Lambda/comprehension nodes are rejected outright,
# so there is no way to reach a __subclasses__-style gadget — not hidden, actually absent.
# Verified: 16/16 tests pass, including the exact gadget-chain string plus 6 other escape vectors,
# while normal verify_step criteria ("succeeded", "exit_code == 0", "'x' in artifacts") still work.
#
# Anatomy: guard (cockpit stopped + venv) → backup touched files → copy payload → patch
# god_engine.py's eval() call site (anchored, idempotent) → py_compile → copy + run tests.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-workflow-safe-eval"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
ENGINE="$REPO_ROOT/src/sovereign_agent/workflow/god_engine.py"

echo "=== aria-workflow-safe-eval apply ==="
if pgrep -f "sovereign cockpit" >/dev/null 2>&1; then echo "ERROR: cockpit running. Stop it first."; exit 1; fi
[[ -x "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
[[ -f "$ENGINE" ]] || { echo "ERROR: $ENGINE not found."; exit 1; }
mkdir -p "$BACKUP_DIR"
cp "$ENGINE" "$BACKUP_DIR/god_engine.py.bak"

# 1. copy the new safe_eval.py into the live workflow/ package
cp "$STAGING/payload/src/sovereign_agent/workflow/safe_eval.py" \
   "$REPO_ROOT/src/sovereign_agent/workflow/safe_eval.py"

# 2. patch god_engine.py: import safe_eval, replace the raw eval() call (anchored + idempotent)
"$VENV_PY" - "$ENGINE" <<'PYEOF'
import sys
from pathlib import Path
p = Path(sys.argv[1]); t = p.read_text(encoding="utf-8")

MARK = "workflow-safe-eval-import-d"
if MARK in t:
    print("SKIP: already patched")
else:
    anchor = "from typing import Any"
    if anchor not in t:
        print(f"ERROR: import anchor not found: {anchor!r}", file=sys.stderr); sys.exit(1)
    t = t.replace(
        anchor,
        anchor + f"\n\nfrom .safe_eval import safe_eval  # {MARK}",
        1,
    )
    old_call = 'result = eval(criteria, {"__builtins__": {}}, ns)  # noqa: S307'
    if old_call not in t:
        print(f"ERROR: eval() call site not found: {old_call!r}", file=sys.stderr); sys.exit(1)
    t = t.replace(old_call, "result = safe_eval(criteria, ns)", 1)
    p.write_text(t, encoding="utf-8")
    print("Patched god_engine.py: import + eval() call site")
PYEOF

echo "→ Compile check..."
"$VENV_PY" -m py_compile "$REPO_ROOT/src/sovereign_agent/workflow/safe_eval.py" "$ENGINE"
echo "  ✓ py_compile clean"

echo "→ Import + smoke check..."
"$VENV_PY" -c "
from sovereign_agent.workflow.god_engine import GodTierEngine
from sovereign_agent.workflow.safe_eval import safe_eval, UnsafeCriteriaError
try:
    safe_eval('().__class__.__bases__[0].__subclasses__()', {})
    print('  ✗ GADGET CHAIN NOT BLOCKED — DO NOT SHIP')
    raise SystemExit(1)
except UnsafeCriteriaError:
    print('  ✓ gadget chain rejected, GodTierEngine imports cleanly')
"

# 3. copy + run tests
cp "$STAGING/tests/test_workflow_safe_eval.py" "$REPO_ROOT/tests/"
echo "Running tests..."
"$VENV_PY" -m pytest "$REPO_ROOT/tests/test_workflow_safe_eval.py" -q

echo "=== aria-workflow-safe-eval applied. Reversible: backup at $BACKUP_DIR/god_engine.py.bak 💛 ==="
