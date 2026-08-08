#!/usr/bin/env bash
# apply_queue.sh {plan|run|status} [--yes] — a dependency-ordered, resumable, SAFE apply queue.
# With 100+ staged modules, applying them one-by-one by hand is error-prone. This queues the UNAPPLIED
# modules in dependency order (the tool-registration anchor chain first), then applies each through
# scripts/safe_apply.sh (cockpit-guard + backup + Tribunal gate + verify + AUTO-ROLLBACK). On any failure it
# STOPS (that module is rolled back) and leaves the rest queued — resume by running again. Quality over speed.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
CMD="${1:-status}"
# flags can appear in any order after the command
YES=""; CONT=0
for a in "$@"; do
  [[ "$a" == "--yes" ]] && YES="--yes"
  [[ "$a" == "--continue" ]] && CONT=1
done

# Dependency order: modules whose apply patches the tool/sentinel registration chain must go first, in chain
# order. Everything else is independent and applied after, alphabetically.
PRIORITY=(
  aria-own-mind aria-immune-system aria-constitution
  aria-tribunal aria-frugality aria-foresight aria-godtier-scanner
  aria-senses aria-autonomy-session aria-nonclassical-godtier aria-nonclassical-supreme
)

_is_applied() {
  # FABLE II M9: `.applied_ok` (written by safe_apply.sh only on a fully
  # verified success) is trusted FIRST — the old "backups/ exists" check
  # is a false positive on a module whose apply FAILED partway (the
  # backup dir is created before the apply script even runs, success or
  # not). Legacy modules applied before this marker existed still fall
  # back to the old heuristic.
  local name="$1"; local slug="${name#aria-}"; slug="${slug//-/_}"
  [[ -f "$REPO_ROOT/$name/.applied_ok" ]] && return 0
  [[ -d "$REPO_ROOT/$name/backups" ]] && return 0
  [[ -f "$REPO_ROOT/tests/test_${slug}.py" ]] && return 0
  # payload-parity fallback (2026-08-02, index-the-project pass): the three
  # checks above all assume the module's own slug names its test file or
  # backup dir — false for any module whose payload files are named after
  # what they DO, not the aria-<slug> folder (aria-real-estate ships
  # real_estate_gate.py, not test_real_estate.py). 13/31 "pending" modules
  # in one audit were actually fully live under this exact gap. If every
  # payload .py file byte-matches its live counterpart, it's applied,
  # regardless of what anything is named.
  local payload="$REPO_ROOT/$name/payload/src/sovereign_agent"
  [[ -d "$payload" ]] || return 1
  local f rel live found=0
  while IFS= read -r -d '' f; do
    found=1
    rel="${f#"$payload"/}"
    live="$REPO_ROOT/src/sovereign_agent/$rel"
    [[ -f "$live" ]] && cmp -s "$f" "$live" || return 1
  done < <(find "$payload" -name '*.py' -print0 2>/dev/null)
  [[ $found -eq 1 ]] && return 0
  return 1
}

_queue() {  # print the ordered list of UNAPPLIED modules with an apply script
  local seen=" "
  for m in "${PRIORITY[@]}"; do
    [[ -d "$REPO_ROOT/$m" ]] && ls "$REPO_ROOT/$m"/apply_*.sh >/dev/null 2>&1 || continue
    _is_applied "$m" || echo "$m"; seen+="$m "
  done
  for d in "$REPO_ROOT"/aria-*/; do
    m="$(basename "$d")"
    [[ "$seen" == *" $m "* ]] && continue
    ls "$d"/apply_*.sh >/dev/null 2>&1 || continue
    _is_applied "$m" || echo "$m"
  done
}

case "$CMD" in
  status)
    total=$(ls -d aria-*/ 2>/dev/null | wc -l | tr -d ' ')
    pending=$(_queue | wc -l | tr -d ' ')
    echo "apply-queue: $total staged · $((total-pending)) applied · $pending pending"
    echo "next up:"; _queue | head -8 | sed 's/^/  /'
    ;;
  plan)
    echo "════ APPLY QUEUE (dependency-ordered, unapplied) ════"
    n=0; while read -r m; do [[ -n "$m" ]] && { n=$((n+1)); printf "  %2d. %s\n" "$n" "$m"; }; done < <(_queue)
    [[ $n -eq 0 ]] && echo "  (queue empty — all staged modules applied)"
    echo "run with:  ./scripts/apply_queue.sh run --yes   (each goes through safe_apply: guarded + rollback)"
    ;;
  run)
    if pgrep -f "sovereign cockpit" >/dev/null 2>&1; then echo "⛔ cockpit running — stop it first."; exit 1; fi
    applied=0; failed=""
    while read -r m; do
      [[ -z "$m" ]] && continue
      echo ""; echo "════ QUEUE → applying $m ════"
      if ./scripts/safe_apply.sh "$m" "$YES"; then
        applied=$((applied+1))
      else
        failed+="$m "
        if [[ $CONT -eq 1 ]]; then
          echo "  ⤼ $m failed (rolled back) — --continue: skipping, queue continues."
        else
          echo ""; echo "⛔ QUEUE STOPPED at $m (rolled back). Fix it, or re-run with --continue to skip failures."
          echo "   applied this run: $applied"; exit 1
        fi
      fi
    done < <(_queue)
    echo ""; echo "✓ QUEUE RUN COMPLETE — applied $applied module(s)."
    [[ -n "$failed" ]] && echo "  rolled back (need attention): $failed"
    echo "💛"
    ;;
  *)
    echo "usage: apply_queue.sh {plan|run|status} [--yes]"; exit 2 ;;
esac
