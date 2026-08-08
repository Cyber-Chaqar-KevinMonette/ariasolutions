"""aria-thread-grooming — the loose-threads first grooming. (FABLE II · M5)

Pre-apply, the patch-dependent tests skip with a written reason; the apply
script re-runs this file and requires zero skips.
"""
from __future__ import annotations

import inspect
import textwrap


def _patched(obj) -> bool:
    return "thread-grooming-d" in inspect.getsource(obj)


# ─── the scanner learns her idioms ───────────────────────────────────────


def test_scanner_knows_mcp_and_channel_idioms(tmp_path):
    import pytest

    from sovereign_agent.loose_threads import scanner as scanner_mod
    from sovereign_agent.loose_threads.scanner import scan_threads

    if not _patched(scanner_mod):
        pytest.skip("pre-apply: scanner not yet taught the idioms")

    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "mod.py").write_text(textwrap.dedent('''
        import mcp

        @mcp.tool()
        def endpoint():
            """framework-called"""

        class FooChannel(MemoryChannel):
            """registered at import"""

        def true_orphan():
            """nobody calls this"""
    '''), encoding="utf-8")
    scan = scan_threads(pkg)
    flagged = {t.symbol.rsplit(".", 1)[-1] for t in scan.threads}
    assert "true_orphan" in flagged
    assert "endpoint" not in flagged
    assert "FooChannel" not in flagged


def test_live_scan_no_longer_flags_the_framework_called(tmp_path):
    import pytest

    import sovereign_agent
    from pathlib import Path

    from sovereign_agent.loose_threads import scanner as scanner_mod
    from sovereign_agent.loose_threads.scanner import scan_threads

    if not _patched(scanner_mod):
        pytest.skip("pre-apply: scanner not yet taught the idioms")
    scan = scan_threads(Path(sovereign_agent.__file__).parent)
    symbols = {t.symbol for t in scan.threads}
    assert not any(s.startswith("sovereign_agent.mcp_server.") for s in symbols)
    assert not any(".mem_channels." in s for s in symbols)


# ─── record_action, wired: the /work lease enforcer ──────────────────────


def test_run_goal_session_is_an_allowed_lease_action():
    import pytest

    from sovereign_agent.autonomy import session as autonomy_session

    if not _patched(autonomy_session):
        pytest.skip("pre-apply: ALLOWED_ACTIONS not yet extended")
    assert "run_goal_session" in autonomy_session.ALLOWED_ACTIONS
    # the forbidden set is untouched — absence, not discouragement
    assert "apply_module" in autonomy_session.FORBIDDEN_ACTIONS


def test_bridge_without_lease_is_todays_behavior():
    import pytest

    from sovereign_agent import session_bridge

    if not _patched(session_bridge):
        pytest.skip("pre-apply: bridge not yet wired")
    session_bridge.disarm_lease()
    assert session_bridge.active_lease() is None
    session_bridge._lease_check("any goal")   # no lease → no-op, no raise


def test_expired_lease_refuses_and_records(tmp_path):
    import pytest

    from sovereign_agent import session_bridge
    from sovereign_agent.autonomy.session import AutonomySession

    if not _patched(session_bridge):
        pytest.skip("pre-apply: bridge not yet wired")
    lease = AutonomySession(session_id="as-test", plan_id="p",
                            status="active", ttl_seconds=60,
                            started_at="2020-01-01T00:00:00Z",
                            expires_at="2020-01-01T00:01:00Z")   # long expired
    session_bridge.arm_lease(lease)
    try:
        with pytest.raises(PermissionError, match="lease refuses"):
            session_bridge._lease_check("some goal")
        # the refusal itself is on the observable log
        assert lease.action_log and not lease.action_log[-1]["allowed"]
    finally:
        session_bridge.disarm_lease()


def test_active_lease_records_the_dispatch(tmp_path):
    import pytest

    from sovereign_agent import session_bridge
    from sovereign_agent.autonomy.session import AutonomySession, start_block

    if not _patched(session_bridge):
        pytest.skip("pre-apply: bridge not yet wired")
    lease = start_block(
        AutonomySession(session_id="as-live", plan_id="p", ttl_seconds=3600),
        approved=True)
    session_bridge.arm_lease(lease)
    try:
        session_bridge._lease_check("harden the garden")
        entry = lease.action_log[-1]
        assert entry["allowed"] and entry["action"] == "run_goal_session"
        assert "harden the garden" in entry["detail"]
    finally:
        session_bridge.disarm_lease()


def test_refused_start_creates_no_session(tmp_path):
    """start_goal_session under an expired lease refuses BEFORE creating
    any session state — zero half-built work."""
    import asyncio

    import pytest

    from sovereign_agent import session_bridge
    from sovereign_agent.agent_session import SessionStore
    from sovereign_agent.autonomy.session import AutonomySession

    if not _patched(session_bridge):
        pytest.skip("pre-apply: bridge not yet wired")
    before = len(SessionStore().list_all())
    lease = AutonomySession(session_id="as-x", plan_id="p", status="active",
                            ttl_seconds=60,
                            started_at="2020-01-01T00:00:00Z",
                            expires_at="2020-01-01T00:01:00Z")
    session_bridge.arm_lease(lease)
    try:
        with pytest.raises(PermissionError):
            asyncio.run(session_bridge.start_goal_session("a goal"))
    finally:
        session_bridge.disarm_lease()
    assert len(SessionStore().list_all()) == before
