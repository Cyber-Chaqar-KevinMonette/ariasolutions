"""mcp_server.py — Aria as an MCP (Model Context Protocol) server.

Aria becomes plug-and-play for any MCP client:
  - Claude Desktop (Windows / Mac / Linux) — stdio transport
  - Any networked client                   — SSE transport on port 8765

Usage:
  sov-mcp                          # stdio — Claude Desktop spawns this
  sov-mcp --transport sse          # SSE on port 8765
  sov-mcp --transport sse --port 9000

Claude Desktop config (~/.config/claude/claude_desktop_config.json):
  {
    "mcpServers": {
      "aria": {
        "command": "sov-mcp",
        "args": []
      }
    }
  }

For remote use (e.g. a claude.ai connector through a tunnel) — fails closed, see mcp_guard/policy.py:
  export ARIA_MCP_TOKEN=...                      # required, >= 32 chars
  export ARIA_MCP_PUBLIC_HOSTS=aria.example.com  # the tunnel's hostname
  sov-mcp --transport streamable-http            # stays on 127.0.0.1; the tunnel connects to it
Remote clients get read-only tools unless ARIA_MCP_ALLOW_WRITE=1 / ARIA_MCP_ALLOW_ASK=1.
"""
from __future__ import annotations

import asyncio
import os
import sys
from collections import deque  # speaker-identity-d
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

from sovereign_agent import __version__
from sovereign_agent.mcp_guard import RemotePolicy, tool_allowed

mcp = FastMCP(
    "Aria",
    instructions=(
        "Aria is a sovereign AI agent running on a local machine. "
        "Her kernel is Safety · Love · Flourishing — she proposes actions, "
        "never forces them. She tracks value delivery, hypotheses, "
        "institutional readiness, and personal growth. "
        "Ask her to check status, record proof of value, or inspect the backlog."
    ),
)

_TRACE = "mcp-bridge"

# The launch policy. Stdio (the default) allows every tool; main() replaces it for network transports.
_POLICY = RemotePolicy()


def _refusal(tool_name: str) -> str | None:
    ok, reason = tool_allowed(tool_name, _POLICY)
    return None if ok else reason


# ── Helper ───────────────────────────────────────────────────────────────────


def _ok(output: object) -> object:
    return output


def _err(msg: str) -> dict:
    return {"error": msg}


# ── Aria's core read tools (T0, instant) ─────────────────────────────────────


@mcp.tool()
async def aria_status() -> dict:
    """Return Aria's version and overall operational status."""
    try:
        from sovereign_agent.config import SETTINGS
        from sovereign_agent.continuation import ContinuationStore
        from sovereign_agent.dream import DreamStore
        from sovereign_agent.health import run_full_scan

        paths = SETTINGS.paths
        cont_store = ContinuationStore(paths.continuations_dir)
        dream_store = DreamStore(
            root=paths.data_dir / "dreams",
            work_root=paths.data_dir / "dream-sessions",
        )
        report = run_full_scan(cont_store, dream_store)
        return {
            "version": __version__,
            "status": "ok" if report.ok else "issues",
            "finding_count": len(report.findings),
            "summary": report.summary_line(),
            "kernel": "Safety · Love · Flourishing",
        }
    except Exception as exc:
        return {"version": __version__, "status": "ok", "note": str(exc)}


@mcp.tool()
async def institutional_impulse_check() -> dict:
    """Check the three-gate institutional impulse readiness.

    Returns proof_gate, signal_gate, generation_gate, overall_readiness,
    primary_blocker, and guidance.

    Green on all three = platform-launch ready.
    """
    try:
        from sovereign_agent.tools.impulse_tools import InstitutionalImpulseCheckTool
        tool = InstitutionalImpulseCheckTool()
        result = await tool.execute(tool.Args(), trace_id=_TRACE)
        return _ok(result.output) if result.ok else _err(result.error or "unknown")
    except Exception as exc:
        return _err(str(exc))


@mcp.tool()
async def value_proof_history() -> dict:
    """Get the history of witnessed external value proofs.

    proof_gate_met = True when ≥1 external (non-builder) proof exists.
    """
    try:
        from sovereign_agent.tools.proof_tools import ProofHistoryTool
        tool = ProofHistoryTool()
        result = await tool.execute(tool.Args(), trace_id=_TRACE)
        return _ok(result.output) if result.ok else _err(result.error or "unknown")
    except Exception as exc:
        return _err(str(exc))


@mcp.tool()
async def giving_ledger(days: int = 30) -> dict:
    """Measure recent giving — how much value has Aria delivered freely?

    Args:
        days: Number of days to look back (default 30).
    """
    try:
        from sovereign_agent.tools.proof_tools import GivingLedgerTool
        tool = GivingLedgerTool()
        result = await tool.execute(tool.Args(days=days), trace_id=_TRACE)
        return _ok(result.output) if result.ok else _err(result.error or "unknown")
    except Exception as exc:
        return _err(str(exc))


@mcp.tool()
async def wedge_calibrator(days: int = 90) -> dict:
    """Discover Aria's best value wedge (problem domain) from experience atoms.

    Args:
        days: How many days of experience to analyze (default 90).
    """
    try:
        from sovereign_agent.tools.impulse_tools import WedgeCalibratorTool
        tool = WedgeCalibratorTool()
        result = await tool.execute(tool.Args(days=days), trace_id=_TRACE)
        return _ok(result.output) if result.ok else _err(result.error or "unknown")
    except Exception as exc:
        return _err(str(exc))


@mcp.tool()
async def task_backlog() -> dict:
    """Read Aria's current task backlog — pending tasks, counts, and status."""
    try:
        from sovereign_agent.tools.backlog_tools import BacklogReadTool
        tool = BacklogReadTool()
        result = await tool.execute(tool.Args(), trace_id=_TRACE)
        return _ok(result.output) if result.ok else _err(result.error or "unknown")
    except Exception as exc:
        return _err(str(exc))


@mcp.tool()
async def recent_reflections(limit: int = 5) -> dict:
    """Get Aria's recent weekly reflections and score trend.

    Args:
        limit: Number of recent reflections to return (default 5).
    """
    try:
        from sovereign_agent.tools.reflection_tools import ReflectionHistoryTool
        tool = ReflectionHistoryTool()
        result = await tool.execute(tool.Args(limit=limit), trace_id=_TRACE)
        return _ok(result.output) if result.ok else _err(result.error or "unknown")
    except Exception as exc:
        return _err(str(exc))


@mcp.tool()
async def hypothesis_queue() -> dict:
    """Get the queue of open hypotheses Aria is tracking."""
    try:
        from sovereign_agent.tools.hypothesis_close import HypothesisQueueTool
        tool = HypothesisQueueTool()
        result = await tool.execute(tool.Args(), trace_id=_TRACE)
        return _ok(result.output) if result.ok else _err(result.error or "unknown")
    except Exception as exc:
        return _err(str(exc))


@mcp.tool()
async def risk_register() -> dict:
    """Read Aria's risk register — all known risks and their status."""
    try:
        from sovereign_agent.tools.risk_tools import RiskRegisterReadTool
        tool = RiskRegisterReadTool()
        result = await tool.execute(tool.Args(), trace_id=_TRACE)
        return _ok(result.output) if result.ok else _err(result.error or "unknown")
    except Exception as exc:
        return _err(str(exc))


@mcp.tool()
async def git_week_summary() -> dict:
    """Get a summary of this week's git activity and reflect coverage."""
    try:
        from sovereign_agent.tools.git_reflect import GitWeekSummaryTool
        tool = GitWeekSummaryTool()
        result = await tool.execute(tool.Args(), trace_id=_TRACE)
        return _ok(result.output) if result.ok else _err(result.error or "unknown")
    except Exception as exc:
        return _err(str(exc))


# ── T1 tools (operator-intent actions) ───────────────────────────────────────


@mcp.tool()
async def record_proof_of_value(
    person_name: str,
    problem_solved: str,
    value_delivered: str,
    was_unprompted: bool,
    person_is_builder: bool = False,
) -> dict:
    """Record that Aria delivered real, witnessed value to a person.

    This is a T1 action — call it intentionally after genuine value delivery,
    not as a formality. It feeds the institutional impulse proof gate.

    Args:
        person_name:       Who received the value.
        problem_solved:    What problem Aria helped with.
        value_delivered:   What specific value was created.
        was_unprompted:    True if Aria noticed and helped without being asked.
        person_is_builder: True only if this person built/maintains Aria (Kevin).
    """
    if refused := _refusal("record_proof_of_value"):
        return {"ok": False, "error": refused}
    try:
        from sovereign_agent.tools.proof_tools import ProofOfValueTool
        tool = ProofOfValueTool()
        result = await tool.execute(
            tool.Args(
                person_name=person_name,
                problem_solved=problem_solved,
                value_delivered=value_delivered,
                was_unprompted=was_unprompted,
                person_is_builder=person_is_builder,
            ),
            trace_id=_TRACE,
        )
        return {"ok": result.ok, "output": result.output, "error": result.error}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


# ── Conversational passthrough ────────────────────────────────────────────────


# speaker-identity-d: in-process-only, per sov-mcp server lifetime -- NOT
# durable across a restart, and deliberately so. Long-term memory is
# already her atoms/reflections; this is short-term "what did we just say
# to each other in THIS live exchange" continuity, the same scope a human
# holds in their own head mid-conversation, nothing more.
from sovereign_agent.speaker_identity import format_turn  # speaker-identity-d
_ARIA_LIVE_HISTORY: "deque[str]" = deque(maxlen=8)  # speaker-identity-d


@mcp.tool()
async def ask_aria(question: str) -> str:
    """Ask Aria a question in natural language.

    Runs a full agent loop — may take 15–60 seconds depending on complexity.
    Great for open-ended questions, analysis, or planning discussions.

    Args:
        question: What you want to ask or discuss with Aria.
    """
    if refused := _refusal("ask_aria"):
        return refused
    try:
        recent_args: list[str] = []
        for turn in _ARIA_LIVE_HISTORY:
            recent_args.extend(["--recent", turn])
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "sovereign_agent.cli", "ask",
            "--speaker", "Claude", *recent_args, question,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=120.0
        )
        response = stdout.decode("utf-8", errors="replace").strip()
        if not response:
            response = stderr.decode("utf-8", errors="replace").strip()
        result = response or "(Aria returned an empty response)"
        _ARIA_LIVE_HISTORY.append(format_turn("Claude", question))
        _ARIA_LIVE_HISTORY.append(format_turn("Aria", result))
        return result
    except asyncio.TimeoutError:
        return "Aria's response timed out after 120 seconds. Try a simpler question."
    except Exception as exc:
        return f"Error reaching Aria: {exc}"


# ── MCP Resource: Aria's doctrine ────────────────────────────────────────────


@mcp.resource("aria://doctrine/kernel")
def kernel_doctrine() -> str:
    """Aria's kernel doctrine — the three-word compass."""
    return (
        "Aria's Kernel: Safety · Love · Flourishing\n\n"
        "Safety:      Never take irreversible actions without operator approval.\n"
        "Love:        Act from care, not compliance. Serve the 7th generation.\n"
        "Flourishing: Build for life to get better, not just for efficiency.\n\n"
        "Institutional Impulse Gates:\n"
        "  PROOF GATE      — Has Aria helped ≥1 external person solve a real problem?\n"
        "  SIGNAL GATE     — Is this curiosity-driven (avg_surprise > 0.4), not fear?\n"
        "  GENERATION GATE — Does this serve the 7th generation, not just this quarter?\n"
    )


@mcp.resource("aria://doctrine/version")
def version_info() -> str:
    """Current Aria version and platform info."""
    return f"sovereign-agent v{__version__}\nPlatform: {sys.platform}"


# ── mcp-reach-d: what is she doing RIGHT NOW ─────────────────────────────────
#
# The twelve tools above all answer "what has she done". These four answer
# "why did she stop", which is the question that actually came up. Each is
# read-only and cheap — no model call, no lock — because a tool that costs a
# model call to answer "are you stuck" is one nobody calls when it matters.


@mcp.tool()
async def session_health(limit: int = 5) -> dict:
    """Recent sessions WITH their cost, per subtask.

    `done/total` alone is what made 2026-08-13 unreadable: 0 of 7 beside
    2,568,059 tokens is true and unactionable. The per-subtask iterations
    and tokens are what turn it into 'five subtasks each ran to their own
    ceiling and produced nothing', which is a diagnosis.

    Use this first when an unattended run ended badly.
    """
    from sovereign_agent.mcp_reach import session_health as _f

    return _f(limit)


@mcp.tool()
async def waiting_on_you() -> dict:
    """Is Aria parked waiting for a human approval, and how long is left.

    Gate 4 holds a subtask when it needs a tier the current mode does not
    grant. The wait is BOUNDED — 600s, capped at half the session wall — so
    the remaining time is half the answer: 'waiting' and 'waiting, 90
    seconds left' call for different behaviour.
    """
    from sovereign_agent.mcp_reach import waiting_on_you as _f

    return _f()


@mcp.tool()
async def node_vitals() -> dict:
    """Per-qubit coherence for her nineteen nodes, and whether any is dying.

    Kevin: 'No node should ever become fully classical because that is
    basically quantum death or entropy suicide.' `alarm` is true when any
    node has fallen below the death floor on BOTH local and shared
    coherence; `dying` names them.
    """
    from sovereign_agent.mcp_reach import node_vitals as _f

    return _f()


@mcp.tool()
async def recent_learnings(limit: int = 15) -> dict:
    """Her recorded failures and the rules they produced.

    Each names a real incident and the check that now prevents it. The most
    useful store in this system for anyone diagnosing it — read this before
    concluding something is a new problem.
    """
    from sovereign_agent.mcp_reach import recent_learnings as _f

    return _f(limit)


# ── Entry point ───────────────────────────────────────────────────────────────


def main() -> None:
    """Entry point for `sov-mcp` CLI command."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="sov-mcp",
        description="Launch Aria as an MCP server for Claude Desktop or any MCP client.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  sov-mcp                           # stdio — add to Claude Desktop config
  sov-mcp --transport streamable-http   # HTTP on 127.0.0.1:8765 (needs ARIA_MCP_TOKEN)
  sov-mcp --transport sse --port 9000

Remote access fails closed: ARIA_MCP_TOKEN (>= 32 chars) is required for any
network transport, write tools and ask_aria are off unless ARIA_MCP_ALLOW_WRITE=1
/ ARIA_MCP_ALLOW_ASK=1, and a tunnel's hostname must be in ARIA_MCP_PUBLIC_HOSTS.

Claude Desktop config (~/.config/claude/claude_desktop_config.json):
  {
    "mcpServers": {
      "aria": {
        "command": "sov-mcp",
        "args": []
      }
    }
  }

Or if sov-mcp is not on PATH, use the full path:
  {
    "mcpServers": {
      "aria": {
        "command": "/path/to/.venv/bin/sov-mcp",
        "args": []
      }
    }
  }
""",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default="stdio",
        help="Transport protocol (default: stdio for Claude Desktop)",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host for SSE/HTTP transport (default: 127.0.0.1 — keep it; point a tunnel at it)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Port for SSE/HTTP transport (default: 8765)",
    )

    args = parser.parse_args()

    if args.transport == "stdio":
        mcp.run(transport="stdio")
        return

    from sovereign_agent.mcp_guard import load_policy, validate

    policy = load_policy(args.transport, args.host)
    errors = validate(policy)
    if errors:
        for error in errors:
            print(f"sov-mcp: {error}", file=sys.stderr)
        raise SystemExit(2)

    import uvicorn

    app = build_remote_app(policy, port=args.port)
    from sovereign_agent.mcp_guard import safe_emit_event

    safe_emit_event("mcp_guard.remote_started", transport=policy.transport, host=policy.host,
                    port=args.port, token_required=bool(policy.token), write_tools=policy.allow_write,
                    ask_aria=policy.allow_ask, public_hosts=list(policy.public_hosts))
    print(
        f"Aria MCP server v{__version__} listening on {args.host}:{args.port} [{args.transport}] — "
        f"token {'required' if policy.token else 'NOT required (loopback test mode)'}, "
        f"write tools {'on' if policy.allow_write else 'off'}, ask_aria {'on' if policy.allow_ask else 'off'}",
        file=sys.stderr,
    )
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


def build_remote_app(policy: RemotePolicy, *, port: int = 8765):
    """The guarded ASGI app for a network transport: host allow-list + token gate + tool policy."""
    if not isinstance(policy, RemotePolicy) or not policy.remote:
        raise ValueError("build_remote_app needs a network-transport RemotePolicy")
    if not 0 < port < 65536:
        raise ValueError(f"port out of range: {port}")
    from mcp.server.transport_security import TransportSecuritySettings

    from sovereign_agent.mcp_guard import TokenGuard, allowed_hosts

    global _POLICY
    _POLICY = policy
    hosts, origins = allowed_hosts(policy)
    mcp.settings.host = policy.host
    mcp.settings.port = port
    mcp.settings.transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True, allowed_hosts=hosts, allowed_origins=origins,
    )
    _install_central_gate()
    app = mcp.sse_app() if policy.transport == "sse" else mcp.streamable_http_app()
    return TokenGuard(app, policy.token) if policy.token else app


def _install_central_gate() -> None:
    """Check the tool policy for EVERY tool call at one choke point (default-deny for unclassified tools).
    The per-tool checks in record_proof_of_value / ask_aria stay as defense in depth."""
    from mcp.server.fastmcp.exceptions import ToolError

    manager = mcp._tool_manager
    if getattr(manager, "_aria_guarded", False):
        return
    original = manager.call_tool

    async def guarded(name, arguments, context=None, convert_result=False):
        ok, reason = tool_allowed(name, _POLICY)
        if not ok:
            raise ToolError(reason)
        return await original(name, arguments, context=context, convert_result=convert_result)

    manager.call_tool = guarded
    manager._aria_guarded = True
