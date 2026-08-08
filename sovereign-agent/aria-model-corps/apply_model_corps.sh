#!/usr/bin/env bash
# apply_model_corps.sh — Model Corps round MC1+MC2: the shared god-tier persona
# generator (model_corps.persona) + the regen script that turns it into real,
# licensed, open-weight Ollama models for every role.
#
# guard (cockpit stopped + venv present) → backup touched files → copy payload
# → py_compile → copy+run tests → copy regen_model_corps.sh into scripts/ →
# RUN it (generates + `ollama create`s all 6 aria-<role> models).
#
# Deliberately does NOT touch .bashrc or config.py here — that's a separate,
# explicit step (see the plan) so a bad pull/persona bug never breaks the live
# cockpit mid-apply. Reversible: backups under aria-model-corps/backups/.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-model-corps"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"

echo "=== aria-model-corps apply ==="
if pgrep -f "sovereign cockpit" >/dev/null 2>&1; then echo "ERROR: cockpit running. Stop it first."; exit 1; fi
[[ -f "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
mkdir -p "$BACKUP_DIR"

# 1. copy payload package (new module, nothing to back up — src/sovereign_agent/model_corps/ doesn't exist yet)
mkdir -p "$REPO_ROOT/src/sovereign_agent/model_corps"
cp "$STAGING"/payload/src/sovereign_agent/model_corps/*.py "$REPO_ROOT/src/sovereign_agent/model_corps/"

echo "→ Compile check..."
"$VENV_PY" -m py_compile "$REPO_ROOT"/src/sovereign_agent/model_corps/*.py

# 2. promote + run tests
cp "$STAGING/tests/test_model_corps.py" "$REPO_ROOT/tests/"
echo "→ Running tests..."
"$VENV_PY" -m pytest "$REPO_ROOT/tests/test_model_corps.py" -q

# 3. install + run the regen script (this is what actually creates the aria-<role> models)
cp "$STAGING/payload/scripts/regen_model_corps.sh" "$REPO_ROOT/scripts/regen_model_corps.sh"
chmod +x "$REPO_ROOT/scripts/regen_model_corps.sh"
echo "→ Generating Modelfiles + running ollama create for all 6 roles..."
"$REPO_ROOT/scripts/regen_model_corps.sh"

echo "=== aria-model-corps applied. Reversible: backups at $BACKUP_DIR 💛 ==="
echo "→ .bashrc / config.py NOT touched yet — that is the next, separate step"
echo "  (swap env vars only after these new aria-<role> models are smoke-tested)."
