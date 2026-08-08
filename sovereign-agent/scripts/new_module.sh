#!/usr/bin/env bash
# new_module.sh <slug> [pkg] — scaffold a new staged aria-<slug>/ module from the canonical template.
#   slug : kebab-case id (e.g. "memory-garden")           pkg : payload subpackage dir (default: <slug_underscored>)
# Creates: payload tree, apply script (from scripts/lib/apply_template.sh), conftest (shared helper),
# test stub, README stub. Reversible: just delete the folder. Never touches live src/.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
SLUG="${1:-}"; [[ -z "$SLUG" ]] && { echo "usage: new_module.sh <slug> [pkg]"; exit 2; }
PKG="${2:-${SLUG//-/_}}"
MOD="$REPO_ROOT/aria-$SLUG"
[[ -e "$MOD" ]] && { echo "ERROR: aria-$SLUG already exists"; exit 2; }

mkdir -p "$MOD/payload/src/sovereign_agent/$PKG" "$MOD/tests"

# payload package init
cat > "$MOD/payload/src/sovereign_agent/$PKG/__init__.py" <<EOF
"""$PKG — (describe what this module gives Aria). Staged; applied via apply_$PKG.sh."""
from __future__ import annotations
EOF

# conftest — uses the shared helper (no reinvention)
cat > "$MOD/tests/conftest.py" <<'EOF'
"""Test-only path shim via the shared helper (scripts/lib/aria_conftest)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts" / "lib"))
from aria_conftest import extend_paths  # noqa: E402

extend_paths(Path(__file__).parent.parent)
EOF

# test stub
cat > "$MOD/tests/test_$PKG.py" <<EOF
"""Tests for aria-$SLUG."""
from __future__ import annotations


def test_package_imports():
    import sovereign_agent.$PKG  # noqa: F401
    assert True   # replace with real behavior tests (prove it WORKS, not just imports)
EOF

# README stub
cat > "$MOD/README.md" <<EOF
# aria-$SLUG — (one-line purpose)

> What it gives Aria, honestly. Propose-only / reversible / staged.

## Payload
- \`src/sovereign_agent/$PKG/\` — (describe)

## Verify / Apply
\`\`\`bash
./scripts/verify_module.sh aria-$SLUG     # before apply
./aria-$SLUG/apply_$PKG.sh                 # cockpit stopped
\`\`\`
EOF

# apply script from the canonical template
sed -e "s/@@SLUG@@/$SLUG/g" -e "s/@@PKG@@/$PKG/g" \
    "$REPO_ROOT/scripts/lib/apply_template.sh" > "$MOD/apply_$PKG.sh"
chmod +x "$MOD/apply_$PKG.sh"

echo "✓ scaffolded aria-$SLUG  (pkg=$PKG)"
echo "  payload: aria-$SLUG/payload/src/sovereign_agent/$PKG/"
echo "  next: build the payload + real tests, then ./scripts/verify_module.sh aria-$SLUG"
