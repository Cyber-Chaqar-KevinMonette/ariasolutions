#!/usr/bin/env bash
# pre_apply_gate.sh <aria-module> — run the Tribunal + 14-gen foresight over a staged module before apply.
# Propose-only: it ADVISES (verdict + synthesis); Kevin/Claude decide. Exit 1 if either engine says stop.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
VENV_PY="$REPO_ROOT/.venv/bin/python"
MOD="${1:-}"; [[ -z "$MOD" ]] && { echo "usage: pre_apply_gate.sh <aria-module>"; exit 2; }
MOD="${MOD%/}"
[[ -d "$MOD" ]] || { echo "ERROR: no such module: $MOD"; exit 2; }

echo "════════ PRE-APPLY GATE: $MOD ════════"
"$VENV_PY" "$REPO_ROOT/scripts/lib/scrutiny.py" --module "$MOD"
rc=$?
# quality-gate-d — the quality gate: real hardening checks over the module's own
# payload, not just prose review. Worst-wins with the scrutiny rc above.
"$VENV_PY" "$REPO_ROOT/scripts/lib/quality_gate.py" --module "$MOD"
qrc=$?
[[ $qrc -ne 0 ]] && rc=$qrc
# grounding-gate-d — the grounding gate: does the module's own README prose hold up?
# Worst-wins with the two rc's above.
"$VENV_PY" "$REPO_ROOT/scripts/lib/grounding_gate.py" --module "$MOD"
grc=$?
[[ $grc -ne 0 ]] && rc=$grc
# integrity-gate-d — the integrity gate: composite anti-misleading check over the
# module's own README. Worst-wins with the three rc's above.
"$VENV_PY" "$REPO_ROOT/scripts/lib/integrity_gate.py" --module "$MOD"
irc=$?
[[ $irc -ne 0 ]] && rc=$irc
# timeout-gate-d — the timeout gate: checks the shared event log for recurring
# unexplained timeouts (not per-module — the same check every apply
# shares). Worst-wins with the four rc's above.
"$VENV_PY" "$REPO_ROOT/scripts/lib/timeout_gate.py"
trc=$?
[[ $trc -ne 0 ]] && rc=$trc
echo "──────────────────────────────────────"
[[ $rc -eq 0 ]] && echo "GATE: clear to apply (propose-only — Kevin decides)" || echo "GATE: a voice says STOP — review before applying"
exit $rc
