"""Tests for atoms compact sentinel + tools (M54 / RISK-008)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ─── Sentinel ────────────────────────────────────────────────────────────

class TestAtomsCompactSentinelContract:
    def setup_method(self, tmp_path=None):
        import tempfile
        self._tmpdir = tempfile.mkdtemp()
        from sovereign_agent.stewardship.atoms_compact_sentinel import AtomsCompactSentinel
        self.sentinel = AtomsCompactSentinel(Path(self._tmpdir))

    def test_id(self):
        assert self.sentinel.id == "atoms-compact"

    def test_title_non_empty(self):
        assert len(self.sentinel.title) > 5

    def test_tier_is_1(self):
        assert self.sentinel.tier == 1

    def test_articles_non_empty(self):
        arts = self.sentinel.articles()
        assert len(arts) >= 4
        assert all(isinstance(a, str) for a in arts)

    def test_registered(self):
        from sovereign_agent.stewardship.registry import registered_ids
        ids = registered_ids()
        assert "atoms-compact" in ids


class TestAtomsCompactSentinelThresholds:
    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path):
        from sovereign_agent.stewardship.atoms_compact_sentinel import AtomsCompactSentinel
        self.sentinel = AtomsCompactSentinel(tmp_path)

    def test_check_count_ok_below_warn(self):
        stats = {"total": 100, "active": 100, "superseded": 0, "superseded_pct": 0,
                 "old_count": 0, "old_days": 90, "by_type": {}, "db_mb": 1.0, "oldest_at": None}
        findings = self.sentinel._check_count(stats)
        assert findings == []

    def test_check_count_warning(self):
        stats = {"total": 6_000}
        findings = self.sentinel._check_count(stats)
        assert len(findings) == 1
        assert findings[0].severity == "warning"
        assert findings[0].kind == "count"

    def test_check_count_alert(self):
        stats = {"total": 25_000}
        findings = self.sentinel._check_count(stats)
        assert len(findings) == 1
        assert findings[0].severity == "alert"

    def test_check_size_ok(self):
        stats = {"total": 10, "db_mb": 5.0}
        findings = self.sentinel._check_size(stats)
        assert findings == []

    def test_check_size_warning(self):
        stats = {"total": 1000, "db_mb": 150.0}
        findings = self.sentinel._check_size(stats)
        assert len(findings) == 1
        assert findings[0].severity == "warning"

    def test_check_size_alert(self):
        stats = {"total": 1000, "db_mb": 600.0}
        findings = self.sentinel._check_size(stats)
        assert len(findings) == 1
        assert findings[0].severity == "alert"

    def test_check_superseded_ok(self):
        stats = {"superseded_pct": 10, "superseded": 10}
        findings = self.sentinel._check_superseded(stats)
        assert findings == []

    def test_check_superseded_warning(self):
        stats = {"superseded_pct": 45, "superseded": 450}
        findings = self.sentinel._check_superseded(stats)
        assert len(findings) == 1
        assert findings[0].severity == "warning"

    def test_check_superseded_alert(self):
        stats = {"superseded_pct": 65, "superseded": 650}
        findings = self.sentinel._check_superseded(stats)
        assert len(findings) == 1
        assert findings[0].severity == "alert"

    def test_check_age_no_old(self):
        stats = {"old_count": 0, "old_days": 90, "oldest_at": None}
        findings = self.sentinel._check_age(stats)
        assert findings == []

    def test_check_age_with_old(self):
        stats = {"old_count": 5, "old_days": 90, "oldest_at": "2026-01-01T00:00:00Z"}
        findings = self.sentinel._check_age(stats)
        assert len(findings) == 1
        assert findings[0].severity == "info"
        assert "90" in findings[0].summary

    def test_check_hotspot_dominant_type(self):
        stats = {"total": 100, "by_type": {"lesson": 60, "experience": 40}}
        findings = self.sentinel._check_hotspot(stats)
        assert any(f.kind == "hotspot" for f in findings)
        assert any(f.severity == "info" for f in findings)

    def test_check_hotspot_no_dominance(self):
        stats = {"total": 100, "by_type": {"lesson": 30, "experience": 30, "other": 40}}
        findings = self.sentinel._check_hotspot(stats)
        # 40% < 50% threshold → no hotspot finding
        assert all(f.kind != "hotspot" for f in findings)

    def test_check_hotspot_empty_store(self):
        stats = {"total": 0, "by_type": {}}
        findings = self.sentinel._check_hotspot(stats)
        assert findings == []


class TestAtomsCompactSentinelHealthStatus:
    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path):
        from sovereign_agent.stewardship.atoms_compact_sentinel import AtomsCompactSentinel
        self.sentinel = AtomsCompactSentinel(tmp_path)

    def test_health_unknown_before_scan(self):
        with patch.object(self.sentinel, "load_catalog", return_value=None):
            status = self.sentinel.health_status()
        assert status.level == "unknown"
        assert status.sentinel_id == "atoms-compact"

    def test_health_ok(self):
        catalog = {
            "scanned_at": "2026-06-20T00:00:00Z",
            "stats": {"total": 10, "db_mb": 1.0},
            "counts": {"alert": 0, "warning": 0, "info": 0},
        }
        with patch.object(self.sentinel, "load_catalog", return_value=catalog):
            status = self.sentinel.health_status()
        assert status.level == "ok"

    def test_health_warning(self):
        catalog = {
            "scanned_at": "2026-06-20T00:00:00Z",
            "stats": {"total": 6000, "db_mb": 10.0},
            "counts": {"alert": 0, "warning": 1, "info": 0},
        }
        with patch.object(self.sentinel, "load_catalog", return_value=catalog):
            status = self.sentinel.health_status()
        assert status.level == "warning"

    def test_health_error(self):
        catalog = {
            "scanned_at": "2026-06-20T00:00:00Z",
            "stats": {"total": 25000, "db_mb": 500.0},
            "counts": {"alert": 2, "warning": 0, "info": 0},
        }
        with patch.object(self.sentinel, "load_catalog", return_value=catalog):
            status = self.sentinel.health_status()
        assert status.level == "error"


# ─── Compact Tools ────────────────────────────────────────────────────────

class TestAtomsCompactPreviewTool:
    def setup_method(self):
        from sovereign_agent.tools.atoms_compact_tool import AtomsCompactPreviewTool
        self.tool = AtomsCompactPreviewTool()

    def test_tier_is_0(self):
        assert self.tool.tier == 0

    def test_name(self):
        assert self.tool.name == "atoms_compact_preview"

    def test_failure_modes_declared(self):
        assert len(self.tool.failure_modes) >= 1

    @pytest.mark.asyncio
    async def test_preview_no_candidates(self):
        with patch("sovereign_agent.tools.atoms_compact_tool._gather_candidates", return_value=[]):
            result = await self.tool.execute(
                self.tool.Args(before_days=90), trace_id="t1"
            )
        assert result.ok
        assert result.output["candidates"] == 0
        assert "Nothing to compact" in result.output["message"]

    @pytest.mark.asyncio
    async def test_preview_with_candidates(self):
        candidates = [
            {"atom_id": "a1", "type": "lesson", "summary": "test", "created_at": "2026-01-01T00:00:00Z"},
            {"atom_id": "a2", "type": "lesson", "summary": "test2", "created_at": "2026-01-15T00:00:00Z"},
        ]
        with patch("sovereign_agent.tools.atoms_compact_tool._gather_candidates", return_value=candidates):
            result = await self.tool.execute(
                self.tool.Args(before_days=90), trace_id="t1"
            )
        assert result.ok
        assert result.output["candidates"] == 2
        assert result.output["groups"] == 1  # both in 2026-01
        assert len(result.output["breakdown"]) == 1


class TestAtomsCompactTool:
    def setup_method(self):
        from sovereign_agent.tools.atoms_compact_tool import AtomsCompactTool
        self.tool = AtomsCompactTool()

    def test_tier_is_2(self):
        assert self.tool.tier == 2

    def test_name(self):
        assert self.tool.name == "atoms_compact"

    def test_dry_run_default_is_true(self):
        instance = self.tool.Args(before_days=90)
        assert instance.dry_run is True

    def test_failure_modes_declared(self):
        assert len(self.tool.failure_modes) >= 1

    @pytest.mark.asyncio
    async def test_dry_run_shows_no_changes(self):
        candidates = [
            {"atom_id": "a1", "type": "lesson", "summary": "s1", "created_at": "2026-01-01T00:00:00Z"},
        ]
        with patch("sovereign_agent.tools.atoms_compact_tool._gather_candidates", return_value=candidates):
            result = await self.tool.execute(
                self.tool.Args(before_days=90, dry_run=True), trace_id="t1"
            )
        assert result.ok
        assert result.output["dry_run"] is True
        assert "DRY RUN" in result.output["message"]

    @pytest.mark.asyncio
    async def test_no_candidates_ok(self):
        with patch("sovereign_agent.tools.atoms_compact_tool._gather_candidates", return_value=[]):
            result = await self.tool.execute(
                self.tool.Args(before_days=90), trace_id="t1"
            )
        assert result.ok
        assert "Nothing to compact" in result.output["message"]


class TestAtomsCompactStatusTool:
    def setup_method(self):
        from sovereign_agent.tools.atoms_compact_tool import AtomsCompactStatusTool
        self.tool = AtomsCompactStatusTool()

    def test_tier_is_0(self):
        assert self.tool.tier == 0

    def test_name(self):
        assert self.tool.name == "atoms_compact_status"

    def test_failure_modes_declared(self):
        assert len(self.tool.failure_modes) >= 1

    @pytest.mark.asyncio
    async def test_returns_health_info(self):
        mock_sentinel = MagicMock()
        mock_sentinel.scan.return_value = MagicMock(summary="0 alert, 0 warning, 0 info — 22 atoms / 4.1 MB")
        mock_sentinel.load_catalog.return_value = {
            "stats": {"total": 22, "active": 22, "superseded": 0, "superseded_pct": 0,
                      "db_mb": 4.1, "oldest_at": "2026-05-10T00:00:00Z",
                      "old_count": 0, "old_days": 90, "by_type": {"lessons": 20}},
            "findings": [],
        }
        with patch("sovereign_agent.stewardship.registry.instantiate", return_value=mock_sentinel):
            result = await self.tool.execute(self.tool.Args(), trace_id="t1")
        assert result.ok
        assert result.output["total"] == 22
        assert result.output["db_mb"] == 4.1


# ─── Grouping helper ─────────────────────────────────────────────────────

class TestGroupByTypeMonth:
    def test_groups_correctly(self):
        from sovereign_agent.tools.atoms_compact_tool import _group_by_type_month
        candidates = [
            {"atom_id": "a1", "type": "lesson", "summary": "s1", "created_at": "2026-01-05T00:00:00Z"},
            {"atom_id": "a2", "type": "lesson", "summary": "s2", "created_at": "2026-01-20T00:00:00Z"},
            {"atom_id": "a3", "type": "experience", "summary": "s3", "created_at": "2026-01-10T00:00:00Z"},
            {"atom_id": "a4", "type": "lesson", "summary": "s4", "created_at": "2026-02-01T00:00:00Z"},
        ]
        groups = _group_by_type_month(candidates)
        assert ("lesson", "2026-01") in groups
        assert len(groups[("lesson", "2026-01")]) == 2
        assert ("lesson", "2026-02") in groups
        assert len(groups[("lesson", "2026-02")]) == 1
        assert ("experience", "2026-01") in groups

    def test_empty_input(self):
        from sovereign_agent.tools.atoms_compact_tool import _group_by_type_month
        assert _group_by_type_month([]) == {}

    def test_all_same_type_month(self):
        from sovereign_agent.tools.atoms_compact_tool import _group_by_type_month
        candidates = [
            {"atom_id": f"a{i}", "type": "lesson", "summary": f"s{i}", "created_at": f"2026-03-0{i+1}T00:00:00Z"}
            for i in range(3)
        ]
        groups = _group_by_type_month(candidates)
        assert len(groups) == 1
        assert ("lesson", "2026-03") in groups
        assert len(groups[("lesson", "2026-03")]) == 3
