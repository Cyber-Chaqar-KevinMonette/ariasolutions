"""Behavior tests for aria-path-scan-triage, promoted to live tests/ —
tests the REAL, already-patched path_scan package directly. Plain imports,
no shadow copy.
"""
from __future__ import annotations

from pathlib import Path


def _make_module(repo: Path, name: str, *, mark: str | None = None,
                 landed: bool = False, payload_rel: str | None = None,
                 bad_line: str = 'p = "/tmp/hardcoded/scratch.txt"') -> Path:
    """Synthesize a staged module with one deliberate false-path block."""
    mod = repo / name
    (mod / "payload" / "src" / "sovereign_agent").mkdir(parents=True)
    src_root = repo / "src" / "sovereign_agent"
    src_root.mkdir(parents=True, exist_ok=True)

    if mark is not None:
        (mod / "patcher.py").write_text(f'MARK = "{mark}"\n', encoding="utf-8")
        if landed:
            (src_root / f"{name.replace('-', '_')}_target.py").write_text(
                f"# {mark}\n", encoding="utf-8"
            )
    rel = payload_rel or "gym_synth.py"
    (mod / "payload" / "src" / "sovereign_agent" / rel).write_text(
        f"{bad_line}\n", encoding="utf-8"
    )
    if landed and mark is None:
        (src_root / rel).write_text("# landed\n", encoding="utf-8")
    return mod


# ── triage classification ─────────────────────────────────────────────────


def test_classify_applied_by_mark(tmp_path):
    from sovereign_agent.path_scan.triage import SrcIndex, classify_module

    mod = _make_module(tmp_path, "aria-landed", mark="landed-d", landed=True)
    index = SrcIndex.build(tmp_path / "src" / "sovereign_agent")
    assert classify_module(mod, index) == "applied"


def test_classify_pending_by_mark(tmp_path):
    from sovereign_agent.path_scan.triage import SrcIndex, classify_module

    mod = _make_module(tmp_path, "aria-unlanded", mark="unlanded-d", landed=False)
    index = SrcIndex.build(tmp_path / "src" / "sovereign_agent")
    assert classify_module(mod, index) == "pending"


def test_classify_applied_by_payload_presence(tmp_path):
    from sovereign_agent.path_scan.triage import SrcIndex, classify_module

    mod = _make_module(tmp_path, "aria-copied", landed=True)
    index = SrcIndex.build(tmp_path / "src" / "sovereign_agent")
    assert classify_module(mod, index) == "applied"


def test_classify_unknown_without_patcher_or_payload(tmp_path):
    from sovereign_agent.path_scan.triage import SrcIndex, classify_module

    mod = tmp_path / "aria-docs-only"
    mod.mkdir()
    (mod / "README.md").write_text("just docs", encoding="utf-8")
    index = SrcIndex.build(tmp_path / "src" / "sovereign_agent")
    assert classify_module(mod, index) == "unknown"


# ── scan_repo downgrade ───────────────────────────────────────────────────


def test_scan_repo_downgrades_applied_module_blocks_to_historical(tmp_path):
    from sovereign_agent.path_scan.scanner import scan_repo

    _make_module(tmp_path, "aria-landed", mark="landed-d", landed=True)
    result = scan_repo(tmp_path)
    assert result.blocks == [], [f.kind for f in result.blocks]
    historical = [f for f in result.findings if f.kind.startswith("historical/")]
    assert historical, "applied module's block was not historicized"
    assert all(f.severity == "warn" for f in historical)
    assert all("[applied module]" in f.message for f in historical)


def test_scan_repo_keeps_blocks_for_pending_modules(tmp_path):
    from sovereign_agent.path_scan.scanner import scan_repo

    _make_module(tmp_path, "aria-unlanded", mark="unlanded-d", landed=False)
    result = scan_repo(tmp_path)
    assert result.blocks, "pending module's real block was wrongly downgraded"


def test_scan_repo_status_aware_false_restores_old_behavior(tmp_path):
    from sovereign_agent.path_scan.scanner import scan_repo

    _make_module(tmp_path, "aria-landed", mark="landed-d", landed=True)
    result = scan_repo(tmp_path, status_aware=False)
    assert result.blocks, "status_aware=False must scan exactly as before"


def test_scan_one_keeps_full_block_semantics_even_for_applied_modules(tmp_path):
    """THE safety property: the apply-time gate never downgrades — an
    applied-classified module re-run through scan_one still blocks."""
    from sovereign_agent.path_scan.scanner import scan_one

    _make_module(tmp_path, "aria-landed", mark="landed-d", landed=True)
    result = scan_one(tmp_path, "landed")
    assert result.blocks, "scan_one must never historicize"


# ── the real repo ─────────────────────────────────────────────────────────


def test_real_repo_scan_has_zero_blocks_now():
    """The actual bloodwork result this module exists for: the live fleet
    scan is block-free (the 32 historical findings are warns now)."""
    import sovereign_agent
    from sovereign_agent.path_scan.scanner import scan_repo

    repo_root = Path(sovereign_agent.__file__).parent.parent.parent
    result = scan_repo(repo_root)
    assert result.blocks == [], [
        f"{f.module}/{f.path}:{f.line} {f.kind}" for f in result.blocks
    ]


def test_real_repo_triage_report_shape():
    import sovereign_agent
    from sovereign_agent.path_scan.triage import triage_report

    repo_root = Path(sovereign_agent.__file__).parent.parent.parent
    report = triage_report(repo_root)
    assert report["counts"]["applied"] > 50  # the overwhelming majority
    assert set(report) == {"counts", "applied", "pending", "unknown"}
