#!/usr/bin/env bash
# apply.sh — the apply system's front door, with bookkeeping.
#
# Kevin's ask: the apply system should not apply something more than once
# unless a newer version / invariant / update. This wrapper computes a
# content fingerprint of the module and consults the apply-ledger BEFORE
# running the module's own apply_*.sh:
#   - never applied, or content changed  → apply, then record
#   - already applied, identical content → SKIP (no-op)
#   - --force                            → apply anyway, then record
#
# Usage: ./scripts/apply.sh aria-<name> [--force]
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
VENV_PY="$REPO_ROOT/.venv/bin/python"

MODULE="${1:-}"; FORCE_FLAG="${2:-}"
[[ -z "$MODULE" ]] && { echo "usage: ./scripts/apply.sh aria-<name> [--force]"; exit 2; }
MODULE="${MODULE%/}"                    # strip trailing slash
MOD_DIR="$REPO_ROOT/$MODULE"
[[ -d "$MOD_DIR" ]] || { echo "ERROR: no such module dir: $MOD_DIR"; exit 1; }
[[ -f "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }

APPLY_SCRIPT="$(ls "$MOD_DIR"/apply_*.sh 2>/dev/null | head -1 || true)"
[[ -n "$APPLY_SCRIPT" ]] || { echo "ERROR: no apply_*.sh in $MODULE"; exit 1; }

FORCE_ARGS=()
[[ "$FORCE_FLAG" == "--force" ]] && FORCE_ARGS=(--force)

# Decide via the ledger (exit 0 = apply, exit 10 = skip-unchanged).
set +e
REASON="$("$VENV_PY" -m sovereign_agent.apply_ledger decide "$MODULE" "$MOD_DIR" "${FORCE_ARGS[@]}")"
DECIDE_RC=$?
set -e
if [[ $DECIDE_RC -eq 10 ]]; then
  echo "✓ $MODULE already applied (unchanged) — nothing to do. Use --force to re-apply."
  exit 0
fi
echo "→ applying $MODULE (reason: ${REASON:-apply})"

# Run the module's own apply script.
bash "$APPLY_SCRIPT"

# Record the successful apply (fingerprint + timestamp).
VERSION="$("$VENV_PY" -c "import sovereign_agent as s; print(getattr(s,'__version__',''))" 2>/dev/null || true)"
"$VENV_PY" -m sovereign_agent.apply_ledger record "$MODULE" "$MOD_DIR" "$VERSION"
echo "✓ $MODULE applied and recorded in the apply-ledger."
