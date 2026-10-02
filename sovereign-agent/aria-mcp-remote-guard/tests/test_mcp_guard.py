"""Tests for aria-mcp-remote-guard — prove remote access fails closed and still works when configured.

The staged mcp_server.py replaces a live module of the same name, so it is loaded from its payload file
(the live one would otherwise shadow it on sovereign_agent.__path__).
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import httpx
import pytest

from sovereign_agent.mcp_guard import (
    MIN_TOKEN_LENGTH,
    RemotePolicy,
    TokenGuard,
    allowed_hosts,
    load_policy,
    tool_allowed,
    validate,
)

TOKEN = "t" * MIN_TOKEN_LENGTH
PAYLOAD_SERVER = Path(__file__).parents[1] / "payload" / "src" / "sovereign_agent" / "mcp_server.py"
MCP_ACCEPT = "application/json, text/event-stream"


_loads = 0


@pytest.fixture(autouse=True)
def events(monkeypatch):
    """Capture audit events (and keep tests from writing to the operator's real event log)."""
    import sovereign_agent.events as events_mod

    captured: list[tuple[str, dict]] = []
    monkeypatch.setattr(events_mod, "emit_event",
                        lambda flag, **kw: captured.append((flag, kw.get("payload") or {})) or "evt")
    return captured


def _staged_server():
    """A FRESH copy of the server module per call (its FastMCP app and _POLICY are module globals, and
    an HTTP session manager can only run once). The payload file before apply; the live file after
    apply copies this test into tests/."""
    global _loads
    _loads += 1
    path = PAYLOAD_SERVER if PAYLOAD_SERVER.is_file() else Path(
        importlib.util.find_spec("sovereign_agent.mcp_server").origin)
    spec = importlib.util.spec_from_file_location(f"sovereign_agent._guard_test_server_{_loads}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ── policy ───────────────────────────────────────────────────────────────────


def test_stdio_is_unchanged_every_tool_allowed():
    policy = load_policy("stdio", "127.0.0.1", env={})
    assert validate(policy) == []
    assert tool_allowed("record_proof_of_value", policy) == (True, "")
    assert tool_allowed("ask_aria", policy) == (True, "")


@pytest.mark.parametrize("transport", ["sse", "streamable-http"])
def test_network_transport_without_token_is_refused_even_on_loopback(transport):
    errors = validate(load_policy(transport, "127.0.0.1", env={}))
    assert errors and "ARIA_MCP_TOKEN" in errors[0]


def test_short_token_is_refused():
    errors = validate(load_policy("streamable-http", "127.0.0.1", env={"ARIA_MCP_TOKEN": "short"}))
    assert errors and "shorter than" in errors[0]


def test_no_token_opt_out_only_on_loopback():
    env = {"ARIA_MCP_ALLOW_NO_TOKEN": "1"}
    assert validate(load_policy("streamable-http", "127.0.0.1", env=env)) == []
    assert validate(load_policy("streamable-http", "0.0.0.0", env=env))


def test_remote_is_read_only_by_default():
    policy = load_policy("streamable-http", "127.0.0.1", env={"ARIA_MCP_TOKEN": TOKEN})
    assert validate(policy) == []
    assert tool_allowed("aria_status", policy) == (True, "")
    allowed, reason = tool_allowed("record_proof_of_value", policy)
    assert not allowed and "ARIA_MCP_ALLOW_WRITE" in reason
    allowed, reason = tool_allowed("ask_aria", policy)
    assert not allowed and "ARIA_MCP_ALLOW_ASK" in reason


def test_write_and_ask_can_be_enabled_explicitly():
    env = {"ARIA_MCP_TOKEN": TOKEN, "ARIA_MCP_ALLOW_WRITE": "1", "ARIA_MCP_ALLOW_ASK": "true"}
    policy = load_policy("streamable-http", "127.0.0.1", env=env)
    assert tool_allowed("record_proof_of_value", policy)[0]
    assert tool_allowed("ask_aria", policy)[0]


def test_public_hosts_join_the_allow_list():
    policy = load_policy("streamable-http", "127.0.0.1",
                         env={"ARIA_MCP_TOKEN": TOKEN, "ARIA_MCP_PUBLIC_HOSTS": "aria.example.com, b.example.org"})
    hosts, origins = allowed_hosts(policy)
    assert "aria.example.com" in hosts and "b.example.org:*" in hosts
    assert "https://aria.example.com" in origins
    assert "127.0.0.1:*" in hosts


# ── token gate ───────────────────────────────────────────────────────────────


async def _echo_app(scope, receive, send):
    body = json.dumps({"path": scope["path"]}).encode()
    await send({"type": "http.response.start", "status": 200,
                "headers": [(b"content-type", b"application/json")]})
    await send({"type": "http.response.body", "body": body})


def _client(app) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1")


async def test_gate_rejects_missing_and_wrong_tokens():
    async with _client(TokenGuard(_echo_app, TOKEN)) as c:
        missing = await c.get("/mcp")
        wrong = await c.get("/mcp", headers={"Authorization": "Bearer " + "x" * MIN_TOKEN_LENGTH})
        wrong_path = await c.get("/k/" + "x" * MIN_TOKEN_LENGTH + "/mcp")
    assert missing.status_code == wrong.status_code == wrong_path.status_code == 401
    assert missing.headers["www-authenticate"].startswith("Bearer")


async def test_gate_accepts_bearer_token():
    async with _client(TokenGuard(_echo_app, TOKEN)) as c:
        r = await c.get("/mcp", headers={"Authorization": f"Bearer {TOKEN}"})
    assert r.status_code == 200 and r.json() == {"path": "/mcp"}


async def test_gate_accepts_and_strips_path_secret():
    async with _client(TokenGuard(_echo_app, TOKEN)) as c:
        r = await c.get(f"/k/{TOKEN}/mcp")
        root = await c.get(f"/k/{TOKEN}")
    assert r.status_code == 200 and r.json() == {"path": "/mcp"}
    assert root.status_code == 200 and root.json() == {"path": "/"}


def test_gate_refuses_empty_token():
    with pytest.raises(ValueError):
        TokenGuard(_echo_app, "")


# ── the real MCP app, end to end ─────────────────────────────────────────────


def _rpc(method: str, params: dict | None = None, rid: int | None = 1) -> dict:
    msg = {"jsonrpc": "2.0", "method": method, "params": params or {}}
    if rid is not None:
        msg["id"] = rid
    return msg


def _rpc_result(response) -> dict:
    """Read a JSON-RPC reply that may come back as JSON or as a server-sent event."""
    if response.headers.get("content-type", "").startswith("text/event-stream"):
        for line in response.text.splitlines():
            if line.startswith("data:"):
                return json.loads(line[5:].strip())
        raise AssertionError(f"no data line in SSE response: {response.text!r}")
    return response.json()


@pytest.fixture
def remote_app():
    from starlette.testclient import TestClient

    server = _staged_server()
    # The server's OWN RemotePolicy class: build_remote_app checks isinstance, and in a full run another test
    # can drop sovereign_agent.mcp_guard from sys.modules, leaving this file's import a different class object.
    policy = server.RemotePolicy(transport="streamable-http", host="127.0.0.1", token=TOKEN,
                          public_hosts=("aria.example.com",))
    app = server.build_remote_app(policy)
    with TestClient(app, base_url="https://aria.example.com") as client:
        client.app_server = server
        yield client


def _initialize(client, prefix: str = "", headers: dict | None = None):
    headers = {"Accept": MCP_ACCEPT, **(headers or {})}
    init = client.post(f"{prefix}/mcp", headers=headers, json=_rpc("initialize", {
        "protocolVersion": "2025-06-18", "capabilities": {},
        "clientInfo": {"name": "guard-test", "version": "0"}}))
    return init, headers


def test_real_server_rejects_requests_without_token(remote_app):
    init, _ = _initialize(remote_app)
    assert init.status_code == 401


def test_real_server_rejects_unlisted_host(remote_app):
    init, _ = _initialize(remote_app, headers={"Authorization": f"Bearer {TOKEN}", "Host": "evil.example.net"})
    assert init.status_code in (400, 403, 421)


def test_real_server_serves_read_tools_and_refuses_writes(remote_app):
    init, headers = _initialize(remote_app, headers={"Authorization": f"Bearer {TOKEN}"})
    assert init.status_code == 200, init.text
    assert _rpc_result(init)["result"]["serverInfo"]["name"] == "Aria"
    headers["mcp-session-id"] = init.headers["mcp-session-id"]
    remote_app.post("/mcp", headers=headers, json=_rpc("notifications/initialized", rid=None))

    listed = _rpc_result(remote_app.post("/mcp", headers=headers, json=_rpc("tools/list", rid=2)))
    names = {t["name"] for t in listed["result"]["tools"]}
    assert {"aria_status", "record_proof_of_value", "ask_aria"} <= names

    call = remote_app.post("/mcp", headers=headers, json=_rpc("tools/call", {
        "name": "record_proof_of_value",
        "arguments": {"person_name": "x", "problem_solved": "x", "value_delivered": "x",
                      "was_unprompted": False}}, rid=3))
    text = json.dumps(_rpc_result(call))
    assert "disabled for remote clients" in text

    ask = remote_app.post("/mcp", headers=headers, json=_rpc("tools/call", {
        "name": "ask_aria", "arguments": {"question": "hello"}}, rid=4))
    assert "disabled for remote clients" in json.dumps(_rpc_result(ask))


def test_real_server_accepts_path_secret(remote_app):
    init, _ = _initialize(remote_app, prefix=f"/k/{TOKEN}")
    assert init.status_code == 200, init.text


def test_stdio_policy_leaves_write_tool_enabled():
    server = _staged_server()
    assert server._refusal("record_proof_of_value") is None
    assert server._refusal("ask_aria") is None


# ── observability + input validation (Aria's quality gate) ───────────────────


def test_refusals_are_audited_without_secrets(events):
    policy = load_policy("streamable-http", "127.0.0.1", env={"ARIA_MCP_TOKEN": TOKEN})
    tool_allowed("record_proof_of_value", policy)
    validate(load_policy("sse", "127.0.0.1", env={}))
    flags = [flag for flag, _ in events]
    assert "mcp_guard.tool_refused" in flags and "mcp_guard.launch_refused" in flags
    assert TOKEN not in json.dumps(events)


async def test_denials_are_audited_once_per_interval_with_a_count(events):
    guard = TokenGuard(_echo_app, TOKEN)
    async with _client(guard) as c:
        for _ in range(5):
            await c.get(f"/k/{'x' * MIN_TOKEN_LENGTH}/mcp")
    denials = [payload for flag, payload in events if flag == "mcp_guard.request_denied"]
    assert len(denials) == 1 and guard.denied_total == 5
    from sovereign_agent.mcp_guard.middleware import DENIAL_EVENT_INTERVAL_S
    assert DENIAL_EVENT_INTERVAL_S >= 1  # the throttle that keeps a flood out of the event log
    assert denials[0]["used_path_secret"] is True
    assert "x" * MIN_TOKEN_LENGTH not in json.dumps(events)


def test_allowed_calls_emit_nothing(events):
    tool_allowed("aria_status", load_policy("streamable-http", "127.0.0.1", env={"ARIA_MCP_TOKEN": TOKEN}))
    assert events == []


def test_bad_inputs_are_rejected():
    with pytest.raises(ValueError):
        load_policy("carrier-pigeon", "127.0.0.1", env={})
    with pytest.raises(ValueError):
        tool_allowed("", RemotePolicy())
    with pytest.raises(TypeError):
        validate("not a policy")
    server = _staged_server()
    with pytest.raises(ValueError):
        server.build_remote_app(server.RemotePolicy())  # stdio policy has no remote app


# ── default-deny: every tool classified, unclassified tools refused remotely ─


def test_every_registered_tool_is_classified():
    """Adding an MCP tool without classifying it in mcp_guard/policy.py fails here, on purpose."""
    from sovereign_agent.mcp_guard import CLASSIFIED_TOOLS

    registered = set(_staged_server().mcp._tool_manager._tools)
    assert registered - CLASSIFIED_TOOLS == set(), "classify these in mcp_guard/policy.py"


def test_unclassified_tools_are_refused_remotely_but_fine_locally():
    remote = load_policy("streamable-http", "127.0.0.1",
                         env={"ARIA_MCP_TOKEN": TOKEN, "ARIA_MCP_ALLOW_WRITE": "1", "ARIA_MCP_ALLOW_ASK": "1"})
    allowed, reason = tool_allowed("brand_new_write_tool", remote)
    assert not allowed and "not classified" in reason
    assert tool_allowed("brand_new_write_tool", RemotePolicy()) == (True, "")   # stdio unchanged


def test_central_gate_blocks_an_unclassified_tool_end_to_end(remote_app):
    init, headers = _initialize(remote_app, headers={"Authorization": f"Bearer {TOKEN}"})
    headers["mcp-session-id"] = init.headers["mcp-session-id"]
    remote_app.post("/mcp", headers=headers, json=_rpc("notifications/initialized", rid=None))
    # register a new, unclassified tool on the same server instance the client is talking to
    mcp_obj = remote_app.app_server.mcp
    mcp_obj.add_tool(lambda: "should never run", name="sneaky_new_tool", description="unclassified")
    call = remote_app.post("/mcp", headers=headers, json=_rpc("tools/call", {
        "name": "sneaky_new_tool", "arguments": {}}, rid=9))
    body = json.dumps(_rpc_result(call))
    assert "not classified" in body and "should never run" not in body
