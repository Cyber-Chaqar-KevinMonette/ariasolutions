#!/usr/bin/env bash
# ╔══════════════════════════════════════════════════════════════════════╗
# ║  sovereign-continue-loop.sh — Re-trigger driver                      ║
# ║                                                                      ║
# ║  Repeatedly invokes ``sovereign continue <task_id>`` until the       ║
# ║  continuation is drained, halted, or a step cap is reached.          ║
# ║                                                                      ║
# ║  Each invocation is a fresh Python process. The model never sees     ║
# ║  more than one step's context per invocation. Memory accumulates     ║
# ║  in events.jsonl and atoms.db across invocations.                    ║
# ║                                                                      ║
# ║  v0.2.6: ``--model-filter NAME`` only runs steps whose required      ║
# ║  model matches. For batched, model-affinity workflows, prefer        ║
# ║  ``sovereign drain-by-model <id>`` which sequences phases auto.      ║
# ╚══════════════════════════════════════════════════════════════════════╝
#
# Usage:
#   sovereign-continue-loop.sh <task_id>                   # run until drained
#   sovereign-continue-loop.sh <task_id> --once            # one step then exit
#   sovereign-continue-loop.sh <task_id> --max 50          # at most 50 steps
#   sovereign-continue-loop.sh <task_id> --model-filter X  # only X-model steps
#
# Environment:
#   SOVEREIGN_BIN     path to the `sovereign` CLI (default: in PATH)
#   COOLDOWN_SECONDS  sleep between successful invocations (default: 2)
#   LOCKED_BACKOFF    sleep when continuation is locked (default: 5)

set -euo pipefail

if [[ $# -lt 1 ]]; then
    cat >&2 <<EOF
usage: $0 <task_id> [--once] [--max N] [--model-filter MODEL]

Examples:
  $0 cont-01J9...
  $0 cont-01J9... --max 10
  $0 cont-01J9... --model-filter orchestrator
  $0 cont-01J9... --model-filter vision

For batched multi-model drains, prefer:
  sovereign drain-by-model cont-01J9...
EOF
    exit 2
fi

TASK_ID="$1"
shift || true

MAX_STEPS=""
ONCE=0
MODEL_FILTER=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --once) ONCE=1; shift ;;
        --max) MAX_STEPS="$2"; shift 2 ;;
        --model-filter) MODEL_FILTER="$2"; shift 2 ;;
        *) echo "unknown arg: $1" >&2; exit 2 ;;
    esac
done

SOVEREIGN_BIN="${SOVEREIGN_BIN:-sovereign}"
COOLDOWN_SECONDS="${COOLDOWN_SECONDS:-2}"
LOCKED_BACKOFF="${LOCKED_BACKOFF:-5}"

steps=0
banner="◊ continue-loop · task=${TASK_ID}"
[[ -n "$MODEL_FILTER" ]] && banner="${banner} · model=${MODEL_FILTER}"
echo "$banner"

while true; do
    if [[ -n "$MAX_STEPS" && "$steps" -ge "$MAX_STEPS" ]]; then
        echo "◊ max-steps reached ($MAX_STEPS); stopping"
        exit 0
    fi

    set +e
    if [[ -n "$MODEL_FILTER" ]]; then
        "$SOVEREIGN_BIN" continue "$TASK_ID" --model-filter "$MODEL_FILTER"
    else
        "$SOVEREIGN_BIN" continue "$TASK_ID"
    fi
    rc=$?
    set -e

    case "$rc" in
        0)
            steps=$((steps + 1))
            [[ "$ONCE" -eq 1 ]] && exit 0
            sleep "$COOLDOWN_SECONDS"
            ;;
        8)
            echo "◊ continuation drained (or no more steps for filter) · steps=${steps}"
            exit 0
            ;;
        9)
            sleep "$LOCKED_BACKOFF"
            ;;
        3)
            echo "◊ HALT armed · stopping" >&2
            exit 3
            ;;
        *)
            echo "◊ continue failed (rc=${rc}); retrying in ${COOLDOWN_SECONDS}s" >&2
            sleep "$COOLDOWN_SECONDS"
            ;;
    esac
done
