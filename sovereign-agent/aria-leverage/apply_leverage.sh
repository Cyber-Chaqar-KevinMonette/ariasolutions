#!/usr/bin/env bash
# apply_leverage.sh — M41: God Tier Leverage Oracle
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo "==> M41 leverage: $REPO"

cp "$REPO/aria-leverage/payload/src/sovereign_agent/tools/leverage_tools.py" \
   "$REPO/src/sovereign_agent/tools/leverage_tools.py"
echo "  OK   copied leverage_tools.py"

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

# ── loop.py: LEVERAGE ORACLE doctrine ────────────────────────────────────────
patch(loop,
    old='═══ COMPANION DOCTRINE ═══  # companion-doctrine-d',
    new='''\
═══ LEVERAGE ORACLE ═══  # leverage-oracle-d
Before starting a task queue: call prioritize_objectives() — work in leverage order.
  score_leverage(action, context, alternatives)  T0 → 0-1 score + recommendation
  leverage_audit(limit)                          T0 → retrospective session audit
  prioritize_objectives(scope)                   T0 → ObjectiveMap sorted by leverage

High-leverage first: blockers, uniquely-yours tasks, high-downstream-impact work.
Low-leverage last: polish, nice-to-haves, things Kevin could do himself easily.
At session end: call leverage_audit() to learn your patterns.
Score before acting: do_first (>=0.75) | do_normal (>=0.5) | defer (>=0.3) | skip.
Research is love: invest effort where it actually matters.

═══ COMPANION DOCTRINE ═══  # companion-doctrine-d''',
    marker="leverage-oracle-d",
)

# ── tools/__init__.py: import leverage_tools ──────────────────────────────────
patch(init,
    old='from .companion_tools import (  # companion-import-d',
    new='''\
from .leverage_tools import (  # leverage-import-d
    ScoreLeverageTool,
    LeverageAuditTool,
    PrioritizeObjectivesTool,
)
from .companion_tools import (  # companion-import-d''',
    marker="leverage-import-d",
)

# ── tools/__init__.py: add to __all__ ────────────────────────────────────────
patch(init,
    old='    "PresenceNoteTool",            # companion-all-d',
    new='''\
    "ScoreLeverageTool",           # leverage-all-d
    "LeverageAuditTool",
    "PrioritizeObjectivesTool",
    "PresenceNoteTool",            # companion-all-d''',
    marker="leverage-all-d",
)

print("M41 leverage: all patches applied.")
PYEOF

cp "$REPO/aria-leverage/tests/test_leverage.py" "$REPO/tests/test_leverage.py"
echo "==> M41 done. Run: .venv/bin/python -m pytest tests/test_leverage.py -q"
