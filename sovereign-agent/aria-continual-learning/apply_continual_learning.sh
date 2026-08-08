#!/usr/bin/env bash
# apply_continual_learning.sh — install continual learning: pipe Reflector
# lessons into the aria_lm training corpus + a bounded, propose-only
# retrain trigger.
#
# Ships:
#   - src/sovereign_agent/aria_lm/retrain_trigger.py — NEW file: counts
#     lessons since the last training run and formats them as corpus text.
#     Never triggers training itself.
#   - src/sovereign_agent/tools/continual_learning_tools.py — NEW file:
#     ProposeRetrainTool (Tier 1, propose-only — training a base-weight
#     model stays Tier 3 / human-gated per aria_lm_tools.py's own
#     doctrine).
#   - src/sovereign_agent/aria_lm/data.py — 1 anchored, idempotent patch:
#     gather_corpus() gains a new lesson-text corpus source, inserted at
#     the FRONT of the parts list (not appended) so it survives the
#     final max_chars truncation even when the distilled-research text
#     alone exceeds it. Degrades to a silent no-op if lessons aren't
#     available — zero regression to the existing corpus path.
#   - src/sovereign_agent/aria_lm/pipeline.py — 1 anchored, idempotent
#     patch: grow_mind() calls record_retrain() (best-effort) after a
#     real training run completes, resetting the trigger's baseline.
#   - src/sovereign_agent/tools/__init__.py — 1 anchored, idempotent
#     patch: registers ProposeRetrainTool (import + __all__ in the same
#     patch — learning from this session's own missing-__all__-entry
#     bug class found earlier).
#
# Anatomy: guard (cockpit stopped + venv) → backup all 3 touched files →
# patch (anchored, idempotent, py_compile-verified) → copy 2 new files →
# copy tests → run.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-continual-learning"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
DATA_PY="$REPO_ROOT/src/sovereign_agent/aria_lm/data.py"
PIPELINE_PY="$REPO_ROOT/src/sovereign_agent/aria_lm/pipeline.py"
TOOLS_INIT="$REPO_ROOT/src/sovereign_agent/tools/__init__.py"
RETRAIN_TRIGGER="$REPO_ROOT/src/sovereign_agent/aria_lm/retrain_trigger.py"
CONTINUAL_TOOLS="$REPO_ROOT/src/sovereign_agent/tools/continual_learning_tools.py"

echo "=== aria-continual-learning apply ==="
if pgrep -fa "sovereign cockpit" | grep -qv "pgrep\|bash -c\|for i in"; then
  echo "ERROR: cockpit running. Stop it first."; exit 1
fi
[[ -x "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
for f in "$DATA_PY" "$PIPELINE_PY" "$TOOLS_INIT"; do
  [[ -f "$f" ]] || { echo "ERROR: $f not found."; exit 1; }
done
mkdir -p "$BACKUP_DIR"
cp "$DATA_PY" "$BACKUP_DIR/data.py.bak"
cp "$PIPELINE_PY" "$BACKUP_DIR/pipeline.py.bak"
cp "$TOOLS_INIT" "$BACKUP_DIR/tools_init.py.bak"

echo "→ Patching data.py, pipeline.py, tools/__init__.py (anchored, idempotent)..."
"$VENV_PY" - "$STAGING" "$DATA_PY" "$PIPELINE_PY" "$TOOLS_INIT" <<'PYEOF'
import sys
from pathlib import Path

staging, data_path, pipeline_path, init_path = (
    Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4])
)
sys.path.insert(0, str(staging))
from patcher import PatchError, patch_data_py, patch_pipeline_py, patch_tools_init

def _apply(name, path, fn):
    text = path.read_text(encoding="utf-8")
    try:
        new_text, changed = fn(text)
    except PatchError as e:
        print(f"ERROR: {name}: {e}", file=sys.stderr)
        sys.exit(1)
    if changed:
        path.write_text(new_text, encoding="utf-8")
        print(f"  ✓ patched {name}")
    else:
        print(f"  SKIP: {name} already patched")

_apply("data.py", data_path, patch_data_py)
_apply("pipeline.py", pipeline_path, patch_pipeline_py)
_apply("tools/__init__.py", init_path, patch_tools_init)
PYEOF

echo "→ Copying new files (retrain_trigger.py, continual_learning_tools.py)..."
cp "$STAGING/payload/src/sovereign_agent/aria_lm/retrain_trigger.py" "$RETRAIN_TRIGGER"
cp "$STAGING/payload/src/sovereign_agent/tools/continual_learning_tools.py" "$CONTINUAL_TOOLS"

echo "→ Compile check..."
"$VENV_PY" -m py_compile "$DATA_PY" "$PIPELINE_PY" "$TOOLS_INIT" "$RETRAIN_TRIGGER" "$CONTINUAL_TOOLS"
echo "  ✓ py_compile clean"

echo "→ Import + registration check..."
"$VENV_PY" -c "
from sovereign_agent.authority import _TIER_REGISTRY
import sovereign_agent.tools  # noqa: F401
assert 'propose_retrain' in _TIER_REGISTRY, 'propose_retrain not registered'
assert _TIER_REGISTRY['propose_retrain'].tier == 1
from sovereign_agent.aria_lm.data import gather_corpus
from sovereign_agent.aria_lm.retrain_trigger import check_retrain_proposal, record_retrain
print('  ✓ imports cleanly and propose_retrain registered at Tier 1')
"

# NOTE: promote test_continual_learning_live.py, NOT test_continual_learning.py.
# The latter uses a shadow-copy-and-patch mechanism needed only for pre-apply
# verification; promoting shadow-copy test files caused real regressions
# elsewhere this session — see aria-security-strip-wire's README for the
# full story.
cp "$STAGING/tests/test_continual_learning_live.py" "$REPO_ROOT/tests/"
echo "Running test suites: continual_learning_live (new), aria_lm_foundation (pre-existing, untouched gather_corpus tests)..."
"$VENV_PY" -m pytest \
  "$REPO_ROOT/tests/test_continual_learning_live.py" \
  "$REPO_ROOT/tests/test_aria_lm_foundation.py" \
  -q

echo "=== aria-continual-learning applied. Reversible: restore all 3 files from $BACKUP_DIR and rm the 2 new files 💛 ==="
