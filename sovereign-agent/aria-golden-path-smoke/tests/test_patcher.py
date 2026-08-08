"""Structural tests for aria-golden-path-smoke's payload script — verify
it's well-formed BEFORE anything is applied. No shadow-copy dance needed:
the script is plain bash invoked via subprocess, so there's no Python
import/sys.modules risk at all (the class of bug this session hit
repeatedly elsewhere doesn't apply to a bash script)."""
from __future__ import annotations

import subprocess
from pathlib import Path

STAGING = Path(__file__).resolve().parent.parent
SCRIPT = STAGING / "payload" / "scripts" / "golden_path_smoke.sh"


def test_script_exists():
    assert SCRIPT.is_file()


def test_script_has_valid_bash_syntax():
    result = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_script_uses_strict_mode():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "set -euo pipefail" in text


def test_script_checks_ollama_reachable_before_anything_else():
    text = SCRIPT.read_text(encoding="utf-8")
    ollama_check_idx = text.index("Ollama unreachable")
    run_idx = text.index('"$SOVEREIGN"')
    assert ollama_check_idx < run_idx


def test_script_asserts_nonzero_exit_is_a_failure():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "EXIT_CODE -ne 0" in text
    assert "unhandled exception" in text


def test_script_asserts_final_message_nonempty():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "final_message" in text
    assert "not a coherent response" in text


def test_script_asserts_events_jsonl_grew():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "LINES_AFTER" in text
    assert "LINES_BEFORE" in text
    assert "event stream may be stalled" in text


def test_script_accepts_a_custom_goal_argument():
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'GOAL="${1:-' in text
