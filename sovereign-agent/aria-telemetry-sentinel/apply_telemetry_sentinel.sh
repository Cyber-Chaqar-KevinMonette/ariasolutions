#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
#  apply_telemetry_sentinel.sh — Watch the telemetry stream for anomalies
#
#  17k samples/day collected. Nobody watching. This sentinel fixes that.
#  Thresholds: VRAM, disk, CPU, RAM, GPU temp.
#
#  Changes:
#  1. Install stewardship/telemetry_sentinel.py
#  2. Patch stewardship/__init__.py — register the sentinel via side-effect import
#
#  Idempotent. Backs up patched files.
# ═══════════════════════════════════════════════════════════════════════════
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${1:-$PWD}"

if [[ ! -f "$ROOT/src/sovereign_agent/cli.py" ]]; then
  d="$PWD"
  while [[ "$d" != "/" ]]; do
    [[ -f "$d/src/sovereign_agent/cli.py" ]] && { ROOT="$d"; break; }
    d="$(dirname "$d")"
  done
fi
[[ -f "$ROOT/src/sovereign_agent/cli.py" ]] || { echo "✗ run from repo root"; exit 1; }
echo "◊ repo root: $ROOT"

PKG="$ROOT/src/sovereign_agent"
STEWARDSHIP="$PKG/stewardship"
INIT="$STEWARDSHIP/__init__.py"
ts(){ date +%Y%m%d%H%M%S; }

# ── 1. Install telemetry_sentinel.py ──────────────────────────────────────
echo "→ installing stewardship/telemetry_sentinel.py"
cp "$HERE/payload/src/sovereign_agent/stewardship/telemetry_sentinel.py" \
   "$STEWARDSHIP/telemetry_sentinel.py"
echo "  ✓ telemetry_sentinel.py"

# ── 2. Patch stewardship/__init__.py ──────────────────────────────────────
echo "→ patching stewardship/__init__.py"
cp "$INIT" "$INIT.bak.$(ts)"

python3 - "$INIT" <<'PYEOF'
import sys, pathlib
init = pathlib.Path(sys.argv[1])
src = init.read_text(encoding="utf-8")

MARKER = "# telemetry-sentinel-d"
if MARKER in src:
    print("  ↷ telemetry_sentinel already registered — skipping")
else:
    # Add after cache_sentinel import
    anchor = "from . import cache_sentinel as _cache_sentinel  # noqa: F401\n"
    if anchor in src:
        new_line = "from . import telemetry_sentinel as _telemetry_sentinel  # noqa: F401  " + MARKER + "\n"
        src = src.replace(anchor, anchor + new_line, 1)
        print("  ✓ telemetry_sentinel import added")
    else:
        # Fallback: look for any sentinel import line
        for fallback in (
            "from . import cache_sentinel",
            "from .registry import",
            "gather_health,",
        ):
            if fallback in src:
                # Find line end and append after
                idx = src.find(fallback)
                line_end = src.find("\n", idx) + 1
                insert = "from . import telemetry_sentinel as _telemetry_sentinel  # noqa: F401  " + MARKER + "\n"
                src = src[:line_end] + insert + src[line_end:]
                print("  ✓ telemetry_sentinel import added (fallback anchor)")
                break
        else:
            print("  ⚠ no suitable anchor — manual registration required")

init.write_text(src, encoding="utf-8")
print("  ✓ stewardship/__init__.py written")
PYEOF

# ── 3. Compile checks ──────────────────────────────────────────────────────
echo "→ compile checks"
python3 -m py_compile "$STEWARDSHIP/telemetry_sentinel.py" "$INIT"
echo "  ✓ all files compile"

cp "$HERE/tests/test_telemetry_sentinel.py" "$ROOT/tests/test_telemetry_sentinel.py"
python3 -m py_compile "$ROOT/tests/test_telemetry_sentinel.py"
echo "  ✓ tests installed + compile"

echo
echo "✓ done. TelemetrySentinel is watching."
echo
echo "  sentinel id: telemetry"
echo "  Thresholds:"
echo "    VRAM > 90% sustained >60s → warning; > 95% → error"
echo "    disk free < 5 GB → warning; < 1 GB → error"
echo "    CPU > 90% sustained >120s → warning"
echo "    RAM > 90% sustained >60s → warning"
echo "    GPU temp > 80°C → warning; > 88°C → error"
echo
echo "  Kill switch: SOV_NO_TELEMETRY_SENTINEL=1"
echo "  run: pytest tests/test_telemetry_sentinel.py -v"
