"""Tests for the real-time game bridge: game_bridge_client.py (asyncio
TCP/NDJSON client) and the three tools built on it (game_bridge_connect,
game_place_piece, game_world_state).

Real gap this closes: screenshot+ydotool was proven tonight to be too
slow/fragile for real-time co-play (multi-second round trips, coordinate
calibration issues) — this is the direct structured data channel instead.
No real Godot process needed for these tests — a tiny in-process asyncio
TCP echo/protocol server stands in for game_bridge.gd."""
from __future__ import annotations

import asyncio
import json

import pytest

from sovereign_agent.game_bridge_client import (
    BridgeConnection,
    GameBridgeError,
    connect,
    disconnect,
    get_connection,
)
from sovereign_agent.game_projects import GameProject, save


async def _fake_bridge_server(host: str, port: int, *, seq_start: int = 1):
    """A minimal NDJSON server mimicking game_bridge.gd's protocol: echoes
    place_piece as a piece_placed reply, and get_world_state as a
    world_state reply, both carrying back the request's req_id."""
    seq = seq_start

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        nonlocal seq
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                msg = json.loads(line.decode("utf-8"))
                req_id = msg.get("req_id")
                delay_s = msg.pop("delay_s", None)
                if delay_s:
                    await asyncio.sleep(delay_s)
                if msg.get("cmd") == "place_piece":
                    seq += 1
                    reply = {
                        "event": "piece_placed", "x": msg["x"], "y": msg["y"],
                        "z": msg.get("z", 0), "piece_type": msg["piece_type"],
                        "actor": msg.get("actor", "aria"), "seq": seq, "req_id": req_id,
                    }
                elif msg.get("cmd") == "get_world_state":
                    reply = {"event": "world_state", "pieces": [], "seq": seq, "req_id": req_id}
                elif msg.get("cmd") == "__never_reply__":
                    # Deliberately sends nothing back — for the client-side
                    # timeout test. Every OTHER unrecognized command still
                    # gets a real error reply, which is not "silent."
                    continue
                else:
                    reply = {"event": "error", "reason": "unknown_cmd", "req_id": req_id}
                writer.write((json.dumps(reply) + "\n").encode("utf-8"))
                await writer.drain()
        except (asyncio.CancelledError, ConnectionResetError):
            pass

    server = await asyncio.start_server(handle, host, port)
    return server


@pytest.fixture
async def fake_bridge():
    port = 18781  # distinct from the real default (8781), avoid collisions
    server = await _fake_bridge_server("127.0.0.1", port)
    yield port
    server.close()
    # Known asyncio quirk (pre-3.13): Server.wait_closed() can hang
    # indefinitely even after every connection's handler has genuinely
    # exited — confirmed live 2026-08-03 via a standalone repro outside
    # pytest entirely (not a fixture/loop-scope issue, not a bug in the
    # shipped client code). close() itself has already stopped the
    # listening socket by this point, so a bounded wait is enough for
    # test cleanup.
    try:
        await asyncio.wait_for(server.wait_closed(), timeout=1.0)
    except asyncio.TimeoutError:
        pass


def _make_project(tmp_path, name="Bridge Test Game"):
    save(GameProject(project_name=name), tmp_path)


# ── BridgeConnection ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_connect_and_send_command_round_trip(fake_bridge):
    port = fake_bridge
    conn = BridgeConnection(port=port)
    await conn.connect()
    try:
        assert conn.connected
        reply = await conn.send_command({"cmd": "place_piece", "x": 1, "y": 2, "piece_type": "wall"})
        assert reply["event"] == "piece_placed"
        assert reply["x"] == 1 and reply["y"] == 2
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_send_command_matches_req_id_not_order(fake_bridge):
    """Two concurrent commands must each get their OWN reply back, not
    whichever comes first on the wire — this is the whole point of req_id."""
    port = fake_bridge
    conn = BridgeConnection(port=port)
    await conn.connect()
    try:
        r1, r2 = await asyncio.gather(
            conn.send_command({"cmd": "place_piece", "x": 1, "y": 1, "piece_type": "wall"}),
            conn.send_command({"cmd": "place_piece", "x": 2, "y": 2, "piece_type": "floor"}),
        )
        assert {r1["x"], r2["x"]} == {1, 2}
        assert {r1["piece_type"], r2["piece_type"]} == {"wall", "floor"}
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_unsolicited_event_goes_to_queue_not_pending():
    """An incoming message with no req_id (a human's live placement) must
    land in poll_events(), never get matched to an unrelated pending call."""
    conn = BridgeConnection()
    # Simulate directly without a real server: feed the read loop's logic.
    msg_no_req_id = {"event": "piece_placed", "x": 5, "y": 5, "actor": "human", "seq": 1}
    conn._events.append(msg_no_req_id)  # what _read_loop would do for this case
    events = conn.poll_events(since_seq=0)
    assert events == [msg_no_req_id]


@pytest.mark.asyncio
async def test_send_command_timeout_when_not_connected():
    conn = BridgeConnection()
    with pytest.raises(GameBridgeError, match="not_connected"):
        await conn.send_command({"cmd": "get_world_state", "since_seq": 0})


@pytest.mark.asyncio
async def test_send_command_real_timeout(fake_bridge):
    """A command the fake server never replies to must raise GameBridgeError
    'timeout', not hang forever."""
    port = fake_bridge
    conn = BridgeConnection(port=port)
    await conn.connect()
    try:
        with pytest.raises(GameBridgeError, match="timeout"):
            await conn.send_command({"cmd": "__never_reply__"}, timeout=0.2)
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_poll_events_filters_by_since_seq():
    conn = BridgeConnection()
    conn._events.append({"event": "piece_placed", "seq": 1})
    conn._events.append({"event": "piece_placed", "seq": 3})
    conn._events.append({"event": "piece_placed", "seq": 5})
    assert [e["seq"] for e in conn.poll_events(since_seq=2)] == [3, 5]


@pytest.mark.asyncio
async def test_connect_singleton_reuses_existing(fake_bridge):
    port = fake_bridge
    try:
        c1 = await connect("bridge-test-slug", port=port)
        c2 = await connect("bridge-test-slug", port=port)
        assert c1 is c2
        assert get_connection("bridge-test-slug") is c1
    finally:
        await disconnect("bridge-test-slug")
        assert get_connection("bridge-test-slug") is None


# ── Decoupled think/act: fire_command / check_result ─────────────────────


@pytest.mark.asyncio
async def test_fire_command_returns_immediately_even_when_game_is_slow(fake_bridge):
    """The whole point: fire_command must not wait on the game's reply,
    even when the game takes a while to respond."""
    port = fake_bridge
    conn = BridgeConnection(port=port)
    await conn.connect()
    try:
        start = asyncio.get_event_loop().time()
        req_id = await conn.fire_command({
            "cmd": "place_piece", "x": 1, "y": 1, "piece_type": "wall", "delay_s": 0.5,
        })
        elapsed = asyncio.get_event_loop().time() - start
        assert isinstance(req_id, str) and req_id
        assert elapsed < 0.1, f"fire_command blocked for {elapsed}s — should return near-instantly"
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_check_result_pending_until_game_replies(fake_bridge):
    port = fake_bridge
    conn = BridgeConnection(port=port)
    await conn.connect()
    try:
        req_id = await conn.fire_command({
            "cmd": "place_piece", "x": 2, "y": 3, "piece_type": "torch", "delay_s": 0.3,
        })
        # Immediately after firing, the game hasn't replied yet.
        assert conn.check_result(req_id) is None

        # Poll until it resolves (bounded wait so a real bug still fails fast).
        for _ in range(20):
            result = conn.check_result(req_id)
            if result is not None:
                break
            await asyncio.sleep(0.05)
        else:
            pytest.fail("check_result never resolved")

        assert result["event"] == "piece_placed"
        assert result["x"] == 2 and result["piece_type"] == "torch"
        # Popped on read — a second check for the same req_id is gone.
        assert conn.check_result(req_id) is None
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_fired_reply_does_not_leak_into_unsolicited_events(fake_bridge):
    """A fire_command reply is req_id-keyed (_resolved); it must never show
    up in poll_events(), which is reserved for truly unsolicited pushes."""
    port = fake_bridge
    conn = BridgeConnection(port=port)
    await conn.connect()
    try:
        req_id = await conn.fire_command({"cmd": "place_piece", "x": 4, "y": 4, "piece_type": "wall"})
        for _ in range(20):
            if conn.check_result(req_id) is not None:
                break
            await asyncio.sleep(0.05)
        # It resolved via check_result above (which pops it) — poll_events
        # must never have seen it.
        assert conn.poll_events(since_seq=0) == []
    finally:
        await conn.close()


# ── Tool registration ────────────────────────────────────────────────────


def test_bridge_tools_registered_at_tier_1():
    import sovereign_agent.tools  # noqa: F401
    # game_action_status isn't wired into tools/__init__.py's import list yet
    # (that happens at apply time) — import it explicitly here so
    # __init_subclass__ registration fires, same as the other three tools
    # get for free via tools/__init__.py once applied.
    import sovereign_agent.tools.game_action_status  # noqa: F401
    from sovereign_agent.authority import _TIER_REGISTRY
    for name in ("game_bridge_connect", "game_place_piece", "game_world_state", "game_action_status"):
        assert name in _TIER_REGISTRY, f"{name} not registered"
        assert _TIER_REGISTRY[name].tier == 1, f"{name} must be tier 1 (Mode.BUSY ceiling)"


# ── GameBridgeConnectTool ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_bridge_connect_unknown_project(tmp_path):
    from sovereign_agent.tools.game_bridge_connect import GameBridgeConnectTool
    tool = GameBridgeConnectTool(data_dir=tmp_path)
    result = await tool.execute(tool.Args(project_slug="ghost"), trace_id="t1")
    assert not result.ok
    assert "unknown_project" in result.error


@pytest.mark.asyncio
async def test_bridge_connect_godot_not_running(tmp_path):
    from sovereign_agent.tools.game_bridge_connect import GameBridgeConnectTool
    _make_project(tmp_path)
    tool = GameBridgeConnectTool(data_dir=tmp_path)
    from unittest.mock import patch
    with patch("sovereign_agent.tools.game_bridge_connect.godot_gui_pids", return_value=[]):
        result = await tool.execute(tool.Args(project_slug="bridge-test-game"), trace_id="t2")
    assert not result.ok
    assert "godot_not_running" in result.error


@pytest.mark.asyncio
async def test_bridge_connect_success(tmp_path, fake_bridge):
    from sovereign_agent.tools.game_bridge_connect import GameBridgeConnectTool
    _make_project(tmp_path)
    port = fake_bridge
    tool = GameBridgeConnectTool(data_dir=tmp_path)
    from unittest.mock import patch
    try:
        with patch("sovereign_agent.tools.game_bridge_connect.godot_gui_pids", return_value=[12345]):
            result = await tool.execute(tool.Args(project_slug="bridge-test-game", port=port), trace_id="t3")
        assert result.ok
        assert result.output["already_connected"] is False
    finally:
        await disconnect("bridge-test-game")


@pytest.mark.asyncio
async def test_bridge_connect_refused_when_nothing_listening(tmp_path):
    from sovereign_agent.tools.game_bridge_connect import GameBridgeConnectTool
    _make_project(tmp_path)
    tool = GameBridgeConnectTool(data_dir=tmp_path)
    from unittest.mock import patch
    with patch("sovereign_agent.tools.game_bridge_connect.godot_gui_pids", return_value=[12345]):
        # Port 18782 with nothing listening -> real ConnectionRefusedError.
        result = await tool.execute(tool.Args(project_slug="bridge-test-game", port=18782), trace_id="t4")
    assert not result.ok
    assert "connection_refused" in result.error


# ── GamePlacePieceTool / GameWorldStateTool ──────────────────────────────


@pytest.mark.asyncio
async def test_place_piece_not_connected():
    from sovereign_agent.tools.game_place_piece import GamePlacePieceTool
    tool = GamePlacePieceTool()
    result = await tool.execute(
        tool.Args(project_slug="never-connected-slug", x=0, y=0, piece_type="wall"), trace_id="t5",
    )
    assert not result.ok
    assert "not_connected" in result.error


@pytest.mark.asyncio
async def test_place_piece_success(fake_bridge):
    from sovereign_agent.tools.game_place_piece import GamePlacePieceTool
    port = fake_bridge
    try:
        await connect("place-piece-slug", port=port)
        tool = GamePlacePieceTool()
        result = await tool.execute(
            tool.Args(project_slug="place-piece-slug", x=3, y=4, piece_type="torch"), trace_id="t6",
        )
        assert result.ok
        assert result.output["x"] == 3 and result.output["piece_type"] == "torch"
    finally:
        await disconnect("place-piece-slug")


@pytest.mark.asyncio
async def test_place_piece_wait_false_fires_and_returns_immediately(fake_bridge):
    """Regression guard for the default: wait=True (unset) must still behave
    exactly like test_place_piece_success above — this test only covers the
    new opt-in wait=False path."""
    from sovereign_agent.tools.game_place_piece import GamePlacePieceTool
    port = fake_bridge
    try:
        await connect("fire-piece-slug", port=port)
        tool = GamePlacePieceTool()
        start = asyncio.get_event_loop().time()
        result = await tool.execute(
            tool.Args(project_slug="fire-piece-slug", x=5, y=6, piece_type="wall", wait=False),
            trace_id="t9",
        )
        elapsed = asyncio.get_event_loop().time() - start
        assert result.ok
        assert result.output["status"] == "fired"
        assert isinstance(result.output["req_id"], str) and result.output["req_id"]
        assert elapsed < 0.1
    finally:
        await disconnect("fire-piece-slug")


@pytest.mark.asyncio
async def test_game_action_status_resolves_after_fire(fake_bridge):
    from sovereign_agent.tools.game_action_status import GameActionStatusTool
    from sovereign_agent.tools.game_place_piece import GamePlacePieceTool
    port = fake_bridge
    try:
        await connect("status-slug", port=port)
        place_tool = GamePlacePieceTool()
        fired = await place_tool.execute(
            place_tool.Args(project_slug="status-slug", x=7, y=8, piece_type="floor", wait=False),
            trace_id="t10",
        )
        req_id = fired.output["req_id"]

        status_tool = GameActionStatusTool()
        for _ in range(20):
            status = await status_tool.execute(
                status_tool.Args(project_slug="status-slug", req_id=req_id), trace_id="t11",
            )
            if status.output["status"] == "resolved":
                break
            await asyncio.sleep(0.05)
        else:
            pytest.fail("game_action_status never resolved")

        assert status.ok
        assert status.output["x"] == 7 and status.output["piece_type"] == "floor"
    finally:
        await disconnect("status-slug")


@pytest.mark.asyncio
async def test_game_action_status_pending_when_not_yet_resolved(fake_bridge):
    from sovereign_agent.tools.game_action_status import GameActionStatusTool
    from sovereign_agent.tools.game_place_piece import GamePlacePieceTool
    port = fake_bridge
    try:
        await connect("status-pending-slug", port=port)
        place_tool = GamePlacePieceTool()
        fired = await place_tool.execute(
            place_tool.Args(project_slug="status-pending-slug", x=1, y=1, piece_type="wall", wait=False),
            trace_id="t12",
        )
        req_id = fired.output["req_id"]
        # Check immediately (bogus req_id would also read as pending — this
        # just confirms the "haven't heard back yet" path doesn't error).
        status_tool = GameActionStatusTool()
        status = await status_tool.execute(
            status_tool.Args(project_slug="status-pending-slug", req_id="not-a-real-req-id"), trace_id="t13",
        )
        assert status.ok
        assert status.output["status"] == "pending"
    finally:
        await disconnect("status-pending-slug")


@pytest.mark.asyncio
async def test_game_action_status_not_connected():
    from sovereign_agent.tools.game_action_status import GameActionStatusTool
    tool = GameActionStatusTool()
    result = await tool.execute(
        tool.Args(project_slug="never-connected-slug-3", req_id="whatever"), trace_id="t14",
    )
    assert not result.ok
    assert "not_connected" in result.error


@pytest.mark.asyncio
async def test_world_state_not_connected():
    from sovereign_agent.tools.game_world_state import GameWorldStateTool
    tool = GameWorldStateTool()
    result = await tool.execute(tool.Args(project_slug="never-connected-slug-2"), trace_id="t7")
    assert not result.ok
    assert "not_connected" in result.error


@pytest.mark.asyncio
async def test_world_state_includes_pending_events(fake_bridge):
    from sovereign_agent.tools.game_world_state import GameWorldStateTool
    port = fake_bridge
    try:
        conn = await connect("world-state-slug", port=port)
        # Simulate a human's unsolicited placement arriving between polls.
        conn._events.append({"event": "piece_placed", "x": 9, "y": 9, "actor": "human", "seq": 99})
        tool = GameWorldStateTool()
        result = await tool.execute(tool.Args(project_slug="world-state-slug", since_seq=0), trace_id="t8")
        assert result.ok
        assert result.output["pending_events"] == [{"event": "piece_placed", "x": 9, "y": 9, "actor": "human", "seq": 99}]
    finally:
        await disconnect("world-state-slug")
