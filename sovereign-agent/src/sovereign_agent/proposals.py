"""
╔══════════════════════════════════════════════════════════════════════════╗
║  proposals.py — Durable proposal store for the self-reflection loop      ║
║  v0.2.9                                                                  ║
║                                                                          ║
║  A proposal is the system saying "I think this should change."           ║
║  An approval is the operator saying "yes, do it."                        ║
║  Without an approval, no change happens.                                 ║
║                                                                          ║
║  This is the safety boundary between scan/reflect (read-only,            ║
║  proposal-only) and apply (mutation, approval-required).                 ║
║                                                                          ║
║  Every approval is HMAC-signed with the same secret as Tier-3 approvals  ║
║  in §approval.py. An applied proposal whose signature doesn't verify is  ║
║  refused at apply-time — even if its status field reads 'approved'.      ║
║                                                                          ║
║  Storage layout:                                                         ║
║    <data_dir>/proposals/<proposal_id>.yaml                               ║
║                                                                          ║
║  The YAML is human-readable and editable. The HMAC binds the action      ║
║  payload, so editing the action invalidates the approval — exactly what  ║
║  we want for tamper-evidence.                                            ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import contextlib
import hashlib
import hmac
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Literal

import yaml
from ulid import ULID


ProposalStatus = Literal["pending", "approved", "rejected", "applied", "failed"]
ProposalKind = Literal["reorganize", "insight", "enhancement", "clean", "code_update"]


_VALID_STATUSES: frozenset[str] = frozenset(
    {"pending", "approved", "rejected", "applied", "failed"}
)
_VALID_KINDS: frozenset[str] = frozenset(
    {"reorganize", "insight", "enhancement", "clean", "code_update"}
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


# ─── Errors ─────────────────────────────────────────────────────────────────


class ProposalError(Exception):
    """Base for proposal store errors."""


class ProposalNotFound(ProposalError):
    pass


class ProposalCorrupt(ProposalError):
    """Malformed proposal YAML or schema violation."""


class ProposalSignatureInvalid(ProposalError):
    """An approval's HMAC didn't verify — proposal was tampered with."""


class ProposalNotApprovable(ProposalError):
    """Cannot transition to approved from the current state."""


# ─── Proposal dataclass ─────────────────────────────────────────────────────


@dataclass
class Proposal:
    """A structured suggestion for a system change.

    Fields:
        id            — stable identifier (ULID-prefixed)
        kind          — reorganize | insight | enhancement | clean
        title         — one-line summary, shown in lists
        rationale     — why this change is being proposed
        action        — structured payload describing the change
                        (kind-specific schema; see APPLY_DISPATCH below)
        source        — who/what produced the proposal (planner name, etc.)
        status        — pending | approved | rejected | applied | failed
        signature     — HMAC over (id, kind, action_canonical) when approved
        created_at    — when proposal was first written
        approved_at   — when operator approved
        applied_at    — when system executed the action
        approved_by   — operator identifier (currently "operator-cli")
        notes         — free-text annotations
        result        — execution outcome summary, populated on apply
        rollback      — inverse-action descriptor, populated on apply
    """

    id: str
    kind: ProposalKind
    title: str
    rationale: str = ""
    action: dict = field(default_factory=dict)
    source: str = ""
    status: ProposalStatus = "pending"
    signature: str | None = None
    created_at: str = field(default_factory=_utc_now)
    approved_at: str | None = None
    applied_at: str | None = None
    approved_by: str | None = None
    notes: str = ""
    result: str | None = None
    rollback: dict | None = None


# ─── Canonical-form serialization (what the HMAC signs) ────────────────────


def _canonical_action_bytes(proposal_id: str, kind: str, action: dict) -> bytes:
    """Stable, deterministic serialization of (id, kind, action) for HMAC.

    Uses sort_keys + separators to ensure identical-content actions produce
    identical bytes. This is what gets signed; if any field of the action
    changes after approval, the HMAC stops verifying.
    """
    payload = {"id": proposal_id, "kind": kind, "action": action}
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def compute_signature(proposal: Proposal, *, secret: bytes) -> str:
    """Compute the HMAC-SHA256 hex digest over the canonical form."""
    canon = _canonical_action_bytes(proposal.id, proposal.kind, proposal.action)
    return hmac.new(secret, canon, hashlib.sha256).hexdigest()


def verify_signature(proposal: Proposal, *, secret: bytes) -> bool:
    """Constant-time compare. False if signature is None, malformed, or wrong."""
    if not proposal.signature:
        return False
    expected = compute_signature(proposal, secret=secret)
    try:
        return hmac.compare_digest(expected, proposal.signature)
    except Exception:  # noqa: BLE001
        return False


# ─── Serialization ──────────────────────────────────────────────────────────


def _to_yaml_dict(p: Proposal) -> dict:
    return asdict(p)


def _from_yaml_dict(d: dict) -> Proposal:
    if not isinstance(d, dict):
        raise ProposalCorrupt("proposal root must be a mapping")
    try:
        pid = str(d["id"])
        kind = str(d["kind"])
        title = str(d["title"])
    except KeyError as e:
        raise ProposalCorrupt(f"missing required field: {e.args[0]}") from None

    if kind not in _VALID_KINDS:
        raise ProposalCorrupt(f"invalid kind: {kind!r}")
    status = str(d.get("status", "pending"))
    if status not in _VALID_STATUSES:
        raise ProposalCorrupt(f"invalid status: {status!r}")

    return Proposal(
        id=pid,
        kind=kind,  # type: ignore[arg-type]
        title=title,
        rationale=str(d.get("rationale") or ""),
        action=dict(d.get("action") or {}),
        source=str(d.get("source") or ""),
        status=status,  # type: ignore[arg-type]
        signature=d.get("signature"),
        created_at=str(d.get("created_at") or _utc_now()),
        approved_at=d.get("approved_at"),
        applied_at=d.get("applied_at"),
        approved_by=d.get("approved_by"),
        notes=str(d.get("notes") or ""),
        result=d.get("result"),
        rollback=d.get("rollback"),
    )


def _atomic_write_yaml(path: Path, data: dict) -> None:
    """Write YAML atomically: tmp + fsync + rename."""
    import os
    import tempfile
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_str = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp = Path(tmp_str)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(yaml.safe_dump(data, sort_keys=False))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        with contextlib.suppress(FileNotFoundError):
            tmp.unlink()
        raise


# ─── Store ──────────────────────────────────────────────────────────────────


class ProposalStore:
    """Filesystem-backed proposal registry under a root directory."""

    def __init__(self, root: Path):
        self.root = Path(root)

    def _path(self, proposal_id: str) -> Path:
        return self.root / f"{proposal_id}.yaml"

    def ensure_root(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    # ── Reads ────────────────────────────────────────────────────────────

    def get(self, proposal_id: str) -> Proposal:
        path = self._path(proposal_id)
        if not path.exists():
            raise ProposalNotFound(proposal_id)
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as e:
            raise ProposalCorrupt(f"YAML parse error in {path}: {e}") from e
        if data is None:
            raise ProposalCorrupt(f"empty proposal: {path}")
        return _from_yaml_dict(data)

    def list_ids(self) -> list[str]:
        if not self.root.exists():
            return []
        return sorted(p.stem for p in self.root.glob("*.yaml") if p.is_file())

    def list_all(self, *, status: str | None = None,
                 kind: str | None = None) -> list[Proposal]:
        out: list[Proposal] = []
        for pid in self.list_ids():
            try:
                p = self.get(pid)
            except ProposalError:
                continue
            if status is not None and p.status != status:
                continue
            if kind is not None and p.kind != kind:
                continue
            out.append(p)
        return out

    # ── Writes ───────────────────────────────────────────────────────────

    def create(
        self,
        *,
        kind: ProposalKind,
        title: str,
        action: dict,
        rationale: str = "",
        source: str = "",
        notes: str = "",
        proposal_id: str | None = None,
    ) -> Proposal:
        """Create a new proposal in 'pending' state. Returns the Proposal."""
        if kind not in _VALID_KINDS:
            raise ProposalError(f"invalid kind: {kind!r}")
        self.ensure_root()
        pid = proposal_id or f"prop-{ULID()}"
        path = self._path(pid)
        if path.exists():
            raise FileExistsError(f"proposal {pid} already exists at {path}")
        proposal = Proposal(
            id=pid, kind=kind, title=title,
            action=dict(action), rationale=rationale,
            source=source, notes=notes,
        )
        _atomic_write_yaml(path, _to_yaml_dict(proposal))
        return proposal

    def approve(
        self,
        proposal_id: str,
        *,
        secret: bytes,
        approved_by: str = "operator-cli",
    ) -> Proposal:
        """Sign and mark a proposal as approved. Returns the updated Proposal.

        Refuses if the proposal isn't currently 'pending'. Operators who
        want to re-approve a rejected proposal should reject-and-create-new
        instead — preserves the audit trail.
        """
        p = self.get(proposal_id)
        if p.status != "pending":
            raise ProposalNotApprovable(
                f"proposal {proposal_id} is in state {p.status!r}, not pending"
            )
        p.status = "approved"
        p.approved_at = _utc_now()
        p.approved_by = approved_by
        p.signature = compute_signature(p, secret=secret)
        _atomic_write_yaml(self._path(proposal_id), _to_yaml_dict(p))
        return p

    def reject(
        self, proposal_id: str, *, reason: str = "operator rejected",
    ) -> Proposal:
        """Mark a proposal as rejected. Cannot be undone."""
        p = self.get(proposal_id)
        if p.status not in ("pending", "approved"):
            raise ProposalNotApprovable(
                f"cannot reject from state {p.status!r}"
            )
        p.status = "rejected"
        p.notes = (p.notes + "\n" if p.notes else "") + f"REJECTED: {reason}"
        _atomic_write_yaml(self._path(proposal_id), _to_yaml_dict(p))
        return p

    def mark_applied(
        self, proposal_id: str, *, result: str, rollback: dict | None = None,
    ) -> Proposal:
        """Transition approved → applied. Records execution result + rollback."""
        p = self.get(proposal_id)
        if p.status != "approved":
            raise ProposalNotApprovable(
                f"can only apply from 'approved' state, got {p.status!r}"
            )
        p.status = "applied"
        p.applied_at = _utc_now()
        p.result = result
        p.rollback = rollback
        _atomic_write_yaml(self._path(proposal_id), _to_yaml_dict(p))
        return p

    def mark_failed(self, proposal_id: str, *, error: str) -> Proposal:
        """Transition approved → failed. Records the error for diagnosis."""
        p = self.get(proposal_id)
        if p.status != "approved":
            raise ProposalNotApprovable(
                f"can only fail from 'approved' state, got {p.status!r}"
            )
        p.status = "failed"
        p.applied_at = _utc_now()
        p.result = f"FAILED: {error}"
        _atomic_write_yaml(self._path(proposal_id), _to_yaml_dict(p))
        return p

    def delete(self, proposal_id: str) -> bool:
        """Hard delete. Use sparingly; reject preserves audit trail better."""
        path = self._path(proposal_id)
        if not path.exists():
            return False
        path.unlink()
        return True


# ─── Open helper ────────────────────────────────────────────────────────────


def open_store(root: Path | str | None = None) -> ProposalStore:
    """Open the proposal store at the configured location."""
    if root is None:
        from .config import SETTINGS
        root = SETTINGS.paths.proposals_dir
    return ProposalStore(Path(root))
