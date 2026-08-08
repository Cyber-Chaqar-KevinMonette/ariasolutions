"""Test fixtures.

The previous conftest reloaded ``config.py`` between tests to pick up new
XDG paths. That worked for ``config.SETTINGS`` itself, but every other module
that did ``from .config import SETTINGS`` kept a *reference* to the old
SETTINGS object — so they wrote to the production paths while assertions
checked the new tmp paths. Reloading those modules then created a second
class-identity bug: ``isinstance(exc, AuthorityViolation)`` failed because
the test had imported the old class object before the reload created a new
one.

This rewrite avoids both problems by NOT RELOADING ANYTHING. We mutate the
existing ``SETTINGS.paths`` attribute in-place via ``object.__setattr__``
(bypassing the frozen dataclass guard). Every module that imported SETTINGS
keeps the same reference, but its ``.paths`` now points at the tmp dir.
Class identities stay stable. Tests stay stable.

We also clear the tool registry and PROTOCOL-ZERO state between tests so
state from one test cannot leak into the next.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from sovereign_agent.config import SETTINGS, Paths


@pytest.fixture(scope="session")
def all_src_python_files() -> list[Path]:
    """glyph-catalog-d (Kevin, 2026-07-21): "remove the redundant glyph
    test from having to run it so often." Every full-repo-scan test
    (test_brand_glyph.py's diamond sweep, test_mos_surface.py's version/
    color/glyph doctrine checks) used to independently `rglob` the whole
    src tree. One shared, session-scoped walk instead of one per test
    file — computed once, reused by every test that needs "every .py
    file under src/sovereign_agent"."""
    import sovereign_agent

    root = Path(sovereign_agent.__file__).parent
    return [p for p in sorted(root.rglob("*.py")) if "__pycache__" not in p.parts]

# Import tools at module level so _TIER_REGISTRY is populated before any fixture.
# On test 2+, the per-test fixture's `import sovereign_agent.tools` is a no-op
# (module already cached), so the registry snapshot would be empty. Loading here
# ensures original_registry always captures the full production set.
try:
    import sovereign_agent.tools as _sov_tools  # noqa: F401
except ImportError:
    pass


@pytest.fixture(autouse=True)
def isolated_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Per-test isolation: redirect SETTINGS.paths into a tmp dir.

    autouse=True — every test gets this, no opt-in.
    """
    config_dir = tmp_path / "config" / "sovereign-agent"
    data_dir = tmp_path / "data" / "sovereign-agent"
    config_dir.mkdir(parents=True)
    data_dir.mkdir(parents=True)

    # Set env vars so any subprocess reads the same values
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))

    # Build a fresh Paths object pointing at tmp, then swap it in.
    # SETTINGS and Paths are frozen dataclasses — object.__setattr__ bypasses.
    new_paths = Paths(config_dir=config_dir, data_dir=data_dir)
    new_paths.ensure()

    original_paths = SETTINGS.paths
    object.__setattr__(SETTINGS, "paths", new_paths)
    try:
        # Also clear the tool registry so register_tool() calls don't
        # accumulate across tests.
        from sovereign_agent.authority import _TIER_REGISTRY

        original_registry = dict(_TIER_REGISTRY)
        _TIER_REGISTRY.clear()

        # Restore the production tool set from the snapshot we captured above.
        # We can't re-trigger __init_subclass__ via import (module is cached),
        # so we restore from original_registry which was populated at module
        # level before the first fixture ran.
        _TIER_REGISTRY.update(original_registry)

        # Clear PROTOCOL-ZERO sentinel from previous test runs
        from sovereign_agent import protocol_zero

        protocol_zero.disarm()

        # Reset events module fsync counters (module-level state)
        try:
            from sovereign_agent import events as _events_mod

            _events_mod._PENDING_FSYNC = 0
            _events_mod._LAST_FSYNC_AT = 0.0
        except (ImportError, AttributeError):
            pass

        yield
    finally:
        # Restore so a test crash doesn't pollute later tests
        object.__setattr__(SETTINGS, "paths", original_paths)
        try:
            from sovereign_agent.authority import _TIER_REGISTRY

            _TIER_REGISTRY.clear()
            _TIER_REGISTRY.update(original_registry)
        except ImportError:
            pass
