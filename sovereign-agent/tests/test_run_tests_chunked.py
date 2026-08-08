"""Tests for aria-timeout-chunked-tests (Timeout round · T5):
scripts/run_tests_chunked.sh — real subprocess execution against a fake
`python -m pytest` stand-in (a genuine hang, a genuine failure, and
genuine passes), verifying the bisection algorithm actually isolates a
real hang to the single offending file without needing the real (slow)
pytest/sovereign_agent stack for the test itself.
"""
from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

def _find_script() -> Path:
    """Works staged (aria-timeout-chunked-tests/payload/scripts/...) or
    promoted to live (scripts/run_tests_chunked.sh, once applied) — same
    "works staged or live" discipline the gate CLI wrappers use."""
    staged = Path(__file__).parents[1] / "payload" / "scripts" / "run_tests_chunked.sh"
    if staged.is_file():
        return staged
    live = Path(__file__).parents[1] / "scripts" / "run_tests_chunked.sh"
    if live.is_file():
        return live
    raise FileNotFoundError(f"run_tests_chunked.sh not found at {staged} or {live}")


SCRIPT = _find_script()


def test_script_is_valid_bash():
    result = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def _make_sandbox(tmp_path: Path) -> Path:
    """A tiny fake repo: .venv/bin/python stands in for the real venv,
    hangs on 'poison', fails on 'bad_', passes otherwise. tests/ holds six
    fixture files."""
    (tmp_path / ".venv" / "bin").mkdir(parents=True)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "tests").mkdir()

    fake_python = tmp_path / ".venv" / "bin" / "python"
    fake_python.write_text(
        "#!/usr/bin/env bash\n"
        'args="$*"\n'
        'if [[ "$args" == *"-m pytest"* ]]; then\n'
        '  if [[ "$args" == *"poison_c.py"* ]]; then sleep 30; exit 0; fi\n'
        '  if [[ "$args" == *"bad_d.py"* ]]; then echo "FAILED bad_d.py::test_x"; exit 1; fi\n'
        "  exit 0\n"
        "fi\n"
        "exit 0\n"
    )
    fake_python.chmod(fake_python.stat().st_mode | stat.S_IEXEC)

    script_copy = tmp_path / "scripts" / "run_tests_chunked.sh"
    script_copy.write_text(SCRIPT.read_text())
    script_copy.chmod(script_copy.stat().st_mode | stat.S_IEXEC)

    for name in ("test_a.py", "test_b.py", "test_bad_d.py", "test_e.py",
                "test_f.py", "test_poison_c.py"):
        (tmp_path / "tests" / name).touch()
    return script_copy


def test_bisection_isolates_a_genuine_hang_to_one_file(tmp_path):
    script = _make_sandbox(tmp_path)
    result = subprocess.run(
        ["bash", str(script), "2", "3"], cwd=str(tmp_path),
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode != 0  # something genuinely failed/timed out
    assert "TIMEOUT (unbisectable): tests/test_poison_c.py" in result.stdout
    # a real failure is reported directly, never needlessly bisected
    assert "FAILED bad_d.py::test_x" in result.stdout
    # the clean files still get counted as passing
    assert "2/6 file(s) in clean chunks" in result.stdout


def test_all_clean_exits_zero(tmp_path):
    (tmp_path / ".venv" / "bin").mkdir(parents=True)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "tests").mkdir()

    fake_python = tmp_path / ".venv" / "bin" / "python"
    fake_python.write_text("#!/usr/bin/env bash\nexit 0\n")
    fake_python.chmod(fake_python.stat().st_mode | stat.S_IEXEC)

    script_copy = tmp_path / "scripts" / "run_tests_chunked.sh"
    script_copy.write_text(SCRIPT.read_text())
    script_copy.chmod(script_copy.stat().st_mode | stat.S_IEXEC)

    for name in ("test_a.py", "test_b.py"):
        (tmp_path / "tests" / name).touch()

    result = subprocess.run(
        ["bash", str(script_copy), "2", "5"], cwd=str(tmp_path),
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0
    assert "2/2 file(s) in clean chunks" in result.stdout
