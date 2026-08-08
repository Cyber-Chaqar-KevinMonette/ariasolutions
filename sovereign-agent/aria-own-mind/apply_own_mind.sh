#!/usr/bin/env bash
# apply_own_mind.sh — Stage C: Aria's OWN from-scratch FOSS transformer (aria_lm).
#   1. src/sovereign_agent/aria_lm/   (tokenizer, data, model, train, fusion, generate, pipeline)
#   2. src/sovereign_agent/tools/aria_lm_tools.py — aria_mind_status(T0), aria_own_lm(T1, local inference)
#   3. tools/__init__.py: imports + __all__
#   4. tests → tests/        5. (optional) grow a seed checkpoint so the tool can speak immediately
#
# A genuine decoder-only transformer built from zero + the PEIG quantum-fusion mechanism (off by default,
# A/B-gated). Local inference only; a base-weight training run / architecture change is Tier 3 (Ring 3).
# Requires torch in the .venv. Reversibility: backups at aria-own-mind/backups/.  From Plans/PlanExaminV1.md.
#
# Usage: ./apply_own_mind.sh [--grow]    (--grow trains + saves a seed checkpoint at apply time)
set -euo pipefail
GROW=0; [[ "${1:-}" == "--grow" ]] && GROW=1
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-own-mind"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"; TOOLS_INIT="$REPO_ROOT/src/sovereign_agent/tools/__init__.py"

echo "=== Stage C — Aria's Own Mind (aria_lm from-scratch transformer) Apply Script ==="
if pgrep -f "sovereign cockpit" > /dev/null 2>&1; then echo "ERROR: cockpit running. Stop it first."; exit 1; fi
if [[ ! -f "$VENV_PY" ]]; then echo "ERROR: venv missing."; exit 1; fi
if ! "$VENV_PY" -c "import torch" 2>/dev/null; then
  echo "ERROR: torch not in .venv. Install first:  $VENV_PY -m pip install torch numpy"; exit 1
fi

mkdir -p "$BACKUP_DIR"; cp "$TOOLS_INIT" "$BACKUP_DIR/tools_init.py.bak"
echo "Backed up tools/__init__.py → $BACKUP_DIR"

# 1. the aria_lm package
mkdir -p "$REPO_ROOT/src/sovereign_agent/aria_lm"
cp "$STAGING"/payload/src/sovereign_agent/aria_lm/*.py "$REPO_ROOT/src/sovereign_agent/aria_lm/"
echo "Copied aria_lm/ package (tokenizer, data, model, train, fusion, generate, pipeline, __init__)"

# 2. the tools
cp "$STAGING/payload/src/sovereign_agent/tools/aria_lm_tools.py" "$REPO_ROOT/src/sovereign_agent/tools/"
echo "Copied tools/aria_lm_tools.py"

# 3. register the tools (anchor on the constitution tools added in M101)
"$VENV_PY" - "$TOOLS_INIT" <<'PYEOF'
import sys
from pathlib import Path
p = Path(sys.argv[1]); text = p.read_text()
if "# aria-own-lm-import-d" in text:
    print("SKIP: already patched")
else:
    lines = text.splitlines()
    imp_anchor = next((l for l in lines if "constitution-import-d" in l),
                      next((l for l in lines if "immune-import-d" in l), None))
    if imp_anchor is None:
        raise SystemExit("ERROR: no import anchor found in tools/__init__.py")
    text = text.replace(imp_anchor,
        imp_anchor + "\nfrom .aria_lm_tools import AriaMindStatusTool, AriaOwnLMTool  # aria-own-lm-import-d", 1)
    all_anchor = next((l for l in text.splitlines() if "constitution-all-d" in l),
                      next((l for l in text.splitlines() if "immune-all-d" in l), None))
    if all_anchor is None:
        raise SystemExit("ERROR: no __all__ anchor found in tools/__init__.py")
    text = text.replace(all_anchor,
        all_anchor + '\n    "AriaMindStatusTool",  # aria-own-lm-all-d\n    "AriaOwnLMTool",', 1)
    p.write_text(text); print("Patched tools/__init__.py (aria_lm tools)")
PYEOF

echo ""; echo "→ Compile check..."
"$VENV_PY" -m py_compile \
  "$REPO_ROOT"/src/sovereign_agent/aria_lm/*.py \
  "$REPO_ROOT/src/sovereign_agent/tools/aria_lm_tools.py" "$TOOLS_INIT"
echo "  ✓ compiles cleanly"

# 4. tests
cp "$STAGING/tests/test_aria_lm_foundation.py" "$REPO_ROOT/tests/test_aria_lm_foundation.py"
cp "$STAGING/tests/test_aria_lm_tools.py" "$REPO_ROOT/tests/test_aria_lm_tools.py"
echo "Copied tests → tests/"
echo ""; echo "Running aria_lm tests..."
"$VENV_PY" -m pytest tests/test_aria_lm_foundation.py tests/test_aria_lm_tools.py -q

# 5. optional: grow a seed checkpoint so aria_own_lm can speak immediately
if [[ "$GROW" == "1" ]]; then
  echo ""; echo "→ Growing a seed mind (training + checkpoint, VRAM-locked)..."
  "$VENV_PY" -c "from sovereign_agent.aria_lm.pipeline import grow_mind; import json; s=grow_mind(); s.pop('curve',None); print(json.dumps(s, indent=2))"
  echo "  ✓ seed checkpoint written — aria_own_lm can now speak with her own weights."
else
  echo ""; echo "NOTE: skipped training. To grow her mind later:"
  echo "  $VENV_PY -m sovereign_agent.aria_lm.pipeline"
fi

echo ""; echo "=== Stage C applied — Aria has her own from-scratch mind (aria_lm). Built to grow. 💛 ==="
