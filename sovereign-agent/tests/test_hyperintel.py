"""Behavior tests for aria-hyperintel — prove the bounded SCAN->CROSS->AUDIT->
DISTILL pass actually cross-validates (a claim in 2+ sources is convergent, a
claim in only 1 is flagged low-confidence), respects the max_sources cap
(never reads more than the bound), and always terminates (single pass, no
autonomous re-querying)."""
from __future__ import annotations

import asyncio

import pytest

from sovereign_agent.hyperintel import audit, cross_validate, run, scan


def _write(tmp_path, name: str, text: str):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return str(p)


# ─── scan: bounded reading ───────────────────────────────────────────────────

def test_scan_reads_provided_files(tmp_path):
    p1 = _write(tmp_path, "a.txt", "hello world\n")
    p2 = _write(tmp_path, "b.txt", "goodbye world\n")
    sources = scan([p1, p2], max_sources=8)
    assert {s.name for s in sources} == {"a.txt", "b.txt"}


def test_scan_never_exceeds_max_sources(tmp_path):
    paths = [_write(tmp_path, f"f{i}.txt", f"content {i}\n") for i in range(10)]
    sources = scan(paths, max_sources=3)
    assert len(sources) == 3


def test_scan_skips_unreadable_paths_without_crashing(tmp_path):
    sources = scan(["/no/such/path/exists.txt"], max_sources=8)
    assert sources == []


# ─── cross-validation: the actual claim ─────────────────────────────────────

def test_convergent_claim_found_across_two_sources(tmp_path):
    p1 = _write(tmp_path, "a.txt", "the cockpit crash was caused by a regression\n")
    p2 = _write(tmp_path, "b.txt", "regression caused the cockpit crash\n")
    sources = scan([p1, p2], max_sources=8)
    convergent, single = cross_validate(sources)
    assert len(convergent) >= 1
    assert set(convergent[0].source_names) == {"a.txt", "b.txt"}


def test_single_source_claim_is_flagged_not_promoted(tmp_path):
    p1 = _write(tmp_path, "a.txt", "an entirely unique unverified claim appears here\n")
    sources = scan([p1], max_sources=8)
    convergent, single = cross_validate(sources)
    assert convergent == []
    assert len(single) == 1
    assert single[0].source_names == ["a.txt"]


def test_unrelated_lines_from_different_sources_do_not_falsely_converge(tmp_path):
    p1 = _write(tmp_path, "a.txt", "the weather today is sunny and warm\n")
    p2 = _write(tmp_path, "b.txt", "database migrations must run before deploy\n")
    sources = scan([p1, p2], max_sources=8)
    convergent, _ = cross_validate(sources)
    assert convergent == []


# ─── audit: risk/uncertainty is named ───────────────────────────────────────

def test_audit_flags_insufficient_sources(tmp_path):
    p1 = _write(tmp_path, "a.txt", "only one source here\n")
    sources = scan([p1], max_sources=8)
    convergent, single = cross_validate(sources)
    risks = audit(sources, convergent, single)
    assert any("only 1 source" in r for r in risks)


def test_audit_flags_no_readable_sources():
    risks = audit([], [], [])
    assert any("no sources were readable" in r for r in risks)


# ─── the full bounded run() always terminates and has all 4 sections ───────

def test_run_terminates_and_report_has_all_sections(tmp_path):
    p1 = _write(tmp_path, "a.txt", "aria's cockpit crash was fixed by a full restore\n")
    p2 = _write(tmp_path, "b.txt", "the cockpit crash was fixed via a full restore\n")
    report = run("what fixed the crash?", [p1, p2], max_sources=8)

    md = report.to_markdown()
    for heading in ("## Scan", "## Cross-Validation", "## Audit", "## Distillation"):
        assert heading in md
    assert report.question == "what fixed the crash?"
    assert len(report.sources_scanned) == 2


def test_run_with_no_sources_still_terminates_cleanly():
    report = run("a question with nothing to go on", [])
    assert report.sources_scanned == []
    assert "No evidence" in report.distillation


def test_run_respects_max_sources_even_with_many_paths(tmp_path):
    paths = [_write(tmp_path, f"f{i}.txt", f"claim number {i} appears\n") for i in range(20)]
    report = run("q", paths, max_sources=4)
    assert len(report.sources_scanned) == 4


# ─── the Tool wrapper ────────────────────────────────────────────────────────

def test_tool_execute_returns_markdown_report(tmp_path):
    from sovereign_agent.tools.hyperintel_tool import HyperIntelTool, _HyperIntelArgs

    p1 = _write(tmp_path, "a.txt", "the fix worked as intended\n")
    p2 = _write(tmp_path, "b.txt", "the fix worked as intended, confirmed\n")
    tool = HyperIntelTool()
    args = _HyperIntelArgs(question="did the fix work?", source_paths=[p1, p2])
    result = asyncio.run(tool.execute(args, trace_id="t1"))
    assert result.ok
    assert "## Distillation" in result.output
    assert result.metadata["sources_scanned"] == 2


def test_tool_rejects_empty_question():
    from sovereign_agent.tools.hyperintel_tool import HyperIntelTool, _HyperIntelArgs

    tool = HyperIntelTool()
    args = _HyperIntelArgs(question="   ", source_paths=[])
    result = asyncio.run(tool.execute(args, trace_id="t1"))
    assert not result.ok
    assert "empty" in result.error
