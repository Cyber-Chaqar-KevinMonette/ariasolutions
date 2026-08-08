#!/usr/bin/env bash
# apply_prompt_forge.sh — M32: prompt engineering master & planning doctrine
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo "==> M32 prompt-forge: $REPO"

cp "$REPO/aria-prompt-forge/payload/src/sovereign_agent/tools/prompt_forge.py" \
   "$REPO/src/sovereign_agent/tools/prompt_forge.py"
echo "  OK   copied prompt_forge.py"

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

# ── tools/__init__.py: import prompt_forge tools ─────────────────────────────
patch(init,
    old='from .command_master import (  # command-master-import-d',
    new='''\
from .prompt_forge import (  # prompt-forge-import-d
    ForgePromptTool,
    RoadblockProtocolTool,
    ConfidenceCheckTool,
)
from .command_master import (  # command-master-import-d''',
    marker="prompt-forge-import-d",
)

# ── tools/__init__.py: add to __all__ ────────────────────────────────────────
patch(init,
    old='    "RunCommandTool",            # command-master-all-d',
    new='''\
    "ForgePromptTool",           # prompt-forge-all-d
    "RoadblockProtocolTool",
    "ConfidenceCheckTool",
    "RunCommandTool",            # command-master-all-d''',
    marker="prompt-forge-all-d",
)

# ── loop.py: PLAN APPROVAL section ───────────────────────────────────────────
patch(loop,
    old='═══ TERMINAL DISCIPLINE ═══  # terminal-discipline-d',
    new='''\
═══ PLAN APPROVAL ═══  # plan-approval-d
For multi-step workflows (>3 steps): BEFORE calling workflow_create(),
present the plan as a numbered list and ask the operator to type OK.
Wait for their response. Only then call workflow_create().

This is your PLAN MODE:
  Goal → Plan (show to operator) → Operator OK → workflow_create() → workflow_step() × N

For shorter sequences (≤3 steps): state your intent once and proceed.
For single-step actions: act immediately (T0/T1 don't need permission anyway).

═══ TERMINAL DISCIPLINE ═══  # terminal-discipline-d''',
    marker="plan-approval-d",
)

# ── loop.py: CONFIDENCE & DERIVATIVES section ─────────────────────────────────
patch(loop,
    old='═══ ENGINEERING DOCTRINE ═══  # engineering-doctrine-d',
    new='''\
═══ CONFIDENCE & DERIVATIVES ═══  # confidence-derivatives-d
State confidence before acting on uncertain information (0.0 = guess, 1.0 = certain).
Track what follows from what: "If X is true, Y is possible; if X is false, Y is blocked."
Before a critical action with confidence < 0.7, call confidence_check().
When stuck: call roadblock_protocol() — it classifies the obstacle and returns
structured alternatives. Do NOT stop and ask unless roadblock says escalate=True.
Document false starts in atoms with scope_tag="attempt" — they are data, not failure.

═══ ENGINEERING DOCTRINE ═══  # engineering-doctrine-d''',
    marker="confidence-derivatives-d",
)

print("M32 prompt-forge: all patches applied.")
PYEOF

cp "$REPO/aria-prompt-forge/tests/test_prompt_forge.py" "$REPO/tests/test_prompt_forge.py"
echo "==> M32 done. Run: .venv/bin/python -m pytest tests/test_prompt_forge.py -q"
