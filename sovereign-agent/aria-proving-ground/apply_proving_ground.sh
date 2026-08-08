#!/usr/bin/env bash
# apply_proving_ground.sh — Fable F3: the first place her scores are written down.
#
# 2026-08-02 (index-the-project pass): this module's v1 payload has been
# superseded live by 7 later wing modules (memory/trust/quality/grounding/
# wellbeing/integrity/timeout — SUITE_VERSION now v8) that each extend
# proving_ground/runner.py in place. The wildcard `cp .../*.py` below would
# silently overwrite runner.py with the stale v1 version, deleting every
# wing's integration. Refuse to run if that's the live state — the module's
# only remaining unapplied artifact is its own test file, already placed
# directly at tests/test_proving_ground_live.py (isolated with tmp_path,
# fixing a pre-existing test-order bug where it wrote into the real
# production results.ndjson).
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-proving-ground"
VENV_PY="$REPO_ROOT/.venv/bin/python"
SRC="$REPO_ROOT/src/sovereign_agent"
if pgrep -fa "sovereign cockpit" | grep -qv "pgrep\|bash -c\|for i in"; then echo "ERROR: cockpit running."; exit 1; fi
if grep -q '^SUITE_VERSION = "v1"$' "$SRC/proving_ground/runner.py" 2>/dev/null; then
  : # live is still v1 — genuinely safe to apply this payload wholesale
else
  echo "✗ refusing: live proving_ground/runner.py is past v1 (later wing modules extend it in place)."
  echo "  This module's own payload is stale and would delete those wings if copied over."
  echo "  Its test file is already placed at tests/test_proving_ground_live.py — nothing else to apply."
  exit 1
fi
mkdir -p "$SRC/proving_ground"
cp "$STAGING"/payload/src/sovereign_agent/proving_ground/*.py "$SRC/proving_ground/"
for f in "$SRC"/proving_ground/*.py; do "$VENV_PY" -m py_compile "$f"; done
cp "$STAGING/tests/test_proving_ground_live.py" "$REPO_ROOT/tests/"
"$VENV_PY" -m pytest "$REPO_ROOT/tests/test_proving_ground_live.py" -q
echo "→ one real offline run against the live data dir..."
"$VENV_PY" -m sovereign_agent.proving_ground offline
echo "=== aria-proving-ground applied 💛 ==="
