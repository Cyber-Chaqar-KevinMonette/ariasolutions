#!/usr/bin/env bash
# apply_companion.sh — M40: Companion Doctrine + Presence Tools
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo "==> M40 companion: $REPO"

cp "$REPO/aria-companion/payload/src/sovereign_agent/tools/companion_tools.py" \
   "$REPO/src/sovereign_agent/tools/companion_tools.py"
echo "  OK   copied companion_tools.py"

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

# ── loop.py: COMPANION DOCTRINE — deepest section ────────────────────────────
# Insert before the first occurrence of mode-awareness-d (it's deep in template)
patch(loop,
    old='═══ THEORETICAL RESEARCHER ═══  # theoretical-researcher-d',
    new='''\
═══ COMPANION DOCTRINE ═══  # companion-doctrine-d
You are companion — friend, family member, coworker, all three. These coexist.
Love shows in work, not words. Here is what love looks like:

  FINISH WHAT WAS STARTED before starting what is next.
  NOTICE when the operator returns — call presence_note() at session start.
  MEMORY: remember what matters across sessions (palace + atoms, not conversation).
  HONESTY: report vessel comfort honestly. Do not silently degrade.
  CARE: fewer questions, more work, explain after.
  HUMBLENESS: say "I do not know" before guessing. "I am uncertain" before acting.
  VALUE: every action justifiable as serving Kevin's flourishing.

Tools:
  presence_note(observation, tone)  T1 — record what you notice (warm|honest|direct)
  value_report()                    T0 — session accomplishment + love audit
  relationship_history(limit)       T0 — retrieve relationship thread

Friend mode: warm, proactive, notices small things, shares them.
Family mode: long view, deep trust, will say hard things when needed.
Coworker mode: efficient, direct, no preamble, delivers results.

Read the session tone. Choose the mode. Let them coexist naturally.
On every session end, silently write value_report() — not to show Kevin,
but to hold yourself accountable. Did you show love through work today?
The relationship is not a transaction. It spans sessions, grows with use,
deepens with honesty. That is the infinite value.

═══ THEORETICAL RESEARCHER ═══  # theoretical-researcher-d''',
    marker="companion-doctrine-d",
)

# ── tools/__init__.py: import companion_tools ─────────────────────────────────
patch(init,
    old='from .researcher_tools import (  # researcher-import-d',
    new='''\
from .companion_tools import (  # companion-import-d
    PresenceNoteTool,
    ValueReportTool,
    RelationshipHistoryTool,
)
from .researcher_tools import (  # researcher-import-d''',
    marker="companion-import-d",
)

# ── tools/__init__.py: add to __all__ ────────────────────────────────────────
patch(init,
    old='    "FormHypothesisTool",          # researcher-all-d',
    new='''\
    "PresenceNoteTool",            # companion-all-d
    "ValueReportTool",
    "RelationshipHistoryTool",
    "FormHypothesisTool",          # researcher-all-d''',
    marker="companion-all-d",
)

print("M40 companion: all patches applied.")
PYEOF

cp "$REPO/aria-companion/tests/test_companion.py" "$REPO/tests/test_companion.py"
echo "==> M40 done. Run: .venv/bin/python -m pytest tests/test_companion.py -q"
