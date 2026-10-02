#!/usr/bin/env bash
# apply_template.sh — the CANONICAL apply-script skeleton for staged aria-* modules.
# This is the reference shape (constitution/tribunal follow it). `new_module.sh` instantiates it,
# substituting mcp-remote-guard (kebab-case id) and mcp_guard (the payload subpackage, if any).
#
# Anatomy every apply script shares:
#   guard (cockpit stopped + venv present) → backup touched files → copy payload → patch registration
#   (anchored, idempotent) → py_compile → copy tests → run tests.  Reversible: backups under <module>/backups.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-mcp-remote-guard"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"; TOOLS_INIT="$REPO_ROOT/src/sovereign_agent/tools/__init__.py"

echo "=== aria-mcp-remote-guard apply ==="
if pgrep -af "cockpit" 2>/dev/null | grep -E "bin/sovereign cockpit|sovereign_agent.*cockpit|[s]overeign cockpit" | grep -vE "pgrep|grep|apply_|bash -c" >/dev/null; then echo "ERROR: cockpit running. Stop it first."; exit 1; fi
[[ -f "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
mkdir -p "$BACKUP_DIR"; cp "$TOOLS_INIT" "$BACKUP_DIR/tools_init.py.bak"

# 1. copy the mcp_guard package, and replace mcp_server.py (original backed up first)
MCP_SERVER="$REPO_ROOT/src/sovereign_agent/mcp_server.py"
cp "$MCP_SERVER" "$BACKUP_DIR/mcp_server.py.bak"
mkdir -p "$REPO_ROOT/src/sovereign_agent/mcp_guard"
cp "$STAGING"/payload/src/sovereign_agent/mcp_guard/*.py "$REPO_ROOT/src/sovereign_agent/mcp_guard/"
cp "$STAGING/payload/src/sovereign_agent/mcp_server.py" "$MCP_SERVER"
# (no tool registration — this module ships no Aria tools; it guards the MCP bridge)

echo "→ Compile check..."; "$VENV_PY" -m py_compile "$REPO_ROOT"/src/sovereign_agent/mcp_guard/*.py "$MCP_SERVER" || \
  { echo "APPLY-FAIL: compile error — restoring mcp_server.py"; cp "$BACKUP_DIR/mcp_server.py.bak" "$MCP_SERVER"; exit 1; }
# test file is named by PKG (new_module.sh writes test_<PKG>.py), NOT slug —
# they differ for every kebab-case slug, so referencing mcp-remote-guard here silently
# skipped the copy + ran pytest on a missing file (hardened 2026-07-19).
[[ -f "$STAGING/tests/test_mcp_guard.py" ]] && cp "$STAGING/tests/test_mcp_guard.py" "$REPO_ROOT/tests/"
echo "Running tests..."; "$VENV_PY" -m pytest "$REPO_ROOT"/tests/test_mcp_guard.py "$REPO_ROOT"/tests/test_mcp_server.py -q || \
  { echo "APPLY-FAIL: applied tests did not pass — restoring mcp_server.py"; cp "$BACKUP_DIR/mcp_server.py.bak" "$MCP_SERVER"; exit 1; }
echo "=== aria-mcp-remote-guard applied. Reversible: backups at $BACKUP_DIR 💛 ==="
