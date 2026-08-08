"""Tests for the promoted, live scripts/golden_path_smoke.sh.

Structural checks (existence, executability, valid syntax) always run —
fast and offline, no Ollama needed. The actual end-to-end invocation
(a real Ollama call, ~30-40s) is deliberately gated behind
RUN_GOLDEN_PATH_LIVE=1, NOT run by default as part of a normal `pytest
tests/` sweep — matching the script's own docstring: it's a separate,
deliberate, manual gate, not baked into the otherwise fast/offline/
deterministic suite. Set the env var to actually exercise it:

    RUN_GOLDEN_PATH_LIVE=1 pytest tests/test_golden_path_smoke_live.py -q

If Ollama isn't reachable when that flag IS set, the test skips with an
honest reason — it never fakes a pass.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


def _find_repo_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / "src" / "sovereign_agent" / "cockpit" / "app.py").is_file():
            return candidate
    raise RuntimeError("could not locate repo root from " + str(start))


REPO_ROOT = _find_repo_root(Path(__file__).resolve())
SCRIPT = REPO_ROOT / "scripts" / "golden_path_smoke.sh"


def test_script_exists_and_is_executable():
    assert SCRIPT.is_file()
    assert os.access(SCRIPT, os.X_OK)


def test_script_has_valid_bash_syntax():
    result = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def _ollama_reachable() -> bool:
    try:
        result = subprocess.run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", "3",
             "http://localhost:11434/api/tags"],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() == "200"
    except Exception:  # noqa: BLE001
        return False


@pytest.mark.skipif(
    os.environ.get("RUN_GOLDEN_PATH_LIVE") != "1",
    reason="opt-in only (RUN_GOLDEN_PATH_LIVE=1) — makes a real ~30-40s Ollama call, "
           "deliberately not run by default in the normal offline/fast test sweep",
)
def test_golden_path_actually_passes_end_to_end():
    if not _ollama_reachable():
        pytest.skip("Ollama unreachable at localhost:11434 — cannot honestly test this")
    result = subprocess.run(
        ["bash", str(SCRIPT), "Say hello and confirm you are working."],
        capture_output=True, text=True, timeout=90, cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert "PASS" in result.stdout
