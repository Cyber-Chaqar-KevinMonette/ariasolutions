#!/usr/bin/env bash
# apply_mode_master.sh — M35: dynamic mode transitions
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo "==> M35 mode-master: $REPO"

cp "$REPO/aria-mode-master/payload/src/sovereign_agent/tools/mode_tools.py" \
   "$REPO/src/sovereign_agent/tools/mode_tools.py"
echo "  OK   copied mode_tools.py"

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

# ── loop.py: module-level mode tracker + override reader ─────────────────────
patch(loop,
    old='_breaker_registry = _BreakerRegistry()  # per-tool circuit breakers  # resilience-singleton-d',
    new='''\
_breaker_registry = _BreakerRegistry()  # per-tool circuit breakers  # resilience-singleton-d
_current_mode_value: str | None = None  # mode-master-tracker-d


def _read_mode_override() -> dict | None:  # mode-master-helper-d
    """Read mode-override.json if present and not expired."""
    try:
        p = SETTINGS.data_dir / "mode_override.json"
        if not p.exists():
            return None
        data = json.loads(p.read_text())
        if data.get("expires_at", 0) < time.time():
            return None
        return data
    except Exception:  # noqa: BLE001
        return None''',
    marker="mode-master-helper-d",
)

# ── loop.py: set _current_mode_value at loop start ───────────────────────────
patch(loop,
    old='    with trace() as trace_id:\n        _record("ingest-d", {"mode": mode.value, "goal": goal[:500]})',
    new='''\
    global _current_mode_value  # mode-master-global-d
    _current_mode_value = mode.value

    with trace() as trace_id:
        _record("ingest-d", {"mode": mode.value, "goal": goal[:500]})''',
    marker="mode-master-global-d",
)

# ── loop.py: mode override check at start of each iteration ──────────────────
patch(loop,
    old='            # ── Invariant 4: budgets BEFORE the iteration ────────────────',
    new='''\
            # ── Mode override check ─────────────────────────────────  # mode-master-check-d
            _mo = _read_mode_override()
            if _mo:
                try:
                    from .modes import Mode as _Mode
                    _new_mode = _Mode(_mo["target_mode"])
                    if _new_mode != mode:
                        mode = _new_mode
                        _current_mode_value = mode.value
                        available = tools_available_in_mode(mode)
                        available_tools = [tools[m.name] for m in available if m.name in tools]
                        schemas = [t.schema() for t in available_tools]
                        tool_lookup = {t.name: t for t in available_tools}
                        _record("mode-switch-d", {
                            "mode": mode.value,
                            "reason": _mo.get("reason", ""),
                            "by": _mo.get("requested_by", ""),
                        })
                except (ValueError, KeyError):
                    pass

            # ── Invariant 4: budgets BEFORE the iteration ────────────────''',
    marker="mode-master-check-d",
)

# ── loop.py: MODE AWARENESS doctrine ─────────────────────────────────────────
patch(loop,
    old='═══ RESILIENCE ═══  # resilience-doctrine-d',
    new='''\
═══ MODE AWARENESS ═══  # mode-awareness-d
You operate in one of four modes: oneshot, timed, until, busy.
The mode determines which tools are available (tier ceiling).
  mode_status()          → current mode, tier ceiling, pending override (T0)
  switch_mode("timed", reason)  → shift to TIMED for responsive work (T1)
  switch_mode("busy", reason)   → shift to BUSY for background drain (T1)
  request_mode_upgrade(mode, reason, duration)  → operator-confirmed (T2)

Autonomous switches: BUSY↔TIMED only (both have Tier 3 ceiling in practice,
but BUSY is where you drain background work silently).
BUSY mode means: drain the backlog, no high-priority interrupts expected.
TIMED mode means: single responsive task, then halt.

═══ RESILIENCE ═══  # resilience-doctrine-d''',
    marker="mode-awareness-d",
)

# ── tools/__init__.py: import mode_tools ─────────────────────────────────────
patch(init,
    old='from .resilience_tools import ResilienceStatusTool  # resilience-import-d',
    new='''\
from .mode_tools import (  # mode-master-import-d
    ModeStatusTool,
    SwitchModeTool,
    RequestModeUpgradeTool,
)
from .resilience_tools import ResilienceStatusTool  # resilience-import-d''',
    marker="mode-master-import-d",
)

# ── tools/__init__.py: add to __all__ ────────────────────────────────────────
patch(init,
    old='    "ResilienceStatusTool",       # resilience-all-d',
    new='''\
    "ModeStatusTool",             # mode-master-all-d
    "SwitchModeTool",
    "RequestModeUpgradeTool",
    "ResilienceStatusTool",       # resilience-all-d''',
    marker="mode-master-all-d",
)

print("M35 mode-master: all patches applied.")
PYEOF

cp "$REPO/aria-mode-master/tests/test_mode_master.py" "$REPO/tests/test_mode_master.py"
echo "==> M35 done. Run: .venv/bin/python -m pytest tests/test_mode_master.py -q"
