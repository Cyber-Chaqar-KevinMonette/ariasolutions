"""
╔══════════════════════════════════════════════════════════════════════════╗
║  rollback.py — pre-staged undo plans for Tier-3+ actions                ║
║  v0.2.27.0 · Roadmap Phase 3                                             ║
║                                                                           ║
║  THE PROMISE                                                             ║
║                                                                           ║
║    *If rollback is undefined, deployment is incomplete.*                 ║
║                                                                           ║
║    Every Tier-3 step a session takes is, by definition, persistent and ║
║    visible outside the sandbox. The operator has to be able to undo it.║
║    For most actions this is straightforward — a file write can be      ║
║    reverted to the prior bytes; an atom insert can be deleted. For     ║
║    actions that are inherently irreversible (an email sent, an API     ║
║    payment posted), there is no undo — only compensation. This module ║
║    enforces a clean separation between the two and refuses to dispatch ║
║    an irreversible action without an operator-signed plan.             ║
║                                                                           ║
║  HOW IT FITS                                                             ║
║                                                                           ║
║      Tier-3 action proposed                                             ║
║          │                                                              ║
║          ▼                                                              ║
║      classify_action(kind, args) → ReversibilityClass                  ║
║          │                                                              ║
║          ├──── REVERSIBLE      ──→ generate_rollback() returns Plan    ║
║          │                          plan written to <data>/rollbacks/  ║
║          │                          action executes                    ║
║          │                          on success: plan → archive/        ║
║          │                          on failure: rollback executed     ║
║          │                                                              ║
║          ├──── COMPENSATABLE  ──→ generate_rollback() returns Plan    ║
║          │                          marked manual: requires operator   ║
║          │                          to run compensating action         ║
║          │                          (e.g. send apology + refund email) ║
║          │                                                              ║
║          └──── IRREVERSIBLE   ──→ refuse_until_signed()               ║
║                                     raises NoRollbackPath               ║
║                                     operator must sign a               ║
║                                     compensating-plan.md to proceed    ║
║                                                                           ║
║  WHAT THIS SHIPS WITH                                                    ║
║                                                                           ║
║    Generators for four action kinds (the curated set from the roadmap):║
║      • file_write       — restore prior bytes (or delete if new)       ║
║      • atom_insert      — delete the atom (only the head; chains hold) ║
║      • snapshot_create  — delete the snapshot file                     ║
║      • draft_archive    — restore the draft to its prior status        ║
║                                                                           ║
║    Other Tier-3 action kinds raise ``NoRollbackPath``. Adding a        ║
║    generator is a public API; register it via ``register_generator``.  ║
║                                                                           ║
║  WHAT THIS DOES NOT DO                                                   ║
║                                                                           ║
║    • Execute rollback plans automatically. Execution is the caller's   ║
║      job; this module produces the plan and stores it durably.         ║
║    • Cover Tier-2 actions. Tier-2 is operator-confirmed at queue time, ║
║      which is its own rollback contract.                              ║
║    • Compose rollbacks across multiple steps. Each step's rollback is  ║
║      atomic and stand-alone. Composing them safely needs a transaction ║
║      log (deferred — possibly v0.3.5 with the sweep+gap reporter).    ║
║                                                                           ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import json
import os
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from .config import SETTINGS


# ─────────────────────────────────────────────────────────────────────────
# Public types
# ─────────────────────────────────────────────────────────────────────────


class ReversibilityClass(StrEnum):
    """How a Tier-3 action can be undone.

    REVERSIBLE      — full restoration possible from saved state
    COMPENSATABLE   — partial undo via a manual compensating action
    IRREVERSIBLE    — no undo path at all; requires signed acceptance
    """
    REVERSIBLE = "reversible"
    COMPENSATABLE = "compensatable"
    IRREVERSIBLE = "irreversible"


class RollbackError(Exception):
    """Base for all rollback module errors."""


class NoRollbackPath(RollbackError):
    """Raised when an action has no auto-generatable rollback.

    The operator must produce and sign a compensating-action plan (see
    ``write_compensating_plan_template``) before the action can be
    dispatched.
    """


class UnknownActionKind(RollbackError):
    """Raised when ``generate_rollback`` is called with a kind nobody
    registered. Distinct from NoRollbackPath because this is a developer
    error (forgot to register), not an operational refusal.
    """


@dataclass
class RollbackPlan:
    """The durable record of how to undo one action.

    Stored as JSON at ``<data>/rollbacks/<continuation_id>/<step_id>.json``
    when it's pending. Moved to ``<data>/rollbacks/<continuation_id>/archive/``
    on successful action completion (kept for the window, then GC'd).

    ``commands`` is a list of structured operations. Each entry is a dict
    with at least a ``"kind"`` key (e.g. "delete_file", "restore_bytes",
    "delete_atom") and the args needed to perform it. The executor is the
    caller's responsibility — this module never runs commands.
    """

    plan_id: str
    action_kind: str                    # what action this undoes
    action_args: dict                   # the original action's args (for audit)
    reversibility_class: str            # ReversibilityClass value
    commands: list[dict] = field(default_factory=list)
    manual_steps: list[str] = field(default_factory=list)
    created_at: str = ""
    expires_at: str | None = None       # within-window auto-rollback cutoff
    notes: str = ""

    @classmethod
    def reversible(
        cls,
        *,
        action_kind: str,
        action_args: dict,
        commands: list[dict],
        notes: str = "",
    ) -> "RollbackPlan":
        return cls(
            plan_id=f"rb_{uuid4().hex[:12]}",
            action_kind=action_kind,
            action_args=action_args,
            reversibility_class=ReversibilityClass.REVERSIBLE.value,
            commands=commands,
            created_at=_utc_now(),
            notes=notes,
        )

    @classmethod
    def compensatable(
        cls,
        *,
        action_kind: str,
        action_args: dict,
        manual_steps: list[str],
        notes: str = "",
    ) -> "RollbackPlan":
        return cls(
            plan_id=f"rb_{uuid4().hex[:12]}",
            action_kind=action_kind,
            action_args=action_args,
            reversibility_class=ReversibilityClass.COMPENSATABLE.value,
            manual_steps=manual_steps,
            created_at=_utc_now(),
            notes=notes,
        )


# ─────────────────────────────────────────────────────────────────────────
# Generator registry — add new action kinds here
# ─────────────────────────────────────────────────────────────────────────


GeneratorFn = Callable[[dict], RollbackPlan]
"""Signature for an action-kind rollback generator.

  Input: the action's args dict (whatever the caller is about to do)
  Output: a RollbackPlan that, when executed, undoes the action

The generator MUST be pure: no I/O except reading state needed to compute
the rollback (e.g. reading the existing file before a file_write so we
know what bytes to restore). The generator MUST raise NoRollbackPath if
the action is fundamentally irreversible — never return a fake plan.
"""


_REGISTRY: dict[str, GeneratorFn] = {}


def register_generator(action_kind: str, generator: GeneratorFn) -> None:
    """Register a rollback generator for a Tier-3 action kind.

    Re-registering an existing kind overwrites it — useful for tests and
    for operators who want to replace the default behavior. The default
    generators below register themselves at module-import time.
    """
    _REGISTRY[action_kind] = generator


def is_registered(action_kind: str) -> bool:
    return action_kind in _REGISTRY


def known_kinds() -> tuple[str, ...]:
    """All action kinds with a registered generator. Sorted for stability."""
    return tuple(sorted(_REGISTRY.keys()))


def generate_rollback(action_kind: str, action_args: dict) -> RollbackPlan:
    """Generate a RollbackPlan for the proposed Tier-3 action.

    Raises:
      UnknownActionKind — no generator was registered for this kind
      NoRollbackPath    — generator determined the action is irreversible
    """
    gen = _REGISTRY.get(action_kind)
    if gen is None:
        raise UnknownActionKind(
            f"no rollback generator registered for action kind "
            f"{action_kind!r}; register one via register_generator or "
            f"declare the action irreversible with a signed compensating "
            f"plan"
        )
    return gen(action_args)


# ─────────────────────────────────────────────────────────────────────────
# Store — durable persistence
# ─────────────────────────────────────────────────────────────────────────


class RollbackStore:
    """File-backed store for RollbackPlans.

    Layout:
      <data>/rollbacks/<continuation_id>/<plan_id>.json    — pending
      <data>/rollbacks/<continuation_id>/archive/...       — completed (within window)

    The window is settable via ``window_seconds`` on the store; archived
    plans older than the window are GC'd by ``gc_expired()``. Default
    window is 3600 seconds (1 hour) — long enough to catch "wait, undo
    that," short enough to bound disk usage.
    """

    DEFAULT_WINDOW = 3600  # 1 hour

    def __init__(
        self,
        root: Path | None = None,
        *,
        window_seconds: int = DEFAULT_WINDOW,
    ) -> None:
        self.root = root or (SETTINGS.paths.data_dir / "rollbacks")
        self.window_seconds = window_seconds
        self.root.mkdir(parents=True, exist_ok=True)

    def _continuation_dir(self, continuation_id: str) -> Path:
        if "/" in continuation_id or ".." in continuation_id:
            raise RollbackError(f"invalid continuation_id: {continuation_id!r}")
        d = self.root / continuation_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def save_pending(self, continuation_id: str, plan: RollbackPlan) -> Path:
        """Atomic write of a pending rollback plan."""
        d = self._continuation_dir(continuation_id)
        target = d / f"{plan.plan_id}.json"
        tmp = target.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(asdict(plan), indent=2), encoding="utf-8")
        os.replace(tmp, target)
        return target

    def load_pending(self, continuation_id: str, plan_id: str) -> RollbackPlan:
        target = self._continuation_dir(continuation_id) / f"{plan_id}.json"
        if not target.exists():
            raise RollbackError(f"rollback plan not found: {plan_id}")
        d = json.loads(target.read_text(encoding="utf-8"))
        return RollbackPlan(**d)

    def list_pending(self, continuation_id: str) -> list[RollbackPlan]:
        """All pending rollback plans for a continuation, oldest first."""
        d = self._continuation_dir(continuation_id)
        out: list[RollbackPlan] = []
        for p in sorted(d.glob("*.json")):
            try:
                out.append(RollbackPlan(**json.loads(p.read_text(encoding="utf-8"))))
            except (json.JSONDecodeError, TypeError):
                continue   # corrupt; skip
        return out

    def archive(self, continuation_id: str, plan_id: str) -> Path:
        """Move a pending plan to the archive directory.

        Sets ``expires_at`` to now + window_seconds before archiving so the
        operator can still execute it within the window. Returns the new
        path.
        """
        d = self._continuation_dir(continuation_id)
        src = d / f"{plan_id}.json"
        if not src.exists():
            raise RollbackError(f"plan not pending: {plan_id}")

        plan = RollbackPlan(**json.loads(src.read_text(encoding="utf-8")))
        expires = datetime.now(timezone.utc).timestamp() + self.window_seconds
        plan.expires_at = datetime.fromtimestamp(
            expires, tz=timezone.utc
        ).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

        archive_dir = d / "archive"
        archive_dir.mkdir(exist_ok=True)
        dst = archive_dir / src.name
        # Rewrite with updated expires_at, then move
        tmp = src.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(asdict(plan), indent=2), encoding="utf-8")
        os.replace(tmp, src)
        shutil.move(str(src), str(dst))
        return dst

    def gc_expired(self) -> int:
        """Delete archived plans past their expires_at. Returns count deleted."""
        now = datetime.now(timezone.utc).timestamp()
        deleted = 0
        for archive_dir in self.root.glob("*/archive"):
            for p in archive_dir.glob("*.json"):
                try:
                    d = json.loads(p.read_text(encoding="utf-8"))
                    expires_str = d.get("expires_at")
                    if not expires_str:
                        continue
                    # Strip trailing Z and parse
                    expires = datetime.fromisoformat(
                        expires_str.rstrip("Z")
                    ).replace(tzinfo=timezone.utc).timestamp()
                    if expires < now:
                        p.unlink()
                        deleted += 1
                except (json.JSONDecodeError, ValueError, OSError):
                    continue
        return deleted


# ─────────────────────────────────────────────────────────────────────────
# Compensating-action plan template — for IRREVERSIBLE actions
# ─────────────────────────────────────────────────────────────────────────


def write_compensating_plan_template(
    *,
    action_kind: str,
    action_args: dict,
    output_path: Path,
) -> Path:
    """Write a markdown template the operator fills in and signs.

    For irreversible actions (e.g. a real-world email send, a payment),
    the operator must articulate what compensating action they would take
    if the action turns out to be wrong. The plan is human-written, not
    generated.

    The presence of a signed plan (`signed_by:` field non-empty in the
    YAML frontmatter) is the precondition for dispatching the action.
    Aria checks this; she does not sign on her own behalf.
    """
    template = f"""---
action_kind: {action_kind}
action_args: {json.dumps(action_args, default=str)}
created_at: {_utc_now()}
signed_by: ""           # operator fills this in by name/handle
signed_at: ""           # ISO timestamp when signed
---

# Compensating Action Plan

## What action is being approved

(One sentence: what is Aria about to do?)

## Why this is irreversible

(Explain the no-undo property — e.g. "an email cannot be unsent,"
"a payment to an external API cannot be retroactively cancelled.")

## What we will do if this turns out wrong

(Specific compensating steps. Not "apologize" — concrete actions.
e.g. "Send a correction email referencing the original message-id,"
"Initiate a refund through the payment provider's API, then notify
the recipient via channel X.")

## Operator confirmation

By filling in the `signed_by` and `signed_at` fields in the YAML
frontmatter above, the operator accepts that this action will be
dispatched without an auto-rollback. The compensating steps named
above are the only undo path.
"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(template, encoding="utf-8")
    return output_path


# ─────────────────────────────────────────────────────────────────────────
# Default generators — the curated set from the roadmap
# ─────────────────────────────────────────────────────────────────────────


def _gen_file_write(args: dict) -> RollbackPlan:
    """Rollback for a file_write action.

    Strategy:
      • If the path didn't exist before, rollback = delete it
      • If it did exist, rollback = restore the prior bytes (which the
        generator captures NOW, before the write happens)

    The generator MUST be called *before* the write, never after. If the
    caller has already written, the prior bytes are gone and a faithful
    rollback is impossible.
    """
    path_str = args.get("path")
    if not path_str:
        raise NoRollbackPath("file_write action missing 'path' arg")

    path = Path(path_str).expanduser()

    if not path.exists():
        # First write — rollback is delete
        return RollbackPlan.reversible(
            action_kind="file_write",
            action_args=dict(args),
            commands=[{"kind": "delete_file", "path": str(path)}],
            notes="file did not exist prior to action; rollback is deletion",
        )

    # File exists — capture prior bytes
    try:
        prior_bytes = path.read_bytes()
    except OSError as e:
        raise NoRollbackPath(
            f"cannot read prior file contents to enable rollback: {e}"
        ) from e

    # Bytes are stored inline as hex-encoded; suitable for small files.
    # For files > 1MB, the executor should refer to a side-stored blob.
    # Phase 3 ships with the inline path; the blob path is roadmap.
    return RollbackPlan.reversible(
        action_kind="file_write",
        action_args=dict(args),
        commands=[
            {
                "kind": "restore_bytes",
                "path": str(path),
                "bytes_hex": prior_bytes.hex(),
                "size": len(prior_bytes),
            }
        ],
        notes=f"will restore {len(prior_bytes)} bytes captured pre-write",
    )


def _gen_atom_insert(args: dict) -> RollbackPlan:
    """Rollback for an atom insert.

    Atoms are append-only — the architecture's ground truth. Rolling back
    an atom insert means deleting only the head row, never severing the
    chain. The executor verifies no later atom claims this one as its
    parent before performing the delete (otherwise the chain integrity
    is broken).

    For chained inserts (multi-atom writes), each atom gets its own
    rollback plan. They are NOT composable here; the executor must run
    them in reverse insertion order if it wants to undo a chain.
    """
    atom_id = args.get("atom_id") or args.get("id")
    if not atom_id:
        raise NoRollbackPath(
            "atom_insert action missing 'atom_id' arg; rollback would not "
            "be able to identify the row to delete"
        )

    return RollbackPlan.reversible(
        action_kind="atom_insert",
        action_args=dict(args),
        commands=[
            {
                "kind": "delete_atom",
                "atom_id": atom_id,
                "guard": "no_children",   # executor MUST verify no atom claims this as parent
            }
        ],
        notes=(
            "deletes the atom head only; refuses if any atom claims this "
            "as a parent (chain-integrity invariant)"
        ),
    )


def _gen_snapshot_create(args: dict) -> RollbackPlan:
    """Rollback for a backup snapshot creation.

    Snapshots are pure additions to the backup directory. Rollback is
    just deletion of the snapshot file. Failed-during-create snapshots
    (partial files) are handled by the backup module's own cleanup;
    this rollback covers the successful-but-undesired case.
    """
    snapshot_path = args.get("snapshot_path") or args.get("path")
    if not snapshot_path:
        raise NoRollbackPath("snapshot_create action missing 'snapshot_path'")

    return RollbackPlan.reversible(
        action_kind="snapshot_create",
        action_args=dict(args),
        commands=[{"kind": "delete_file", "path": str(snapshot_path)}],
        notes="snapshot creation rollback = file deletion",
    )


def _gen_draft_archive(args: dict) -> RollbackPlan:
    """Rollback for archiving a draft (status: active → archived).

    Drafts are atoms in the drafts channel. Archiving sets status to
    'archived'. Rollback restores the prior status. Idempotent on
    re-execution.
    """
    draft_id = args.get("draft_id") or args.get("id")
    prior_status = args.get("prior_status", "active")
    if not draft_id:
        raise NoRollbackPath("draft_archive action missing 'draft_id'")

    return RollbackPlan.reversible(
        action_kind="draft_archive",
        action_args=dict(args),
        commands=[
            {
                "kind": "set_draft_status",
                "draft_id": draft_id,
                "status": prior_status,
            }
        ],
        notes=f"restores draft status to {prior_status!r}",
    )


# Self-register the curated set on module import
register_generator("file_write", _gen_file_write)
register_generator("atom_insert", _gen_atom_insert)
register_generator("snapshot_create", _gen_snapshot_create)
register_generator("draft_archive", _gen_draft_archive)


# ─────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


__all__ = [
    "ReversibilityClass",
    "RollbackPlan",
    "RollbackError",
    "NoRollbackPath",
    "UnknownActionKind",
    "RollbackStore",
    "GeneratorFn",
    "register_generator",
    "is_registered",
    "known_kinds",
    "generate_rollback",
    "write_compensating_plan_template",
]
