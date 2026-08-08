"""proving_ground/timeout_wing.py — the timeout wing of the proving ground.
(Timeout round · T4)

Five scored tasks for the T1-T3 machinery — the stick before any tuning,
same discipline as every other wing: real machinery, mechanical scorers,
no LLM judge; a task crash is a FAIL, never a run crash (the runner
guarantees that).

Fixture events are written DIRECTLY into a tempdir's own `events/
events-<date>.jsonl` file rather than through the real `emit_event()` —
`emit_event()` always writes to the GLOBAL `SETTINGS.paths.events_jsonl`
with no `data_dir` override, so calling it from a proving task would
pollute the real production event log every time the suite runs. Writing
the fixture file directly is real machinery on the READ side (`timeouts.
ledger`'s own glob-and-parse) with a controlled, isolated input on the
write side — the same "real sentinel, fixture input" discipline every
other wing's diagnosis-readable task already uses.

  timeout-scan-persists         a scan over a justified fixture round-trips
                                 through the ledger
  timeout-gate-blocks           the gate BLOCKs a recurring-unexplained fixture
  timeout-diagnosis-readable    the standing sentinel logs a real readable
                                 TMOT-* case
  timeout-catalogued-justified  a known-bounded timeout source scores justified
  timeout-uncatalogued-unexplained  an uncatalogued source scores unexplained
"""
from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def _write_event(data_dir: Path, flag: str, tool: str, timeout_seconds: float,
                 trace_id: str = "test") -> None:
    """Write one event line directly into data_dir/events/events-<today>.jsonl
    — bypasses the real, global emit_event() on purpose (see module docstring)."""
    events_dir = data_dir / "events"
    events_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = events_dir / f"events-{today}.jsonl"
    record = {
        "event_id": f"01FIXTURE{trace_id}",
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "flag": flag, "plane": "control", "trace_id": trace_id, "parent_id": None,
        "payload": {"tool": tool, "timeout_seconds": timeout_seconds},
    }
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


async def _task_timeout_scan_persists() -> tuple[bool, str]:
    """A timeout scan over a justified fixture round-trips through the
    ledger: the returned result and the freshly-read latest_timeout_scan()
    agree."""
    from sovereign_agent.timeouts import latest_timeout_scan, record_timeout_scan

    with tempfile.TemporaryDirectory() as td:
        data_dir = Path(td)
        _write_event(data_dir, "vram-lock-timeout-d", "aria_lm.grow_mind", 60.0)
        result = record_timeout_scan(data_dir=data_dir)
        latest = latest_timeout_scan(data_dir)
        ok = (latest is not None
             and latest.get("scan_id") == result.scan_id
             and latest.get("verdict") == result.verdict == "justified")
    return ok, f"timeout scan {result.scan_id} persisted and round-tripped"


async def _task_timeout_gate_blocks() -> tuple[bool, str]:
    """A fixture with 3 repeated unexplained timeouts for the SAME tool
    must BLOCK — the exact recurring-hang signal this gate exists to
    catch, distinct from one slow call."""
    from sovereign_agent.timeouts.gate import gate

    with tempfile.TemporaryDirectory() as td:
        data_dir = Path(td)
        for i in range(3):
            _write_event(data_dir, "flaky-thing-timeout-d", "flaky_thing", 5.0, trace_id=f"x{i}")
        verdict = gate(data_dir=data_dir)
    ok = verdict.verdict == "BLOCK" and "flaky_thing" in verdict.recurring_tools
    return ok, f"gate verdict {verdict.verdict} on a recurring-unexplained fixture"


async def _task_timeout_diagnosis_readable() -> tuple[bool, str]:
    """The standing sentinel logs a real, readable TMOT-* case into the
    diagnosis catalog — proves T3's wiring stays live."""
    from sovereign_agent.diagnosis import ConflictCatalog
    from sovereign_agent.stewardship.timeout_sentinel import TimeoutSentinel

    with tempfile.TemporaryDirectory() as td:
        data_dir = Path(td)
        _write_event(data_dir, "some-new-subsystem-timeout-d", "brand_new_thing", 5.0)

        sentinel = TimeoutSentinel(data_dir)
        sentinel.scan()
        standing = sentinel.load_catalog(name="standing-audit")
        ok = False
        if standing and str(standing.get("case_id", "")).startswith("TMOT"):
            cat = ConflictCatalog(data_dir / "diagnosis")
            conflict = cat.get_conflict(standing["case_id"])
            ok = conflict is not None
    return ok, f"standing audit case_id={standing.get('case_id') if standing else None!r}"


async def _task_timeout_catalogued_justified() -> tuple[bool, str]:
    """A known-bounded timeout source (git_tools, within its own 15s
    bound) must score justified."""
    from sovereign_agent.timeouts import record_timeout_scan

    with tempfile.TemporaryDirectory() as td:
        data_dir = Path(td)
        _write_event(data_dir, "git-tools-timeout-d", "git_tools", 12.0)
        result = record_timeout_scan(data_dir=data_dir)
    ok = bool(result.events) and result.events[0].verdict == "justified"
    return ok, f"catalogued source scored {result.events[0].verdict if result.events else 'nothing'}"


async def _task_timeout_uncatalogued_unexplained() -> tuple[bool, str]:
    """An uncatalogued source must score unexplained — never silently
    assumed fine just because it's a "timeout" like any other."""
    from sovereign_agent.timeouts import record_timeout_scan

    with tempfile.TemporaryDirectory() as td:
        data_dir = Path(td)
        _write_event(data_dir, "mystery-subsystem-timeout-d", "mystery_subsystem", 5.0)
        result = record_timeout_scan(data_dir=data_dir)
    ok = bool(result.events) and result.events[0].verdict == "unexplained"
    return ok, f"uncatalogued source scored {result.events[0].verdict if result.events else 'nothing'}"


TIMEOUT_TASKS = {
    "timeout-scan-persists": _task_timeout_scan_persists,
    "timeout-gate-blocks": _task_timeout_gate_blocks,
    "timeout-diagnosis-readable": _task_timeout_diagnosis_readable,
    "timeout-catalogued-justified": _task_timeout_catalogued_justified,
    "timeout-uncatalogued-unexplained": _task_timeout_uncatalogued_unexplained,
}
