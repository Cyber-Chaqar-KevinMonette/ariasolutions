#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
#  new_module.sh <slug> [pkg] — scaffold a staged aria-<slug>/ module.
#
#  Was documented in SKILL.md since this skill's creation but never actually
#  built — every real staged module (aria-screenshot, aria-game-dev-helpers,
#  ...) was hand-scaffolded instead. Built live 2026-08-03 from those two as
#  the real, proven template, not from the SKILL.md prose alone.
#
#  Usage:
#    ./scripts/new_module.sh game-dev-helpers game_dev_helpers
#
#  Creates aria-<slug>/:
#    payload/src/sovereign_agent/tools/   — put new tool .py files here
#    tests/test_<pkg>.py                  — stub test file to fill in
#    apply_<pkg>.sh                       — from scripts/lib/apply_template.sh,
#                                            TOOL_FILES/IMPORTS TODOs left for
#                                            you to fill in once tools exist
#    README.md                            — one-paragraph stub
#
#  Matches the proven shape of aria-screenshot (single tool) and
#  aria-game-dev-helpers (multiple tools) — both real, applied modules.
# ═══════════════════════════════════════════════════════════════════════════
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

SLUG="${1:-}"
PKG="${2:-${SLUG//-/_}}"

if [[ -z "$SLUG" ]]; then
  echo "usage: $0 <slug> [pkg]" >&2
  echo "  slug: kebab-case, e.g. 'game-dev-helpers' -> aria-game-dev-helpers/" >&2
  echo "  pkg:  snake_case package name, defaults to slug with - -> _" >&2
  exit 1
fi
if [[ ! "$SLUG" =~ ^[a-z0-9][a-z0-9-]*$ ]]; then
  echo "✗ slug must be kebab-case (lowercase, digits, hyphens): $SLUG" >&2
  exit 1
fi
if [[ ! "$PKG" =~ ^[a-z0-9_]+$ ]]; then
  echo "✗ pkg must be snake_case: $PKG" >&2
  exit 1
fi

ROOT="$PWD"
if [[ ! -f "$ROOT/src/sovereign_agent/cli.py" ]]; then
  d="$PWD"
  while [[ "$d" != "/" ]]; do
    [[ -f "$d/src/sovereign_agent/cli.py" ]] && { ROOT="$d"; break; }
    d="$(dirname "$d")"
  done
fi
[[ -f "$ROOT/src/sovereign_agent/cli.py" ]] || { echo "✗ run from repo root"; exit 1; }

MODULE_DIR="$ROOT/aria-$SLUG"
if [[ -e "$MODULE_DIR" ]]; then
  echo "✗ $MODULE_DIR already exists — pick a different slug or remove it first" >&2
  exit 1
fi

echo "◊ scaffolding aria-$SLUG (pkg: $PKG) at $MODULE_DIR"

mkdir -p "$MODULE_DIR/payload/src/sovereign_agent/tools"
mkdir -p "$MODULE_DIR/tests"

cat > "$MODULE_DIR/payload/src/sovereign_agent/tools/.gitkeep" <<'EOF'
Put new tool .py file(s) here (e.g. PKG_tool.py). Follow an existing tool
in src/sovereign_agent/tools/ for the Tool subclass shape: name, tier,
description (with FAILURE MODES:), failure_modes, Args (pydantic
BaseModel), async execute(). Reuse existing helpers (game_workspace_dir,
check_write_path, etc.) before writing new plumbing — see .claude/PLAYBOOK.md's
reuse map.
EOF

cat > "$MODULE_DIR/tests/test_${PKG}.py" <<EOF
"""Tests for ${PKG} — TODO: describe what this module does and the real
gap/bug it closes. Prove behavior WORKS, not just that it imports."""
from __future__ import annotations

import pytest


def test_${PKG}_tool_registered():
    # TODO: replace tool_name with the real registered tool name once
    # the payload exists, and uncomment.
    # import sovereign_agent.tools  # noqa: F401
    # from sovereign_agent.authority import _TIER_REGISTRY
    # assert "TOOL_NAME" in _TIER_REGISTRY
    pytest.skip("TODO: fill in once the payload tool exists")
EOF

cat > "$MODULE_DIR/README.md" <<EOF
# aria-$SLUG

TODO: one paragraph — what real gap/bug this closes, who asked for it and
why (name them), and what it delivers (tool name(s), tier(s)).

## Apply

\`\`\`bash
./apply_${PKG}.sh
.venv/bin/python -m pytest tests/test_${PKG}.py -v
\`\`\`
EOF

sed -e "s/__PKG__/${PKG}/g" \
    "$HERE/lib/apply_template.sh" > "$MODULE_DIR/apply_${PKG}.sh"
chmod +x "$MODULE_DIR/apply_${PKG}.sh"

echo "  ✓ payload/src/sovereign_agent/tools/ (empty — add tool files here)"
echo "  ✓ tests/test_${PKG}.py (stub — fill in)"
echo "  ✓ apply_${PKG}.sh (template — fill in TOOL_FILES/IMPORTS TODOs)"
echo "  ✓ README.md (stub — fill in)"
echo
echo "Next: write the real payload, fill in the test stub and the apply"
echo "script's TODOs, then run:"
echo "  ./.claude/skills/aria-verify/scripts/verify_module.sh aria-$SLUG"
