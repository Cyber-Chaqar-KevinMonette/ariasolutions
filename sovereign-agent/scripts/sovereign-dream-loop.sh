#!/usr/bin/env bash
# ╔══════════════════════════════════════════════════════════════════════╗
# ║  sovereign-dream-loop.sh — Outer driver for a dream session          ║
# ║  v0.2.12                                                             ║
# ║                                                                      ║
# ║  Repeatedly invokes ``sovereign dream advance <dream_id>`` until     ║
# ║  the session is paused, exhausted, or halted. Same shape as          ║
# ║  sovereign-continue-loop.sh — fresh Python process per advance,      ║
# ║  bounded model context, OS-managed lifecycle.                        ║
# ╚══════════════════════════════════════════════════════════════════════╝
#
# Usage:
#   sovereign-dream-loop.sh <dream_id>                  # run until terminal
#   sovereign-dream-loop.sh <dream_id> --once           # one step then exit
#   sovereign-dream-loop.sh <dream_id> --max-steps 50   # at most N steps
#
# Environment:
#   SOVEREIGN_BIN     path to the `sovereign` CLI (default: in PATH)
#   COOLDOWN_SECONDS  sleep between successful advances (default: 2)
#   LOCKED_BACKOFF    sleep when a cycle is locked (default: 5)
#   POISON_BACKOFF    sleep after a poison outcome (default: 10)

set -euo pipefail

if [[ $# -lt 1 ]]; then
    cat >&2 <<EOF
usage: $0 <dream_id> [--once] [--max-steps N]

Examples:
  $0 dream-01J9...
  $0 dream-01J9... --max-steps 200
  $0 dream-01J9... --once
EOF
    exit 2
fi

DREAM_ID="$1"
shift || true

MAX_STEPS=""
ONCE=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --once) ONCE=1; shift ;;
        --max-steps) MAX_STEPS="$2"; shift 2 ;;
        *) echo "unknown arg: $1" >&2; exit 2 ;;
    esac
done

SOVEREIGN_BIN="${SOVEREIGN_BIN:-sovereign}"
COOLDOWN_SECONDS="${COOLDOWN_SECONDS:-2}"
LOCKED_BACKOFF="${LOCKED_BACKOFF:-5}"
POISON_BACKOFF="${POISON_BACKOFF:-10}"

steps=0
echo "◊ dream-loop · ${DREAM_ID} · Ctrl-C to stop"

while true; do
    if [[ -n "$MAX_STEPS" && "$steps" -ge "$MAX_STEPS" ]]; then
        echo "◊ max-steps reached ($MAX_STEPS) · stopping"
        exit 0
    fi

    set +e
    "$SOVEREIGN_BIN" dream advance "$DREAM_ID"
    rc=$?
    set -e

    case "$rc" in
        0)
            steps=$((steps + 1))
            [[ "$ONCE" -eq 1 ]] && exit 0
            sleep "$COOLDOWN_SECONDS"
            ;;
        8)
            # DRAINED — used for both terminal dream states AND for paused.
            # The advance command's stdout already prints which one. Exit
            # cleanly so a wrapping `until` / cron driver doesn't restart
            # us forever on an exhausted dream.
            echo "◊ dream session terminal (paused / exhausted / completed) · steps=${steps}"
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
            echo "◊ advance returned rc=${rc} · backing off ${POISON_BACKOFF}s" >&2
            sleep "$POISON_BACKOFF"
            ;;
    esac
done
