#!/usr/bin/env bash
# safe_apply.sh <aria-module> [--yes] — apply ANY staged module SAFELY, regardless of the script's own guards.
# Wraps the module's apply_*.sh with god-tier guards so even the 97 scripts that lack them become safe:
#   1. cockpit-stopped guard   2. snapshot (git-based: every TRACKED file's exact content, dirty or not)
#   3. pre-apply Tribunal + 14-gen foresight gate   4. run the apply script
#   5. post-apply: module tests + floor_check   6. AUTO-ROLLBACK on any failure   7. report backup path
#
# FABLE II M9 (2026-07-05): the rollback used to restore only two hardcoded
# files (tools/__init__.py, stewardship/__init__.py) — any OTHER existing
# file an apply script patched in place (agent_session.py, cli.py, cockpit/
# app.py, loop.py, CLAUDE.md, handoff/*.md, …) was left mid-patched on a
# failed apply, three times in the FABLE II round alone (M6, M7, M8 — always
# caught by hand via each module's OWN backups/ dir, never by this script).
# The fix: `git stash create` snapshots EVERY tracked file's exact byte
# content (whatever it was — clean or already dirty from other in-flight
# work) as one commit-ish, without touching the working tree; on failure,
# `git checkout <snapshot> -- .` restores the whole tree to EXACTLY that
# state. This also means a dirty starting tree (mid-round, other modules'
# uncommitted work sitting there) is handled correctly by construction —
# no separate dirty-tree guard needed. New untracked files (freshly-copied
# payload/tests) are still tracked and removed the old way (git doesn't
# snapshot those into the stash commit).
set -uo pipefail

# step 0 — false-path / anti-ghost / anti-zombie gate  # path-scan-gate-d
SLUG="${1:-}"; SLUG="${SLUG#aria-}"
if [[ -n "$SLUG" ]] && [[ "${*}" != *--no-path-scan* ]]; then
  if ! "$(dirname "$0")/../.venv/bin/python" -m sovereign_agent.path_scan "$SLUG"; then
    echo "⛔ path-scan: blocking false/ghost path in aria-$SLUG (override: --no-path-scan)"; exit 1
  fi
fi
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
VENV_PY="$REPO_ROOT/.venv/bin/python"
MOD="${1:-}"; YES="${2:-}"
[[ -z "$MOD" ]] && { echo "usage: safe_apply.sh <aria-module> [--yes]"; exit 2; }
MOD="${MOD%/}"; MOD="$(basename "$MOD")"
[[ -d "$REPO_ROOT/$MOD" ]] || { echo "ERROR: no such module: $MOD"; exit 2; }
SCRIPT="$(ls "$REPO_ROOT/$MOD"/apply_*.sh 2>/dev/null | head -1)"
[[ -f "$SCRIPT" ]] || { echo "ERROR: no apply script in $MOD"; exit 2; }

# legacy fallback targets (kept as a belt-and-suspenders restore path if
# git itself is unavailable or not a repo — see rollback() below)
TOOLS_INIT="src/sovereign_agent/tools/__init__.py"
STEW_INIT="src/sovereign_agent/stewardship/__init__.py"
SNAP="$REPO_ROOT/$MOD/.safe_apply_snapshot"

echo "════════ SAFE-APPLY: $MOD ════════"

# 1. cockpit-stopped guard (enforced even if the script lacks it)
if pgrep -f "sovereign cockpit" >/dev/null 2>&1; then
  echo "⛔ cockpit is RUNNING — stop it before applying (safe_apply refuses to mutate live src beneath it)."; exit 1
fi
[[ -x "$VENV_PY" ]] || { echo "⛔ venv missing."; exit 1; }

# 2. snapshot for rollback
#    a) git-based (primary): a stash-create commit-ish captures every
#       TRACKED file's exact current bytes — dirty or clean — without
#       touching the working tree. `git stash create` returns empty when
#       the tree has no tracked changes at all; fall back to HEAD (the
#       worktree already equals HEAD in that case, so checking it out is
#       a correct no-op restore target).
rm -rf "$SNAP"; mkdir -p "$SNAP"
GIT_OK=0
if git rev-parse --git-dir >/dev/null 2>&1; then
  GIT_OK=1
  SNAPSHOT_COMMIT="$(git stash create 2>/dev/null || true)"
  [[ -z "$SNAPSHOT_COMMIT" ]] && SNAPSHOT_COMMIT="$(git rev-parse HEAD 2>/dev/null || true)"
  echo "$SNAPSHOT_COMMIT" > "$SNAP/snapshot_commit.txt"
fi
#    b) legacy fallback copies (used only if git restore fails below)
[[ -f "$TOOLS_INIT" ]] && cp "$TOOLS_INIT" "$SNAP/tools_init.bak"
[[ -f "$STEW_INIT" ]] && cp "$STEW_INIT" "$SNAP/stew_init.bak"
#    c) untracked-file bookkeeping (git checkout never touches these)
find src tests -name '*.py' 2>/dev/null | sort > "$SNAP/files_before.txt"
find src tests -type d 2>/dev/null | sort > "$SNAP/dirs_before.txt"
echo "  ✓ snapshot taken → $SNAP"

rollback() {
  echo "  ↩ ROLLING BACK…"
  local restored=0
  if [[ $GIT_OK -eq 1 && -s "$SNAP/snapshot_commit.txt" ]]; then
    local snap_commit; snap_commit="$(cat "$SNAP/snapshot_commit.txt")"
    # `git checkout <commit> -- .` restores CONTENT correctly but also
    # STAGES every restored path (it updates the index to match, which
    # differs from HEAD the same way the pre-apply dirty tree did). Follow
    # with `git reset -- .` to un-stage — content stays restored, staging
    # state returns to "unstaged changes vs HEAD" (this session's shape
    # throughout; a deliberately pre-staged file is the one narrow case
    # this doesn't perfectly preserve, and it only affects staging, never
    # content).
    if git checkout "$snap_commit" -- . 2>/dev/null; then
      git reset -- . >/dev/null 2>&1 || true
      echo "      restored every tracked file to its exact pre-apply content (git)"
      restored=1
    fi
  fi
  if [[ $restored -eq 0 ]]; then
    echo "      (git restore unavailable — falling back to the two-file legacy restore)"
    [[ -f "$SNAP/tools_init.bak" ]] && cp "$SNAP/tools_init.bak" "$TOOLS_INIT"
    [[ -f "$SNAP/stew_init.bak" ]] && cp "$SNAP/stew_init.bak" "$STEW_INIT"
  fi
  # remove files that appeared after the snapshot (newly-copied payload/tests
  # — git checkout above does not touch untracked files, so this still runs
  # even after a successful git-based restore)
  find src tests -name '*.py' 2>/dev/null | sort > "$SNAP/files_after.txt"
  comm -13 "$SNAP/files_before.txt" "$SNAP/files_after.txt" | while read -r f; do
    [[ -n "$f" ]] && rm -f "$f" && echo "      removed new file: $f"
  done
  # prune newly-created directories that weren't present before (deepest first), if now empty
  find src tests -type d 2>/dev/null | sort > "$SNAP/dirs_after.txt"
  comm -13 "$SNAP/dirs_before.txt" "$SNAP/dirs_after.txt" | sort -r | while read -r d; do
    [[ -n "$d" && -d "$d" ]] && rmdir "$d" 2>/dev/null && echo "      removed new dir: $d"
  done
  echo "  ↩ rollback complete — live src restored to pre-apply state."
}

# 3. pre-apply Tribunal + 14-gen foresight gate (advisory; human decides)
echo "  → pre-apply gate (Tribunal + 14-gen foresight)…"
if [[ -x scripts/pre_apply_gate.sh ]]; then
  if ! scripts/pre_apply_gate.sh "$MOD" >/tmp/_sa_gate.out 2>&1; then
    echo "  ⚠ gate flagged a concern:"; grep -E "VERDICT|risk:" /tmp/_sa_gate.out | head -4 | sed 's/^/      /'
    if [[ "$YES" != "--yes" ]]; then
      echo "  Re-run with --yes to apply anyway, or address the concern first."; exit 1
    fi
    echo "  (--yes given — proceeding despite the gate.)"
  else
    grep -E "GATE:" /tmp/_sa_gate.out | head -1 | sed 's/^/      /'
  fi
fi

# 4. run the apply script
echo "  → running $(basename "$SCRIPT")…"
if ! bash "$SCRIPT" >/tmp/_sa_apply.out 2>&1; then
  echo "  ✗ apply script FAILED:"; tail -8 /tmp/_sa_apply.out | sed 's/^/      /'
  rollback; echo "════════ SAFE-APPLY: FAILED + ROLLED BACK ════════"; exit 1
fi
echo "  ✓ apply script ran"

# 5. post-apply verification: module tests + floor
slug="${MOD#aria-}"; slug="${slug//-/_}"
testfile="tests/test_${slug}.py"
ok=1
if [[ -f "$testfile" ]]; then
  if "$VENV_PY" -m pytest "$testfile" -q >/tmp/_sa_test.out 2>&1; then
    echo "  ✓ module tests pass"
  else
    echo "  ✗ module tests FAILED:"; tail -6 /tmp/_sa_test.out | sed 's/^/      /'; ok=0
  fi
fi
if [[ -x scripts/floor_check.sh ]]; then
  scripts/floor_check.sh --quiet >/dev/null 2>&1 && echo "  ✓ floor still MET" || { echo "  ✗ floor regressed"; ok=0; }
fi

# quality-gate-d — quality gate: the .py files THIS apply actually touched (via
# the snapshot commit already written in step 2), scored for real. Rides
# the SAME rollback path as every other post-apply check — no new
# machinery, just a new signal feeding the existing `ok` variable.
if [[ -f "$SNAP/snapshot_commit.txt" && -f "$REPO_ROOT/scripts/lib/quality_gate.py" ]]; then
  changed_py=$(git diff --name-only "$(cat "$SNAP/snapshot_commit.txt")" -- '*.py' 2>/dev/null || true)
  if [[ -n "$changed_py" ]]; then
    if "$VENV_PY" "$REPO_ROOT/scripts/lib/quality_gate.py" --paths $changed_py; then
      echo "  ✓ quality gate PASS/WARN"
    else
      echo "  ✗ quality gate BLOCK"; ok=0
    fi
  fi
fi

# 6. auto-rollback on any post-apply failure
if [[ $ok -eq 0 ]]; then
  rollback; echo "════════ SAFE-APPLY: VERIFICATION FAILED + ROLLED BACK ════════"; exit 1
fi

# 7. success marker (apply_queue.sh's _is_applied trusts this over the old
#    backups/-dir-exists heuristic, which false-positived on a FAILED
#    attempt that still got as far as creating its own backup dir)
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$REPO_ROOT/$MOD/.applied_ok"

echo "  ✓ applied + verified. Snapshot kept at $SNAP (rollback: restore from there)."
echo "════════ SAFE-APPLY: $MOD APPLIED SAFELY 💛 ════════"
