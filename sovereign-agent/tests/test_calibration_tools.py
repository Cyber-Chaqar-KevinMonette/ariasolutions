"""Tests for calibration tools (M79).

calibration_tools.py is already applied to live — imports the real module
directly, no shadow-copy/injection needed. (An earlier version of this
file injected the staging payload under the live module name; that only
worked by accident — see test_self_portrait.py's own fix this session
for the full explanation of why the injection pattern silently breaks in
isolation once the target module is genuinely live.)

8 tests covering: log prediction, resolve prediction (correct/incorrect),
already-resolved error, empty ledger, calibration score accuracy, overconfidence
detection, domain filtering, and unresolved entries excluded from score.
"""
from __future__ import annotations

import pytest

import sovereign_agent.tools.calibration_tools as _cal_mod

LogPredictionTool = _cal_mod.LogPredictionTool
ResolvePredictionTool = _cal_mod.ResolvePredictionTool
CalibrationLedgerTool = _cal_mod.CalibrationLedgerTool


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_log_prediction_writes_to_ledger(tmp_path, monkeypatch):
    """log_prediction writes an entry; entry has outcome=None."""
    cal_dir = tmp_path / "calibration"
    cal_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(_cal_mod, "_ledger_path", lambda: cal_dir / "ledger.ndjson")

    tool = LogPredictionTool()
    result = await tool.execute(
        tool.Args(claim="tests will pass", confidence=0.9, domain="testing"),
        trace_id="test",
    )

    assert result.ok is True
    entry_id = result.output["entry_id"]
    assert entry_id

    # Verify the file has the entry
    entries = _cal_mod._read_entries(tmp_path / "calibration" / "ledger.ndjson")
    assert len(entries) == 1
    assert entries[0]["outcome_correct"] is None
    assert entries[0]["entry_id"] == entry_id


@pytest.mark.asyncio
async def test_resolve_prediction_marks_correct(tmp_path, monkeypatch):
    """resolve_prediction marks an entry correct=True."""
    cal_dir = tmp_path / "calibration"
    cal_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(_cal_mod, "_ledger_path", lambda: cal_dir / "ledger.ndjson")

    log_tool = LogPredictionTool()
    log_result = await log_tool.execute(
        log_tool.Args(claim="the test passes", confidence=0.8, domain="testing"),
        trace_id="test",
    )
    entry_id = log_result.output["entry_id"]

    resolve_tool = ResolvePredictionTool()
    res = await resolve_tool.execute(
        resolve_tool.Args(entry_id=entry_id, correct=True, notes="it did pass"),
        trace_id="test",
    )

    assert res.ok is True
    entries = _cal_mod._read_entries(tmp_path / "calibration" / "ledger.ndjson")
    resolved = [e for e in entries if e["entry_id"] == entry_id]
    assert len(resolved) == 1
    assert resolved[0]["outcome_correct"] is True


@pytest.mark.asyncio
async def test_resolve_already_resolved_error(tmp_path, monkeypatch):
    """Resolving an already-resolved entry → ok=False, error='already_resolved'."""
    cal_dir = tmp_path / "calibration"
    cal_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(_cal_mod, "_ledger_path", lambda: cal_dir / "ledger.ndjson")

    log_tool = LogPredictionTool()
    log_result = await log_tool.execute(
        log_tool.Args(claim="a claim", confidence=0.7, domain="testing"),
        trace_id="test",
    )
    entry_id = log_result.output["entry_id"]

    resolve_tool = ResolvePredictionTool()
    await resolve_tool.execute(
        resolve_tool.Args(entry_id=entry_id, correct=True),
        trace_id="test",
    )
    # Second resolve → error
    res2 = await resolve_tool.execute(
        resolve_tool.Args(entry_id=entry_id, correct=False),
        trace_id="test",
    )

    assert res2.ok is False
    assert "already_resolved" in res2.error


@pytest.mark.asyncio
async def test_calibration_ledger_empty_ok(tmp_path, monkeypatch):
    """Empty ledger → ok=True, total_predictions=0."""
    cal_dir = tmp_path / "calibration"
    cal_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(_cal_mod, "_ledger_path", lambda: cal_dir / "ledger.ndjson")

    tool = CalibrationLedgerTool()
    result = await tool.execute(tool.Args(), trace_id="test")

    assert result.ok is True
    assert result.output["total_predictions"] == 0
    assert result.output["calibration_score"] is None


@pytest.mark.asyncio
async def test_calibration_score_good(tmp_path, monkeypatch):
    """10 predictions at 0.8 confidence, 8 correct → calibration_score ≥ 0.7."""
    cal_dir = tmp_path / "calibration"
    cal_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(_cal_mod, "_ledger_path", lambda: cal_dir / "ledger.ndjson")

    log_tool = LogPredictionTool()
    resolve_tool = ResolvePredictionTool()

    for i in range(10):
        log_res = await log_tool.execute(
            log_tool.Args(claim=f"claim {i}", confidence=0.8, domain="testing"),
            trace_id="test",
        )
        await resolve_tool.execute(
            resolve_tool.Args(entry_id=log_res.output["entry_id"], correct=(i < 8)),
            trace_id="test",
        )

    result = await CalibrationLedgerTool().execute(CalibrationLedgerTool.Args(), trace_id="test")

    assert result.ok is True
    score = result.output["calibration_score"]
    assert score is not None and score >= 0.7, f"Expected score ≥ 0.7, got {score}"


@pytest.mark.asyncio
async def test_calibration_score_overconfident(tmp_path, monkeypatch):
    """10 predictions at 0.9 confidence, 5 correct → score < 0.7, negative drift."""
    cal_dir = tmp_path / "calibration"
    cal_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(_cal_mod, "_ledger_path", lambda: cal_dir / "ledger.ndjson")

    log_tool = LogPredictionTool()
    resolve_tool = ResolvePredictionTool()

    for i in range(10):
        log_res = await log_tool.execute(
            log_tool.Args(claim=f"claim {i}", confidence=0.9, domain="testing"),
            trace_id="test",
        )
        await resolve_tool.execute(
            resolve_tool.Args(entry_id=log_res.output["entry_id"], correct=(i < 5)),
            trace_id="test",
        )

    result = await CalibrationLedgerTool().execute(CalibrationLedgerTool.Args(), trace_id="test")

    assert result.ok is True
    score = result.output["calibration_score"]
    assert score is not None and score < 0.7, f"Expected score < 0.7 (overconfident), got {score}"

    # Check that drift is negative for the 0.9 bucket
    bucket_09 = next((b for b in result.output["by_bucket"] if abs(b["confidence_bucket"] - 0.9) < 0.05), None)
    if bucket_09:
        assert bucket_09["drift"] < 0, f"Expected negative drift for 0.9 bucket, got {bucket_09['drift']}"


@pytest.mark.asyncio
async def test_calibration_domain_filter(tmp_path, monkeypatch):
    """Mixed domains → domain='testing' filter returns only testing entries."""
    cal_dir = tmp_path / "calibration"
    cal_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(_cal_mod, "_ledger_path", lambda: cal_dir / "ledger.ndjson")

    log_tool = LogPredictionTool()
    for domain in ["testing", "code-review", "testing", "security"]:
        await log_tool.execute(
            log_tool.Args(claim=f"claim for {domain}", confidence=0.7, domain=domain),
            trace_id="test",
        )

    result = await CalibrationLedgerTool().execute(
        CalibrationLedgerTool.Args(domain="testing"), trace_id="test"
    )

    assert result.ok is True
    assert result.output["total_predictions"] == 2
    for pred in result.output["recent_predictions"]:
        assert pred["domain"] == "testing"


@pytest.mark.asyncio
async def test_calibration_unresolved_excluded(tmp_path, monkeypatch):
    """Unresolved predictions don't affect calibration_score; score = None if all unresolved."""
    cal_dir = tmp_path / "calibration"
    cal_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(_cal_mod, "_ledger_path", lambda: cal_dir / "ledger.ndjson")

    log_tool = LogPredictionTool()
    for i in range(5):
        await log_tool.execute(
            log_tool.Args(claim=f"claim {i}", confidence=0.8, domain="testing"),
            trace_id="test",
        )
    # No resolutions

    result = await CalibrationLedgerTool().execute(CalibrationLedgerTool.Args(), trace_id="test")

    assert result.ok is True
    assert result.output["total_predictions"] == 5
    assert result.output["resolved_predictions"] == 0
    assert result.output["calibration_score"] is None
