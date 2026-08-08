#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
#  apply_workflow_wire.sh — The architectural crown: wire workflows to the agent
#
#  The workflow/agentic_loop.py skeleton (v0.2.37) has the full plan→act→check
#  loop with pluggable handlers — and the handlers (shell, file_write,
#  file_read) are already implemented in workflow/handlers/. What was missing:
#  agent tools to CREATE and DRIVE those workflows from inside a chat session.
#
#  This module adds three tools:
#    workflow_create  (T1) — build a workflow with plan steps; returns workflow_id
#    workflow_step    (T1) — execute the next pending step; returns outcome
#    workflow_status  (T0) — query progress without executing
#
#  Changes:
#    1. Install tools/workflow_tools.py
#    2. Patch tools/__init__.py — import + __all__ (markers: workflow-wire-*)
#    3. Patch loop.py — add WORKFLOW section before ═══ COMPLETION ═══
#       (marker: # workflow-wire-d)
#
#  Idempotent. Backs up patched files.
# ═══════════════════════════════════════════════════════════════════════════
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${1:-$PWD}"

if [[ ! -f "$ROOT/src/sovereign_agent/cli.py" ]]; then
  d="$PWD"
  while [[ "$d" != "/" ]]; do
    [[ -f "$d/src/sovereign_agent/cli.py" ]] && { ROOT="$d"; break; }
    d="$(dirname "$d")"
  done
fi
[[ -f "$ROOT/src/sovereign_agent/cli.py" ]] || { echo "✗ run from repo root"; exit 1; }
echo "◊ repo root: $ROOT"

PKG="$ROOT/src/sovereign_agent"
TOOLS="$PKG/tools"
LOOP="$PKG/loop.py"
INIT="$TOOLS/__init__.py"
ts(){ date +%Y%m%d%H%M%S; }

# ── 1. Install workflow_tools.py ──────────────────────────────────────────
echo "→ installing tools/workflow_tools.py"
cp "$HERE/payload/src/sovereign_agent/tools/workflow_tools.py" \
   "$TOOLS/workflow_tools.py"
echo "  ✓ workflow_tools.py"

# ── 2. Patch tools/__init__.py ────────────────────────────────────────────
echo "→ patching tools/__init__.py"
cp "$INIT" "$INIT.bak.$(ts)"

python3 - "$INIT" <<'PYEOF'
import sys, pathlib
init = pathlib.Path(sys.argv[1])
src = init.read_text(encoding="utf-8")

IMPORT_MARKER = "# workflow-wire-import-d"
ALL_MARKER    = "# workflow-wire-all-d"

if IMPORT_MARKER not in src:
    # Add import after the last existing tool import
    anchor = "from .write_file import WriteFileTool\n"
    if anchor in src:
        inject = (
            "from .workflow_tools import (  " + IMPORT_MARKER + "\n"
            "    WorkflowCreateTool, WorkflowStepTool, WorkflowStatusTool,\n"
            ")\n"
        )
        src = src.replace(anchor, anchor + inject, 1)
        print("  ✓ workflow_tools import added")
    else:
        # Fallback: append before __all__
        idx = src.find("__all__ = [")
        if idx >= 0:
            inject = (
                "from .workflow_tools import (  " + IMPORT_MARKER + "\n"
                "    WorkflowCreateTool, WorkflowStepTool, WorkflowStatusTool,\n"
                ")\n"
            )
            src = src[:idx] + inject + src[idx:]
            print("  ✓ workflow_tools import added (fallback)")
        else:
            print("  ⚠ no anchor for import — manual edit required")
else:
    print("  ↷ workflow_tools import already present")

if ALL_MARKER not in src:
    # Add names to __all__
    anchor = '"WriteFileTool",'
    if anchor in src:
        inject = (
            '"WriteFileTool",\n'
            '    "WorkflowCreateTool",  ' + ALL_MARKER + '\n'
            '    "WorkflowStepTool",\n'
            '    "WorkflowStatusTool",'
        )
        src = src.replace(anchor, inject, 1)
        print("  ✓ workflow tools added to __all__")
    else:
        print("  ⚠ WriteFileTool anchor not found in __all__ — skipping __all__ patch")
else:
    print("  ↷ workflow tools already in __all__")

init.write_text(src, encoding="utf-8")
print("  ✓ tools/__init__.py written")
PYEOF

# ── 3. Patch loop.py — add WORKFLOW section ───────────────────────────────
echo "→ patching loop.py"
cp "$LOOP" "$LOOP.bak.$(ts)"

python3 - "$LOOP" <<'PYEOF'
import sys, pathlib
loop = pathlib.Path(sys.argv[1])
src = loop.read_text(encoding="utf-8")

MARKER = "# workflow-wire-d"
if MARKER in src:
    print("  ↷ WORKFLOW section already present — skipping")
else:
    section = '''
═══ WORKFLOW ═══  # workflow-wire-d
For multi-step work that must survive restarts, use the workflow system.

  workflow_create(goal, steps=[...])
    Build a persistent workflow. steps: [{title, action_kind, action_input}]
    action_kinds: note · shell · file_write · file_read
    Returns workflow_id — store it; it is durable across restarts.

  workflow_step(workflow_id)
    Execute the next planned step. Returns succeeded, summary, artifacts.
    A blocked step (succeeded=False) waits for operator review.
    Call workflow_status to see what blocked before continuing.

  workflow_status(workflow_id)
    Query step counts and next_step_title without executing.
    On restart: call this first to find where the workflow left off.

When a goal has ordered, distinct steps — create a workflow.
When a session goal has side effects that should outlive the session —
create a workflow. When it is short and atomic — do it directly.

'''
    anchor = "═══ UNTRUSTED INPUT DOCTRINE ═══"
    if anchor in src:
        src = src.replace(anchor, section + anchor, 1)
        print("  ✓ WORKFLOW section inserted before UNTRUSTED INPUT DOCTRINE")
    else:
        # Fallback: before COMPLETION
        anchor2 = "═══ COMPLETION ═══"
        if anchor2 in src:
            src = src.replace(anchor2, section + anchor2, 1)
            print("  ✓ WORKFLOW section inserted before COMPLETION (fallback)")
        else:
            print("  ⚠ no anchor found in loop.py — manual edit required")

loop.write_text(src, encoding="utf-8")
print("  ✓ loop.py written")
PYEOF

# ── 4. Compile checks ─────────────────────────────────────────────────────
echo "→ compile checks"
python3 -m py_compile "$TOOLS/workflow_tools.py" "$INIT" "$LOOP"
echo "  ✓ all files compile"

cp "$HERE/tests/test_workflow_wire.py" "$ROOT/tests/test_workflow_wire.py"
python3 -m py_compile "$ROOT/tests/test_workflow_wire.py"
echo "  ✓ tests installed + compile"

echo
echo "✓ done. Workflow tools are wired."
echo
echo "  workflow_create  (T1) — create a workflow with steps; returns workflow_id"
echo "  workflow_step    (T1) — execute the next pending step"
echo "  workflow_status  (T0) — query progress without executing"
echo
echo "  Handlers available inside workflows:"
echo "    note       — no side effect"
echo "    shell      — runs allowlisted commands (uv, python, pytest, ls, grep, ...)"
echo "    file_write — writes inside SETTINGS.paths.sandbox_dir"
echo "    file_read  — reads inside SETTINGS.paths.sandbox_dir"
echo
echo "  run: pytest tests/test_workflow_wire.py -v"
