"""Behavior tests for aria-loose-threads, promoted to live tests/."""
from __future__ import annotations

from pathlib import Path

import pytest


def _write(root: Path, rel: str, text: str):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_finds_a_run_session_shaped_orphan(tmp_path):
    """The proof of worth: public, tested-elsewhere, uncalled → found."""
    from sovereign_agent.loose_threads import scan_threads

    src = tmp_path / "pkg"
    _write(src, "__init__.py", "")
    _write(src, "engine.py",
           "async def run_session(x):\n    return x\n\n"
           "def used_helper():\n    return 1\n")
    _write(src, "caller.py",
           "from .engine import used_helper\n\nVALUE = used_helper()\n")
    scan = scan_threads(src)
    symbols = {t.symbol for t in scan.threads}
    assert "pkg.engine.run_session" in symbols
    assert "pkg.engine.used_helper" not in symbols


def test_repo_idioms_are_not_wolves(tmp_path):
    """Tool subclasses, sentinel decorators, typer commands, UI dispatch —
    implicit callers, never flagged."""
    from sovereign_agent.loose_threads import scan_threads

    src = tmp_path / "pkg"
    _write(src, "__init__.py", "")
    _write(src, "stuff.py",
           "from .base import Tool\n"
           "import typer\napp = typer.Typer()\n\n"
           "class MyTool(Tool):\n    name = 't'\n\n"
           "@app.command()\ndef do_thing():\n    pass\n\n"
           "def on_mount(self):\n    pass\n\n"
           "def action_toggle(self):\n    pass\n")
    scan = scan_threads(src)
    assert scan.threads == [], [t.symbol for t in scan.threads]


def test_string_references_count_as_callers(tmp_path):
    """Dispatch tables / registries reference by string — real callers."""
    from sovereign_agent.loose_threads import scan_threads

    src = tmp_path / "pkg"
    _write(src, "__init__.py", "")
    _write(src, "a.py", "def dispatch_me():\n    pass\n")
    _write(src, "b.py", 'TABLE = {"dispatch_me": 1}\n')
    scan = scan_threads(src)
    assert scan.threads == []


def test_ledger_dispositions_silence_threads_with_reasons(tmp_path):
    from sovereign_agent.loose_threads import DispositionLedger
    from sovereign_agent.loose_threads.scanner import Thread

    led = DispositionLedger(tmp_path)
    t1 = Thread(symbol="pkg.a.orphan", kind="function", module="pkg.a", lineno=1)
    t2 = Thread(symbol="pkg.b.other", kind="function", module="pkg.b", lineno=1)
    assert len(led.undispositioned([t1, t2])) == 2
    led.disposition("pkg.a.orphan", "ACCEPTED", "future API kept deliberately")
    assert [t.symbol for t in led.undispositioned([t1, t2])] == ["pkg.b.other"]
    with pytest.raises(ValueError):
        led.disposition("pkg.b.other", "ACCEPTED", "")  # no silent suppression


def test_sentinel_registered_and_healthy_cycle(tmp_path):
    from sovereign_agent.stewardship import registry

    assert "loose-threads" in registry.registered_ids()
    from sovereign_agent.loose_threads.sentinel import LooseThreadsSentinel

    s = LooseThreadsSentinel(data_dir=tmp_path)
    assert s.health_status().level == "ok"  # not yet scanned
    report = s.scan()  # the real tree — expensive but honest
    assert report.findings_count >= 0
    hs = s.health_status()
    assert hs.level in ("ok", "warning")
