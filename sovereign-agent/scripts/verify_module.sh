#!/usr/bin/env bash
# verify_module.sh <aria-module-folder> — verify a STAGED module end-to-end (before apply).
#   1. py_compile the payload   2. run the module's tests   3. confirm live src/ untouched
#   4. confirm tool/sentinel registration anchors are present in the payload
# Read-only: never mutates anything. Exit non-zero if any check fails.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
VENV_PY="$REPO_ROOT/.venv/bin/python"
MOD="${1:-}"
[[ -z "$MOD" ]] && { echo "usage: verify_module.sh <aria-module-folder>"; exit 2; }
MOD="${MOD%/}"
[[ -d "$MOD" ]] || { echo "ERROR: no such module folder: $MOD"; exit 2; }

fail=0
echo "── verifying staged module: $MOD ──"

# 1. compile
PAYLOAD="$MOD/payload/src/sovereign_agent"
if [[ -d "$PAYLOAD" ]]; then
  if find "$PAYLOAD" -name '*.py' -print0 | xargs -0 "$VENV_PY" -m py_compile 2>/tmp/_vm_compile.err; then
    echo "  ✓ py_compile clean"
  else
    echo "  ✗ py_compile FAILED:"; sed 's/^/      /' /tmp/_vm_compile.err; fail=1
  fi
else
  echo "  · no payload/ tree (doc/script-only module)"
fi

# 2. tests
if ls "$MOD"/tests/test_*.py >/dev/null 2>&1; then
  if "$VENV_PY" -m pytest "$MOD"/tests/ >/tmp/_vm_test.out 2>&1; then
    echo "  ✓ tests pass ($(grep -oE '[0-9]+ passed' /tmp/_vm_test.out | tail -1))"
  else
    echo "  ✗ tests FAILED:"; tail -8 /tmp/_vm_test.out | sed 's/^/      /'; fail=1
  fi
else
  echo "  · no tests/ (consider adding some)"
fi

# 3. live src/ untouched — FABLE II M9: a payload file that already EXISTS
#    live is not automatically a leak — a whole-file-replacement module
#    (the "whole NEW files, mirrored paths" convention also covers
#    REPLACING an existing file wholesale, e.g. aria-cache-crown's
#    cache.py, aria-git-flow's git_write.py) is EXPECTED to name a file
#    that's already live. The honest signal is CONTENT: identical bytes
#    means either a true accidental pre-copy or an already-applied
#    module (worth flagging); different bytes means a normal pending
#    replacement, not a leak.
if [[ -d "$PAYLOAD" ]]; then
  leaked=0; replacing=0
  while IFS= read -r -d '' f; do
    rel="${f#"$PAYLOAD"/}"
    live="src/sovereign_agent/$rel"
    if [[ -e "$live" ]]; then
      if cmp -s "$f" "$live"; then
        echo "      ! identical to live: $rel (already applied, or an accidental pre-copy?)"
        leaked=1
      else
        echo "      · replaces existing (content differs, not yet applied): $rel"
        replacing=1
      fi
    fi
  done < <(find "$PAYLOAD" -name '*.py' -print0)
  if [[ $leaked -eq 0 && $replacing -eq 0 ]]; then
    echo "  ✓ live src/ untouched (module is staged-only)"
  elif [[ $leaked -eq 0 ]]; then
    echo "  ✓ live src/ differs from payload (whole-file replacement, pending apply)"
  else
    echo "  ⚠ some payload files are BYTE-IDENTICAL to live (already applied?)"
  fi
fi

# 4. registration anchors present (if it ships tools) — checks the apply
#    script's OWN text AND (FABLE II M9) a sourced patcher.py, since the
#    newer convention composes anchors dynamically there (the anchor text
#    never appears literally in the .sh file itself).
if ls "$PAYLOAD"/tools/*_tools.py >/dev/null 2>&1; then
  anchor_found=0
  if ls "$MOD"/apply_*.sh >/dev/null 2>&1 && grep -q -- "-import-d" "$MOD"/apply_*.sh 2>/dev/null; then
    anchor_found=1
  elif [[ -f "$MOD/patcher.py" ]] && grep -q -- "-import-d" "$MOD/patcher.py" 2>/dev/null; then
    anchor_found=1
  fi
  if [[ $anchor_found -eq 1 ]]; then
    echo "  ✓ apply script patches tool registration (-import-d anchor)"
  else
    echo "  ⚠ ships tools but apply script may not register them (check -import-d / -all-d anchors)"
  fi
fi

[[ $fail -eq 0 ]] && echo "── VERIFY: PASS ──" || echo "── VERIFY: FAIL ──"
exit $fail
