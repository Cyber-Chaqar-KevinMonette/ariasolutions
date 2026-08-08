"""Tier 3 approval-token contract. Architecture §7a.

Properties enforced:
  - One approval = one tool call (token unlinked on use)
  - Args binding (HMAC over args_hash; mutated args invalidate the token)
  - Expiry (default 5 min)
  - Auditability (approval-needed-d / approval-d / approval-x events)
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .config import SETTINGS
from .events import emit_event


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _hash_args(args: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(args).encode("utf-8")).hexdigest()


def _load_or_create_secret() -> bytes:
    path = SETTINGS.paths.secret_key_file
    if path.exists():
        return path.read_bytes()
    # Generate 256-bit secret on first use
    key = secrets.token_bytes(32)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Write atomically with restrictive perms
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(key)
    tmp.chmod(0o600)
    tmp.replace(path)
    return key


def _hmac(message: str) -> str:
    key = _load_or_create_secret()
    return hmac.new(key, message.encode("utf-8"), hashlib.sha256).hexdigest()


def _hmac_message(event_id: str, args_hash: str, expiry_ts: str) -> str:
    return f"{event_id}|{args_hash}|{expiry_ts}"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class ApprovalRequest:
    event_id: str
    tool_name: str
    args: dict[str, Any]
    args_hash: str
    justification: str
    expiry_ts: str  # RFC3339


@dataclass(frozen=True)
class ApprovalGrant:
    event_id: str
    args_hash: str
    expiry_ts: str
    hmac_hex: str


class ApprovalDenied(Exception):
    """Tier 3 dispatch refused at the approval layer."""


def request_approval(
    *,
    tool_name: str,
    args: dict[str, Any],
    justification: str,
    trace_id: str,
    expiry_seconds: int | None = None,
) -> ApprovalRequest:
    """Emit approval-needed-d. Returns the request object the agent re-presents
    to the dispatcher after a human runs `sovereign approve <event_id>`.
    """
    expiry_seconds = expiry_seconds or SETTINGS.approval_default_expiry_seconds
    expiry_ts = (
        datetime.fromtimestamp(time.time() + expiry_seconds, tz=timezone.utc)
        .strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    )
    args_hash = _hash_args(args)
    event_id = emit_event(
        "approval-needed-d",
        plane="control",
        trace_id=trace_id,
        payload={
            "tool_name": tool_name,
            "args_hash": args_hash,
            "args_preview": _canonical_json(args)[:500],
            "justification": justification,
            "expiry_ts": expiry_ts,
        },
    )
    return ApprovalRequest(
        event_id=event_id,
        tool_name=tool_name,
        args=args,
        args_hash=args_hash,
        justification=justification,
        expiry_ts=expiry_ts,
    )


def write_grant(req: ApprovalRequest) -> None:
    """Called by the CLI `sovereign approve` command.

    Writes the token file at ~/.config/sovereign-agent/approvals/<event_id>.tok.
    Atomic via temp-file-then-rename.
    """
    msg = _hmac_message(req.event_id, req.args_hash, req.expiry_ts)
    token = {
        "event_id": req.event_id,
        "args_hash": req.args_hash,
        "expiry_ts": req.expiry_ts,
        "hmac": _hmac(msg),
    }
    path = SETTINGS.paths.approvals_dir / f"{req.event_id}.tok"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(_canonical_json(token))
    tmp.chmod(0o600)
    tmp.replace(path)


def write_denial(event_id: str, *, trace_id: str, reason: str = "user denied") -> None:
    emit_event(
        "approval-denied-d",
        plane="control",
        trace_id=trace_id,
        payload={"event_id": event_id, "reason": reason},
    )


def consume_grant(
    *,
    event_id: str,
    tool_name: str,
    args: dict[str, Any],
    trace_id: str,
) -> None:
    """Called by the dispatcher right before Tier 3 tool dispatch.

    Validates: token file present, HMAC valid, args_hash matches, not expired.
    On success: unlinks the token (one-shot) and emits approval-d.
    On failure: emits approval-x and raises ApprovalDenied.
    """
    path = SETTINGS.paths.approvals_dir / f"{event_id}.tok"
    if not path.exists():
        emit_event(
            "approval-x",
            plane="control",
            trace_id=trace_id,
            payload={"event_id": event_id, "reason": "token_missing"},
        )
        raise ApprovalDenied("token file not found — approval not granted")

    try:
        token = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        emit_event(
            "approval-x",
            plane="control",
            trace_id=trace_id,
            payload={"event_id": event_id, "reason": f"token_unreadable: {e}"},
        )
        raise ApprovalDenied(f"token unreadable: {e}") from e

    # Args binding — model may have changed args between request and dispatch
    current_hash = _hash_args(args)
    if token.get("args_hash") != current_hash:
        path.unlink(missing_ok=True)
        emit_event(
            "approval-x",
            plane="control",
            trace_id=trace_id,
            payload={"event_id": event_id, "reason": "args_hash_mismatch"},
        )
        raise ApprovalDenied(
            "args differ between approval request and dispatch — token invalidated"
        )

    # Expiry
    expiry = datetime.strptime(
        token["expiry_ts"].replace("Z", "+0000"), "%Y-%m-%dT%H:%M:%S.%f%z"
    )
    if _utc_now() >= expiry:
        path.unlink(missing_ok=True)
        emit_event(
            "approval-x",
            plane="control",
            trace_id=trace_id,
            payload={"event_id": event_id, "reason": "expired"},
        )
        raise ApprovalDenied("approval token expired")

    # HMAC
    expected = _hmac(_hmac_message(event_id, current_hash, token["expiry_ts"]))
    if not hmac.compare_digest(expected, token.get("hmac", "")):
        path.unlink(missing_ok=True)
        emit_event(
            "approval-x",
            plane="control",
            trace_id=trace_id,
            payload={"event_id": event_id, "reason": "hmac_mismatch"},
        )
        raise ApprovalDenied("HMAC validation failed — token forged or corrupted")

    # All checks pass — consume the token.
    path.unlink(missing_ok=True)
    emit_event(
        "approval-d",
        plane="control",
        trace_id=trace_id,
        payload={"event_id": event_id, "tool_name": tool_name},
    )
