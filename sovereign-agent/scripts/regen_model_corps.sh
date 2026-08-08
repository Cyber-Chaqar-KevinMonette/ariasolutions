#!/usr/bin/env bash
# regen_model_corps.sh — the one command that regenerates every aria-<role> Ollama
# model from the single shared source: model_corps.persona.build_role_persona(),
# which itself pulls mos_canon.py's frozen priorities + GOD_TIER_STANDARD.md's nine
# floor dimensions live. Run this again any time the floor ratchets upward (a new
# dimension, a raised bar) and every model in the roster picks up the change on its
# next `ollama create` — that's the actual leverage: one source, regenerated
# everywhere, never five hand-maintained SYSTEM blocks drifting apart.
#
# model-corps-unify-d (Kevin, 2026-07-21): "rebuild the entire models system
# if you have to and make it nice." This script used to carry its OWN copy of
# the role -> base-model/temperature mapping in a hardcoded bash associative
# array — a second source of truth that could (and did) drift out of sync
# with whatever `sov models promote <slot>` had actually built live. Now both
# this script AND promote_slot() read the exact same file
# (src/sovereign_agent/model_corps/bases.json) through the exact same
# function (model_corps.build_modelfile_text()) — there is nothing left here
# to drift.
#
# Safe to re-run: `ollama create` overwrites the existing tag idempotently;
# base models must already be pulled (this script does not pull them).
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
ARCHIVE_DIR="$REPO_ROOT/docs/model_corps_2026-07-06"

[[ -f "$VENV_PY" ]] || { echo "ERROR: venv missing at $VENV_PY"; exit 1; }
mkdir -p "$ARCHIVE_DIR"

echo "=== regen_model_corps: generating personas from mos_canon.py + GOD_TIER_STANDARD.md ==="
echo "=== base models read live from src/sovereign_agent/model_corps/bases.json ==="

for role in orchestrator coder fast reflector interpreter vision; do
  modelfile="$ARCHIVE_DIR/aria-${role}.Modelfile"

  "$VENV_PY" -c "
import sys
sys.path.insert(0, '$REPO_ROOT/src')
from sovereign_agent.model_corps import build_modelfile_text
sys.stdout.write(build_modelfile_text('$role'))
" > "$modelfile"

  base="$(head -1 "$modelfile" | sed 's/^FROM //')"
  echo "→ aria-${role}  (FROM ${base})"
  ollama create "aria-${role}" -f "$modelfile"
done

echo "=== done. Archived Modelfiles: $ARCHIVE_DIR ==="
ollama list | grep '^aria-' || true
