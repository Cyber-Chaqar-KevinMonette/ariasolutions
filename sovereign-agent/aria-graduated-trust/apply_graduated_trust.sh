#!/usr/bin/env bash
# apply_graduated_trust.sh — FABLE II M7: graduated trust (hold-and-continue at Gate 4).
# guard → backup → copy trust_wing payload → patch 5 code files + 2 doc files
# → compile → tests (0 skips expected post-patch) → related suites.
#
# Tool registration: this module ships no tools/ payload — nothing for
# path_scan's ships-tools/no-registration check to flag.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-graduated-trust"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
SRC="$REPO_ROOT/src/sovereign_agent"

echo "=== aria-graduated-trust apply ==="
if pgrep -fa "sovereign cockpit" | grep -qv "pgrep\|bash -c\|for i in"; then echo "ERROR: cockpit running. Stop it first."; exit 1; fi
[[ -f "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
mkdir -p "$BACKUP_DIR"
for rel in agent_session.py cli.py cockpit/app.py proving_ground/runner.py loop.py; do
  mkdir -p "$BACKUP_DIR/$(dirname "$rel")"
  cp "$SRC/$rel" "$BACKUP_DIR/$rel.bak"
done
mkdir -p "$BACKUP_DIR/handoff"
cp "$REPO_ROOT/handoff/02_SAFETY_MODEL.md" "$BACKUP_DIR/handoff/02_SAFETY_MODEL.md.bak"
cp "$REPO_ROOT/CLAUDE.md" "$BACKUP_DIR/CLAUDE.md.bak"

# 1. the trust wing payload
cp "$STAGING/payload/src/sovereign_agent/proving_ground/trust_wing.py" "$SRC/proving_ground/"

# 2. anchored, idempotent code patches
"$VENV_PY" - "$STAGING" "$SRC" <<'PYEOF'
import sys
from pathlib import Path
staging, src = Path(sys.argv[1]), Path(sys.argv[2])
sys.path.insert(0, str(staging))
from patcher import ALL_PATCHES
for rel, fn in ALL_PATCHES.items():
    path = src / rel
    text = path.read_text(encoding="utf-8")
    new, changed = fn(text)
    if changed:
        path.write_text(new, encoding="utf-8"); print(f"  ✓ {rel}")
    else:
        print(f"  SKIP {rel} (already patched)")
PYEOF

# 3. doctrine text — same words, one place each
"$VENV_PY" - "$STAGING" "$REPO_ROOT" <<'PYEOF'
import sys
from pathlib import Path
staging, repo = Path(sys.argv[1]), Path(sys.argv[2])
sys.path.insert(0, str(staging))
from patcher import DOC_PATCHES
for rel, fn in DOC_PATCHES.items():
    path = repo / rel
    text = path.read_text(encoding="utf-8")
    new, changed = fn(text)
    if changed:
        path.write_text(new, encoding="utf-8"); print(f"  ✓ {rel}")
    else:
        print(f"  SKIP {rel} (already patched)")
PYEOF

echo "→ Compile check..."
"$VENV_PY" -m py_compile "$SRC/agent_session.py" "$SRC/cli.py" "$SRC/cockpit/app.py" \
  "$SRC/proving_ground/runner.py" "$SRC/proving_ground/trust_wing.py" "$SRC/loop.py"
"$VENV_PY" -c "
from sovereign_agent import cli
assert hasattr(cli, 'session_app')
print('  ✓ sov session sub-app registered')"

# 4. promote the live tests + run them; post-patch this file must run with
#    ZERO skips (the skips only exist pre-apply)
cp "$STAGING/tests/test_graduated_trust_live.py" "$REPO_ROOT/tests/"
"$VENV_PY" -m pytest "$REPO_ROOT/tests/test_graduated_trust_live.py" -q -rs | tee /tmp/graduated_trust_pytest.out
if grep -q "SKIPPED" /tmp/graduated_trust_pytest.out; then
  echo "ERROR: post-apply skips remain — a patch did not land."; exit 1
fi
"$VENV_PY" -m pytest "$REPO_ROOT/tests/test_agent_session.py" \
  "$REPO_ROOT/tests/test_proving_ground_live.py" \
  "$REPO_ROOT/tests/test_cli.py" -q
echo "→ one real v3 offline proving run against the live data dir..."
"$VENV_PY" -m sovereign_agent.proving_ground offline
echo "=== aria-graduated-trust applied. Reversible: backups at $BACKUP_DIR 💛 ==="
