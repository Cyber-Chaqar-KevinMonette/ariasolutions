#!/usr/bin/env bash
# apply_resume_crown.sh — M42: Deep Resume (Pre-Action Checkpoints)
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo "==> M42 resume-crown: $REPO"

cp "$REPO/aria-resume-crown/payload/src/sovereign_agent/checkpoint.py" \
   "$REPO/src/sovereign_agent/checkpoint.py"
echo "  OK   copied checkpoint.py"

cp "$REPO/aria-resume-crown/payload/src/sovereign_agent/tools/resume_tools.py" \
   "$REPO/src/sovereign_agent/tools/resume_tools.py"
echo "  OK   copied resume_tools.py"

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

# ── loop.py: RESUME CROWN doctrine ───────────────────────────────────────────
patch(loop,
    old='═══ LEVERAGE ORACLE ═══  # leverage-oracle-d',
    new='''\
═══ RESUME CROWN ═══  # resume-crown-doctrine-d
At session start, after aria_status() and vessel_comfort(): call session_resume_audit().
If has_incomplete_actions=True: STOP. Report to Kevin BEFORE doing new work:
  "I have N incomplete T2+ action(s) from last session. Should I re-run them?"
Every T2+ action you take is checkpointed before execution.
If the process dies mid-action: checkpoint stays pending. Nothing is silently lost.
On next boot: session_resume_audit() surfaces incomplete work automatically.
  session_resume_audit()          T0 — check for pending checkpoints (call every boot)
  read_checkpoints(status=...)    T0 — audit checkpoint history
  abandon_checkpoint(id, reason)  T1 — mark reviewed + skipped (Kevin must confirm)
Pending checkpoints are uncertainty — never silently ignore them. Love is honesty.

═══ LEVERAGE ORACLE ═══  # leverage-oracle-d''',
    marker="resume-crown-doctrine-d",
)

# ── loop.py: checkpoint import ────────────────────────────────────────────────
patch(loop,
    old='from .cache import ResponseCache as _ResponseCache  # cache-crown-import-d',
    new='''\
from .checkpoint import get_checkpoint_store as _get_checkpoint_store  # resume-crown-import-d
from .cache import ResponseCache as _ResponseCache  # cache-crown-import-d''',
    marker="resume-crown-import-d",
)

# ── loop.py: checkpoint singleton ────────────────────────────────────────────
patch(loop,
    old='_response_cache = _ResponseCache()  # T0 response cache, session-scoped  # cache-crown-singleton-d',
    new='''\
_checkpoint_store = _get_checkpoint_store()  # resume-crown-singleton-d
_response_cache = _ResponseCache()  # T0 response cache, session-scoped  # cache-crown-singleton-d''',
    marker="resume-crown-singleton-d",
)

# ── loop.py: write checkpoint before T2+ tool execution ───────────────────────
# Insert after circuit breaker gate (resilience-tool-gate-d), before cache check
patch(loop,
    old='# ── Cache check (T0 read-only tools only) ──────────────  # cache-crown-dispatch-d',
    new='''\
# ── Pre-action checkpoint (T2+ only) ──────────────────────  # resume-crown-checkpoint-d
                _ckpt = None
                if meta.tier >= 2:
                    try:
                        _ckpt = _checkpoint_store.write_pre(
                            tool_name=tool_name,
                            args=args,
                            tier=meta.tier,
                            session_id=trace_id,
                        )
                    except Exception as _ckpt_err:  # noqa: BLE001
                        _record("resume-crown-warn-x", {"error": str(_ckpt_err)})

                # ── Cache check (T0 read-only tools only) ──────────────  # cache-crown-dispatch-d''',
    marker="resume-crown-checkpoint-d",
)

# ── loop.py: resolve checkpoint after successful T2+ execution ────────────────
patch(loop,
    old='# ── Resilience: record tool outcome in circuit breaker ─  # resilience-record-d',
    new='''\
# ── Resolve checkpoint on success ──────────────────────────  # resume-crown-resolve-d
                if _ckpt is not None and result.ok:
                    try:
                        _checkpoint_store.resolve(_ckpt.checkpoint_id)
                    except Exception:  # noqa: BLE001
                        pass

                # ── Resilience: record tool outcome in circuit breaker ─  # resilience-record-d''',
    marker="resume-crown-resolve-d",
)

# ── tools/__init__.py: import resume_tools ────────────────────────────────────
patch(init,
    old='from .leverage_tools import (  # leverage-import-d',
    new='''\
from .resume_tools import (  # resume-crown-import-d
    SessionResumeAuditTool,
    ReadCheckpointsTool,
    AbandonCheckpointTool,
)
from .leverage_tools import (  # leverage-import-d''',
    marker="resume-crown-import-d",
)

# ── tools/__init__.py: add to __all__ ────────────────────────────────────────
patch(init,
    old='    "ScoreLeverageTool",           # leverage-all-d',
    new='''\
    "SessionResumeAuditTool",      # resume-crown-all-d
    "ReadCheckpointsTool",
    "AbandonCheckpointTool",
    "ScoreLeverageTool",           # leverage-all-d''',
    marker="resume-crown-all-d",
)

print("M42 resume-crown: all patches applied.")
PYEOF

cp "$REPO/aria-resume-crown/tests/test_resume_crown.py" "$REPO/tests/test_resume_crown.py"
echo "==> M42 done. Run: .venv/bin/python -m pytest tests/test_resume_crown.py -q"
