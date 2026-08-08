"""memory_compact/compact.py — bounded growth with dignity. (FABLE II · M2)

Compaction here NEVER loses meaning — it is COLD STORAGE with a pointer,
not summarize-and-discard:

  · records older than the cutoff move, RAW LINE VERBATIM, from the hot
    file to `<store>.cold-YYYY-MM.ndjson` beside it (append + fsync);
  · the hot file is rewritten atomically with only the remaining raw
    lines (a timestamped .bak of the original is kept beside it);
  · `compact_index.json` (the pointer) records each period's cold file,
    count, and a small mechanical digest — the summarized-with-pointer
    promise: the summary is in the index, the verbatim is on disk, cold;
  · lines whose timestamp cannot be parsed are NEVER moved (they stay
    hot — we do not relocate what we cannot date);
  · a post-write count verification restores the .bak on any mismatch.

Propose-first: the MemoryCompactSentinel only ever proposes; execution is
the operator's explicit `sov compact run <store>`. Kill switches:
SOV_NO_COMPACT=1 (master) and SOV_NO_COMPACT_<STORE>=1 (per store).
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .stores import REGISTRY, StoreSpec, record_ts

MARK = "memory-compact-d"
DEFAULT_BEFORE_DAYS = 180   # "older than N months" — 6 by default
MASTER_KILL = "SOV_NO_COMPACT"


class CompactError(Exception):
    pass


def compaction_enabled(store_id: str) -> bool:
    if os.environ.get(MASTER_KILL):
        return False
    per_store = f"SOV_NO_COMPACT_{store_id.upper().replace('-', '_')}"
    return not os.environ.get(per_store)


def _data_dir(data_dir: Path | None) -> Path:
    if data_dir is None:
        from sovereign_agent.config import SETTINGS

        data_dir = SETTINGS.paths.data_dir
    return Path(data_dir)


def _index_path(hot_path: Path) -> Path:
    return hot_path.parent / "compact_index.json"


def load_index(store_id: str, data_dir: Path | None = None) -> dict:
    spec = REGISTRY[store_id]
    path = _index_path(_data_dir(data_dir) / spec.rel_path)
    if not path.exists():
        return {"store": store_id, "periods": {}}
    try:
        idx = json.loads(path.read_text(encoding="utf-8"))
        idx.setdefault("periods", {})
        return idx
    except ValueError:
        return {"store": store_id, "periods": {}, "note": "index was corrupt; rebuilt"}


def _save_index(hot_path: Path, index: dict) -> None:
    path = _index_path(hot_path)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(index, indent=1, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


@dataclass
class CompactPlan:
    """What a run WOULD do — the preview the operator approves."""

    store_id: str
    hot_path: str
    before_days: int
    cutoff: str
    total_records: int = 0
    to_move: int = 0
    unparseable_kept_hot: int = 0
    periods: dict = field(default_factory=dict)   # "YYYY-MM" -> count
    bytes_to_move: int = 0

    def as_dict(self) -> dict:
        return asdict(self)


def _split_lines(spec: StoreSpec, hot_path: Path, cutoff: datetime):
    """(keep_lines, move_by_period, digests_by_period) — raw lines, verbatim."""
    keep: list[str] = []
    move: dict[str, list[str]] = {}
    digest: dict[str, dict] = {}
    unparseable = 0
    for raw in hot_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not raw.strip():
            continue
        try:
            rec = json.loads(raw)
            if not isinstance(rec, dict):
                raise ValueError
        except ValueError:
            keep.append(raw)     # we do not relocate what we cannot read
            unparseable += 1
            continue
        ts = record_ts(rec, spec)
        if ts is None:
            keep.append(raw)     # we do not relocate what we cannot date
            unparseable += 1
            continue
        if ts >= cutoff:
            keep.append(raw)
            continue
        period = ts.strftime("%Y-%m")
        move.setdefault(period, []).append(raw)
        d = digest.setdefault(period, {"count": 0, "first_ts": "", "last_ts": ""})
        d["count"] += 1
        iso = ts.strftime("%Y-%m-%dT%H:%M:%SZ")
        if not d["first_ts"] or iso < d["first_ts"]:
            d["first_ts"] = iso
        if not d["last_ts"] or iso > d["last_ts"]:
            d["last_ts"] = iso
        if spec.digest_extra:
            try:
                val = float(rec.get(spec.digest_extra, 0.0))
                d.setdefault("_sum", 0.0)
                d["_sum"] += val
            except (TypeError, ValueError):
                pass
    for d in digest.values():
        if "_sum" in d and d["count"]:
            d[f"avg_{spec.digest_extra}"] = round(d.pop("_sum") / d["count"], 3)
        d.pop("_sum", None)
    return keep, move, digest, unparseable


def preview(store_id: str, *, before_days: int = DEFAULT_BEFORE_DAYS,
            data_dir: Path | None = None) -> CompactPlan:
    spec = REGISTRY.get(store_id)
    if spec is None:
        raise CompactError(f"unknown store {store_id!r} — see `sov compact audit`")
    if not spec.compactable:
        raise CompactError(
            f"store {store_id!r} is audit-only: {spec.reason} — compacting it "
            f"would change meaning, which is forbidden")
    hot_path = _data_dir(data_dir) / spec.rel_path
    cutoff = datetime.now(timezone.utc) - timedelta(days=before_days)
    plan = CompactPlan(store_id=store_id, hot_path=str(hot_path),
                       before_days=before_days,
                       cutoff=cutoff.strftime("%Y-%m-%dT%H:%M:%SZ"))
    if not hot_path.exists():
        return plan
    keep, move, _digest, unparseable = _split_lines(spec, hot_path, cutoff)
    plan.total_records = len(keep) + sum(len(v) for v in move.values())
    plan.to_move = sum(len(v) for v in move.values())
    plan.unparseable_kept_hot = unparseable
    plan.periods = {p: len(v) for p, v in sorted(move.items())}
    plan.bytes_to_move = sum(len(line) + 1 for v in move.values() for line in v)
    return plan


@dataclass
class CompactResult:
    store_id: str
    moved: int
    kept: int
    periods: dict
    cold_files: list[str]
    backup: str
    ok: bool = True

    def as_dict(self) -> dict:
        return asdict(self)


def run(store_id: str, *, before_days: int = DEFAULT_BEFORE_DAYS,
        data_dir: Path | None = None) -> CompactResult:
    """Execute a compaction — operator-invoked, kill-switched, verified,
    reversible (the .bak stays)."""
    if not compaction_enabled(store_id):
        raise CompactError(
            f"compaction for {store_id!r} is disabled by kill switch")
    spec = REGISTRY.get(store_id)
    if spec is None:
        raise CompactError(f"unknown store {store_id!r}")
    if not spec.compactable:
        raise CompactError(f"store {store_id!r} is audit-only: {spec.reason}")
    hot_path = _data_dir(data_dir) / spec.rel_path
    if not hot_path.exists():
        return CompactResult(store_id=store_id, moved=0, kept=0, periods={},
                             cold_files=[], backup="")
    cutoff = datetime.now(timezone.utc) - timedelta(days=before_days)
    original = hot_path.read_text(encoding="utf-8", errors="replace")
    original_count = sum(1 for line in original.splitlines() if line.strip())
    keep, move, digest, _unparseable = _split_lines(spec, hot_path, cutoff)

    if not move:
        return CompactResult(store_id=store_id, moved=0, kept=len(keep),
                             periods={}, cold_files=[], backup="")

    # 1. reversibility first: timestamped backup of the hot file
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup = hot_path.with_name(hot_path.name + f".bak-compact-{stamp}")
    backup.write_text(original, encoding="utf-8")

    # 2. cold files: append the raw lines, verbatim, fsync
    stem = hot_path.name.rsplit(".", 1)[0]
    cold_files: list[str] = []
    for period, lines in sorted(move.items()):
        cold = hot_path.parent / f"{stem}.cold-{period}.ndjson"
        with open(cold, "a", encoding="utf-8") as fh:
            for line in lines:
                fh.write(line + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        cold_files.append(str(cold))

    # 3. hot rewrite, atomic
    tmp = hot_path.with_suffix(hot_path.suffix + ".tmp")
    tmp.write_text("".join(line + "\n" for line in keep), encoding="utf-8")
    os.replace(tmp, hot_path)

    # 4. verify: nothing lost — kept + moved == original line count
    new_count = sum(1 for line in hot_path.read_text(encoding="utf-8",
                                                     errors="replace").splitlines()
                    if line.strip())
    moved = sum(len(v) for v in move.values())
    if new_count + moved != original_count:
        hot_path.write_text(original, encoding="utf-8")   # restore; .bak also kept
        raise CompactError(
            f"count verification failed for {store_id!r} "
            f"({new_count}+{moved} != {original_count}) — hot file restored")

    # 5. the pointer: update the compact index (append-merge per period)
    index = load_index(store_id, data_dir)
    for period, lines in move.items():
        entry = index["periods"].get(period, {"count": 0})
        entry["count"] = int(entry.get("count", 0)) + len(lines)
        entry["cold"] = f"{stem}.cold-{period}.ndjson"
        for k, v in digest.get(period, {}).items():
            if k != "count":
                entry[k] = v
        index["periods"][period] = entry
    index["store"] = store_id
    index["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    _save_index(hot_path, index)

    try:
        from sovereign_agent.events import emit_event

        emit_event("compact-d", plane="control", trace_id=f"compact-{store_id}",
                   payload={"store": store_id, "moved": moved,
                            "periods": {p: len(v) for p, v in move.items()},
                            "backup": str(backup)})
    except Exception:  # noqa: BLE001 — events are best-effort here
        pass

    return CompactResult(store_id=store_id, moved=moved, kept=len(keep),
                         periods={p: len(v) for p, v in sorted(move.items())},
                         cold_files=cold_files, backup=str(backup))


def iter_cold_records(store_id: str, store_dir: Path):
    """Yield parsed records from every cold file the index names — the
    read-back path that keeps compacted records addressable."""
    store_dir = Path(store_dir)
    index_path = store_dir / "compact_index.json"
    if not index_path.exists():
        return
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except ValueError:
        return
    for entry in index.get("periods", {}).values():
        cold = store_dir / str(entry.get("cold", ""))
        if not cold.exists():
            continue
        for raw in cold.read_text(encoding="utf-8", errors="replace").splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                rec = json.loads(raw)
            except ValueError:
                continue
            if isinstance(rec, dict):
                yield rec
