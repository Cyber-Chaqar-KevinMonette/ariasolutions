"""Tests for AegisConductor resilience at failure paths (M77).

Tests are self-contained: each uses a tmp_path fixture for data_dir and
a fresh AegisConductor per test. No shared state.

Coverage targets: conductor.py lines 224-234 (state load), 479-534
(DEFCON elevation/downgrade), 577-578 (BLACK token rotation), 610-630
(quiesce exception isolation), 240-252 (ledger failure at bootstrap).
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import pytest

from sovereign_agent.aegis.conductor import (
    AegisConductor,
    ConductorState,
    QUIET_PERIOD_SECONDS,
)
from sovereign_agent.aegis.defcon import Defcon
from sovereign_agent.aegis.incidents import (
    DamageReport,
    Evidence,
    IncidentId,
)
from sovereign_agent.aegis.radius import BlastRadius


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_conductor(data_dir: Path) -> AegisConductor:
    c = AegisConductor(data_dir)
    c.bootstrap()
    return c


def _warning_report(incident_id: str) -> DamageReport:
    return DamageReport(
        incident_id=IncidentId(incident_id),
        sentinel_id="test-sentinel",
        radius=BlastRadius.R0_ARTIFACT,
        severity="warning",
        confidence=0.8,
        summary="test warning",
        evidence=[Evidence(kind="other", summary="test")],
    )


def _alert_report(incident_id: str) -> DamageReport:
    return DamageReport(
        incident_id=IncidentId(incident_id),
        sentinel_id="test-sentinel",
        radius=BlastRadius.R1_SURFACE,
        severity="alert",
        confidence=0.9,
        summary="test alert",
        evidence=[Evidence(kind="other", summary="test alert")],
    )


def _tampered_report(incident_id: str, sentinel_id: str = "test-sentinel") -> DamageReport:
    return DamageReport(
        incident_id=IncidentId(incident_id),
        sentinel_id=sentinel_id,
        radius=BlastRadius.R2_SOFTWARE,
        severity="critical",
        confidence=1.0,
        summary="manifest tampered",
        evidence=[Evidence(kind="manifest-tampered", summary="chain broken")],
    )


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_bootstrap_malformed_state_json(tmp_path):
    """Garbage state.json → conductor starts from clean GREEN, no exception."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
    aegis_dir = data_dir / "aegis"
    aegis_dir.mkdir(mode=0o700)
    state_path = aegis_dir / "state.json"
    state_path.write_text("{not valid json!!!}", encoding="utf-8")

    conductor = _make_conductor(data_dir)
    assert conductor.defcon == Defcon.GREEN
    assert conductor.open_incident_count == 0


def test_bootstrap_valid_yellow_state_carries_defcon(tmp_path):
    """Crash-resume: YELLOW state written by first conductor is loaded by second."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)

    c1 = _make_conductor(data_dir)
    c1.intake(_warning_report("inc-001"))
    # Write YELLOW state
    state_json = c1._state.to_json()
    c1._state_path.write_text(state_json, encoding="utf-8")

    # Second conductor bootstraps from that state
    c2 = AegisConductor(data_dir)
    c2.bootstrap()
    assert c2.defcon == Defcon.YELLOW


def test_quiesce_exception_does_not_propagate(tmp_path):
    """sentinel.quiesce() raises → conductor swallows the exception and continues."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)

    conductor = _make_conductor(data_dir)

    class BurstySentinel:
        id = "bursty-sentinel"

        def quiesce(self):
            raise RuntimeError("quiesce failed badly")

        def unquiesce(self):
            pass

    conductor.register_sentinel(BurstySentinel())

    # _quiesce_neighbors must not propagate the exception
    conductor._quiesce_neighbors("other-sentinel")
    # If we get here without exception the test passes
    assert conductor.defcon == Defcon.GREEN


def test_defcon_green_to_yellow_to_orange(tmp_path):
    """warning incident → YELLOW, alert incident → ORANGE."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)

    conductor = _make_conductor(data_dir)
    assert conductor.defcon == Defcon.GREEN

    conductor.intake(_warning_report("inc-w"))
    assert conductor.defcon == Defcon.YELLOW

    conductor.intake(_alert_report("inc-a"))
    assert conductor.defcon == Defcon.ORANGE


def test_defcon_black_rotates_writer_token(tmp_path):
    """3 manifest-tampered incidents from different sentinels → BLACK, writer_token changes."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)

    conductor = _make_conductor(data_dir)
    pre_black_token = conductor._state.writer_token

    for i, sid in enumerate(["s1", "s2", "s3"]):
        conductor.intake(_tampered_report(f"inc-tamper-{i}", sentinel_id=sid))

    assert conductor.defcon == Defcon.BLACK
    assert conductor._state.writer_token != pre_black_token


def test_downgrade_yellow_requires_quiet_period(tmp_path):
    """YELLOW auto-downgrade only fires after QUIET_PERIOD_SECONDS."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)

    conductor = _make_conductor(data_dir)
    conductor.intake(_warning_report("inc-quiet"))
    assert conductor.defcon == Defcon.YELLOW

    # Immediate call: still YELLOW (quiet period not met)
    conductor._maybe_downgrade()
    assert conductor.defcon == Defcon.YELLOW

    # Fake the last_yellow_evidence_at to be old enough
    past = (datetime.now(timezone.utc) - timedelta(seconds=QUIET_PERIOD_SECONDS + 60))
    conductor._state.last_yellow_evidence_at = past.strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    conductor._maybe_downgrade()
    assert conductor.defcon == Defcon.GREEN


def test_downgrade_malformed_timestamp(tmp_path):
    """Unparseable last_yellow_evidence_at → _maybe_downgrade returns early, no crash."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)

    conductor = _make_conductor(data_dir)
    conductor.intake(_warning_report("inc-ts"))
    assert conductor.defcon == Defcon.YELLOW

    conductor._state.last_yellow_evidence_at = "NOT-A-TIMESTAMP"
    conductor._maybe_downgrade()

    # No exception, stays YELLOW
    assert conductor.defcon == Defcon.YELLOW


def test_shutdown_ledger_failure_swallowed(tmp_path):
    """AegisConductor.shutdown() catches ledger failure — no exception propagates."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)

    conductor = _make_conductor(data_dir)
    assert conductor._bootstrapped

    from sovereign_agent.aegis import ledger as ledger_mod
    with mock.patch.object(ledger_mod.AegisLedger, "append", side_effect=OSError("disk full")):
        # shutdown explicitly wraps ledger.append in try/except — must not raise
        try:
            conductor.shutdown()
        except OSError:
            pytest.fail("shutdown must swallow ledger errors")
