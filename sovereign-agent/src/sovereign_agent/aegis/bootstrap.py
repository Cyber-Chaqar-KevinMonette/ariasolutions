"""aegis/bootstrap.py — initialize the aegis subsystem's persistent surface.

THE GAP: the LocatorSentinel seeds an `aegis_dir` entry with
criticality="alert" (locator_sentinel.py), but nothing in the codebase ever
bootstrapped `data_dir/aegis/` — the Conductor/AegisLedger/key machinery
all exist in code yet only create their dir when first constructed, and
nothing constructs them on a fresh install. Result: a permanent error-level
sentinel finding on every healthy system.

THE FIX, honestly: create the dir because the subsystem is genuinely
initialized (ledger dir 0o700 + conductor signing key 0600), not because a
sentinel needed hushing. Idempotent — safe to call from doctor runs.
"""
from __future__ import annotations

from pathlib import Path


def ensure_aegis_bootstrap(data_dir: Path) -> dict:
    """Initialize aegis' persistent surface. Idempotent.

    Creates (if missing): `data_dir/aegis/` (0o700, via AegisLedger's own
    constructor) and the conductor signing key (0600, via
    load_or_create_conductor_key — which also REFUSES to proceed on wrong
    existing permissions rather than silently self-repairing).
    """
    data_dir = Path(data_dir)
    from .ledger import AegisLedger
    from .leases import conductor_key_path, load_or_create_conductor_key

    ledger = AegisLedger(data_dir)  # mkdirs data_dir/aegis mode=0o700
    key_existed = conductor_key_path(data_dir).exists()
    load_or_create_conductor_key(data_dir)
    return {
        "aegis_dir": str(data_dir / "aegis"),
        "ledger_path": str(ledger.path),
        "key_created": not key_existed,
    }
