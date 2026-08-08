"""Behavior tests for aria-locator-events-fix — prove LocatorSentinel's default
events_log entry checks the real, daily-rotated events_dir, not a flat
events.jsonl the events system stopped writing long ago. Also proves a scan
against a real (empty) data_dir now reports events_log as 'ok', not 'missing'."""
from __future__ import annotations

import sys
from pathlib import Path


def _find_repo_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / "src/sovereign_agent/stewardship/locator_sentinel.py").is_file():
            return candidate
    raise RuntimeError("could not locate repo root from " + str(start))


REPO_ROOT = _find_repo_root(Path(__file__).resolve())
LOCATOR_SRC = REPO_ROOT / "src/sovereign_agent/stewardship/locator_sentinel.py"


def _fresh_locator_sentinel():
    sys.path.insert(0, str(REPO_ROOT / "src"))
    for mod in list(sys.modules):
        if mod.startswith("sovereign_agent"):
            del sys.modules[mod]
    from sovereign_agent.stewardship.locator_sentinel import LocatorSentinel
    return LocatorSentinel


def test_source_no_longer_expects_a_flat_events_jsonl():
    text = LOCATOR_SRC.read_text(encoding="utf-8")
    assert '"events.jsonl"' not in text, (
        "locator_sentinel.py should no longer expect a flat events.jsonl file"
    )


def test_default_events_log_entry_points_at_events_dir(tmp_path):
    """The seeded default entry (fresh install, no catalog file yet) should
    expect events_dir/ as a directory, matching config.py's actual daily-
    rotation design (events_dir / f'events-{today}.jsonl'), not a flat file."""
    LocatorSentinel = _fresh_locator_sentinel()
    sentinel = LocatorSentinel(tmp_path / "fresh_data_dir")
    entries = sentinel._seed_default_entries()
    events_entry = next(e for e in entries if e.key == "events_log")
    assert events_entry.path.endswith("events"), events_entry.path
    assert events_entry.expected_kind == "dir"


def test_scan_reports_events_log_ok_when_events_dir_exists_with_rotated_files(tmp_path):
    """End-to-end: a real data_dir with a rotated events file (exactly what
    every real Aria installation has) must scan as 'ok', not 'missing'."""
    LocatorSentinel = _fresh_locator_sentinel()
    data_dir = tmp_path / "data"
    (data_dir / "events").mkdir(parents=True)
    (data_dir / "events" / "events-2026-07-03.jsonl").write_text("{}\n")

    sentinel = LocatorSentinel(data_dir)
    report = sentinel.scan()
    findings = report.details["findings"]
    events_findings = [f for f in findings if f["key"] == "events_log"]
    assert events_findings == [], f"events_log should not be flagged: {events_findings}"


def test_scan_still_flags_a_genuinely_empty_events_dir_as_missing(tmp_path):
    """Precision check: if events_dir itself doesn't exist at all (a truly
    fresh install that has never run), events_log should still correctly
    report missing — this fix narrows the false-positive, it doesn't remove
    the check."""
    LocatorSentinel = _fresh_locator_sentinel()
    data_dir = tmp_path / "data"  # events_dir deliberately not created
    sentinel = LocatorSentinel(data_dir)
    report = sentinel.scan()
    findings = report.details["findings"]
    events_findings = [f for f in findings if f["key"] == "events_log"]
    assert len(events_findings) == 1
    assert events_findings[0]["issue"] == "missing"
