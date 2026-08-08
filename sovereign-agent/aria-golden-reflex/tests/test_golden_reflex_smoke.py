"""Structural tests for the Golden Reflex smoke gate — fast, offline,
always run. The REAL end-to-end invocation (a live Ollama call) is the
script itself, run manually or gated behind RUN_GOLDEN_PATH_LIVE=1 —
same discipline as tests/test_golden_path_smoke.py.
"""
from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest


def _find_repo_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / "src" / "sovereign_agent").is_dir():
            return candidate
    raise RuntimeError("could not locate repo root from " + str(start))


REPO_ROOT = _find_repo_root(Path(__file__).resolve())
SCRIPT = REPO_ROOT / "scripts" / "golden_reflex_smoke.sh"


def test_script_exists():
    assert SCRIPT.is_file(), "scripts/golden_reflex_smoke.sh missing — run apply_golden_reflex.sh"


def test_script_is_executable():
    assert os.stat(SCRIPT).st_mode & stat.S_IXUSR


def test_script_is_valid_bash():
    proc = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


def test_script_asserts_the_reflex_chain():
    """The gate's teeth: dispatch event, result feedback, non-empty answer."""
    text = SCRIPT.read_text(encoding="utf-8")
    assert "tool-start-d" in text
    assert "final_message" in text
    assert "exit 1" in text  # it can actually fail


def test_script_fails_honestly_when_ollama_unreachable():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "Ollama unreachable" in text
    assert "honest FAILURE" in text or "Honest FAILURE" in text


@pytest.mark.skipif(
    not os.environ.get("RUN_GOLDEN_PATH_LIVE"),
    reason="live gate: set RUN_GOLDEN_PATH_LIVE=1 to run the real Ollama turn (~60s)",
)
def test_real_reflex_gate_live():
    proc = subprocess.run(["bash", str(SCRIPT)], capture_output=True, text=True, timeout=180)
    assert proc.returncode == 0, proc.stdout + proc.stderr
