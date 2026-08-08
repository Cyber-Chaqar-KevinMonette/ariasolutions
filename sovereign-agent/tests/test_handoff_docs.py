"""Doc-drift guards for handoff/ — docs that lie fail the suite."""
from __future__ import annotations

import re
from pathlib import Path

import sovereign_agent

REPO = Path(sovereign_agent.__file__).parent.parent.parent
HANDOFF = REPO / "handoff"
SRC = Path(sovereign_agent.__file__).parent


def test_all_eight_docs_exist_and_are_substantial():
    names = ["00_START_HERE.md", "01_ARCHITECTURE.md", "02_SAFETY_MODEL.md",
             "03_CONVENTIONS.md", "04_EVENT_VOCABULARY.md",
             "05_ENGINEERING_LESSONS.md", "06_RUNBOOK.md", "07_ROADMAP.md"]
    for n in names:
        p = HANDOFF / n
        assert p.is_file(), n
        assert len(p.read_text(encoding="utf-8")) > 500, f"{n} too thin"


def test_every_named_kill_switch_exists_in_code():
    doc = (HANDOFF / "02_SAFETY_MODEL.md").read_text(encoding="utf-8")
    switches = set(re.findall(r"SOV_(?:NO|BACKUP)_[A-Z_]+", doc))
    corpus = "\n".join(p.read_text(encoding="utf-8", errors="replace")
                       for p in SRC.rglob("*.py") if "__pycache__" not in p.parts)
    missing = {s for s in switches
               if s not in corpus and not s.endswith("_SENTINEL")}
    assert not missing, f"documented switches not found in code: {missing}"


def test_every_documented_store_module_exists():
    doc = (HANDOFF / "01_ARCHITECTURE.md").read_text(encoding="utf-8")
    for mod in ("db.py", "events.py", "palace.py", "thread_identity.py",
                "rest_point.py", "self_witness.py", "curiosity.py",
                "scope.py", "pathguard.py", "session_bridge.py"):
        assert mod in doc, f"{mod} missing from architecture doc"
        assert (SRC / mod).is_file() or list(SRC.rglob(mod)), mod
