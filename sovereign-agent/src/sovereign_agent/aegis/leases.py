"""
╔══════════════════════════════════════════════════════════════════════════╗
║  aegis/leases.py — repair leases, HMAC-signed and time-bounded          ║
║                                                                           ║
║  The lease is what stops sentinels from fighting for the wheel. Only    ║
║  one lease per scope at a time. No sentinel may execute repair without ║
║  presenting a valid, signed, in-scope, unexpired lease — even if you    ║
║  call repair_execute() directly in a test, the Sentinel will refuse.   ║
║                                                                           ║
║  Why HMAC and not asymmetric signing:                                    ║
║                                                                           ║
║    The Conductor and the Sentinels live in the same process; a shared   ║
║    secret is fine. We're not defending against a remote forger — we're ║
║    defending against accidental misuse, test-mode bypass, and confused- ║
║    deputy attacks where a Sentinel believes it has authority it doesn't.║
║    HMAC-SHA256 is the right tool for that threat model.                 ║
║                                                                           ║
║    A future federation release (R5) will need asymmetric keys per node, ║
║    but that's not this release.                                          ║
║                                                                           ║
║  Why time-bounded:                                                       ║
║                                                                           ║
║    Eternal authority is a leak. If a Conductor crashes mid-incident     ║
║    and a lease lives forever, the Sentinel could hold the wheel after   ║
║    the orchestrator has gone home. Bounded leases mean a dead Conductor ║
║    can't strand authority — the lease just expires.                    ║
║                                                                           ║
║  Key storage:                                                            ║
║                                                                           ║
║    ~/.local/share/sovereign-agent/aegis/conductor.key                   ║
║    Mode 0600. Checked on every Conductor bootstrap. If permissions      ║
║    drift, Aegis refuses to start.                                        ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import stat
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .radius import BlastRadius
from .incidents import IncidentId, LeaseId


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


# ─── Exceptions ──────────────────────────────────────────────────────────


class LeaseRefused(Exception):
    """Raised when a Sentinel attempts to execute repair without a valid lease."""


class KeyPermissionError(Exception):
    """Raised when the conductor key has wrong permissions (mode != 0600)."""


# ─── RepairLease ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RepairLease:
    """A signed grant of authority to execute one specific RepairPlan.

    Frozen: cannot be modified post-issuance. Signed: cannot be forged
    without the conductor key. Scoped: covers exactly one (sentinel,
    plan_hash, scope) tuple. Bounded: expires_at is checked on every
    use; an expired lease is dead.
    """
    lease_id: LeaseId
    incident_id: IncidentId
    sentinel_id: str                           # who is authorized
    scope: BlastRadius                         # what authority extends to
    plan_hash: str                             # which RepairPlan this authorizes
    granted_at: str
    expires_at: str
    granted_by: str = "conductor"              # logical issuer; not free-form
    signature: str = ""                        # hex HMAC-SHA256

    def signable_payload(self) -> bytes:
        """Deterministic bytes signed by the conductor key.

        Note: 'signature' is excluded — we sign the rest, then add the
        signature field. Verification recomputes over the same fields.
        """
        d = asdict(self)
        d.pop("signature", None)
        return json.dumps(d, sort_keys=True).encode("utf-8")

    def is_expired(self, now: str | None = None) -> bool:
        """True if expires_at is in the past."""
        when = now or _iso_now()
        return when >= self.expires_at

    def covers(self, *, sentinel_id: str, plan_hash: str) -> bool:
        """True if this lease authorizes the given (sentinel, plan) pair."""
        return self.sentinel_id == sentinel_id and self.plan_hash == plan_hash


# ─── Key handling ────────────────────────────────────────────────────────


def conductor_key_path(data_dir: Path) -> Path:
    """Canonical location for the conductor's signing key."""
    p = data_dir / "aegis" / "conductor.key"
    return p


def load_or_create_conductor_key(data_dir: Path) -> bytes:
    """Load the signing key, creating it on first run.

    Enforces mode 0600 on the key file. If permissions are wrong (e.g.,
    a previous installer left it world-readable), refuses to proceed —
    the operator must fix the permissions, not us. Silent self-repair of
    permission failures is the kind of helpfulness that hides real
    problems.

    Returns the 32-byte secret. Never returns the path content directly
    to anything outside this module.
    """
    key_path = conductor_key_path(data_dir)
    if key_path.is_file():
        st = key_path.stat()
        mode = stat.S_IMODE(st.st_mode)
        if mode != 0o600:
            raise KeyPermissionError(
                f"conductor key {key_path} has mode {oct(mode)}; "
                f"expected 0o600. Fix with: chmod 600 {key_path}"
            )
        return key_path.read_bytes()

    # First run: create.
    key_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    key = secrets.token_bytes(32)
    # Write with restrictive umask so the file lands at 0600.
    old_umask = os.umask(0o077)
    try:
        key_path.write_bytes(key)
        os.chmod(key_path, 0o600)
    finally:
        os.umask(old_umask)
    return key


# ─── Sign / verify ───────────────────────────────────────────────────────


def sign_lease(
    *,
    lease_id: LeaseId,
    incident_id: IncidentId,
    sentinel_id: str,
    scope: BlastRadius,
    plan_hash: str,
    ttl_seconds: int,
    key: bytes,
    granted_at: str | None = None,
) -> RepairLease:
    """Construct and HMAC-sign a RepairLease.

    `granted_at` defaults to now; `expires_at` is granted_at + ttl_seconds.
    The signature covers every other field; modifying any one of them
    invalidates the signature.
    """
    granted = granted_at or _iso_now()
    # expires_at: compute as ISO of (granted + ttl).
    granted_dt = datetime.strptime(granted, "%Y-%m-%dT%H:%M:%S.%fZ").replace(
        tzinfo=timezone.utc
    )
    from datetime import timedelta
    expires_dt = granted_dt + timedelta(seconds=ttl_seconds)
    expires = expires_dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    unsigned = RepairLease(
        lease_id=lease_id,
        incident_id=incident_id,
        sentinel_id=sentinel_id,
        scope=scope,
        plan_hash=plan_hash,
        granted_at=granted,
        expires_at=expires,
        signature="",
    )
    sig = hmac.new(key, unsigned.signable_payload(), hashlib.sha256).hexdigest()
    # Reconstruct frozen dataclass with signature filled in.
    return RepairLease(
        lease_id=unsigned.lease_id,
        incident_id=unsigned.incident_id,
        sentinel_id=unsigned.sentinel_id,
        scope=unsigned.scope,
        plan_hash=unsigned.plan_hash,
        granted_at=unsigned.granted_at,
        expires_at=unsigned.expires_at,
        signature=sig,
    )


def verify_lease(lease: RepairLease, *, key: bytes) -> bool:
    """True if the lease's signature matches the key over its payload.

    Uses hmac.compare_digest for constant-time comparison. False if the
    signature is missing, malformed, or doesn't match.
    """
    if not lease.signature:
        return False
    expected = hmac.new(key, lease.signable_payload(), hashlib.sha256).hexdigest()
    try:
        return hmac.compare_digest(expected, lease.signature)
    except (TypeError, ValueError):
        return False


__all__ = [
    "RepairLease",
    "LeaseRefused",
    "KeyPermissionError",
    "conductor_key_path",
    "load_or_create_conductor_key",
    "sign_lease",
    "verify_lease",
]
