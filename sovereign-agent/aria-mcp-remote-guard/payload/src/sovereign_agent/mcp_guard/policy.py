"""mcp_guard/policy.py — who may reach Aria's MCP server, and what they may do once there.

Local stdio (Claude Desktop / Claude Code spawning `sov-mcp`) is unchanged: the operator's own
machine, the operator's own process, every tool available.

Any network transport (sse / streamable-http) is treated as REMOTE and fails closed:
  - a token is required (ARIA_MCP_TOKEN, >= 32 chars) — even on 127.0.0.1, because a tunnel
    (cloudflared, ngrok) forwards the public internet to localhost;
  - write tools (record_proof_of_value) are off unless ARIA_MCP_ALLOW_WRITE=1;
  - ask_aria (runs Aria's full agent loop) is off unless ARIA_MCP_ALLOW_ASK=1;
  - public hostnames a tunnel uses must be listed in ARIA_MCP_PUBLIC_HOSTS, or the MCP library's
    DNS-rebinding protection rejects every tunneled request (it only trusts localhost by default).

The only way to run a network transport without a token is ARIA_MCP_ALLOW_NO_TOKEN=1 on a
loopback host — an explicit, local-testing-only opt-out.
"""
from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field

MIN_TOKEN_LENGTH = 32
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})

# Every MCP tool must be classified here. Remote clients get REMOTE_READ_TOOLS only; write and agent tools
# need an explicit opt-in; anything unclassified is REFUSED remotely (default-deny), so a tool added later
# is never exposed by accident. `test_every_registered_tool_is_classified` fails until a new tool is listed.
REMOTE_READ_TOOLS = frozenset({
    "aria_status", "git_week_summary", "giving_ledger", "hypothesis_queue", "institutional_impulse_check",
    "node_vitals", "recent_learnings", "recent_reflections", "risk_register", "session_health",
    "task_backlog", "value_proof_history", "waiting_on_you", "wedge_calibrator",
})
WRITE_TOOLS = frozenset({"record_proof_of_value"})
AGENT_TOOLS = frozenset({"ask_aria"})
CLASSIFIED_TOOLS = REMOTE_READ_TOOLS | WRITE_TOOLS | AGENT_TOOLS

TRANSPORTS = frozenset({"stdio", "sse", "streamable-http"})

TOKEN_HINT = "generate one with: python -c \"import secrets; print(secrets.token_urlsafe(32))\""


def _flag(env: Mapping[str, str], name: str) -> bool:
    return env.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class RemotePolicy:
    transport: str = "stdio"
    host: str = "127.0.0.1"
    token: str | None = None
    allow_write: bool = False
    allow_ask: bool = False
    allow_no_token: bool = False
    public_hosts: tuple[str, ...] = field(default_factory=tuple)

    @property
    def remote(self) -> bool:
        return self.transport != "stdio"

    @property
    def loopback(self) -> bool:
        return self.host in LOOPBACK_HOSTS


def load_policy(transport: str, host: str, env: Mapping[str, str] | None = None) -> RemotePolicy:
    """Build the policy for this launch from the environment (never from a file in the repo)."""
    if transport not in TRANSPORTS:
        raise ValueError(f"unknown transport {transport!r}; expected one of {sorted(TRANSPORTS)}")
    if not host:
        raise ValueError("host must be non-empty")
    env = os.environ if env is None else env
    token = env.get("ARIA_MCP_TOKEN", "").strip() or None
    hosts = tuple(h.strip() for h in env.get("ARIA_MCP_PUBLIC_HOSTS", "").split(",") if h.strip())
    return RemotePolicy(
        transport=transport,
        host=host,
        token=token,
        allow_write=_flag(env, "ARIA_MCP_ALLOW_WRITE"),
        allow_ask=_flag(env, "ARIA_MCP_ALLOW_ASK"),
        allow_no_token=_flag(env, "ARIA_MCP_ALLOW_NO_TOKEN"),
        public_hosts=hosts,
    )


def validate(policy: RemotePolicy) -> list[str]:
    """Reasons this launch must be refused. Empty list = safe to start. Refusals are audited."""
    _require_policy(policy)
    if not policy.remote:
        return []
    errors: list[str] = []
    if policy.token is None:
        if not (policy.allow_no_token and policy.loopback):
            errors.append(
                f"refusing to serve {policy.transport} without ARIA_MCP_TOKEN — a tunnel would expose "
                f"Aria to anyone with the URL; {TOKEN_HINT}"
            )
    elif len(policy.token) < MIN_TOKEN_LENGTH:
        errors.append(f"ARIA_MCP_TOKEN is shorter than {MIN_TOKEN_LENGTH} characters; {TOKEN_HINT}")
    if policy.allow_no_token and not policy.loopback:
        errors.append("ARIA_MCP_ALLOW_NO_TOKEN only works on a loopback host (127.0.0.1 / localhost)")
    if errors:
        from . import safe_emit_event

        safe_emit_event("mcp_guard.launch_refused", transport=policy.transport, host=policy.host,
                     reasons=errors)
    return errors


def tool_allowed(name: str, policy: RemotePolicy) -> tuple[bool, str]:
    """Whether a tool may run under this policy, with the reason when it may not. Refusals are audited."""
    if not name:
        raise ValueError("tool name must be non-empty")
    _require_policy(policy)
    if not policy.remote or name in REMOTE_READ_TOOLS:
        return True, ""
    reason = ""
    if name in WRITE_TOOLS:
        if not policy.allow_write:
            reason = f"{name} is a write tool and is disabled for remote clients (set ARIA_MCP_ALLOW_WRITE=1)"
    elif name in AGENT_TOOLS:
        if not policy.allow_ask:
            reason = f"{name} runs Aria's agent loop and is disabled for remote clients (set ARIA_MCP_ALLOW_ASK=1)"
    else:
        reason = (f"{name} is not classified as read-only, so it is disabled for remote clients "
                  "(classify it in mcp_guard/policy.py)")
    if not reason:
        return True, ""
    from . import safe_emit_event

    safe_emit_event("mcp_guard.tool_refused", tool=name, transport=policy.transport)
    return False, reason


def allowed_hosts(policy: RemotePolicy) -> tuple[list[str], list[str]]:
    """Host and Origin allow-lists for the MCP library's DNS-rebinding protection."""
    _require_policy(policy)
    hosts = ["127.0.0.1:*", "localhost:*", "[::1]:*"]
    origins = ["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"]
    for public in policy.public_hosts:
        hosts += [public, f"{public}:*"]
        origins.append(f"https://{public}")
    return hosts, origins


def _require_policy(policy: object) -> None:
    if not isinstance(policy, RemotePolicy):
        raise TypeError(f"expected RemotePolicy, got {type(policy).__name__}")
