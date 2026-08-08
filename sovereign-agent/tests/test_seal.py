"""Daily seal tests — Merkle root tamper detection."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sovereign_agent.config import SETTINGS
from sovereign_agent.events import emit_event, force_fsync
from sovereign_agent.seal import compute_seal, seal_yesterday, verify_seal


def _make_event_yesterday(flag: str = "test-d") -> str:
    """Force an event into yesterday's events file (for testing seal_yesterday)."""
    yesterday = (datetime.now(timezone.utc).date() - timedelta(days=1))
    path = SETTINGS.paths.events_dir / f"events-{yesterday.isoformat()}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)

    # Use the live emit path but redirect to yesterday's file
    eid = emit_event(flag, plane="control", trace_id="t-seal", payload={"x": 1})
    force_fsync()

    # Move the just-written line to yesterday's file
    today_path = SETTINGS.paths.events_jsonl
    today_lines = today_path.read_text().splitlines() if today_path.exists() else []
    if today_lines:
        last = today_lines[-1]
        today_path.write_text("\n".join(today_lines[:-1]) + ("\n" if today_lines[:-1] else ""))
        with path.open("a") as f:
            f.write(last + "\n")
    return eid


def test_compute_seal_empty_returns_none():
    seal = compute_seal(date(1970, 1, 1))
    assert seal is None


def test_seal_yesterday_writes_root():
    _make_event_yesterday()
    _make_event_yesterday()
    root = seal_yesterday()
    assert root is not None
    assert len(root) == 64  # sha256 hex


def test_seal_verifies_clean():
    _make_event_yesterday()
    seal_yesterday()
    yesterday = (datetime.now(timezone.utc).date() - timedelta(days=1))
    matches, msg = verify_seal(yesterday)
    assert matches, msg


def test_seal_detects_tampering():
    _make_event_yesterday()
    seal_yesterday()
    yesterday = (datetime.now(timezone.utc).date() - timedelta(days=1))

    # Tamper with the JSONL — append a line after the seal was computed
    path = SETTINGS.paths.events_dir / f"events-{yesterday.isoformat()}.jsonl"
    with path.open("a") as f:
        f.write('{"event_id": "fake", "ts": "x", "flag": "tampered", "plane": "x", "trace_id": "x", "parent_id": null, "payload": {}}\n')

    matches, msg = verify_seal(yesterday)
    assert not matches
    assert "MISMATCH" in msg
