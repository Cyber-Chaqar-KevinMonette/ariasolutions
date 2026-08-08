#!/usr/bin/env bash
# apply_auto_crown.sh — M43: Timed Autonomous Operation
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo "==> M43 auto-crown: $REPO"

cp "$REPO/aria-auto-crown/payload/src/sovereign_agent/auto_crown.py" \
   "$REPO/src/sovereign_agent/auto_crown.py"
echo "  OK   copied auto_crown.py"

cp "$REPO/aria-auto-crown/payload/src/sovereign_agent/tools/auto_tools.py" \
   "$REPO/src/sovereign_agent/tools/auto_tools.py"
echo "  OK   copied auto_tools.py"

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

# ── loop.py: AUTO CROWN doctrine ─────────────────────────────────────────────
patch(loop,
    old='═══ RESUME CROWN ═══  # resume-crown-doctrine-d',
    new='''\
═══ AUTO CROWN ═══  # auto-crown-d
Timed autonomous operation — wall-clock timer governs session length.
Trust tiers control max duration (Kevin sets via set_auto_trust_tier T3):
  Tier 1 (default): max 1hr  |  Tier 2: max 2hr  |  Tier 3: max 4hr  |  Tier 4: max 8hr
  auto_status()                      T0 — remaining time, session info
  start_auto(duration_hours, reason) T2 — begin timed auto session (Kevin confirms)
  stop_auto(reason)                  T1 — early graceful stop
  extend_auto(additional_hours)      T3 — extend (approval required)
  set_auto_trust_tier(tier)          T3 — unlock higher tiers (approval required)
When timer expires: loop exits cleanly, auto-expired-d is recorded.
Tier ceiling stays T1 during auto — safety is unchanged by duration.
Auto mode is BUSY mode with a heartbeat. Work hard. Stop when time is up.

═══ RESUME CROWN ═══  # resume-crown-doctrine-d''',
    marker="auto-crown-d",
)

# ── loop.py: auto_crown import ────────────────────────────────────────────────
patch(loop,
    old='from .checkpoint import get_checkpoint_store as _get_checkpoint_store  # resume-crown-import-d',
    new='''\
from .auto_crown import get_auto_crown_store as _get_auto_crown_store  # auto-crown-import-d
from .checkpoint import get_checkpoint_store as _get_checkpoint_store  # resume-crown-import-d''',
    marker="auto-crown-import-d",
)

# ── loop.py: auto_crown singleton ────────────────────────────────────────────
patch(loop,
    old='_checkpoint_store = _get_checkpoint_store()  # resume-crown-singleton-d',
    new='''\
_auto_crown_store = _get_auto_crown_store()  # auto-crown-singleton-d
_checkpoint_store = _get_checkpoint_store()  # resume-crown-singleton-d''',
    marker="auto-crown-singleton-d",
)

# ── loop.py: expiry check after mode-master-check-d, before budget ────────────
patch(loop,
    old='            # ── Invariant 4: budgets BEFORE the iteration ────────────────',
    new='''\
            # ── Auto-crown expiry check ──────────────────────────  # auto-crown-expiry-d
            if _auto_crown_store.is_expired():
                _record("auto-expired-d", {"reason": "timer_expired"})
                _auto_crown_store.expire()
                outcome = "complete"
                break

            # ── Invariant 4: budgets BEFORE the iteration ────────────────''',
    marker="auto-crown-expiry-d",
)

# ── tools/__init__.py: import auto_tools ──────────────────────────────────────
patch(init,
    old='from .resume_tools import (  # resume-crown-import-d',
    new='''\
from .auto_tools import (  # auto-crown-import-d
    AutoStatusTool,
    StartAutoTool,
    StopAutoTool,
    ExtendAutoTool,
    SetAutoTrustTierTool,
)
from .resume_tools import (  # resume-crown-import-d''',
    marker="auto-crown-import-d",
)

# ── tools/__init__.py: add to __all__ ────────────────────────────────────────
patch(init,
    old='    "SessionResumeAuditTool",      # resume-crown-all-d',
    new='''\
    "AutoStatusTool",               # auto-crown-all-d
    "StartAutoTool",
    "StopAutoTool",
    "ExtendAutoTool",
    "SetAutoTrustTierTool",
    "SessionResumeAuditTool",      # resume-crown-all-d''',
    marker="auto-crown-all-d",
)

print("M43 auto-crown: all patches applied.")
PYEOF

cp "$REPO/aria-auto-crown/tests/test_auto_crown.py" "$REPO/tests/test_auto_crown.py"
echo "==> M43 done. Run: .venv/bin/python -m pytest tests/test_auto_crown.py -q"
