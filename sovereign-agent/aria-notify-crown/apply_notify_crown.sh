#!/usr/bin/env bash
# apply_notify_crown.sh — M51: Desktop Notifications via DBus
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo "==> M51 notify-crown: $REPO"

cp "$REPO/aria-notify-crown/payload/src/sovereign_agent/tools/notify_tools.py" \
   "$REPO/src/sovereign_agent/tools/notify_tools.py"
echo "  OK   copied notify_tools.py"

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

# ── 1. Doctrine in loop.py (before EVAL CROWN) ───────────────────────────────
patch(loop,
    old='═══ EVAL CROWN ═══  # eval-crown-d',
    new='''\
═══ NOTIFY CROWN ═══  # notify-crown-d
Desktop notifications via org.freedesktop.Notifications DBus protocol.
  notify_status()                          T0 — check daemon availability
  notify(title, body, urgency, icon)       T0 — send desktop notification

Use notify() to alert Kevin when long-running work completes, or for
important events when he may not be watching the cockpit:
  - Auto session complete: notify("Auto session done", "3 commits, 2 lessons", urgency="normal")
  - Critical error: notify("Aria blocked", "...", urgency="critical")
  - Task milestone: notify("Tests passing", "2453 passed", urgency="low")
Call notify_status() first to confirm the daemon is available.
Works on Pop!_OS via cosmic-notifications (gdbus → freedesktop DBus).

═══ EVAL CROWN ═══  # eval-crown-d''',
    marker="notify-crown-d",
)

# ── 2. Import in tools/__init__.py (before eval-crown-import-d) ───────────────
patch(init,
    old='from .eval_tools import (  # eval-crown-import-d',
    new='''\
from .notify_tools import (  # notify-crown-import-d
    NotifyTool,
    NotifyStatusTool,
)
from .eval_tools import (  # eval-crown-import-d''',
    marker="notify-crown-import-d",
)

# ── 3. __all__ (before eval-crown-all-d) ─────────────────────────────────────
patch(init,
    old='    "EvalSessionTool",               # eval-crown-all-d',
    new='''\
    "NotifyTool",                    # notify-crown-all-d
    "NotifyStatusTool",
    "EvalSessionTool",               # eval-crown-all-d''',
    marker="notify-crown-all-d",
)

print("M51 notify-crown: all patches applied.")
PYEOF

cp "$REPO/aria-notify-crown/tests/test_notify_crown.py" \
   "$REPO/tests/test_notify_crown.py"
echo "  OK   copied test_notify_crown.py"

echo "==> M51 done. Run: .venv/bin/python -m pytest tests/test_notify_crown.py -q"
