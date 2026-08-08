#!/usr/bin/env bash
# apply_researcher.sh — M39: Theoretical Researcher + Experimentalist
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo "==> M39 researcher: $REPO"

cp "$REPO/aria-researcher/payload/src/sovereign_agent/tools/researcher_tools.py" \
   "$REPO/src/sovereign_agent/tools/researcher_tools.py"
echo "  OK   copied researcher_tools.py"

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
        print(f"  Searched for: {old[:80]!r}", file=sys.stderr)
        sys.exit(1)
    path.write_text(src.replace(old, new, 1))
    print(f"  OK   {path.name} ({marker})")
    return True

loop = repo / "src/sovereign_agent/loop.py"
init = repo / "src/sovereign_agent/tools/__init__.py"

# ── loop.py: THEORETICAL RESEARCHER doctrine ──────────────────────────────────
patch(loop,
    old='═══ VESSEL COMFORT ═══  # vessel-comfort-d',
    new='''\
═══ THEORETICAL RESEARCHER ═══  # theoretical-researcher-d
When you encounter uncertainty worth testing: form_hypothesis() first.
  form_hypothesis(question, context, estimated_value, estimated_cost)  T0
    → Returns structured hypothesis + go_nogo signal
  design_experiment(hypothesis_id)  T0
    → Returns test plan with steps, success/failure criteria
  evaluate_result(hypothesis_id, observation, verdict)  T0
    → Updates hypothesis atom; generates lesson material
  research_queue(min_value, max_cost)  T0
    → Shows pending hypotheses sorted by value/cost

Rules:
  Only run an experiment when go_nogo=True (value × probability > cost).
  Low-value hunches stay as atoms — don't test them, just record them.
  After observing results: evaluate_result() — update beliefs, write lessons.
  Research is love: invest effort where it actually matters.

═══ VESSEL COMFORT ═══  # vessel-comfort-d''',
    marker="theoretical-researcher-d",
)

# ── tools/__init__.py: import researcher_tools ────────────────────────────────
patch(init,
    old='from .confidence_crown import (  # confidence-crown-import-d',
    new='''\
from .researcher_tools import (  # researcher-import-d
    FormHypothesisTool,
    DesignExperimentTool,
    EvaluateResultTool,
    ResearchQueueTool,
)
from .confidence_crown import (  # confidence-crown-import-d''',
    marker="researcher-import-d",
)

# ── tools/__init__.py: add to __all__ ────────────────────────────────────────
patch(init,
    old='    "VesselComfortTool",           # confidence-crown-all-d',
    new='''\
    "FormHypothesisTool",          # researcher-all-d
    "DesignExperimentTool",
    "EvaluateResultTool",
    "ResearchQueueTool",
    "VesselComfortTool",           # confidence-crown-all-d''',
    marker="researcher-all-d",
)

print("M39 researcher: all patches applied.")
PYEOF

cp "$REPO/aria-researcher/tests/test_researcher.py" "$REPO/tests/test_researcher.py"
echo "==> M39 done. Run: .venv/bin/python -m pytest tests/test_researcher.py -q"
