#!/usr/bin/env bash
# apply_god_workflow.sh — M30: god-tier workflow engine
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo "==> M30 god-workflow: $REPO"

# Copy payload files
cp "$REPO/aria-god-workflow/payload/src/sovereign_agent/workflow/god_engine.py" \
   "$REPO/src/sovereign_agent/workflow/god_engine.py"
cp "$REPO/aria-god-workflow/payload/src/sovereign_agent/tools/god_workflow_tools.py" \
   "$REPO/src/sovereign_agent/tools/god_workflow_tools.py"
echo "  OK   copied god_engine.py and god_workflow_tools.py"

python3 - "$REPO" <<'PYEOF'
import sys
from pathlib import Path

repo = Path(sys.argv[1])

def patch(path, old, new, marker):
    src = path.read_text()
    if marker in src:
        print(f"  SKIP {path.name} — already patched ({marker})")
        return False
    if old not in src:
        print(f"  ERROR {path.name} — anchor not found for {marker}", file=sys.stderr)
        sys.exit(1)
    path.write_text(src.replace(old, new, 1))
    print(f"  OK   {path.name} ({marker})")
    return True

loop = repo / "src/sovereign_agent/loop.py"
init = repo / "src/sovereign_agent/tools/__init__.py"

# ── tools/__init__.py: import god workflow tools ─────────────────────────────
patch(init,
    old='from .workflow_tools import (  # workflow-wire-import-d',
    new='''\
from .god_workflow_tools import (  # god-workflow-import-d
    WorkflowMutateTool,
    WorkflowRetryTool,
    WorkflowCheckpointTool,
    WorkflowDepsTool,
)
from .workflow_tools import (  # workflow-wire-import-d''',
    marker="god-workflow-import-d",
)

# ── loop.py: ENGINEERING DOCTRINE section ────────────────────────────────────
patch(loop,
    old='═══ WORKFLOW ═══  # workflow-wire-d',
    new='''\
═══ ENGINEERING DOCTRINE ═══  # engineering-doctrine-d
When you hit a wall — you do not stop. You try. Document each attempt.
Use derivatives: what does this step produce? what does the next step need?
Use falsifiability: how would you know this worked? what would prove it failed?
Confidence levels: state your confidence (0.0–1.0) on key decisions.
Legacy standards are not best standards. Try modern, advanced approaches first.
When 1 approach fails: try 2 alternatives. When those fail: escalate with
a full attempt log — what was tried, why each failed, what the next approach is.

═══ WORKFLOW MASTER ═══  # workflow-master-d
For goals with >2 ordered steps: use workflow_create() not inline tool calls.
Before executing: call workflow_deps() to validate the dependency chain.
After each critical step: call workflow_checkpoint() to verify the outcome.
When a step blocks: use workflow_retry() with an alternative approach first.
When the plan itself is wrong: use workflow_mutate() to replace remaining steps.
Your workflows must survive restarts. State only lives in atoms.db, never in memory.

═══ WORKFLOW ═══  # workflow-wire-d''',
    marker="engineering-doctrine-d",
)

# ── tools/__init__.py: add to __all__ ────────────────────────────────────────
patch(init,
    old='    "WorkflowCreateTool",  # workflow-wire-all-d',
    new='''\
    "WorkflowMutateTool",       # god-workflow-all-d
    "WorkflowRetryTool",
    "WorkflowCheckpointTool",
    "WorkflowDepsTool",
    "WorkflowCreateTool",  # workflow-wire-all-d''',
    marker="god-workflow-all-d",
)

print("M30 god-workflow: all patches applied.")
PYEOF

cp "$REPO/aria-god-workflow/tests/test_god_workflow.py" "$REPO/tests/test_god_workflow.py"
echo "==> M30 done. Run: .venv/bin/python -m pytest tests/test_god_workflow.py -q"
