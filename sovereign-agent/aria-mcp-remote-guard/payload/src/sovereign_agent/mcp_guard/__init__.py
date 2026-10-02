"""mcp_guard — fail-closed remote access for Aria's MCP server (token gate, read-only by default,
tunnel-ready host allow-list). Local stdio use is unchanged. Staged; applied via apply_mcp_guard.sh."""
from __future__ import annotations

from typing import Any

TRACE_ID = "mcp-guard"


def safe_emit_event(flag: str, **payload: Any) -> None:
    """Best-effort `emit_event`: write one audit event to Aria's event log (plane=control). A logging
    failure must never break the guard itself. Never pass a token or a secret path in `payload`."""
    if not flag:
        raise ValueError("safe_emit_event needs a flag")
    try:
        from sovereign_agent.events import emit_event

        emit_event(flag, plane="control", trace_id=TRACE_ID, payload=payload)
    except Exception:  # noqa: BLE001 — observability is best-effort, the guard is not
        pass


from .middleware import TokenGuard  # noqa: E402 — safe_emit_event must exist before submodules load
from .policy import (  # noqa: E402
    AGENT_TOOLS,
    CLASSIFIED_TOOLS,
    MIN_TOKEN_LENGTH,
    REMOTE_READ_TOOLS,
    WRITE_TOOLS,
    RemotePolicy,
    allowed_hosts,
    load_policy,
    tool_allowed,
    validate,
)

__all__ = [
    "AGENT_TOOLS",
    "CLASSIFIED_TOOLS",
    "MIN_TOKEN_LENGTH",
    "REMOTE_READ_TOOLS",
    "TRACE_ID",
    "WRITE_TOOLS",
    "RemotePolicy",
    "TokenGuard",
    "allowed_hosts",
    "load_policy",
    "safe_emit_event",
    "tool_allowed",
    "validate",
]
