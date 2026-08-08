"""Behavior tests for aria-path-sentinel — prove the scanner catches the
defects it claims to, and stays quiet when the module is clean."""
from __future__ import annotations

from pathlib import Path

from sovereign_agent.path_scan import scan_module, scan_repo, scan_text


# ─── helpers ──────────────────────────────────────────────────────────────

def _make_module(repo: Path, name: str, *, code: str = "",
                 rel: str = "demo/mod.py", apply: str | None = None) -> Path:
    """Create a minimal aria-<name>/ staged module with one payload file."""
    mod = repo / f"aria-{name}"
    payload = mod / "payload" / "src" / "sovereign_agent"
    target = payload / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(code, encoding="utf-8")
    if apply is not None:
        (mod / f"apply_{name.replace('-', '_')}.sh").write_text(apply, encoding="utf-8")
    return mod


# ─── false / test paths (the named flaw) ──────────────────────────────────

def test_flags_test_path_left_in_shipped_code(tmp_path):
    mod = _make_module(tmp_path, "leaky", code='DATA = open("tests/fixtures/x.json")\n')
    findings = scan_module(mod)
    kinds = {f.kind for f in findings}
    assert "false-path/test-dir" in kinds
    assert any(f.severity == "block" for f in findings)


def test_flags_test_import_in_shipped_code(tmp_path):
    mod = _make_module(tmp_path, "imptest", code="from tests.helpers import thing\n")
    findings = scan_module(mod)
    assert any(f.kind == "false-path/test-import" and f.severity == "block" for f in findings)


def test_flags_machine_specific_absolute_path(tmp_path):
    mod = _make_module(tmp_path, "abs", code='ROOT = "/home/kmon/secret/data"\n')
    findings = scan_module(mod)
    assert any(f.kind == "false-path/absolute-home" and f.severity == "block" for f in findings)


def test_flags_temp_path(tmp_path):
    mod = _make_module(tmp_path, "tmp", code='CACHE = "/tmp/aria-cache"\n')
    findings = scan_module(mod)
    assert any(f.kind == "false-path/temp" and f.severity == "block" for f in findings)


def test_flags_placeholder_path(tmp_path):
    mod = _make_module(tmp_path, "ph", code='MODEL = "/path/to/model.bin"\n')
    findings = scan_module(mod)
    assert any(f.kind == "false-path/placeholder" and f.severity == "block" for f in findings)


# ─── precision: don't cry wolf ────────────────────────────────────────────

def test_clean_module_has_no_blocks(tmp_path):
    mod = _make_module(
        tmp_path, "clean",
        code='from pathlib import Path\nROOT = Path(__file__).parent\n',
        apply="cp payload/src/sovereign_agent/demo/mod.py src/sovereign_agent/demo/\n",
    )
    result_findings = scan_module(mod)
    assert [f for f in result_findings if f.severity == "block"] == []


def test_false_path_in_comment_is_info_not_block(tmp_path):
    mod = _make_module(tmp_path, "cmt", code='# example: /home/kmon/notes.txt\nX = 1\n')
    findings = scan_module(mod)
    home = [f for f in findings if f.kind == "false-path/absolute-home"]
    assert home, "should still surface the comment"
    assert all(f.severity == "info" for f in home), "a comment never blocks"


def test_test_file_in_payload_may_reference_tests(tmp_path):
    # a payload that ships a test fixture under tests/ is allowed to say "tests/"
    mod = _make_module(tmp_path, "fix", rel="demo/tests/test_demo.py",
                       code='PATH = "tests/data"\n')
    findings = scan_module(mod)
    assert [f for f in findings if f.severity == "block"] == []


# ─── anti-ghost ───────────────────────────────────────────────────────────

def test_flags_payload_not_mirroring_src(tmp_path):
    mod = tmp_path / "aria-ghost"
    stray = mod / "payload" / "stray.py"      # NOT under payload/src/sovereign_agent
    stray.parent.mkdir(parents=True)
    stray.write_text("X = 1\n", encoding="utf-8")
    findings = scan_module(mod)
    assert any(f.kind == "ghost/mirror" for f in findings)


def test_flags_tool_module_without_registration_anchor(tmp_path):
    mod = _make_module(tmp_path, "tooly", rel="tools/tooly_tools.py",
                       code="class ToolyTool: pass\n",
                       apply="cp payload/src/sovereign_agent/tools/tooly_tools.py src/sovereign_agent/tools/\n")
    findings = scan_module(mod)
    assert any(f.kind == "ghost/no-registration" and f.severity == "block" for f in findings)


# ─── anti-zombie ──────────────────────────────────────────────────────────

def test_flags_bak_file_in_payload(tmp_path):
    mod = _make_module(tmp_path, "zomb", code="X = 1\n")
    bak = mod / "payload" / "src" / "sovereign_agent" / "demo" / "mod.py.bak.20260101"
    bak.write_text("old\n", encoding="utf-8")
    findings = scan_module(mod)
    assert any(f.kind == "zombie/bak" for f in findings)


def test_apply_script_copying_to_tmp_is_blocked(tmp_path):
    mod = _make_module(tmp_path, "badcp", code="X = 1\n",
                       apply='cp payload/src/sovereign_agent/demo/mod.py /tmp/mod.py\n')
    findings = scan_module(mod)
    assert any(f.kind == "false-path/temp" and f.severity == "block" for f in findings)


# ─── repo-level aggregation ───────────────────────────────────────────────

def test_scan_repo_aggregates_and_reports_clean(tmp_path):
    _make_module(tmp_path, "a", code="X = 1\n")
    _make_module(tmp_path, "b", code='BAD = "/tmp/x"\n')
    result = scan_repo(tmp_path)
    assert result.modules_scanned == 2
    assert not result.clean            # module b blocks
    assert result.for_module("aria-b")
    assert result.for_module("aria-a") == []


def test_allow_pragma_exempts_a_reviewed_line(tmp_path):
    mod = _make_module(tmp_path, "pragma",
                       code='BAD = "/tmp/x"  # path-scan: allow\nfine = 1\n')
    findings = scan_module(mod)
    assert [f for f in findings if f.severity == "block"] == []


def test_scanner_does_not_self_flag(tmp_path):
    # The scanner's own pattern table names /tmp, /home, tests/ etc. inside
    # regexes — those reviewed lines carry the allow pragma and must not block.
    repo_root = Path(__file__).resolve().parents[1]   # the aria-path-sentinel/ folder's parent is repo
    # scan just this module's payload
    mod = Path(__file__).resolve().parents[1]
    findings = scan_module(mod)
    assert [f for f in findings if f.severity == "block"] == [], \
        [f"{f.path}:{f.line} {f.kind}" for f in findings if f.severity == "block"]


def test_scan_text_directly():
    findings = scan_text('p = "/home/someone/x"\n', module="m", rel_path="x.py")
    assert any(f.kind == "false-path/absolute-home" for f in findings)


# ─── sentinel wrapper registers and reports ───────────────────────────────

def test_sentinel_registers_and_reports(tmp_path):
    from sovereign_agent.path_scan.sentinel import PathSentinel
    from sovereign_agent.stewardship.registry import get_sentinel_class

    assert get_sentinel_class("path") is PathSentinel
    s = PathSentinel(tmp_path)
    health = s.health_status()
    assert health.sentinel_id == "path"
    assert health.level in ("ok", "warning", "error")
