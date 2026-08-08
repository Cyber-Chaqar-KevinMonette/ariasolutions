"""Tests for M57 — Risk Register tools."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_REGISTER = """\
# Aria — Weakness & Risk Register

### 🔴 Critical

---
**RISK-001 — Hard ceiling.**
`Category: Hardware · Confidence: Observed · Status: ACCEPTED · Owner: Kevin`
Detail text here.

---
**RISK-002 — Junior model.**
`Category: Model · Confidence: Observed/Inferred · Status: MITIGATING · Owner: Kevin`
More detail.

### 🟡 Material

---
**RISK-003 — Surface area.**
`Category: Sustainability · Confidence: Observed · Status: OPEN · Owner: Kevin`
Blah blah.

---
**RISK-004 — Unproven value.**
`Category: Product/Validation · Confidence: Observed · Status: OPEN · Owner: Kevin`
Another one.

### 🟢 Watch

---
**RISK-005 — Hash friction.**
`Category: Ops · Confidence: Inferred · Status: WATCH · Owner: Kevin`
Watch item.
"""


def _parse(text: str):
    from sovereign_agent.tools.risk_tools import _parse_register
    return _parse_register(text)


# ---------------------------------------------------------------------------
# Test: parsing
# ---------------------------------------------------------------------------

class TestRiskParsing:
    def test_parses_all_risks(self):
        risks = _parse(SAMPLE_REGISTER)
        assert len(risks) == 5

    def test_risk_ids_correct(self):
        risks = _parse(SAMPLE_REGISTER)
        ids = [r["id"] for r in risks]
        assert ids == ["RISK-001", "RISK-002", "RISK-003", "RISK-004", "RISK-005"]

    def test_status_parsed(self):
        risks = _parse(SAMPLE_REGISTER)
        by_id = {r["id"]: r for r in risks}
        assert by_id["RISK-001"]["status"] == "ACCEPTED"
        assert by_id["RISK-002"]["status"] == "MITIGATING"
        assert by_id["RISK-003"]["status"] == "OPEN"
        assert by_id["RISK-005"]["status"] == "WATCH"

    def test_severity_glyph_mapped(self):
        risks = _parse(SAMPLE_REGISTER)
        by_id = {r["id"]: r for r in risks}
        assert by_id["RISK-001"]["severity"] == "critical"
        assert by_id["RISK-003"]["severity"] == "material"
        assert by_id["RISK-005"]["severity"] == "watch"

    def test_category_parsed(self):
        risks = _parse(SAMPLE_REGISTER)
        by_id = {r["id"]: r for r in risks}
        assert by_id["RISK-001"]["category"] == "Hardware"
        assert by_id["RISK-003"]["category"] == "Sustainability"

    def test_owner_parsed(self):
        risks = _parse(SAMPLE_REGISTER)
        by_id = {r["id"]: r for r in risks}
        assert by_id["RISK-001"]["owner"] == "Kevin"

    def test_full_register_14_risks(self):
        reg = Path(__file__).parents[1] / "docs" / "Aria_Weakness_Risk_Register.md"
        if not reg.is_file():
            pytest.skip("register not found in working tree")
        risks = _parse(reg.read_text())
        assert len(risks) == 14, f"expected 14 risks, got {len(risks)}: {[r['id'] for r in risks]}"

    def test_real_register_key_risks_present(self):
        reg = Path(__file__).parents[1] / "docs" / "Aria_Weakness_Risk_Register.md"
        if not reg.is_file():
            pytest.skip("register not found")
        risks = _parse(reg.read_text())
        statuses = {r["id"]: r["status"] for r in risks}
        assert "RISK-004" in statuses
        assert "RISK-008" in statuses
        assert "RISK-011" in statuses


# ---------------------------------------------------------------------------
# Test: RiskRegisterReadTool
# ---------------------------------------------------------------------------

class TestRiskRegisterReadTool:
    @pytest.fixture(autouse=True)
    def _setup(self):
        from sovereign_agent.tools.risk_tools import RiskRegisterReadTool
        self.tool = RiskRegisterReadTool()

    def test_tier_is_0(self):
        assert self.tool.tier == 0

    def test_name(self):
        assert self.tool.name == "risk_register_read"

    @pytest.mark.asyncio
    async def test_missing_file_returns_empty_ok(self):
        with patch("sovereign_agent.tools.risk_tools._register_path", return_value=Path("/no/such/file.md")):
            result = await self.tool.execute(self.tool.Args(), trace_id="trace-01")
        assert result.ok is True
        assert result.output["total"] == 0

    @pytest.mark.asyncio
    async def test_read_sample_register(self, tmp_path):
        reg = tmp_path / "register.md"
        reg.write_text(SAMPLE_REGISTER)
        with patch("sovereign_agent.tools.risk_tools._register_path", return_value=reg):
            result = await self.tool.execute(self.tool.Args(), trace_id="trace-02")
        assert result.ok is True
        assert result.output["total"] == 5

    @pytest.mark.asyncio
    async def test_status_filter(self, tmp_path):
        reg = tmp_path / "register.md"
        reg.write_text(SAMPLE_REGISTER)
        with patch("sovereign_agent.tools.risk_tools._register_path", return_value=reg):
            result = await self.tool.execute(self.tool.Args(status_filter="OPEN"), trace_id="trace-03")
        assert result.ok is True
        assert result.output["total"] == 2  # RISK-003 and RISK-004


# ---------------------------------------------------------------------------
# Test: RiskRegisterProposeTool
# ---------------------------------------------------------------------------

class TestRiskRegisterProposeTool:
    @pytest.fixture(autouse=True)
    def _setup(self):
        from sovereign_agent.tools.risk_tools import RiskRegisterProposeTool
        self.tool = RiskRegisterProposeTool()

    def test_tier_is_1(self):
        assert self.tool.tier == 1

    def test_name(self):
        assert self.tool.name == "risk_register_propose"

    @pytest.mark.asyncio
    async def test_propose_writes_atom_not_markdown(self, tmp_path):
        """Proposal writes an atom; does not edit the markdown file."""
        reg = tmp_path / "register.md"
        reg.write_text(SAMPLE_REGISTER)
        content_before = reg.read_text()

        written = {}
        mock_conn = MagicMock()

        def _fake_write(conn, atom):
            written["atom"] = atom
            return "fake-atom-id"

        with (
            patch("sovereign_agent.tools.risk_tools.open_atoms_db", return_value=mock_conn),
            patch("sovereign_agent.tools.risk_tools.write_atom", side_effect=_fake_write),
            patch("sovereign_agent.tools.risk_tools._register_path", return_value=reg),
        ):
            result = await self.tool.execute(
                self.tool.Args(
                    risk_id="RISK-004",
                    current_status="OPEN",
                    proposed_status="MITIGATING",
                    rationale="eval-crown deployed and producing scores",
                    mitigations_deployed=["M49-eval-crown"],
                ),
                trace_id="trace-04",
            )

        assert result.ok is True
        assert reg.read_text() == content_before  # markdown unchanged
        assert "atom" in written
        assert written["atom"].type == "risk-proposal"

    @pytest.mark.asyncio
    async def test_propose_atom_type_is_risk_proposal(self):
        written = {}
        mock_conn = MagicMock()

        def _fake_write(conn, atom):
            written["atom"] = atom
            return "x"

        with (
            patch("sovereign_agent.tools.risk_tools.open_atoms_db", return_value=mock_conn),
            patch("sovereign_agent.tools.risk_tools.write_atom", side_effect=_fake_write),
        ):
            await self.tool.execute(
                self.tool.Args(
                    risk_id="RISK-008",
                    current_status="OPEN",
                    proposed_status="MITIGATING",
                    rationale="AtomsCompactSentinel monitors unbounded growth now",
                ),
                trace_id="t05",
            )

        assert written["atom"].type == "risk-proposal"
        assert "RISK-008" in written["atom"].summary

    def test_propose_requires_nonempty_rationale(self):
        from pydantic import ValidationError
        with pytest.raises((ValidationError, ValueError)):
            self.tool.Args(
                risk_id="RISK-004",
                current_status="OPEN",
                proposed_status="MITIGATING",
                rationale="ab",  # less than 10 chars
            )

    @pytest.mark.asyncio
    async def test_propose_db_unavailable_returns_error(self):
        with (
            patch("sovereign_agent.tools.risk_tools.open_atoms_db", None),
            patch("sovereign_agent.tools.risk_tools.Atom", None),
            patch("sovereign_agent.tools.risk_tools.write_atom", None),
        ):
            result = await self.tool.execute(
                self.tool.Args(
                    risk_id="RISK-011",
                    current_status="OPEN",
                    proposed_status="MITIGATING",
                    rationale="session briefs and memory persistence now implemented",
                ),
                trace_id="t06",
            )
        assert result.ok is False
        assert "unavailable" in result.error.lower()
