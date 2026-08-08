#!/usr/bin/env bash
# apply_realestate_geo.sh — wire sale-date urgency into the live poll loop.
#
# pre-foreclosure-d (Kevin, 2026-08-03): a county foreclosure listing whose
# sale date has PASSED is not a lead. Measured live: 10 of 13 listings on the
# county pages were for a sale a week gone. This ships the filter + the
# countdown label that makes the remaining ones actionable.
#
# guard (cockpit stopped + venv) → backup → copy payload → patch (anchored,
# idempotent) → py_compile → run tests.  Reversible: backups under backups/.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-realestate-geo"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
PKG="$STAGING/payload/src/sovereign_agent/realestate_geo"

echo "=== aria-realestate-geo apply ==="
if pgrep -af "cockpit" 2>/dev/null | grep -E "bin/sovereign cockpit|sovereign_agent.*cockpit|[s]overeign cockpit" | grep -vE "pgrep|grep|apply_|bash -c" >/dev/null; then
  echo "ERROR: cockpit running. Stop it first."; exit 1; fi
[[ -f "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }

mkdir -p "$BACKUP_DIR"
cp "$REPO_ROOT/src/sovereign_agent/discord_runtime/runtime.py" "$BACKUP_DIR/runtime.py.bak"
echo "→ backed up runtime.py to $BACKUP_DIR"

# 1. the urgency module, named to match its real_estate_* siblings in src/
cp "$PKG/sale_urgency.py" "$REPO_ROOT/src/sovereign_agent/real_estate_sale_urgency.py"
echo "→ installed real_estate_sale_urgency.py"

# 2. wire it into poll_once() (anchored + idempotent; refuses to guess)
"$VENV_PY" "$PKG/patches.py" "$REPO_ROOT/src/sovereign_agent"

# 3. prove it still compiles
"$VENV_PY" -m py_compile \
  "$REPO_ROOT/src/sovereign_agent/real_estate_sale_urgency.py" \
  "$REPO_ROOT/src/sovereign_agent/discord_runtime/runtime.py"
echo "→ compile OK"

# 4. tests — the module's own, plus the runtime suite it just modified
cp "$STAGING/tests/test_sale_urgency.py" "$REPO_ROOT/tests/"
"$VENV_PY" -m pytest "$REPO_ROOT/tests/test_sale_urgency.py" \
                     "$REPO_ROOT/tests/test_discord_runtime.py" -q \
  || { echo "APPLY-FAIL: tests did not pass — restore from $BACKUP_DIR"; exit 1; }

echo "=== applied. Reversible: backups at $BACKUP_DIR 💛 ==="
echo "next: systemctl --user restart aria-duty.service   (picks up the change)"
