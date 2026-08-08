#!/usr/bin/env bash
# regen_model_corps.sh — the one command that regenerates every aria-<role> Ollama
# model from the single shared source: model_corps.persona.build_role_persona(),
# which itself pulls mos_canon.py's frozen priorities + GOD_TIER_STANDARD.md's nine
# floor dimensions live. Run this again any time the floor ratchets upward (a new
# dimension, a raised bar) and every model in the roster picks up the change on its
# next `ollama create` — that's the actual leverage: one source, regenerated
# everywhere, never five hand-maintained SYSTEM blocks drifting apart.
#
# Safe to re-run: `ollama create` overwrites the existing tag idempotently; base
# models must already be pulled (this script does not pull them).
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
ARCHIVE_DIR="$REPO_ROOT/docs/model_corps_2026-07-06"
WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$WORK_DIR"' EXIT

[[ -f "$VENV_PY" ]] || { echo "ERROR: venv missing at $VENV_PY"; exit 1; }
mkdir -p "$ARCHIVE_DIR"

# role -> base tag, role -> temperature (low/deterministic for coder+interpreter,
# matching the archived aria-* models' own 0.1-0.15 convention; a little more room
# for orchestrator's tool-selection reasoning and reflector's honest prose)
declare -A BASE_MODEL=(
  [orchestrator]="qwen3:8b"
  [coder]="qwen2.5-coder:7b"
  [fast]="phi4-mini:3.8b"
  [reflector]="phi4-mini:3.8b"
  [interpreter]="phi4-mini:3.8b"
  [vision]="qwen3-vl:4b"
)
declare -A TEMPERATURE=(
  [orchestrator]="0.3"
  [coder]="0.15"
  [fast]="0.3"
  [reflector]="0.4"
  [interpreter]="0.15"
  [vision]="0.2"
)

echo "=== regen_model_corps: generating personas from mos_canon.py + GOD_TIER_STANDARD.md ==="

for role in orchestrator coder fast reflector interpreter vision; do
  base="${BASE_MODEL[$role]}"
  temp="${TEMPERATURE[$role]}"
  persona_file="$WORK_DIR/${role}.persona.txt"
  modelfile="$ARCHIVE_DIR/aria-${role}.Modelfile"

  "$VENV_PY" -c "
import sys
sys.path.insert(0, '$REPO_ROOT/src')
from sovereign_agent.model_corps import build_role_persona
sys.stdout.write(build_role_persona('$role'))
" > "$persona_file"

  {
    echo "FROM $base"
    echo
    echo "SYSTEM \"\"\""
    cat "$persona_file"
    echo "\"\"\""
    echo
    echo "PARAMETER temperature $temp"
    echo "PARAMETER num_ctx 16384"
  } > "$modelfile"

  echo "→ aria-${role}  (FROM ${base}, temp=${temp})"
  ollama create "aria-${role}" -f "$modelfile"
done

echo "=== done. Archived Modelfiles: $ARCHIVE_DIR ==="
ollama list | grep '^aria-' || true
