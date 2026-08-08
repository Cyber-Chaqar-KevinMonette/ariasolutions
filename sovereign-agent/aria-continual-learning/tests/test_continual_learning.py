"""Behavior tests for aria-continual-learning — prove the lesson-corpus
pipe and the bounded retrain trigger actually work, using a shadow copy of
the whole package (never touches real src/). STAGED ONLY: never promoted —
see test_continual_learning_live.py for the promoted copy."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest


def _find_repo_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / "src" / "sovereign_agent" / "aria_lm" / "data.py").is_file():
            return candidate
    raise RuntimeError("could not locate repo root from " + str(start))


def _find_staging_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / "aria-continual-learning" / "patcher.py").is_file():
            return candidate / "aria-continual-learning"
    raise RuntimeError("could not locate aria-continual-learning/ from " + str(start))


REPO_ROOT = _find_repo_root(Path(__file__).resolve())
STAGING = _find_staging_root(Path(__file__).resolve())


def _build_shadow(tmp_path) -> Path:
    """Mirrors the real repo layout (shadow/src/sovereign_agent/... +
    shadow/sql/...), not just the package alone — db.py's own
    open_atoms_db() locates sql/002_atoms.sql via
    Path(__file__).parent.parent.parent, which requires 'src' and 'sql'
    to be siblings, exactly as they are in the real repo."""
    import shutil

    sys.path.insert(0, str(STAGING))
    from patcher import patch_data_py, patch_pipeline_py, patch_tools_init

    shadow = tmp_path / "shadow"
    shutil.copytree(REPO_ROOT / "src" / "sovereign_agent", shadow / "src" / "sovereign_agent")
    shutil.copytree(REPO_ROOT / "sql", shadow / "sql")
    for pyc in shadow.rglob("__pycache__"):
        shutil.rmtree(pyc)

    data_py = shadow / "src" / "sovereign_agent" / "aria_lm" / "data.py"
    patched, _ = patch_data_py(data_py.read_text(encoding="utf-8"))
    data_py.write_text(patched, encoding="utf-8")

    pipeline_py = shadow / "src" / "sovereign_agent" / "aria_lm" / "pipeline.py"
    patched, _ = patch_pipeline_py(pipeline_py.read_text(encoding="utf-8"))
    pipeline_py.write_text(patched, encoding="utf-8")

    tools_init = shadow / "src" / "sovereign_agent" / "tools" / "__init__.py"
    patched, _ = patch_tools_init(tools_init.read_text(encoding="utf-8"))
    tools_init.write_text(patched, encoding="utf-8")

    # New files
    (shadow / "src" / "sovereign_agent" / "aria_lm" / "retrain_trigger.py").write_text(
        (STAGING / "payload" / "src" / "sovereign_agent" / "aria_lm" / "retrain_trigger.py")
        .read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (shadow / "src" / "sovereign_agent" / "tools" / "continual_learning_tools.py").write_text(
        (STAGING / "payload" / "src" / "sovereign_agent" / "tools" / "continual_learning_tools.py")
        .read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    return shadow / "src"


@pytest.fixture
def shadow_pkg(tmp_path, monkeypatch):
    shadow = _build_shadow(tmp_path)
    saved = {
        name: mod for name, mod in sys.modules.items()
        if name == "sovereign_agent" or name.startswith("sovereign_agent.")
    }
    for name in saved:
        del sys.modules[name]

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    sys.path.insert(0, str(shadow))
    try:
        import sovereign_agent
        yield sovereign_agent
    finally:
        sys.path.remove(str(shadow))
        for name in list(sys.modules):
            if name == "sovereign_agent" or name.startswith("sovereign_agent."):
                del sys.modules[name]
        sys.modules.update(saved)


def _write_lesson(conn, *, trigger="t", context="c", rule="always write under sandbox dir",
                   correction="use sandbox path", failure_mode=None, confidence=0.8):
    import json
    from datetime import datetime, timezone
    from ulid import ULID

    conn.execute(
        "INSERT INTO lessons "
        "(lesson_id, ts, trigger, context, failure_mode, correction, rule, evidence_refs, confidence) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            str(ULID()),
            datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            trigger, context, failure_mode, correction, rule,
            json.dumps([]), confidence,
        ),
    )
    conn.commit()


# ── gather_corpus() integration ───────────────────────────────────────────


def test_gather_corpus_degrades_gracefully_with_no_lessons(shadow_pkg, tmp_path, monkeypatch):
    """Zero regression: with no lessons table populated, gather_corpus()
    behaves exactly as before (falls back to distilled/seed text)."""
    from sovereign_agent.aria_lm.data import gather_corpus

    corpus = gather_corpus(max_chars=50000)
    assert isinstance(corpus, str) and len(corpus) > 100


def test_gather_corpus_includes_real_lesson_text_when_lessons_exist(shadow_pkg, tmp_path):
    from sovereign_agent import db as _db
    from sovereign_agent.aria_lm.data import gather_corpus

    conn = _db.open_atoms_db()
    try:
        _write_lesson(
            conn,
            trigger="wrote-outside-sandbox",
            rule="always write under sandbox dir",
            correction="use the sandbox-scoped path helper",
        )
    finally:
        conn.close()

    corpus = gather_corpus(max_chars=50000, clean=False)
    assert "always write under sandbox dir" in corpus
    assert "use the sandbox-scoped path helper" in corpus


def test_lesson_text_survives_truncation_when_distilled_corpus_is_huge(shadow_pkg, tmp_path, monkeypatch):
    """Regression guard: the distilled-research text can easily exceed
    max_chars on its own; if lesson text were appended AFTER it (rather
    than inserted at the front), a small max_chars would silently cut
    lessons out entirely. Proven here with a synthetic huge distilled dir
    and a tiny max_chars."""
    from sovereign_agent import db as _db
    from sovereign_agent.aria_lm import data as data_module

    fake_distilled = tmp_path / "fake_distilled"
    fake_distilled.mkdir()
    (fake_distilled / "huge.md").write_text("filler prose text here. " * 50000, encoding="utf-8")
    monkeypatch.setattr(data_module.Path, "home", staticmethod(lambda: tmp_path / "fakehome"))
    (tmp_path / "fakehome" / "AA-Archive" / "Genesis-Seeds").mkdir(parents=True)
    (tmp_path / "fakehome" / "AA-Archive" / "Genesis-Seeds" / "distilled").symlink_to(fake_distilled)

    conn = _db.open_atoms_db()
    try:
        _write_lesson(conn, rule="a very specific rare lesson marker xyzzy123")
    finally:
        conn.close()

    corpus = data_module.gather_corpus(max_chars=500, clean=False)
    assert "xyzzy123" in corpus, "lesson text was truncated away — must be prioritized over distilled bulk"


def test_gather_lesson_text_never_raises_on_missing_db(shadow_pkg, tmp_path, monkeypatch):
    from sovereign_agent.aria_lm import retrain_trigger

    def _boom():
        raise RuntimeError("no db here")

    monkeypatch.setattr(retrain_trigger, "_open_db", _boom)
    assert retrain_trigger.gather_lesson_text() == ""
    assert retrain_trigger.total_lesson_count() == 0


# ── retrain trigger ───────────────────────────────────────────────────────


def test_check_retrain_proposal_none_when_below_threshold(shadow_pkg, tmp_path):
    from sovereign_agent import db as _db
    from sovereign_agent.aria_lm.retrain_trigger import check_retrain_proposal

    conn = _db.open_atoms_db()
    try:
        for _ in range(5):
            _write_lesson(conn)
    finally:
        conn.close()

    proposal = check_retrain_proposal(tmp_path / "data", threshold=20)
    assert proposal is None


def test_check_retrain_proposal_fires_once_threshold_reached(shadow_pkg, tmp_path):
    from sovereign_agent import db as _db
    from sovereign_agent.aria_lm.retrain_trigger import check_retrain_proposal

    conn = _db.open_atoms_db()
    try:
        for _ in range(21):
            _write_lesson(conn)
    finally:
        conn.close()

    proposal = check_retrain_proposal(tmp_path / "data", threshold=20)
    assert proposal is not None
    assert proposal["due"] is True
    assert proposal["new_lessons_since_last_retrain"] == 21
    assert proposal["suggested_command"] == "python -m sovereign_agent.aria_lm.pipeline"


def test_record_retrain_resets_the_baseline(shadow_pkg, tmp_path):
    from sovereign_agent import db as _db
    from sovereign_agent.aria_lm.retrain_trigger import (
        check_retrain_proposal, record_retrain, total_lesson_count,
    )

    conn = _db.open_atoms_db()
    try:
        for _ in range(25):
            _write_lesson(conn)
    finally:
        conn.close()

    data_dir = tmp_path / "data"
    assert check_retrain_proposal(data_dir, threshold=20) is not None

    record_retrain(data_dir)
    # Immediately after recording, no NEW lessons have accumulated yet.
    assert check_retrain_proposal(data_dir, threshold=20) is None

    conn = _db.open_atoms_db()
    try:
        for _ in range(3):
            _write_lesson(conn)
    finally:
        conn.close()
    # Still below threshold — only 3 new lessons since the reset.
    assert check_retrain_proposal(data_dir, threshold=20) is None
    assert total_lesson_count() == 28


@pytest.mark.asyncio
async def test_propose_retrain_tool_never_calls_grow_mind(shadow_pkg, tmp_path, monkeypatch):
    """The tool must only ever PROPOSE — it must never import or call
    grow_mind()/train_model() itself. Confirmed by patching grow_mind to
    raise if called at all."""
    from sovereign_agent.tools.continual_learning_tools import ProposeRetrainTool

    def _must_not_be_called(*a, **kw):
        raise AssertionError("propose_retrain must never call grow_mind()")

    import sovereign_agent.aria_lm.pipeline as pipeline_module
    monkeypatch.setattr(pipeline_module, "grow_mind", _must_not_be_called)

    tool = ProposeRetrainTool()
    result = await tool.execute(tool.Args(threshold=1), trace_id="t1")
    assert result.ok


def test_propose_retrain_tool_registered_at_tier_1(shadow_pkg):
    import sovereign_agent.tools  # noqa: F401
    from sovereign_agent.authority import _TIER_REGISTRY

    assert "propose_retrain" in _TIER_REGISTRY
    assert _TIER_REGISTRY["propose_retrain"].tier == 1


@pytest.mark.asyncio
async def test_propose_retrain_tool_reports_due_false_when_no_lessons(shadow_pkg, tmp_path):
    from sovereign_agent.tools.continual_learning_tools import ProposeRetrainTool

    tool = ProposeRetrainTool()
    result = await tool.execute(tool.Args(threshold=20), trace_id="t2")
    assert result.ok
    assert result.output["due"] is False
