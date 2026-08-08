#!/usr/bin/env bash
# apply_pane_recovery.sh — make /obs all recover Memory and Atelier from Movie split view.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAGE="$REPO/aria-pane-recovery"

if pgrep -f '(^|[[:space:]])(sov|sovereign)[[:space:]]+cockpit([[:space:]]|$)' >/dev/null; then
    echo "Refusing to apply while the Sovereign cockpit is running. Stop it, review this module, then retry." >&2
    exit 1
fi

REPO="$REPO" python3 - <<'PYEOF'
import os
import sys
from pathlib import Path

path = Path(os.environ["REPO"]) / "src/sovereign_agent/cockpit/app.py"
src = path.read_text()
old = '''        if mode == "focus":
            main.add_class("obs-focus")
        else:
            main.remove_class("obs-focus")
        try:
'''
new = '''        if mode == "focus":
            main.add_class("obs-focus")
        else:
            # `movie-split` hides Memory and Atelier independently of
            # observability.  Returning to All must be a complete recovery
            # path, not a misleading no-op while Movie split is still active.
            main.remove_class("obs-focus")
            main.remove_class("movie-split")  # pane-recovery-d
        try:
'''
if new not in src:
    if old not in src:
        print("Anchor missing in cockpit/app.py", file=sys.stderr)
        raise SystemExit(1)
    path.write_text(src.replace(old, new, 1))
PYEOF

cp "$STAGE/tests/test_pane_recovery.py" "$REPO/tests/test_pane_recovery.py"
echo "Applied aria-pane-recovery. Verify with: .venv/bin/python -m pytest tests/test_pane_recovery.py tests/test_movie_focus_toggle_buttons.py -q"
