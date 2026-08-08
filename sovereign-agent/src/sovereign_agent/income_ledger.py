"""income_ledger.py — a real "income earned" metric, VERIFIED-only.

Kevin, 2026-07-25: "make income earned a real metric too, but only updates
on verified income received." Same append-only NDJSON discipline as
aria_xp.py (one shared mental model for every live-ledger metric in this
cockpit) — but this ledger accepts an entry ONLY from a real, Stripe-
confirmed succeeded charge, never a subscription's "active" status alone
(a subscription can be active without a fresh charge just landed, and a
charge can fail/be disputed after "active" already looked true). Charge
ids are the natural de-duplication key — re-polling Stripe never double-
counts the same payment.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

__all__ = [
    "IncomeEvent",
    "record_income",
    "load_events",
    "total_income_cents",
    "recent_events",
    "is_recorded",
]


@dataclass
class IncomeEvent:
    charge_id: str
    amount_cents: int
    source: str = "stripe"
    note: str = ""
    ts: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


def _ledger_path(data_dir: Path | None = None) -> Path:
    if data_dir is None:
        from sovereign_agent.config import SETTINGS
        data_dir = SETTINGS.paths.data_dir
    return Path(data_dir) / "income_ledger.ndjson"


def load_events(data_dir: Path | None = None) -> list[IncomeEvent]:
    path = _ledger_path(data_dir)
    if not path.is_file():
        return []
    out: list[IncomeEvent] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                out.append(IncomeEvent(**d))
            except Exception:  # noqa: BLE001 — one bad line never breaks the read
                continue
    except Exception:  # noqa: BLE001
        return []
    return out


def is_recorded(charge_id: str, data_dir: Path | None = None) -> bool:
    """True if this exact Stripe charge has already been ledgered — the
    de-duplication check callers use BEFORE recording, so a re-poll of
    Stripe's charge list never double-counts the same payment."""
    charge_id = (charge_id or "").strip()
    if not charge_id:
        return False
    return any(e.charge_id == charge_id for e in load_events(data_dir))


def record_income(
    charge_id: str, amount_cents: int, *, source: str = "stripe",
    note: str = "", data_dir: Path | None = None,
) -> IncomeEvent | None:
    """Append ONE verified income event. Returns None (no-op) if this
    charge_id is already recorded — idempotent by design, so a caller can
    always re-poll Stripe's recent-charges list without fear of double-
    counting. `charge_id` must be non-empty: an unverifiable amount with
    no real charge behind it is never recorded, by construction."""
    charge_id = (charge_id or "").strip()
    if not charge_id:
        raise ValueError("charge_id is required — income must be a real, verified charge")
    if amount_cents <= 0:
        raise ValueError("amount_cents must be positive")
    if is_recorded(charge_id, data_dir):
        return None
    event = IncomeEvent(charge_id=charge_id, amount_cents=int(amount_cents),
                        source=source, note=note[:200], ts=time.time())
    path = _ledger_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event.to_dict()) + "\n")
    return event


def total_income_cents(data_dir: Path | None = None) -> int:
    return sum(e.amount_cents for e in load_events(data_dir))


def recent_events(n: int = 20, data_dir: Path | None = None) -> list[IncomeEvent]:
    return load_events(data_dir)[-n:][::-1]
