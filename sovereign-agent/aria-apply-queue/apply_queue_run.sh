#!/usr/bin/env bash
# apply_queue_run.sh — drain the cockpit-selected apply queue, SAFELY, one module at a time.
#
# Kevin's flow: select modules in the cockpit (writes the durable queue) → close the cockpit →
# run this. Each module goes through scripts/safe_apply.sh (cockpit-guard + snapshot + Tribunal
# gate + verify + AUTO-ROLLBACK). On success the module LEAVES the queue (marked applied). On a
# rollback it is routed to QUARANTINE for evaluation until fixed — never lost. Watch progress in
# the terminal (▸ [n/N] slug …). A desktop notification summarises successes + quarantines at the end.
#
# Usage:  ./scripts/apply_queue_run.sh [--dry-run]
#         --dry-run : show the plan + per-module Tribunal verdict, mutate nothing.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
VENV_PY="$REPO_ROOT/.venv/bin/python"
PYQ=("$VENV_PY" -m sovereign_agent.apply_queue)
DRY=0; [[ "${1:-}" == "--dry-run" ]] && DRY=1

[[ -x "$VENV_PY" ]] || { echo "⛔ venv missing."; exit 1; }
if pgrep -f "sovereign cockpit" >/dev/null 2>&1; then
  echo "⛔ cockpit is RUNNING — close it first (the queue applies into live src beneath it)."; exit 1
fi

# Count the queue up front (for the [n/N] progress display).
mapfile -t QUEUE < <("${PYQ[@]}" list | awk '{print $2}')
TOTAL=${#QUEUE[@]}
if [[ $TOTAL -eq 0 ]]; then echo "✓ apply queue is empty — nothing to do. 💛"; exit 0; fi

echo "════════ APPLY QUEUE — $TOTAL module(s) selected ════════"
"${PYQ[@]}" list

if [[ $DRY -eq 1 ]]; then
  echo ""; echo "── DRY RUN (Tribunal/foresight preview per module; nothing applied) ──"
  for slug in "${QUEUE[@]}"; do
    if [[ -x scripts/pre_apply_gate.sh ]]; then
      verdict=$(scripts/pre_apply_gate.sh "$slug" 2>&1 | grep -E "VERDICT|GATE:" | head -1)
      echo "  · $slug — ${verdict:-no gate output}"
    else
      echo "  · $slug — (no pre_apply_gate.sh; safe_apply still gates at run time)"
    fi
  done
  echo "Run without --dry-run to apply."; exit 0
fi

applied=(); quarantined=()
n=0
while :; do
  slug="$("${PYQ[@]}" next 2>/dev/null)" || break   # exit 1 ⇒ queue empty
  [[ -z "$slug" ]] && break
  n=$((n+1))
  echo ""; echo "▸ [$n/$TOTAL] $slug — applying…"
  "${PYQ[@]}" mark "$slug" applying >/dev/null

  if ./scripts/safe_apply.sh "$slug" --yes; then
    "${PYQ[@]}" mark "$slug" applied >/dev/null      # leaves the active queue
    applied+=("$slug")
    echo "  ✓ [$n/$TOTAL] $slug applied — removed from queue."
  else
    # safe_apply already rolled the module back; route it to quarantine.
    snap="$REPO_ROOT/$slug/.safe_apply_snapshot"
    "${PYQ[@]}" quarantine add "$slug" "apply rolled back during queue run" >/dev/null
    "${PYQ[@]}" mark "$slug" quarantined >/dev/null
    quarantined+=("$slug")
    echo "  ⛔ [$n/$TOTAL] $slug rolled back → QUARANTINED (snapshot: $snap)"
  fi
done

echo ""; echo "════════ QUEUE COMPLETE ════════"
echo "  applied:     ${#applied[@]}  ${applied[*]:-—}"
echo "  quarantined: ${#quarantined[@]}  ${quarantined[*]:-—}"

# Desktop notification (best-effort; gdbus on Pop!_OS / any freedesktop daemon).
summary="${#applied[@]} applied · ${#quarantined[@]} quarantined"
if command -v gdbus >/dev/null 2>&1; then
  icon="dialog-information"; [[ ${#quarantined[@]} -gt 0 ]] && icon="dialog-warning"
  gdbus call --session \
    --dest org.freedesktop.Notifications \
    --object-path /org/freedesktop/Notifications \
    --method org.freedesktop.Notifications.Notify \
    "aria-apply-queue" 0 "$icon" "Apply queue finished" "$summary" "[]" "{}" 10000 \
    >/dev/null 2>&1 || true
fi
echo "💛  $summary"
[[ ${#quarantined[@]} -gt 0 ]] && exit 1 || exit 0
