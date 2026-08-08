"""loose_threads/ledger.py — the disposition ledger.

Every loose thread gets a DURABLE disposition — WIRED / RETIRED /
ACCEPTED: <reason> — the diagnosis.py discipline applied to her own
anatomy. A dispositioned thread stops warning. No nagging; no
suppression without a written reason. Append-only NDJSON, atomic.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

VALID = frozenset({"WIRED", "RETIRED", "ACCEPTED"})


class DispositionLedger:
    def __init__(self, root: Path | None = None) -> None:
        if root is None:
            from sovereign_agent.config import SETTINGS

            root = SETTINGS.paths.data_dir / "loose_threads"
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "ledger.ndjson"

    def disposition(self, symbol: str, verdict: str, reason: str = "") -> dict:
        verdict = verdict.upper()
        if verdict not in VALID:
            raise ValueError(f"verdict must be one of {sorted(VALID)}")
        if verdict == "ACCEPTED" and not reason.strip():
            raise ValueError("ACCEPTED requires a written reason — no silent suppression")
        rec = {"symbol": symbol, "verdict": verdict, "reason": reason.strip(),
               "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")}
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, separators=(",", ":")) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        return rec

    def dispositions(self) -> dict[str, dict]:
        """Latest disposition per symbol."""
        out: dict[str, dict] = {}
        # read-repair-d — counted skips, never a wedge, never a crash
        from sovereign_agent.read_repair import read_ndjson_tolerant

        for rec in read_ndjson_tolerant(self.path, store="loose-threads").records:
            if rec.get("symbol"):
                out[rec["symbol"]] = rec
        return out

    def undispositioned(self, threads) -> list:
        seen = self.dispositions()
        return [t for t in threads if t.symbol not in seen]
