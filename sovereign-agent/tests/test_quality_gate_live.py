"""aria-quality-gate — wiring qa/hardening into real gates. (Quality round · Q2)

`quality/gate.py` is a brand-new file inside the already-live `quality/`
package — reachable pre-apply via the staged conftest's path extension
(unlike a whole-file replacement, a new submodule resolves fine). The
top-level `sovereign_agent.quality.gate` EXPORT (via `__init__.py`) and
the two shell-script wirings are patch-dependent and skip honestly
pre-apply; the apply script re-runs this file and requires zero skips.
"""
from __future__ import annotations

import inspect
import subprocess
import sys
import textwrap
from pathlib import Path

def _find_repo_root(start: Path) -> Path:
    """Robust to running from either the staged location (aria-quality-
    gate/tests/) or the promoted live location (tests/), which differ in
    nesting depth — the exact path-depth bug class this round already
    fixed elsewhere (test_apply_system.py, quality_gate.py's own REPO
    resolution) — a fixed parents[N] count breaks the moment the file
    moves from staged to promoted."""
    for candidate in (start, *start.parents):
        if (candidate / "src" / "sovereign_agent" / "cockpit" / "app.py").is_file():
            return candidate
    raise RuntimeError(f"could not locate repo root from {start}")


REPO_ROOT = _find_repo_root(Path(__file__).resolve())

# The CLI under test: the REAL promoted copy once applied (scripts/lib/
# quality_gate.py), falling back to the staged payload copy pre-apply —
# "works staged or live", same discipline as scrutiny.py.
_PROMOTED_CLI = REPO_ROOT / "scripts" / "lib" / "quality_gate.py"
_STAGED_CLI = (REPO_ROOT / "aria-quality-gate" / "payload" / "scripts"
              / "lib" / "quality_gate.py")
STAGED_QUALITY_GATE_CLI = _PROMOTED_CLI if _PROMOTED_CLI.is_file() else _STAGED_CLI


def _write_good_module(path: Path) -> None:
    """A module that satisfies every CRITICAL (weight-≥8) hardening check,
    not just input validation — `harden_module()`'s repo_root walk-up
    falls back to the target's own parent dir when no pyproject.toml is
    found (as in a tmp_path fixture), so `has_tests` and `observability`
    need real satisfying content here, not just a plausible-looking
    function; a fixture that only "looks good" but still fails two
    critical checks isn't testing a PASS path at all — caught live when
    this exact gap made the CLI tests assert PASS against a real BLOCK."""
    path.write_text(textwrap.dedent('''
        """A well-behaved module. Emits events (observability)."""
        from __future__ import annotations


        def add(a: int, b: int) -> int:
            if not isinstance(a, int) or not isinstance(b, int):
                raise ValueError("a and b must be int")
            emit_event = None  # placeholder call site, satisfies the checklist
            return a + b
    '''), encoding="utf-8")
    tests_dir = path.parent / "tests"
    tests_dir.mkdir(exist_ok=True)
    (tests_dir / f"test_{path.stem}.py").write_text(
        f'"""Tests for {path.stem}."""\n', encoding="utf-8")


def _write_bad_module(path: Path) -> None:
    path.write_text(textwrap.dedent('''
        def risky(x):
            try:
                return 1 / x
            except:
                pass
    '''), encoding="utf-8")


# ─── quality/gate.py — a new submodule, reachable pre-apply ──────────────


def test_gate_passes_a_clean_file(tmp_path):
    from sovereign_agent.quality.gate import gate

    good = tmp_path / "good.py"
    _write_good_module(good)
    verdict = gate([good])
    assert verdict.verdict == "PASS"
    assert verdict.critical_ok


def test_gate_blocks_a_critically_bad_file(tmp_path):
    from sovereign_agent.quality.gate import gate

    bad = tmp_path / "bad.py"
    _write_bad_module(bad)
    verdict = gate([bad])
    assert verdict.verdict == "BLOCK"
    assert not verdict.critical_ok
    assert verdict.notes


def test_gate_passes_honestly_on_empty_input():
    from sovereign_agent.quality.gate import gate

    verdict = gate([])
    assert verdict.verdict == "PASS"
    assert verdict.files_checked == 0


def test_gate_never_raises_on_a_broken_target(tmp_path):
    from sovereign_agent.quality.gate import gate

    broken = tmp_path / "broken.py"
    broken.write_text("def f(:\n", encoding="utf-8")
    verdict = gate([broken])   # must not raise
    assert verdict.verdict == "PASS"   # nothing scoreable → honest PASS


def test_gate_kill_switch(tmp_path, monkeypatch):
    from sovereign_agent.quality.gate import gate

    monkeypatch.setenv("SOV_NO_QUALITY_GATE", "1")
    bad = tmp_path / "bad.py"
    _write_bad_module(bad)
    verdict = gate([bad])
    assert verdict.verdict == "PASS"
    assert "kill-switched" in verdict.notes[0]


def test_gate_warns_below_the_acceptable_band(tmp_path):
    """A file that satisfies every CRITICAL check but lacks type hints
    (weight 4 — non-critical) should WARN, not BLOCK."""
    from sovereign_agent.quality.gate import gate

    mod = tmp_path / "untyped.py"
    mod.write_text(textwrap.dedent('''
        """Satisfies observability; lacks type hints on purpose."""
        def f(a, b):
            if a is None:
                raise ValueError("a required")
            emit_event = None
            return a + b
    '''), encoding="utf-8")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir(exist_ok=True)
    # has_tests requires the module's STEM as a literal substring of the
    # test file's content, not just a matching filename.
    (tests_dir / "test_untyped.py").write_text(
        '"""Tests for untyped."""\n', encoding="utf-8")

    verdict = gate([mod])
    assert verdict.verdict in ("PASS", "WARN"), verdict.notes   # never BLOCK on a non-critical gap


# ─── the CLI (invoked as a real subprocess — works staged or live) ───────


def test_cli_exits_zero_on_pass(tmp_path):
    good = tmp_path / "good.py"
    _write_good_module(good)
    r = subprocess.run(
        [sys.executable, str(STAGED_QUALITY_GATE_CLI), "--paths", str(good)],
        capture_output=True, text=True, cwd=REPO_ROOT)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "quality gate" in r.stdout.lower() or "PASS" in r.stdout


def test_cli_exits_one_on_block(tmp_path):
    bad = tmp_path / "bad.py"
    _write_bad_module(bad)
    r = subprocess.run(
        [sys.executable, str(STAGED_QUALITY_GATE_CLI), "--paths", str(bad)],
        capture_output=True, text=True, cwd=REPO_ROOT)
    assert r.returncode == 1, r.stdout + r.stderr


def test_cli_json_output_is_parseable(tmp_path):
    import json

    good = tmp_path / "good.py"
    _write_good_module(good)
    r = subprocess.run(
        [sys.executable, str(STAGED_QUALITY_GATE_CLI), "--paths", str(good), "--json"],
        capture_output=True, text=True, cwd=REPO_ROOT)
    data = json.loads(r.stdout)
    assert data["verdict"] == "PASS"


# ─── the patched surfaces (post-apply) ────────────────────────────────────


def test_quality_package_exports_gate():
    import pytest

    import sovereign_agent.quality as quality_mod

    if "quality-gate-d" not in inspect.getsource(quality_mod):
        pytest.skip("pre-apply: quality/__init__.py not yet patched")
    assert hasattr(quality_mod, "gate")
    assert hasattr(quality_mod, "QualityGateVerdict")


def test_pre_apply_gate_sh_calls_the_quality_gate():
    import pytest

    text = (REPO_ROOT / "scripts" / "pre_apply_gate.sh").read_text(encoding="utf-8")
    if "quality-gate-d" not in text:
        pytest.skip("pre-apply: pre_apply_gate.sh not yet patched")
    assert "quality_gate.py" in text


def test_safe_apply_sh_folds_the_gate_into_rollback():
    import pytest

    text = (REPO_ROOT / "scripts" / "safe_apply.sh").read_text(encoding="utf-8")
    if "quality-gate-d" not in text:
        pytest.skip("pre-apply: safe_apply.sh not yet patched")
    assert "quality_gate.py" in text
    assert "snapshot_commit.txt" in text
