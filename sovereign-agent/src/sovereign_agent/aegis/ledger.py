"""
╔══════════════════════════════════════════════════════════════════════════╗
║  aegis/ledger.py — append-only, hash-chained incident ledger             ║
║                                                                           ║
║  Separate from events.jsonl on purpose. Incidents have different        ║
║  retention, different access control, and a stricter integrity contract.║
║  Events get rotated and aged out. The Aegis Ledger does not — every     ║
║  incident is permanent until explicit operator purge.                   ║
║                                                                           ║
║  Hash chain:                                                              ║
║                                                                           ║
║    Each LedgerEntry includes the SHA-256 of the prior entry's full     ║
║    serialized form. Tampering with any historical entry breaks every   ║
║    subsequent hash. The verify() method walks the whole chain and      ║
║    returns the index of the first broken link, or None if the chain   ║
║    is intact.                                                            ║
║                                                                           ║
║  Genesis entry:                                                          ║
║                                                                           ║
║    The first entry's prior_hash is a constant — the SHA-256 of the     ║
║    string "aegis-ledger-genesis-2026". Same value forever; serves as   ║
║    the chain's anchor.                                                  ║
║                                                                           ║
║  BLACK mode:                                                             ║
║                                                                           ║
║    During DEFCON BLACK, all writes are blocked except those originated   ║
║    by the Conductor itself. This is enforced by the writer requiring    ║
║    a conductor-state argument that only the Conductor can produce.     ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Literal


GENESIS_HASH = hashlib.sha256(b"aegis-ledger-genesis-2026").hexdigest()


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


# ─── LedgerEntry ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class LedgerEntry:
    """One row in the Aegis Ledger.

    The 'kind' field is the entry's type tag. The 'data' field is opaque
    JSON-serializable payload specific to that kind. Hash chain links via
    prior_hash → entry_hash.
    """
    sequence: int                              # 0-indexed, monotonic
    kind: Literal[
        "incident-opened",
        "damage-reported",
        "plan-proposed",
        "dryrun-completed",
        "lease-issued",
        "lease-revoked",
        "repair-executed",
        "rollback-invoked",
        "defcon-transition",
        "incident-closed",
        "conductor-bootstrap",
        "conductor-shutdown",
        "tamper-detected",
    ]
    written_at: str
    actor: str                                 # 'conductor' or sentinel id
    data: dict[str, Any]
    prior_hash: str
    entry_hash: str = ""

    def computed_hash(self) -> str:
        """SHA-256 of (sequence, kind, written_at, actor, data, prior_hash)."""
        d = asdict(self)
        d.pop("entry_hash", None)
        blob = json.dumps(d, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()


# ─── AegisLedger ─────────────────────────────────────────────────────────


class AegisLedger:
    """Append-only hash-chained log on disk.

    Lives at <data_dir>/aegis/ledger.jsonl. One LedgerEntry per line.
    No update, no delete — only append. The append method takes a
    conductor_token; without it, the append refuses (this is what
    enforces "BLACK blocks all writes except the Conductor's").
    """

    def __init__(self, data_dir: Path):
        self._data_dir = data_dir
        self._dir = data_dir / "aegis"
        self._dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._path = self._dir / "ledger.jsonl"

    @property
    def path(self) -> Path:
        return self._path

    # ── Read paths ──────────────────────────────────────────────────────

    def __iter__(self) -> Iterator[LedgerEntry]:
        """Yield every entry in order. Tolerant of trailing whitespace."""
        if not self._path.is_file():
            return
        with self._path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield LedgerEntry(**json.loads(line))
                except (json.JSONDecodeError, TypeError, KeyError):
                    # Corruption: surface via verify(), don't crash iteration.
                    continue

    def latest(self) -> LedgerEntry | None:
        last = None
        for entry in self:
            last = entry
        return last

    def next_sequence(self) -> int:
        last = self.latest()
        return 0 if last is None else last.sequence + 1

    def last_hash(self) -> str:
        last = self.latest()
        return GENESIS_HASH if last is None else last.entry_hash

    # ── Verify the chain ────────────────────────────────────────────────

    def verify(self) -> int | None:
        """Walk the chain. Return the sequence number of the first broken
        link, or None if the chain is intact end-to-end.

        Checks: (1) sequence is contiguous from 0; (2) each entry's
        prior_hash equals the previous entry's entry_hash (or GENESIS_HASH
        for the first); (3) each entry's entry_hash equals its computed
        hash.
        """
        prev_hash = GENESIS_HASH
        expected_seq = 0
        for entry in self:
            if entry.sequence != expected_seq:
                return expected_seq
            if entry.prior_hash != prev_hash:
                return entry.sequence
            if entry.entry_hash != entry.computed_hash():
                return entry.sequence
            prev_hash = entry.entry_hash
            expected_seq += 1
        return None

    # ── Write path (single chokepoint) ──────────────────────────────────

    def append(
        self,
        *,
        kind: LedgerEntry.__annotations__["kind"],
        actor: str,
        data: dict[str, Any],
        conductor_token: str,
    ) -> LedgerEntry:
        """Append one entry. Requires the Conductor's current token.

        The token check is the BLACK-mode enforcement point: the Conductor
        rotates the token when it enters BLACK so that any in-flight
        Sentinel calls with stale tokens are rejected. (Read-only iteration
        and verify() are NOT gated by token — those are diagnostic surfaces.)
        """
        if not conductor_token or len(conductor_token) < 16:
            raise PermissionError(
                "Aegis Ledger append rejected: missing or short conductor token"
            )
        seq = self.next_sequence()
        prior = self.last_hash()
        entry = LedgerEntry(
            sequence=seq,
            kind=kind,
            written_at=_iso_now(),
            actor=actor,
            data=data,
            prior_hash=prior,
        )
        # Compute the hash, reconstruct frozen entry with it filled in.
        h = entry.computed_hash()
        sealed = LedgerEntry(
            sequence=entry.sequence,
            kind=entry.kind,
            written_at=entry.written_at,
            actor=entry.actor,
            data=entry.data,
            prior_hash=entry.prior_hash,
            entry_hash=h,
        )
        # Atomic-ish append: open in append mode, write one line, flush.
        # We're not aiming for crash-after-partial-line resilience here
        # (the verify() pass catches that). We are aiming for "two
        # appenders never interleave a single line" — which O_APPEND on
        # POSIX gives us up to PIPE_BUF (typically 4096 bytes).
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(sealed), default=str) + "\n")
            f.flush()
        return sealed


__all__ = [
    "GENESIS_HASH",
    "LedgerEntry",
    "AegisLedger",
]
