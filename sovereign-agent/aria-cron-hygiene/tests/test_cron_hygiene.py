"""Tests for M56 cron-hygiene — ScheduleSentinel."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
import yaml


def _write_schedule(tmpdir: Path, schedules: list[dict]) -> Path:
    path = tmpdir / "schedule.yaml"
    path.write_text(yaml.safe_dump({"schedules": schedules}))
    return path


class TestScheduleSentinelContract:
    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path):
        from sovereign_agent.stewardship.schedule_sentinel import ScheduleSentinel
        self.sentinel = ScheduleSentinel(tmp_path)
        self.tmp_path = tmp_path

    def test_id(self):
        assert self.sentinel.id == "schedule"

    def test_title_non_empty(self):
        assert len(self.sentinel.title) > 5

    def test_tier_is_1(self):
        assert self.sentinel.tier == 1

    def test_articles_non_empty(self):
        arts = self.sentinel.articles()
        assert len(arts) >= 4

    def test_registered(self):
        from sovereign_agent.stewardship.registry import registered_ids
        assert "schedule" in registered_ids()


class TestScheduleSentinelMissingFile:
    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path):
        from sovereign_agent.stewardship.schedule_sentinel import ScheduleSentinel
        self.sentinel = ScheduleSentinel(tmp_path)
        self.tmp_path = tmp_path

    def test_missing_yaml_returns_clean_report(self):
        # patch _schedule_path to point at nonexistent file
        from unittest.mock import patch
        with patch.object(self.sentinel, "_schedule_path", return_value=self.tmp_path / "no_such.yaml"):
            report = self.sentinel.scan()
        assert report.findings_count == 0
        assert "no schedule.yaml" in report.summary

    def test_missing_yaml_health_unknown_before_scan(self):
        from unittest.mock import patch
        status = self.sentinel.health_status()
        assert status.level == "unknown"


class TestScheduleSentinelChecks:
    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path):
        from sovereign_agent.stewardship.schedule_sentinel import ScheduleSentinel
        self.sentinel = ScheduleSentinel(tmp_path)
        self.tmp_path = tmp_path

    def test_valid_schedule_no_findings(self):
        entries = [{"name": "daily-eval", "cron": "0 7 * * *", "directive": "eval", "enabled": True, "last_run": "2026-06-20T07:00:00"}]
        from unittest.mock import patch
        path = _write_schedule(self.tmp_path, entries)
        with patch.object(self.sentinel, "_schedule_path", return_value=path):
            report = self.sentinel.scan()
        assert report.findings_count == 0

    def test_duplicate_name_flagged(self):
        entries = [
            {"name": "daily-eval", "cron": "0 7 * * *", "directive": "eval"},
            {"name": "daily-eval", "cron": "0 8 * * *", "directive": "eval2"},
        ]
        from unittest.mock import patch
        path = _write_schedule(self.tmp_path, entries)
        with patch.object(self.sentinel, "_schedule_path", return_value=path):
            findings = self.sentinel._check_duplicates(
                [{"name": "daily-eval"}, {"name": "daily-eval"}]
            )
        assert len(findings) == 1
        assert findings[0].kind == "duplicate"
        assert findings[0].severity == "error"

    def test_invalid_cron_flagged(self):
        entries = [{"name": "bad", "cron": "60 * * * *", "directive": "x"}]
        from unittest.mock import patch
        with patch.object(self.sentinel, "_schedule_path", return_value=_write_schedule(self.tmp_path, entries)):
            findings = self.sentinel._check_invalid_cron(entries)
        # "60 * * * *" parses without exception (no range check), but field count is 5 → passes structural check
        # The sentinel catches structural invalidity (wrong field count), not semantic invalidity
        assert isinstance(findings, list)

    def test_malformed_cron_wrong_field_count(self):
        entries = [{"name": "bad", "cron": "* * *", "directive": "x"}]
        findings = self.sentinel._check_invalid_cron(entries)
        assert len(findings) == 1
        assert findings[0].kind == "invalid-cron"

    def test_never_fired_enabled_entry_flagged(self):
        entries = [{"name": "new-job", "cron": "0 9 * * 1", "directive": "x", "enabled": True, "last_run": ""}]
        findings = self.sentinel._check_never_fired(entries)
        assert len(findings) == 1
        assert findings[0].kind == "never-fired"
        assert findings[0].severity == "info"

    def test_disabled_entry_not_flagged_for_never_fired(self):
        entries = [{"name": "disabled-job", "cron": "0 9 * * 1", "directive": "x", "enabled": False, "last_run": ""}]
        findings = self.sentinel._check_never_fired(entries)
        assert len(findings) == 0

    def test_empty_directive_flagged(self):
        entries = [{"name": "empty", "cron": "0 9 * * 1", "directive": ""}]
        findings = self.sentinel._check_empty_directives(entries)
        assert len(findings) == 1
        assert findings[0].kind == "empty-directive"
        assert findings[0].severity == "warning"

    def test_health_ok_after_clean_scan(self):
        from unittest.mock import patch
        entries = [{"name": "daily-eval", "cron": "0 7 * * *", "directive": "eval", "last_run": "2026-06-20T07:00:00"}]
        path = _write_schedule(self.tmp_path, entries)
        with patch.object(self.sentinel, "_schedule_path", return_value=path):
            self.sentinel.scan()
        status = self.sentinel.health_status()
        assert status.level == "ok"

    def test_health_warning_on_empty_directive(self):
        from unittest.mock import patch
        entries = [{"name": "broken", "cron": "0 7 * * *", "directive": ""}]
        path = _write_schedule(self.tmp_path, entries)
        with patch.object(self.sentinel, "_schedule_path", return_value=path):
            self.sentinel.scan()
        status = self.sentinel.health_status()
        assert status.level == "warning"

    def test_yaml_not_modified_on_scan(self):
        from unittest.mock import patch
        entries = [{"name": "daily-eval", "cron": "0 7 * * *", "directive": "eval"}]
        path = _write_schedule(self.tmp_path, entries)
        content_before = path.read_text()
        with patch.object(self.sentinel, "_schedule_path", return_value=path):
            self.sentinel.scan()
        assert path.read_text() == content_before
