"""read_repair.py — ONE tolerant ndjson reader for every store. (FABLE II · M3)

The gym round fixed events ingestion with the readline/skip/count
discipline; this module makes that discipline SHARED instead of
hand-rolled eight different ways. Corruption honesty at every read path:

  · a corrupt line is SKIPPED and COUNTED — never a wedge, never a crash,
    never a silent disappearance;
  · a non-dict JSON line (a bare number, a string) counts as corrupt for
    dict stores — the caller receives dicts only;
  · when skips happen, ONE `corrupt-lines-d` event per read names the
    store, the file, and the counts — the operator can see decay the day
    it starts instead of the day it wedges something;
  · a missing file is honest absence: empty result, zero skipped.

Property-tested (Hypothesis): for any interleaving of valid records and
garbage, records come back in order, counts add up, nothing raises.

(read-repair-d)
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

MARK = "read-repair-d"


@dataclass
class NdjsonRead:
    """One tolerant read: what survived, and what didn't — counted."""

    records: list[dict] = field(default_factory=list)
    total_lines: int = 0        # non-blank lines seen
    skipped: int = 0            # corrupt / non-dict lines
    path: str = ""
    store: str = ""

    @property
    def ok(self) -> bool:
        return self.skipped == 0


def read_ndjson_tolerant(path: Path | str, *, store: str = "",
                         emit: bool = True) -> NdjsonRead:
    """Read an NDJSON/JSONL store with counted skips. NEVER raises.

    ``store`` names the store in the corrupt-lines event. ``emit=False``
    suppresses the event (for hot loops that read the same file
    repeatedly and for the property tests).
    """
    result = NdjsonRead(path=str(path), store=store)
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return result
    except OSError:
        return result
    for raw in text.splitlines():
        raw = raw.strip()
        if not raw:
            continue
        result.total_lines += 1
        try:
            rec = json.loads(raw)
        except ValueError:
            result.skipped += 1
            continue
        if not isinstance(rec, dict):
            result.skipped += 1
            continue
        result.records.append(rec)
    if result.skipped and emit:
        _emit_corrupt(result)
    return result


def _emit_corrupt(result: NdjsonRead) -> None:
    """Best-effort corruption honesty — the event must never break the read."""
    try:
        from sovereign_agent.events import emit_event

        emit_event(
            "corrupt-lines-d",
            plane="control",
            trace_id=f"read-repair-{result.store or 'store'}",
            payload={
                "store": result.store,
                "file": Path(result.path).name,
                "skipped": result.skipped,
                "total_lines": result.total_lines,
            },
        )
    except Exception:  # noqa: BLE001
        pass


__all__ = ["MARK", "NdjsonRead", "read_ndjson_tolerant"]
