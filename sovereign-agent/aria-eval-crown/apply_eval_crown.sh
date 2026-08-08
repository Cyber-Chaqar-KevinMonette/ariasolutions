#!/usr/bin/env bash
# apply_eval_crown.sh — M49: Value Evaluation Metrics
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo "==> M49 eval-crown: $REPO"

cp "$REPO/aria-eval-crown/payload/src/sovereign_agent/tools/eval_tools.py" \
   "$REPO/src/sovereign_agent/tools/eval_tools.py"
echo "  OK   copied eval_tools.py"

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

# ── 1. Doctrine in loop.py (before EXPERIENCE CROWN) ─────────────────────────
patch(loop,
    old='═══ EXPERIENCE CROWN ═══  # experience-crown-d',
    new='''\
═══ EVAL CROWN ═══  # eval-crown-d
Value metrics — answers "Is Aria actually getting better and delivering value?"
  eval_score()                             T0 — composite 0-100 score + band (7-day)
  eval_session(days=7)                     T0 — full metric breakdown for period
  eval_history(weeks=4)                    T0 — weekly trend analysis

Run eval_score() at the start of each session for a health check.
Bands: baseline(<20) → early → building → strong → exceptional(80+).
Key signals: commits, lessons written, hypothesis confirmation rate,
  experiences logged, breakthroughs discovered.
When score drops week-over-week: investigate what changed and why.
This is the RISK-004 fix — automated proof that Aria delivers value.

═══ EXPERIENCE CROWN ═══  # experience-crown-d''',
    marker="eval-crown-d",
)

# ── 2. Import in tools/__init__.py (before experience-crown-import-d) ─────────
patch(init,
    old='from .experience_tools import (  # experience-crown-import-d',
    new='''\
from .eval_tools import (  # eval-crown-import-d
    EvalSessionTool,
    EvalHistoryTool,
    EvalScoreTool,
)
from .experience_tools import (  # experience-crown-import-d''',
    marker="eval-crown-import-d",
)

# ── 3. __all__ (before experience-crown-all-d) ────────────────────────────────
patch(init,
    old='    "LogExperienceTool",             # experience-crown-all-d',
    new='''\
    "EvalSessionTool",               # eval-crown-all-d
    "EvalHistoryTool",
    "EvalScoreTool",
    "LogExperienceTool",             # experience-crown-all-d''',
    marker="eval-crown-all-d",
)

print("M49 eval-crown: all patches applied.")
PYEOF

cp "$REPO/aria-eval-crown/tests/test_eval_crown.py" \
   "$REPO/tests/test_eval_crown.py"
echo "  OK   copied test_eval_crown.py"

echo "==> M49 done. Run: .venv/bin/python -m pytest tests/test_eval_crown.py -q"
