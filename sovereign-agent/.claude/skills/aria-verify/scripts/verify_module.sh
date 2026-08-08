#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
#  verify_module.sh aria-<slug> — full pre-apply verification.
#
#  Was documented in SKILL.md since this skill's creation but never actually
#  built. Built live 2026-08-03 after discovering the gap while verifying
#  aria-game-dev-helpers by hand.
#
#  Runs, in order:
#    1. py_compile every payload .py file
#    2. staged-only check — no payload file already exists at its target
#       path in live src/
#    3. apply-script registration check — if the module ships tools/*.py,
#       confirm the apply script actually patches tools/__init__.py
#    4. the module's real pytest suite, via a DISPOSABLE git worktree:
#       apply the module into a throwaway worktree (never the real repo),
#       run pytest there with PYTHONPATH pointed at the worktree's src/ so
#       imports resolve to the worktree's copy, then delete the worktree.
#       This is the only way to genuinely test a tools-shipping module
#       pre-apply — its own tests import from live sovereign_agent.tools.X,
#       which doesn't exist until applied (same pattern aria-screenshot's
#       tests already use).
#
#  Reports PASS/FAIL per step. Any FAIL stops before the next step.
# ═══════════════════════════════════════════════════════════════════════════
set -uo pipefail
MODULE="${1:-}"
[[ -n "$MODULE" ]] || { echo "usage: $0 aria-<slug>"; exit 1; }

ROOT="$PWD"
if [[ ! -f "$ROOT/src/sovereign_agent/cli.py" ]]; then
  d="$PWD"
  while [[ "$d" != "/" ]]; do
    [[ -f "$d/src/sovereign_agent/cli.py" ]] && { ROOT="$d"; break; }
    d="$(dirname "$d")"
  done
fi
[[ -f "$ROOT/src/sovereign_agent/cli.py" ]] || { echo "✗ run from repo root"; exit 1; }

MODULE_DIR="$ROOT/$MODULE"
[[ -d "$MODULE_DIR" ]] || { echo "✗ $MODULE_DIR not found"; exit 1; }

PASS=1
step(){ echo; echo "◊ $1"; }
ok(){ echo "  ✓ $1"; }
fail(){ echo "  ✗ $1"; PASS=0; }

# ── 1. py_compile ────────────────────────────────────────────────────────
step "py_compile payload"
PAYLOAD_FILES=$(find "$MODULE_DIR/payload" "$MODULE_DIR/tests" -name '*.py' 2>/dev/null)
if [[ -z "$PAYLOAD_FILES" ]]; then
  fail "no .py files found under payload/ or tests/"
else
  if python3 -m py_compile $PAYLOAD_FILES 2>&1; then
    ok "compiles ($(echo "$PAYLOAD_FILES" | wc -l) files)"
  else
    fail "compile error above"
  fi
fi
[[ "$PASS" == 1 ]] || { echo; echo "✗ FAIL — fix compile errors before continuing"; exit 1; }

# ── 2. staged-only ────────────────────────────────────────────────────────
step "staged-only (payload files must not already exist in live src/)"
LEAK=0
while IFS= read -r f; do
  rel="${f#"$MODULE_DIR"/payload/}"
  target="$ROOT/$rel"
  if [[ -f "$target" ]]; then
    fail "already live: $rel"
    LEAK=1
  fi
done < <(find "$MODULE_DIR/payload" -name '*.py' 2>/dev/null)
[[ "$LEAK" == 0 ]] && ok "no payload file exists in live src/ yet"

# ── 3. apply script registers tools ──────────────────────────────────────
step "apply script patches tool registration (if module ships tools)"
TOOL_FILES=$(find "$MODULE_DIR/payload/src/sovereign_agent/tools" -name '*.py' ! -name '.gitkeep' 2>/dev/null)
APPLY_SCRIPT=$(find "$MODULE_DIR" -maxdepth 1 -name 'apply_*.sh' | head -1)
if [[ -z "$TOOL_FILES" ]]; then
  ok "module ships no tools — nothing to register"
elif [[ -z "$APPLY_SCRIPT" ]]; then
  fail "module ships tools but has no apply_*.sh script"
else
  if grep -q "__init__.py" "$APPLY_SCRIPT" && grep -q "__all__\|tools/__init__" "$APPLY_SCRIPT"; then
    ok "$(basename "$APPLY_SCRIPT") patches tools/__init__.py"
  else
    fail "$(basename "$APPLY_SCRIPT") doesn't appear to patch tools/__init__.py"
  fi
fi

[[ "$PASS" == 1 ]] || { echo; echo "✗ FAIL — fix the above before continuing to the pytest stage"; exit 1; }

# ── 4. real pytest suite, in a disposable worktree ───────────────────────
step "module pytest suite (disposable git worktree — real repo untouched)"
if [[ -z "$APPLY_SCRIPT" ]]; then
  ok "module ships no apply script — skipping isolated pytest run"
else
  WT_DIR="$(mktemp -d)/verify-worktree"
  cleanup(){ git -C "$ROOT" worktree remove --force "$WT_DIR" >/dev/null 2>&1; rm -rf "$(dirname "$WT_DIR")"; }
  trap cleanup EXIT

  # ROOT (sovereign-agent) may be a SUBDIRECTORY of the actual git root
  # (found live 2026-08-03: this repo's git root is its parent — a
  # monorepo). A worktree checks out the whole git root, so the project
  # lives at WT_DIR/<same relative offset>, not WT_DIR itself — using
  # WT_DIR directly here silently searched upward and hit the REAL repo
  # instead (see apply script's root-detect-safety-d fix). Compute the
  # same offset and use it explicitly, so a wrong path fails loudly via
  # the apply script's own explicit-root check rather than silently
  # resolving elsewhere.
  GIT_TOP="$(git -C "$ROOT" rev-parse --show-toplevel)"
  case "$ROOT" in
    "$GIT_TOP") WT_PROJECT_ROOT="$WT_DIR" ;;
    "$GIT_TOP"/*) WT_PROJECT_ROOT="$WT_DIR/${ROOT#"$GIT_TOP"/}" ;;
    *) fail "ROOT ($ROOT) is not under its own git top ($GIT_TOP) — can't compute worktree offset"; WT_PROJECT_ROOT="" ;;
  esac

  if [[ -z "$WT_PROJECT_ROOT" ]]; then
    : # already failed above
  elif ! git -C "$ROOT" worktree add --detach "$WT_DIR" HEAD >/dev/null 2>&1; then
    fail "could not create a disposable git worktree — is this a git repo with a commit?"
  else
    ok "worktree created at $WT_DIR (project root: $WT_PROJECT_ROOT)"
    if timeout 90 bash "$APPLY_SCRIPT" "$WT_PROJECT_ROOT" >/tmp/verify_apply.log 2>&1; then
      ok "apply script ran cleanly in the worktree"
      # Target ONLY this module's own test file(s) by basename — a
      # worktree checks out the WHOLE tests/ directory (every other
      # module's tests too), so a blanket test_*.py glob against it ran
      # the entire repo's test suite instead of just this module's
      # (found live 2026-08-03: looked like a hang, was actually a
      # multi-hundred-test real run).
      MODULE_TEST_ARGS=()
      for t in "$MODULE_DIR"/tests/test_*.py; do
        [[ -f "$t" ]] && MODULE_TEST_ARGS+=("$WT_PROJECT_ROOT/tests/$(basename "$t")")
      done
      # Trust the actual exit code (pipefail is set at the top of this
      # script), not a text-parsed summary line — found live 2026-08-03
      # that this repo's pytest config prints no "N passed" line under
      # -q at all when everything passes, which made a genuinely clean
      # run read as a false FAIL.
      if timeout 90 env PYTHONPATH="$WT_PROJECT_ROOT/src:${PYTHONPATH:-}" "$ROOT/.venv/bin/python" -m pytest \
          "${MODULE_TEST_ARGS[@]}" -q --rootdir="$WT_PROJECT_ROOT" 2>&1 | tee /tmp/verify_pytest.log | tail -20; then
        ok "pytest suite passed in isolation"
      else
        fail "pytest suite failed or errored — see /tmp/verify_pytest.log"
      fi
    else
      fail "apply script failed in the worktree — see /tmp/verify_apply.log"
      tail -30 /tmp/verify_apply.log
    fi
  fi
fi

echo
if [[ "$PASS" == 1 ]]; then
  echo "✓ PASS — $MODULE is ready to apply for real (see its apply_*.sh)"
  exit 0
else
  echo "✗ FAIL — see the ✗ lines above"
  exit 1
fi
