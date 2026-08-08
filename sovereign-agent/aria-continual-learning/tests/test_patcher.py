"""Patcher tests for aria-continual-learning — verify the patch functions
themselves against the CURRENT live files, before anything is applied."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

STAGING = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(STAGING))
from patcher import MARK, PatchError, patch_data_py, patch_pipeline_py, patch_tools_init  # noqa: E402

REPO_ROOT = STAGING.parent
DATA_PY = REPO_ROOT / "src" / "sovereign_agent" / "aria_lm" / "data.py"
PIPELINE_PY = REPO_ROOT / "src" / "sovereign_agent" / "aria_lm" / "pipeline.py"
TOOLS_INIT = REPO_ROOT / "src" / "sovereign_agent" / "tools" / "__init__.py"
RETRAIN_TRIGGER_PAYLOAD = STAGING / "payload" / "src" / "sovereign_agent" / "aria_lm" / "retrain_trigger.py"
CONTINUAL_TOOLS_PAYLOAD = STAGING / "payload" / "src" / "sovereign_agent" / "tools" / "continual_learning_tools.py"


def _compiles(text: str) -> None:
    import py_compile
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(text)
        tmp_path = f.name
    py_compile.compile(tmp_path, doraise=True)


# ─── patch_data_py ───────────────────────────────────────────────────────


def test_patch_data_py_applies_cleanly():
    new_text, _ = patch_data_py(DATA_PY.read_text(encoding="utf-8"))
    assert MARK in new_text
    assert "from .retrain_trigger import gather_lesson_text" in new_text


def test_patch_data_py_idempotent():
    once, _ = patch_data_py(DATA_PY.read_text(encoding="utf-8"))
    twice, changed2 = patch_data_py(once)
    assert changed2 is False
    assert once == twice


def test_patched_data_py_compiles():
    new_text, _ = patch_data_py(DATA_PY.read_text(encoding="utf-8"))
    _compiles(new_text)


def test_data_py_lesson_source_wrapped_in_try_except():
    """gather_corpus() must never regress when lessons aren't available."""
    new_text, _ = patch_data_py(DATA_PY.read_text(encoding="utf-8"))
    idx = new_text.index("from .retrain_trigger import gather_lesson_text")
    surrounding = new_text[max(0, idx - 200):idx + 300]
    assert "try:" in surrounding
    assert "except Exception:" in surrounding


def test_data_py_lesson_text_inserted_at_front_not_appended():
    """Regression guard: lesson text must be prioritized ahead of the
    (often much larger) distilled-research text so it survives the
    final max_chars truncation, which keeps only the corpus's start."""
    new_text, _ = patch_data_py(DATA_PY.read_text(encoding="utf-8"))
    assert "parts.insert(0, lesson_text)" in new_text
    assert "parts.append(lesson_text)" not in new_text


def test_data_py_missing_anchor_raises():
    with pytest.raises(PatchError):
        patch_data_py("no anchors here at all")


# ─── patch_pipeline_py ───────────────────────────────────────────────────


def test_patch_pipeline_py_applies_cleanly():
    new_text, _ = patch_pipeline_py(PIPELINE_PY.read_text(encoding="utf-8"))
    assert MARK in new_text
    assert "from .retrain_trigger import record_retrain" in new_text
    assert "record_retrain(SETTINGS.paths.data_dir)" in new_text


def test_patch_pipeline_py_idempotent():
    once, _ = patch_pipeline_py(PIPELINE_PY.read_text(encoding="utf-8"))
    twice, changed2 = patch_pipeline_py(once)
    assert changed2 is False
    assert once == twice


def test_patched_pipeline_py_compiles():
    new_text, _ = patch_pipeline_py(PIPELINE_PY.read_text(encoding="utf-8"))
    _compiles(new_text)


def test_pipeline_py_record_retrain_call_is_best_effort():
    new_text, _ = patch_pipeline_py(PIPELINE_PY.read_text(encoding="utf-8"))
    idx = new_text.index("record_retrain(SETTINGS.paths.data_dir)")
    surrounding = new_text[max(0, idx - 200):idx + 100]
    assert "try:" in surrounding
    assert "except Exception:" in surrounding


def test_pipeline_py_missing_anchor_raises():
    with pytest.raises(PatchError):
        patch_pipeline_py("no anchors here at all")


# ─── patch_tools_init ────────────────────────────────────────────────────


def test_patch_tools_init_applies_cleanly():
    new_text, _ = patch_tools_init(TOOLS_INIT.read_text(encoding="utf-8"))
    assert MARK in new_text
    assert "from .continual_learning_tools import ProposeRetrainTool" in new_text
    assert '"ProposeRetrainTool"' in new_text


def test_patch_tools_init_idempotent():
    once, _ = patch_tools_init(TOOLS_INIT.read_text(encoding="utf-8"))
    twice, changed2 = patch_tools_init(once)
    assert changed2 is False
    assert once == twice


def test_patched_tools_init_compiles():
    new_text, _ = patch_tools_init(TOOLS_INIT.read_text(encoding="utf-8"))
    _compiles(new_text)


def test_tools_init_missing_anchor_raises():
    with pytest.raises(PatchError):
        patch_tools_init("no anchors here at all")


# ─── new payload files compile ───────────────────────────────────────────


def test_retrain_trigger_payload_compiles():
    _compiles(RETRAIN_TRIGGER_PAYLOAD.read_text(encoding="utf-8"))


def test_continual_learning_tools_payload_compiles():
    _compiles(CONTINUAL_TOOLS_PAYLOAD.read_text(encoding="utf-8"))
