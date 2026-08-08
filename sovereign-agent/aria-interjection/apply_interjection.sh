#!/usr/bin/env bash
# apply_interjection.sh — M37: Safe BTW/Interjection system (Objective Map)
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo "==> M37 interjection: $REPO"

cp "$REPO/aria-interjection/payload/src/sovereign_agent/objective_map.py" \
   "$REPO/src/sovereign_agent/objective_map.py"
echo "  OK   copied objective_map.py"

cp "$REPO/aria-interjection/payload/src/sovereign_agent/tools/interjection_tools.py" \
   "$REPO/src/sovereign_agent/tools/interjection_tools.py"
echo "  OK   copied interjection_tools.py"

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

# ── loop.py: OBJECTIVE MAP doctrine ──────────────────────────────────────────
patch(loop,
    old='═══ COMPRESSION ORACLE ═══  # compression-oracle-d',
    new='''\
═══ OBJECTIVE MAP ═══  # objective-map-d
Secondary goals and BTW notes are parked here without interrupting active work.
At session start (after aria_status): call list_objectives() to surface parked goals.
  add_objective(text, priority, scope)  T1 — inject a goal without stopping flow
  btw_note(text)                        T1 — lightweight note, no action required
  list_objectives()                     T0 — show all active objectives by priority
  complete_objective(id)                T1 — mark done when addressed
Priority order: primary → secondary → background.
Address primary immediately. Secondary at natural pause points.
Background when opportunistic — never skip primary for background.
Kevin may inject objectives while you work; they surface next iteration.
You may also inject your own secondary objectives while working on primary.

═══ COMPRESSION ORACLE ═══  # compression-oracle-d''',
    marker="objective-map-d",
)

# ── tools/__init__.py: import interjection_tools ──────────────────────────────
patch(init,
    old='from .compression_tools import (  # compression-import-d',
    new='''\
from .interjection_tools import (  # interjection-import-d
    AddObjectiveTool,
    BtwNoteTool,
    ListObjectivesTool,
    CompleteObjectiveTool,
)
from .compression_tools import (  # compression-import-d''',
    marker="interjection-import-d",
)

# ── tools/__init__.py: add to __all__ ────────────────────────────────────────
patch(init,
    old='    "ContextStatsTool",           # compression-all-d',
    new='''\
    "AddObjectiveTool",            # interjection-all-d
    "BtwNoteTool",
    "ListObjectivesTool",
    "CompleteObjectiveTool",
    "ContextStatsTool",           # compression-all-d''',
    marker="interjection-all-d",
)

print("M37 interjection: all patches applied.")
PYEOF

cp "$REPO/aria-interjection/tests/test_interjection.py" "$REPO/tests/test_interjection.py"
echo "==> M37 done. Run: .venv/bin/python -m pytest tests/test_interjection.py -q"
