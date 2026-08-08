"""aria-checkpoint-chunks/tests/conftest.py — pre-apply test shim.

checkpoint_chunks/ and tools/recall_chunk_tool.py are both brand-new — no
live conflict, so the standard extend_paths append works without any
sys.modules preemption trick (unlike modes.py/requests.py in N/O)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_MODULE_ROOT = _HERE.parent

sys.path.insert(0, str(_MODULE_ROOT.parent / "scripts" / "lib"))
from aria_conftest import extend_paths  # noqa: E402

extend_paths(_MODULE_ROOT)


@pytest.fixture(autouse=True)
def isolated_paths(tmp_path: Path):
    """Redirect SETTINGS.paths into a tmp dir — ChunkStore writes NDJSON
    under data_dir. Mirrors tests/conftest.py's own fixture."""
    from sovereign_agent.config import SETTINGS, Paths

    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    config_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    new_paths = Paths(config_dir=config_dir, data_dir=data_dir)
    new_paths.ensure()

    original_paths = SETTINGS.paths
    object.__setattr__(SETTINGS, "paths", new_paths)
    try:
        yield
    finally:
        object.__setattr__(SETTINGS, "paths", original_paths)
