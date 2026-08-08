"""game_bridge_client.py — asyncio TCP/NDJSON client for the live
real-time game bridge.

Kevin (2026-08-03), after Ember Keep's playtest fight with screenshots and
synthetic clicks: "It can assist just not for fast paced workflows. That
is why we have to engineer a system optimized for her." For the new
co-building game, this is the fast path — a direct structured data
channel between the running Godot game (a `game_bridge.gd` autoload
listening on a TCPServer) and Aria's agent loop, instead of
screenshot-then-click round trips. Screenshots stay available as a
secondary, async channel for aesthetic judgment; this is the primary
control/perception path for real-time co-play.

Wire protocol (NDJSON — one JSON object per line, either direction):
  Aria -> game:
    {"cmd": "get_world_state", "since_seq": 0, "req_id": "..."}
    {"cmd": "place_piece", "x": 0, "y": 0, "z": 0, "piece_type": "wall",
     "actor": "aria", "req_id": "..."}
  game -> Aria:
    direct reply, echoes the same "req_id" so send_command can match it:
      {"event": "world_state", "pieces": [...], "seq": N, "req_id": "..."}
      {"event": "piece_placed", "x":.., "y":.., "z":.., "piece_type":..,
       "actor":.., "seq": N, "req_id": "..."}
      {"event": "error", "reason": "...", "detail": "...", "req_id": "..."}
    unsolicited broadcast (e.g. a human's click), NO req_id — routed to
    the event queue instead of matched to a pending call:
      {"event": "piece_placed", "x":.., "actor": "human", "seq": N}

One connection per project slug, held as a process-local singleton so
repeated tool calls within the same agent run reuse it rather than
reconnecting every time.

Decoupled think/act (2026-08-03): `send_command()` blocks the caller on the
game's reply — fine for a one-off, but the agent's main loop (loop.py) awaits
each tool call sequentially, so a blocking placement call freezes Aria's whole
reasoning loop for up to `_ACK_TIMEOUT` seconds. `fire_command()` is the
non-blocking sibling: it writes the command and returns the req_id
immediately, without creating or awaiting a future. When that command's reply
later arrives on `_read_loop` with no pending future to fulfill (because
nobody awaited it), it's stashed in `_resolved` — keyed by req_id, distinct
from `_events` (which is for genuinely unsolicited human-actor broadcasts
that never had a req_id at all) — so `check_result()` can retrieve it later
without blocking.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from collections import OrderedDict, deque
from typing import Any, Optional

_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 8781
_ACK_TIMEOUT = 5.0
_EVENT_QUEUE_MAXLEN = 500
_RESOLVED_MAXLEN = 200


class GameBridgeError(Exception):
    """Base error for bridge client failures. str(exc) is the failure_mode
    string a Tool should return, e.g. 'timeout' or 'not_connected'."""


class BridgeConnection:
    """One persistent NDJSON connection to a running game's bridge server."""

    def __init__(self, host: str = _DEFAULT_HOST, port: int = _DEFAULT_PORT) -> None:
        self._host = host
        self._port = port
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._pending: dict[str, "asyncio.Future[dict[str, Any]]"] = {}
        self._events: deque[dict[str, Any]] = deque(maxlen=_EVENT_QUEUE_MAXLEN)
        self._resolved: "OrderedDict[str, dict[str, Any]]" = OrderedDict()
        self._reader_task: Optional[asyncio.Task] = None
        self._closed = True

    @property
    def connected(self) -> bool:
        return self._writer is not None and not self._closed

    async def connect(self) -> None:
        self._reader, self._writer = await asyncio.open_connection(self._host, self._port)
        self._closed = False
        self._reader_task = asyncio.create_task(self._read_loop())

    async def close(self) -> None:
        self._closed = True
        if self._reader_task is not None:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        if self._writer is not None:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except Exception:  # noqa: BLE001
                pass
        self._writer = None
        self._reader = None

    async def _read_loop(self) -> None:
        assert self._reader is not None
        try:
            while True:
                line = await self._reader.readline()
                if not line:
                    break
                try:
                    msg = json.loads(line.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
                req_id = msg.get("req_id")
                fut = self._pending.pop(req_id, None) if req_id else None
                if fut is not None:
                    if not fut.done():
                        fut.set_result(msg)
                elif req_id:
                    # A reply to a fired-not-awaited command (fire_command) —
                    # keep it retrievable via check_result(), distinct from
                    # genuinely unsolicited events below (which have no
                    # req_id at all, e.g. a human's live placement).
                    self._resolved[req_id] = msg
                    if len(self._resolved) > _RESOLVED_MAXLEN:
                        self._resolved.popitem(last=False)
                else:
                    self._events.append(msg)
        except asyncio.CancelledError:
            pass
        except Exception:  # noqa: BLE001 — connection just dies, close() handles state
            pass
        finally:
            self._closed = True

    async def send_command(self, cmd: dict[str, Any], *, timeout: float = _ACK_TIMEOUT) -> dict[str, Any]:
        if not self.connected:
            raise GameBridgeError("not_connected")
        req_id = uuid.uuid4().hex[:12]
        payload = {**cmd, "req_id": req_id}
        loop = asyncio.get_running_loop()
        fut: "asyncio.Future[dict[str, Any]]" = loop.create_future()
        self._pending[req_id] = fut
        try:
            assert self._writer is not None
            self._writer.write((json.dumps(payload) + "\n").encode("utf-8"))
            await self._writer.drain()
            return await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            raise GameBridgeError("timeout") from None
        finally:
            self._pending.pop(req_id, None)

    async def fire_command(self, cmd: dict[str, Any]) -> str:
        """Non-blocking sibling of send_command(): writes the command and
        returns its req_id immediately, without creating or awaiting a
        future. The reasoning loop can keep going; check_result(req_id)
        retrieves the reply later, once _read_loop has it."""
        if not self.connected:
            raise GameBridgeError("not_connected")
        req_id = uuid.uuid4().hex[:12]
        payload = {**cmd, "req_id": req_id}
        assert self._writer is not None
        self._writer.write((json.dumps(payload) + "\n").encode("utf-8"))
        await self._writer.drain()
        return req_id

    def check_result(self, req_id: str) -> Optional[dict[str, Any]]:
        """Pop and return a fired command's reply if it has arrived, else
        None (still in flight, or an unknown req_id)."""
        return self._resolved.pop(req_id, None)

    def poll_events(self, since_seq: int = 0) -> list[dict[str, Any]]:
        """Unsolicited events (no matching pending request) received since
        since_seq — e.g. a human's placement pushed out live."""
        return [e for e in self._events if e.get("seq", 0) > since_seq]


# Process-local singleton registry: one connection per project slug, so
# repeated tool calls in the same agent run reuse it instead of
# reconnecting every time.
_connections: dict[str, BridgeConnection] = {}


def get_connection(project_slug: str) -> Optional[BridgeConnection]:
    return _connections.get(project_slug)


async def connect(project_slug: str, *, host: str = _DEFAULT_HOST, port: int = _DEFAULT_PORT) -> BridgeConnection:
    existing = _connections.get(project_slug)
    if existing is not None and existing.connected:
        return existing
    conn = BridgeConnection(host=host, port=port)
    await conn.connect()
    _connections[project_slug] = conn
    return conn


async def disconnect(project_slug: str) -> None:
    conn = _connections.pop(project_slug, None)
    if conn is not None:
        await conn.close()


__all__ = ["GameBridgeError", "BridgeConnection", "get_connection", "connect", "disconnect"]
