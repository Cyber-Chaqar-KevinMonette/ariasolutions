"""memory_compact/stores.py — the append-only store registry, audited honestly.

Every append-only store now grows forever. This registry names them all,
says which are COMPACTABLE (readers consume only recent records, so old
ones can move to cold storage without changing any read), and says WHY
the others are not (their readers reduce over full history — compacting
them would change meaning, which is forbidden here).

(FABLE II · M2 · memory-compact-d)
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class StoreSpec:
    store_id: str
    rel_path: str                       # ndjson/jsonl file under data_dir
    ts_fields: tuple[str, ...]          # first present field wins
    compactable: bool
    reason: str = ""                    # honest WHY when not compactable
    digest_extra: str = ""              # optional numeric field to average


REGISTRY: dict[str, StoreSpec] = {
    "chunks": StoreSpec(
        "chunks", "checkpoint_chunks/chunks.ndjson", ("sealed_at",),
        compactable=True, digest_extra=""),
    "qa": StoreSpec(
        "qa", "qa/qa.ndjson", ("asked_at",),
        compactable=True, digest_extra="confidence"),
    "field-notes": StoreSpec(
        "field-notes", "stewardship/field-notes.jsonl", ("ts",),
        compactable=True),
    "proving-results": StoreSpec(
        "proving-results", "proving_ground/results.ndjson", ("ts",),
        compactable=True, digest_extra="score"),
    "calibration": StoreSpec(
        "calibration", "calibration/ledger.ndjson", ("ts",),
        compactable=True),
    "interpretations": StoreSpec(
        "interpretations", "interpretations.ndjson", ("ts", "at"),
        compactable=True),
    # ── audit-only: readers reduce over FULL history — moving records
    #    would change what a read returns. Meaning first. ──
    "epistemic-beliefs": StoreSpec(
        "epistemic-beliefs", "epistemic/beliefs.ndjson", ("created_at",),
        compactable=False,
        reason="current_beliefs()/lineage() reduce over the whole log"),
    "uncertainties": StoreSpec(
        "uncertainties", "epistemic/uncertainties.ndjson", ("opened_at",),
        compactable=False,
        reason="_state() reduces the whole log (last record per id wins)"),
    "loose-threads": StoreSpec(
        "loose-threads", "loose_threads/ledger.ndjson", ("at",),
        compactable=False,
        reason="dispositions() reduces the whole log; also tiny by nature"),
    "honor": StoreSpec(
        "honor", "stewardship/honor.jsonl", ("ts", "at"),
        compactable=False,
        reason="honor entries are read as a whole ledger"),
    "behavior-patterns": StoreSpec(
        "behavior-patterns", "behavior-patterns.ndjson", ("ts", "at"),
        compactable=False,
        reason="pattern matching reads the whole catalog"),
}


@dataclass
class StoreAudit:
    store_id: str
    path: str
    exists: bool
    bytes: int = 0
    records: int = 0
    corrupt_lines: int = 0
    first_ts: str = ""
    last_ts: str = ""
    records_per_day: float = 0.0
    compactable: bool = False
    reason: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def _parse_ts(value: str) -> datetime | None:
    value = str(value or "").strip()
    if not value:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(value[:27], fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(value).astimezone(timezone.utc)
    except ValueError:
        return None


def record_ts(rec: dict, spec: StoreSpec) -> datetime | None:
    for f in spec.ts_fields:
        ts = _parse_ts(rec.get(f, ""))
        if ts is not None:
            return ts
    return None


def _data_dir(data_dir: Path | None) -> Path:
    if data_dir is None:
        from sovereign_agent.config import SETTINGS

        data_dir = SETTINGS.paths.data_dir
    return Path(data_dir)


def audit_store(spec: StoreSpec, data_dir: Path | None = None) -> StoreAudit:
    base = _data_dir(data_dir)
    path = base / spec.rel_path
    out = StoreAudit(store_id=spec.store_id, path=str(path),
                     exists=path.exists(), compactable=spec.compactable,
                     reason=spec.reason)
    if not out.exists:
        return out
    out.bytes = path.stat().st_size
    first: datetime | None = None
    last: datetime | None = None
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            rec = json.loads(raw)
            if not isinstance(rec, dict):
                raise ValueError
        except ValueError:
            out.corrupt_lines += 1
            continue
        out.records += 1
        ts = record_ts(rec, spec)
        if ts is not None:
            if first is None or ts < first:
                first = ts
            if last is None or ts > last:
                last = ts
    if first is not None and last is not None:
        out.first_ts = first.strftime("%Y-%m-%dT%H:%M:%SZ")
        out.last_ts = last.strftime("%Y-%m-%dT%H:%M:%SZ")
        span_days = max((last - first).total_seconds() / 86400.0, 1.0)
        out.records_per_day = round(out.records / span_days, 2)
    return out


@dataclass
class JournalAudit:
    """journal/ is one small file per day — bounded by design; audit-only."""

    path: str
    exists: bool
    files: int = 0
    bytes: int = 0

    def as_dict(self) -> dict:
        return asdict(self)


def audit_journal(data_dir: Path | None = None) -> JournalAudit:
    base = _data_dir(data_dir)
    j = base / "journal"
    out = JournalAudit(path=str(j), exists=j.is_dir())
    if not out.exists:
        return out
    for p in j.iterdir():
        if p.is_file():
            out.files += 1
            out.bytes += p.stat().st_size
    return out


def audit_all(data_dir: Path | None = None) -> dict:
    """Sizes + growth rates for every registered store, plus the journal."""
    stores = [audit_store(spec, data_dir) for spec in REGISTRY.values()]
    return {
        "audited_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "stores": [a.as_dict() for a in stores],
        "journal": audit_journal(data_dir).as_dict(),
        "total_bytes": sum(a.bytes for a in stores),
        "total_records": sum(a.records for a in stores),
    }
