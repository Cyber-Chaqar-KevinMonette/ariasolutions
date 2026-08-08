"""Approval-token contract tests. Architecture §7a.

The four properties to verify:
  1. Args binding — mutated args invalidate a granted token
  2. Expiry — tokens past their expiry_ts are rejected
  3. One-shot — token file unlinked after successful consume
  4. HMAC — forged tokens (wrong signature) rejected
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import pytest

from sovereign_agent.approval import (
    ApprovalDenied,
    consume_grant,
    request_approval,
    write_grant,
)
from sovereign_agent.config import SETTINGS


def _make_request(tool_name="git_push", args=None, expiry=300):
    args = args or {"remote": "origin", "branch": "main"}
    return request_approval(
        tool_name=tool_name,
        args=args,
        justification="committing v0.1 scaffold",
        trace_id="test-trace",
        expiry_seconds=expiry,
    )


def test_grant_and_consume_succeeds():
    req = _make_request()
    write_grant(req)
    # Consume should not raise
    consume_grant(
        event_id=req.event_id,
        tool_name=req.tool_name,
        args=req.args,
        trace_id="test-trace",
    )
    # Token is one-shot — file gone
    token_file = SETTINGS.paths.approvals_dir / f"{req.event_id}.tok"
    assert not token_file.exists()


def test_consume_without_grant_raises():
    req = _make_request()
    # No write_grant
    with pytest.raises(ApprovalDenied, match="not found"):
        consume_grant(
            event_id=req.event_id,
            tool_name=req.tool_name,
            args=req.args,
            trace_id="test-trace",
        )


def test_args_binding_blocks_argument_swap():
    """Model can't approve `git push origin main` then swap to `git push origin master`."""
    req = _make_request(args={"remote": "origin", "branch": "main"})
    write_grant(req)
    with pytest.raises(ApprovalDenied, match="args differ"):
        consume_grant(
            event_id=req.event_id,
            tool_name=req.tool_name,
            args={"remote": "origin", "branch": "master"},  # swapped!
            trace_id="test-trace",
        )


def test_expired_token_rejected():
    req = _make_request(expiry=1)
    write_grant(req)
    time.sleep(1.5)
    with pytest.raises(ApprovalDenied, match="expired"):
        consume_grant(
            event_id=req.event_id,
            tool_name=req.tool_name,
            args=req.args,
            trace_id="test-trace",
        )


def test_forged_hmac_rejected():
    req = _make_request()
    write_grant(req)
    # Tamper with the token file
    token_file = SETTINGS.paths.approvals_dir / f"{req.event_id}.tok"
    contents = token_file.read_text()
    # Flip a character in the hmac field — easiest: overwrite with a known-bad value
    import json

    token = json.loads(contents)
    token["hmac"] = "0" * 64
    token_file.write_text(json.dumps(token))

    with pytest.raises(ApprovalDenied, match="HMAC"):
        consume_grant(
            event_id=req.event_id,
            tool_name=req.tool_name,
            args=req.args,
            trace_id="test-trace",
        )


def test_consumed_token_cannot_be_replayed():
    req = _make_request()
    write_grant(req)
    consume_grant(
        event_id=req.event_id,
        tool_name=req.tool_name,
        args=req.args,
        trace_id="test-trace",
    )
    # Second consume must fail — token was unlinked
    with pytest.raises(ApprovalDenied):
        consume_grant(
            event_id=req.event_id,
            tool_name=req.tool_name,
            args=req.args,
            trace_id="test-trace",
        )
