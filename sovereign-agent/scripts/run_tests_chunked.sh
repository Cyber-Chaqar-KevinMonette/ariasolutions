#!/usr/bin/env bash
# run_tests_chunked.sh — Timeout round T5: the actual fix for the thing
# that happened twice this session — a pytest chunk of ~48-50 files
# exceeding the harness's own ~280s command timeout, several slow
# "_live" (real-Ollama-calling) tests clustering together by bad luck.
#
# Splits tests/test_*.py into N even chunks (default 10 — the size that
# worked by hand today after 6-chunk sizing started timing out), runs
# each with an explicit foreground `timeout` command, and on a chunk
# TIMEOUT (not a real test failure) automatically bisects that one chunk
# in half and retries — mirroring exactly the manual recovery done today
# — rather than just failing outward.
#
# Usage: ./scripts/run_tests_chunked.sh [n_chunks] [timeout_seconds]
#   defaults: 10 chunks, 270s per chunk (comfortably under a 280s harness
#   command-timeout budget).
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
VENV_PY="$REPO_ROOT/.venv/bin/python"
N_CHUNKS="${1:-10}"
TIMEOUT_SECONDS="${2:-270}"
# test-speed-d (Kevin, 2026-07-19: "make tests quicker"). Measured on
# this box: a 60-file sample went 104.8s serial -> 41.7s at -n auto
# (2.5x), memory stable throughout (the earlier scare that session was
# from STACKING several independent heavy processes at once, not from
# xdist itself). Override/disable with a 3rd arg, e.g. `... 10 270 0`.
XDIST_WORKERS="${3:-auto}"

mapfile -t ALL_TESTS < <(find tests -maxdepth 1 -name "test_*.py" | sort)
TOTAL=${#ALL_TESTS[@]}
[[ $TOTAL -eq 0 ]] && { echo "no test files found under tests/"; exit 2; }

echo "=== run_tests_chunked: $TOTAL test files, $N_CHUNKS chunks, ${TIMEOUT_SECONDS}s/chunk ==="

declare -a FAILED_SUMMARY=()
PASSED_FILES=0
OVERALL_RC=0

# run_chunk <file...> — recursive: on a real TIMEOUT (exit 124), bisect
# and retry each half; on any other non-zero exit, surface the actual
# pytest failure lines (never marks a passing file as failed just
# because it shared a chunk with a genuinely failing one).
run_chunk() {
  local files=("$@")
  local n=${#files[@]}
  [[ $n -eq 0 ]] && return 0
  local log; log="$(mktemp)"
  local xdist_flag=()
  [[ "$XDIST_WORKERS" != "0" ]] && xdist_flag=(-n "$XDIST_WORKERS")
  timeout "$TIMEOUT_SECONDS" "$VENV_PY" -m pytest "${files[@]}" -q \
    "${xdist_flag[@]}" > "$log" 2>&1
  local rc=$?

  if [[ $rc -eq 124 ]]; then
    if [[ $n -eq 1 ]]; then
      echo "  ✗ TIMEOUT on a single file (${files[0]}) — a real hang, not a sizing problem"
      FAILED_SUMMARY+=("TIMEOUT (unbisectable): ${files[0]}")
      OVERALL_RC=1
    else
      echo "  ⏱ chunk of $n files timed out — bisecting and retrying..."
      local half=$(( n / 2 ))
      run_chunk "${files[@]:0:$half}"
      run_chunk "${files[@]:$half}"
    fi
  elif [[ $rc -ne 0 ]]; then
    echo "  ✗ chunk of $n files: real test failure(s)"
    grep -E "^FAILED |failed," "$log" | sed 's/^/      /'
    FAILED_SUMMARY+=("$(grep -c "^FAILED " "$log" || true) failure(s) in a $n-file chunk (see log)")
    OVERALL_RC=1
  else
    echo "  ✓ chunk of $n files passed"
    PASSED_FILES=$(( PASSED_FILES + n ))
  fi
  rm -f "$log"
}

CHUNK_SIZE=$(( (TOTAL + N_CHUNKS - 1) / N_CHUNKS ))
for ((i = 0; i < TOTAL; i += CHUNK_SIZE)); do
  chunk=("${ALL_TESTS[@]:i:CHUNK_SIZE}")
  run_chunk "${chunk[@]}"
done

echo "──────────────────────────────────────"
echo "=== $PASSED_FILES/$TOTAL file(s) in clean chunks ==="
if [[ ${#FAILED_SUMMARY[@]} -gt 0 ]]; then
  echo "Problems found:"
  printf '  · %s\n' "${FAILED_SUMMARY[@]}"
fi
exit $OVERALL_RC
