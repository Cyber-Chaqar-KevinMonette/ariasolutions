#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
#  apply_ripple_coalesce.sh — merge same-colour ripple-border runs via Rich's
#  Segment.simplify, so fewer per-cell quads means fewer sub-pixel seams (and
#  less per-frame diff work at 17fps). ZERO visual change. Idempotent.
#  Safe to re-run. Rides the existing SOV_NO_RIPPLE_BORDER kill switch.
#
#  Patches:
#    • cockpit/ripple_border.py   (wrap the 4 Strip(...) constructions in
#                                  Segment.simplify(...) — 3 in ripple_frame_
#                                  strips, 1 in RippleBorderMixin.recolor)
#  Adds:
#    • tests/test_ripple_coalesce.py
# ═══════════════════════════════════════════════════════════════════════════
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PAYLOAD="$HERE/payload"

# ── locate repo root ────────────────────────────────────────────────────────
ROOT="${1:-$PWD}"
if [[ ! -f "$ROOT/src/sovereign_agent/cli.py" ]]; then
  d="$PWD"
  while [[ "$d" != "/" ]]; do
    if [[ -f "$d/src/sovereign_agent/cli.py" ]]; then ROOT="$d"; break; fi
    d="$(dirname "$d")"
  done
fi
if [[ ! -f "$ROOT/src/sovereign_agent/cli.py" ]]; then
  echo "✗ could not find src/sovereign_agent/cli.py."
  echo "  run from your sovereign-agent repo root, or: bash apply_ripple_coalesce.sh /path/to/repo"
  exit 1
fi
echo "◊ repo root: $ROOT"

PKG="$ROOT/src/sovereign_agent"
RB="$PKG/cockpit/ripple_border.py"

# ── 1. test ─────────────────────────────────────────────────────────────────
echo "→ installing tests"
cp "$PAYLOAD/tests/test_ripple_coalesce.py" "$ROOT/tests/test_ripple_coalesce.py"
echo "  ✓ test_ripple_coalesce.py"

# ── 2. patch ripple_border.py (idempotent + drift guard, atomic) ────────────
if grep -q "Segment.simplify" "$RB"; then
  echo "→ ripple_border.py already coalesced — skipping patch"
else
  echo "→ wrapping Strip(...) constructions in Segment.simplify(...)"
  cp "$RB" "$RB.bak.$(date +%Y%m%d%H%M%S)"
  python3 - "$RB" <<'PY'
import sys
path = sys.argv[1]
src = open(path, encoding="utf-8").read()

n_segs = src.count("Strip(segs, w)")
n_out = src.count("Strip(out, strip.cell_length)")
if n_segs != 3 or n_out != 1:
    print(f"✗ unexpected anchors (Strip(segs, w)={n_segs}, "
          f"Strip(out, strip.cell_length)={n_out}); file drifted. No changes made.")
    raise SystemExit(1)

src = src.replace("Strip(segs, w)", "Strip(list(Segment.simplify(segs)), w)")
src = src.replace(
    "Strip(out, strip.cell_length)",
    "Strip(list(Segment.simplify(out)), strip.cell_length)",
)
open(path, "w", encoding="utf-8").write(src)
print("  ✓ wrapped 4 Strip constructions (3 frame-strips + 1 recolor)")
PY
fi

# ── 3. compile check ────────────────────────────────────────────────────────
echo "→ compile check"
python3 -m py_compile "$RB" "$ROOT/tests/test_ripple_coalesce.py"
echo "  ✓ all files compile"

echo
echo "✓ done. next:"
echo "    .venv/bin/python -m pytest -q tests/test_ripple_coalesce.py"
echo "    .venv/bin/sovereign cockpit          # ripple looks identical, fewer seams"
echo
echo "  to revert this patch only:"
echo "    git checkout -- src/sovereign_agent/cockpit/ripple_border.py"
echo "    # (or restore the ripple_border.py.bak.* this script just wrote)"
