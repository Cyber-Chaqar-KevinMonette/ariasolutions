#!/usr/bin/env bash
# apply_unverified_claims.sh — install the claim/proof gap detector and wire
# it into review_journal's README as an additive section.
#
# Sourced from long-running-agent-main (MIT, hardware-liberation zip corpus):
# "never trust the model's say-so, only real test/lint/build results."
# Aria's subtask completion (agent_session.py) marks `done` from the model's
# own loop_result.ok with no independent check. This module doesn't touch
# that gate (deliberately, same precedent as aria-review-journal shipping
# its library before the session-close-out hook) — it adds a second,
# independent honesty check to the review doc: does a subtask's own
# result_summary claim verification that its own trace never performed?
#
# guard → backup dir → copy payload → py_compile → patch review_journal →
# copy tests → run tests.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-unverified-claims"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"
TARGET="$REPO_ROOT/src/sovereign_agent/unverified_claims.py"
RJ_INIT="$REPO_ROOT/src/sovereign_agent/review_journal/__init__.py"

echo "=== aria-unverified-claims apply ==="
if pgrep -f "sovereign cockpit" >/dev/null 2>&1; then echo "ERROR: cockpit running. Stop it first."; exit 1; fi
[[ -f "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }
[[ -f "$RJ_INIT" ]] || { echo "ERROR: review_journal/__init__.py not found — apply aria-review-journal first."; exit 1; }
mkdir -p "$BACKUP_DIR"
cp "$RJ_INIT" "$BACKUP_DIR/__init__.py.bak"

cp "$STAGING/payload/src/sovereign_agent/unverified_claims.py" "$TARGET"

echo "→ Compile check..."; "$VENV_PY" -m py_compile "$TARGET"

echo "→ Patching review_journal/__init__.py (idempotent)..."
"$VENV_PY" - "$RJ_INIT" <<'PYEOF'
import sys
path = sys.argv[1]
text = open(path, encoding="utf-8").read()
marker = "unverified-claims-section-d"
if marker in text:
    print("  already patched, skipping.")
else:
    anchor = '    lines.append("## How to inspect it")'
    if anchor not in text:
        raise SystemExit("ERROR: anchor line not found — review_journal.py has drifted, patch manually.")
    insert = (
        '    # unverified-claims-section-d — an independent honesty check next\n'
        '    # to the sentinel warnings: does a subtask\'s own result_summary\n'
        '    # claim verification its own trace never performed? Best-effort;\n'
        '    # a missing/broken module must never break the review itself.\n'
        '    try:\n'
        '        from sovereign_agent.unverified_claims import render_unverified_claims_section\n'
        '        lines.append(render_unverified_claims_section(subs, actions))\n'
        '    except Exception:  # noqa: BLE001\n'
        '        pass\n\n'
        + anchor
    )
    text = text.replace(anchor, insert, 1)
    open(path, "w", encoding="utf-8").write(text)
    print("  patched.")
PYEOF

echo "→ Compile check (review_journal)..."; "$VENV_PY" -m py_compile "$RJ_INIT"

cp "$STAGING/tests/test_unverified_claims.py" "$REPO_ROOT/tests/"
echo "→ Running tests..."
"$VENV_PY" -m pytest "$REPO_ROOT/tests/test_unverified_claims.py" -q
if [[ -f "$REPO_ROOT/tests/test_review_journal.py" ]]; then
  "$VENV_PY" -m pytest "$REPO_ROOT/tests/test_review_journal.py" -q
fi

echo "=== aria-unverified-claims applied. Reversible: restore $BACKUP_DIR/__init__.py.bak over review_journal/__init__.py, and remove $TARGET + its test. 💛 ==="
