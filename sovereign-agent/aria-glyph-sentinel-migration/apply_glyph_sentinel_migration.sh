#!/usr/bin/env bash
# apply_glyph_sentinel_migration.sh — migrate glyph_sentinel.py to the
# unified @register_sentinel pattern.
#
# THE GAP: glyph_sentinel.py is a functional module (free functions
# scan_source_tree/generate_proposals/detect_coverage_gaps/load_catalog/
# save_catalog over plain dataclasses), not an OOP sentinel — invisible
# to `sov sentinels list`/`gather_health()`/`scan_all()` entirely.
#
# THE FIX: add a NEW `GlyphSentinel(Sentinel)` class INSIDE
# glyph_sentinel.py that *delegates* to the existing free functions
# unchanged, registers via @register_sentinel, and writes its OWN
# rollup catalog under the base class's own sentinels/glyphs/catalogs/
# convention. The legacy glyph_catalog.json path and all 4 existing call
# sites (doctor.py, cli.py, workflow/catalog.py, cosmic_fitness.py) stay
# completely untouched — purely additive.
#
# health_status() deliberately reads the last CACHED rollup rather than
# re-running the ~3s full-source-tree scan_source_tree() — gather_health()
# runs on the cockpit's 8s strip-refresh cadence in 4 places; re-scanning
# fresh on every call would reintroduce the exact GIL-contention
# regression already root-caused and fixed twice this session
# (security-strip-wire, vessel-health). scan() remains the expensive,
# explicit, on-demand full walk.
#
# Anatomy: guard (cockpit stopped + venv) → backup both touched files →
# patch (anchored, idempotent, py_compile-verified) → copy tests → run.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-glyph-sentinel-migration"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
GLYPH_SENTINEL="$REPO_ROOT/src/sovereign_agent/stewardship/glyph_sentinel.py"
STEWARDSHIP_INIT="$REPO_ROOT/src/sovereign_agent/stewardship/__init__.py"

echo "=== aria-glyph-sentinel-migration apply ==="
if pgrep -f "sovereign cockpit" >/dev/null 2>&1; then echo "ERROR: cockpit running. Stop it first."; exit 1; fi
[[ -x "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
[[ -f "$GLYPH_SENTINEL" ]] || { echo "ERROR: $GLYPH_SENTINEL not found."; exit 1; }
[[ -f "$STEWARDSHIP_INIT" ]] || { echo "ERROR: $STEWARDSHIP_INIT not found."; exit 1; }
mkdir -p "$BACKUP_DIR"
cp "$GLYPH_SENTINEL" "$BACKUP_DIR/glyph_sentinel.py.bak"
cp "$STEWARDSHIP_INIT" "$BACKUP_DIR/stewardship_init.py.bak"

echo "→ Patching glyph_sentinel.py + stewardship/__init__.py (anchored, idempotent)..."
"$VENV_PY" - "$STAGING" "$GLYPH_SENTINEL" "$STEWARDSHIP_INIT" <<'PYEOF'
import sys
from pathlib import Path

staging, glyph_path, init_path = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
sys.path.insert(0, str(staging))
from patcher import PatchError, patch_glyph_sentinel, patch_stewardship_init

glyph_text = glyph_path.read_text(encoding="utf-8")
try:
    new_glyph, changed1 = patch_glyph_sentinel(glyph_text)
except PatchError as e:
    print(f"ERROR: glyph_sentinel.py: {e}", file=sys.stderr)
    sys.exit(1)
if changed1:
    glyph_path.write_text(new_glyph, encoding="utf-8")
    print("  ✓ patched glyph_sentinel.py")
else:
    print("  SKIP: glyph_sentinel.py already patched")

init_text = init_path.read_text(encoding="utf-8")
try:
    new_init, changed2 = patch_stewardship_init(init_text)
except PatchError as e:
    print(f"ERROR: stewardship/__init__.py: {e}", file=sys.stderr)
    sys.exit(1)
if changed2:
    init_path.write_text(new_init, encoding="utf-8")
    print("  ✓ patched stewardship/__init__.py")
else:
    print("  SKIP: stewardship/__init__.py already patched")
PYEOF

echo "→ Compile check..."
"$VENV_PY" -m py_compile "$GLYPH_SENTINEL" "$STEWARDSHIP_INIT"
echo "  ✓ py_compile clean"

echo "→ Import + registration check..."
"$VENV_PY" -c "
from sovereign_agent.stewardship import registry
assert 'glyphs' in registry.registered_ids(), 'glyphs sentinel not registered'
from sovereign_agent.stewardship.glyph_sentinel import GlyphSentinel
print('  ✓ GlyphSentinel registered and importable')
"

# NOTE: promote test_glyph_sentinel_migration_live.py, NOT
# test_glyph_sentinel_migration.py. The latter uses a shadow-copy-and-patch
# mechanism needed only for pre-apply verification; promoting shadow-copy
# test files caused real regressions elsewhere this session — see
# aria-security-strip-wire's README for the full story.
cp "$STAGING/tests/test_glyph_sentinel_migration_live.py" "$REPO_ROOT/tests/"
echo "Running test suites: glyph_sentinel_migration_live (new), glyph_sentinel (pre-existing, untouched free functions)..."
"$VENV_PY" -m pytest \
  "$REPO_ROOT/tests/test_glyph_sentinel_migration_live.py" \
  "$REPO_ROOT/tests/test_glyph_sentinel.py" \
  -q

echo "→ Smoke-testing sov sentinels CLI..."
"$VENV_PY" -m sovereign_agent.cli sentinels list 2>&1 | grep -i glyphs && echo "  ✓ 'glyphs' visible in sov sentinels list"

echo "=== aria-glyph-sentinel-migration applied. Reversible: restore both files from $BACKUP_DIR 💛 ==="
