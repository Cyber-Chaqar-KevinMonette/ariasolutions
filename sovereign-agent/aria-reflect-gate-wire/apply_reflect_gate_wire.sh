#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
#  apply_reflect_gate_wire.sh — wire the tribunal's Ring-2 EXPAI gate to the
#  reflector's lesson-write path (safe self-improvement: propose-only)
#
#  tribunal.gate_ring2_improvement() is fully built, wired to the Tribunal +
#  improvement_gov ledger, and PLAYBOOK.md already advertises it as the
#  standing "Evidence-gated change log" — but it has zero callers. reflector.py
#  captures a durable Lesson on every settle-d/poison-d event and never routes
#  anything through it. This wires exactly one trigger to that one gate: a
#  lesson written with confidence > 0.8 gets proposed through the tribunal +
#  EXPAI ledger. The gate only PROPOSES/LOGS a promote/dismiss decision to an
#  append-only ndjson ledger — it never edits code or values; a human reviews
#  the ledger. No new mechanism, no autonomous action.
#
#  Changes:
#    1. Patch reflector.py — import gate_ring2_improvement, add the
#       _gate_high_confidence_lesson() helper, call it from reflect()'s
#       success path (markers: reflect-gate-wire-*)
#    2. Patch tests/test_reflector.py — three new tests covering: gate fires
#       above threshold, gate does not fire below threshold, gate failure
#       never fails lesson capture (marker: reflect-gate-wire-tests-d)
#
#  Idempotent. Backs up patched files.
# ═══════════════════════════════════════════════════════════════════════════
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${1:-$PWD}"

if [[ ! -f "$ROOT/src/sovereign_agent/cli.py" ]]; then
  d="$PWD"
  while [[ "$d" != "/" ]]; do
    [[ -f "$d/src/sovereign_agent/cli.py" ]] && { ROOT="$d"; break; }
    d="$(dirname "$d")"
  done
fi
[[ -f "$ROOT/src/sovereign_agent/cli.py" ]] || { echo "✗ run from repo root"; exit 1; }
echo "◊ repo root: $ROOT"

PKG="$ROOT/src/sovereign_agent"
REFLECTOR="$PKG/reflector.py"
TESTS="$ROOT/tests/test_reflector.py"
ts(){ date +%Y%m%d%H%M%S; }

# ── 1. Patch reflector.py ─────────────────────────────────────────────────
echo "→ patching reflector.py"
cp "$REFLECTOR" "$REFLECTOR.bak.$(ts)"

python3 - "$REFLECTOR" <<'PYEOF'
import sys, pathlib
p = pathlib.Path(sys.argv[1])
src = p.read_text(encoding="utf-8")

IMPORT_MARKER = "# reflect-gate-wire-import-d"
FN_MARKER     = "# reflect-gate-wire-fn-d"
CALL_MARKER   = "# reflect-gate-wire-call-d"

if IMPORT_MARKER not in src:
    anchor = "from .ollama_client import CallKind, OllamaClient\n"
    if anchor in src:
        inject = "from .tribunal import gate_ring2_improvement  " + IMPORT_MARKER + "\n"
        src = src.replace(anchor, anchor + inject, 1)
        print("  ✓ gate_ring2_improvement import added")
    else:
        print("  ⚠ ollama_client import anchor not found — manual edit required")
else:
    print("  ↷ gate import already present")

if FN_MARKER not in src:
    anchor = "async def reflect(\n    *,\n"
    if anchor in src:
        helper = '''async def _gate_high_confidence_lesson(*, trace_id: str, lesson_id: str, lesson: "Lesson") -> None:  ''' + FN_MARKER + '''
    """Route a high-confidence lesson through the tribunal + EXPAI evidence gate.

    Propose-only: gate_ring2_improvement never mutates code or values -- it appends a
    promote/dismiss decision to improvement_ledger.ndjson for human review. Best-effort:
    a gate failure must never affect reflect()'s already-successful lesson capture.
    """
    proposal = {
        "change": lesson.rule,
        "ring": "ring-2",
        "reversible": True,  # a lesson is a lessons-table row; deleting/superseding it has zero blast radius
        "evidence": (
            f"reflector lesson_id={lesson_id} confidence={lesson.confidence:.2f} "
            f"trigger={lesson.trigger} evidence_events={lesson.evidence_event_ids}"
        ),
        "changelog": f"Reflector captured high-confidence lesson: {lesson.rule}",
    }
    try:
        result = await asyncio.to_thread(gate_ring2_improvement, proposal, SETTINGS.paths.data_dir)
    except Exception as exc:  # noqa: BLE001 -- gate is best-effort, never blocks lesson capture
        emit_event(
            "reflect-gate-x",
            plane="control",
            trace_id=trace_id,
            payload={"lesson_id": lesson_id, "error": str(exc)[:500]},
        )
        return
    emit_event(
        "reflect-gate-d",
        plane="control",
        trace_id=trace_id,
        payload={
            "lesson_id": lesson_id,
            "tribunal_verdict": result.get("tribunal_verdict"),
            "gate_decision": result.get("gate_decision"),
        },
    )


'''
        src = src.replace(anchor, helper + anchor, 1)
        print("  ✓ _gate_high_confidence_lesson helper added")
    else:
        print("  ⚠ 'async def reflect(' anchor not found — manual edit required")
else:
    print("  ↷ gate helper already present")

if CALL_MARKER not in src:
    anchor = '''    emit_event(
        "reflect-d",
        plane="control",
        trace_id=trace_id,
        payload={
            "lesson_id": lesson_id,
            "rule": lesson.rule,
            "confidence": lesson.confidence,
        },
    )
    return lesson_id'''
    if anchor in src:
        inject = anchor.replace(
            "    return lesson_id",
            "    if lesson.confidence > 0.8:  " + CALL_MARKER + "\n"
            "        await _gate_high_confidence_lesson(trace_id=trace_id, lesson_id=lesson_id, lesson=lesson)\n\n"
            "    return lesson_id",
        )
        src = src.replace(anchor, inject, 1)
        print("  ✓ gate call site wired into reflect() success path")
    else:
        print("  ⚠ reflect-d emit_event anchor not found — manual edit required")
else:
    print("  ↷ gate call site already present")

p.write_text(src, encoding="utf-8")
print("  ✓ reflector.py written")
PYEOF

# ── 2. Patch tests/test_reflector.py ──────────────────────────────────────
echo "→ patching tests/test_reflector.py"
cp "$TESTS" "$TESTS.bak.$(ts)"

python3 - "$TESTS" <<'PYEOF'
import sys, pathlib
p = pathlib.Path(sys.argv[1])
src = p.read_text(encoding="utf-8")

MARKER = "# reflect-gate-wire-tests-d"
if MARKER in src:
    print("  ↷ gate tests already present — skipping")
else:
    tests = '''

''' + MARKER + '''
async def test_reflect_gates_high_confidence_lesson():
    """confidence > 0.8 must route through gate_ring2_improvement."""
    conn = open_atoms_db()
    conn.close()

    high_conf = _valid_lesson()
    high_conf["confidence"] = 0.9
    fake_response = _fake_chat_response(high_conf)

    with patch(
        "sovereign_agent.reflector.OllamaClient.chat",
        new=AsyncMock(return_value=fake_response),
    ), patch(
        "sovereign_agent.reflector.gate_ring2_improvement",
        return_value={"tribunal_verdict": "proceed", "gate_decision": "promoted"},
    ) as mock_gate:
        lesson_id = await reflect(
            trace_id="test-trace-gate",
            outcome="settle",
            goal="x",
            final_message=None,
            recent_events=[],
        )

    assert lesson_id is not None
    mock_gate.assert_called_once()
    args, kwargs = mock_gate.call_args
    proposal = args[0] if args else kwargs["proposal"]
    assert proposal["change"] == high_conf["rule"]
    assert proposal["ring"] == "ring-2"
    assert proposal["reversible"] is True


async def test_reflect_does_not_gate_low_confidence_lesson():
    """confidence <= 0.8 must NOT trigger the tribunal gate."""
    conn = open_atoms_db()
    conn.close()

    low_conf = _valid_lesson()
    low_conf["confidence"] = 0.7
    fake_response = _fake_chat_response(low_conf)

    with patch(
        "sovereign_agent.reflector.OllamaClient.chat",
        new=AsyncMock(return_value=fake_response),
    ), patch(
        "sovereign_agent.reflector.gate_ring2_improvement",
    ) as mock_gate:
        lesson_id = await reflect(
            trace_id="test-trace-nogate",
            outcome="settle",
            goal="x",
            final_message=None,
            recent_events=[],
        )

    assert lesson_id is not None
    mock_gate.assert_not_called()


async def test_reflect_gate_failure_does_not_fail_lesson():
    """A gate error must never turn a successful lesson capture into a failure."""
    conn = open_atoms_db()
    conn.close()

    high_conf = _valid_lesson()
    high_conf["confidence"] = 0.95
    fake_response = _fake_chat_response(high_conf)

    with patch(
        "sovereign_agent.reflector.OllamaClient.chat",
        new=AsyncMock(return_value=fake_response),
    ), patch(
        "sovereign_agent.reflector.gate_ring2_improvement",
        side_effect=RuntimeError("boom"),
    ):
        lesson_id = await reflect(
            trace_id="test-trace-gate-fail",
            outcome="settle",
            goal="x",
            final_message=None,
            recent_events=[],
        )

    assert lesson_id is not None
'''
    src = src.rstrip("\n") + "\n" + tests
    print("  ✓ 3 gate tests appended")

p.write_text(src, encoding="utf-8")
print("  ✓ test_reflector.py written")
PYEOF

# ── 3. Compile checks ─────────────────────────────────────────────────────
echo "→ compile checks"
python3 -m py_compile "$REFLECTOR" "$TESTS"
echo "  ✓ all files compile"

echo
echo "✓ done. Reflector lessons above confidence 0.8 now route through the"
echo "  tribunal's Ring-2 EXPAI gate (propose-only; logs to improvement_ledger.ndjson)."
echo
echo "  run: pytest tests/test_reflector.py -v"
