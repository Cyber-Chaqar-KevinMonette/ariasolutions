#!/usr/bin/env bash
# apply_template.sh — the CANONICAL apply-script skeleton for staged aria-* modules.
# This is the reference shape (constitution/tribunal follow it). `new_module.sh` instantiates it,
# substituting cloud-persona (kebab-case id) and cloud_persona (the payload subpackage, if any).
#
# Anatomy every apply script shares:
#   guard (cockpit stopped + venv present) → backup touched files → copy payload → patch registration
#   (anchored, idempotent) → py_compile → copy tests → run tests.  Reversible: backups under <module>/backups.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-cloud-persona"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"; TOOLS_INIT="$REPO_ROOT/src/sovereign_agent/tools/__init__.py"

echo "=== aria-cloud-persona apply ==="
if pgrep -af "cockpit" 2>/dev/null | grep -E "bin/sovereign cockpit|sovereign_agent.*cockpit|[s]overeign cockpit" | grep -vE "pgrep|grep|apply_|bash -c" >/dev/null; then echo "ERROR: cockpit running. Stop it first."; exit 1; fi
[[ -f "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
mkdir -p "$BACKUP_DIR"; cp "$TOOLS_INIT" "$BACKUP_DIR/tools_init.py.bak"

# 1. copy the cloud_persona package, and replace cloud_client.py (original backed up first)
CLOUD_CLIENT="$REPO_ROOT/src/sovereign_agent/cloud_client.py"
cp "$CLOUD_CLIENT" "$BACKUP_DIR/cloud_client.py.bak"
mkdir -p "$REPO_ROOT/src/sovereign_agent/cloud_persona"
cp "$STAGING"/payload/src/sovereign_agent/cloud_persona/*.py "$REPO_ROOT/src/sovereign_agent/cloud_persona/"
cp "$STAGING/payload/src/sovereign_agent/cloud_client.py" "$CLOUD_CLIENT"
# (no tool registration — this module conditions cloud calls; it ships no tools)

echo "→ Compile check..."; "$VENV_PY" -m py_compile "$REPO_ROOT"/src/sovereign_agent/cloud_persona/*.py "$CLOUD_CLIENT" || \
  { echo "APPLY-FAIL: compile error — restoring cloud_client.py"; cp "$BACKUP_DIR/cloud_client.py.bak" "$CLOUD_CLIENT"; exit 1; }
# test file is named by PKG (new_module.sh writes test_<PKG>.py), NOT slug —
# they differ for every kebab-case slug, so referencing cloud-persona here silently
# skipped the copy + ran pytest on a missing file (hardened 2026-07-19).
[[ -f "$STAGING/tests/test_cloud_persona.py" ]] && cp "$STAGING/tests/test_cloud_persona.py" "$REPO_ROOT/tests/"
echo "Running tests..."; "$VENV_PY" -m pytest "$REPO_ROOT"/tests/test_cloud_persona.py $(ls "$REPO_ROOT"/tests/test_cloud*.py | grep -v test_cloud_persona) -q || \
  { echo "APPLY-FAIL: applied tests did not pass — restoring cloud_client.py"; cp "$BACKUP_DIR/cloud_client.py.bak" "$CLOUD_CLIENT"; exit 1; }
echo "=== aria-cloud-persona applied. Reversible: backups at $BACKUP_DIR 💛 ==="
