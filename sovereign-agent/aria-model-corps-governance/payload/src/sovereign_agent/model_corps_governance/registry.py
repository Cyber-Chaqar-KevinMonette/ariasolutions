"""model_corps_governance/registry.py — the persisted model roster ledger.
(Model Corps round · MC3)

Mirrors `quality/ledger.py`'s exact discipline: append-only NDJSON, fsync'd,
`latest_registry()` reads only what was actually stored. The roster itself
(role -> base tag -> license -> approximate VRAM) is a plain declared table,
not auto-detected — auto-detecting a license from an Ollama blob is not
reliable, so this stays an honest, explicit, human-reviewable source of
truth that `model_corps_sentinel.py` checks the LIVE `ollama list` output
against (drift), rather than pretending to infer it.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

MARK = "model-corps-registry-d"

ALLOWED_LICENSES = frozenset({"Apache-2.0", "MIT", "BSD-3-Clause"})

# The declared roster — role -> (base tag, license, approx VRAM MB at the
# quantization actually pulled). Update this table (and re-run
# scripts/regen_model_corps.sh) when the roster changes; the sentinel's
# license/drift checks read this table, not the other way around.
ROSTER: dict[str, dict[str, object]] = {
    "orchestrator": {"base": "qwen3:8b", "license": "Apache-2.0", "vram_mb": 5200},
    "coder": {"base": "qwen2.5-coder:7b", "license": "Apache-2.0", "vram_mb": 4700},
    "fast": {"base": "phi4-mini:3.8b", "license": "MIT", "vram_mb": 2500},
    "reflector": {"base": "phi4-mini:3.8b", "license": "MIT", "vram_mb": 2500},
    "interpreter": {"base": "phi4-mini:3.8b", "license": "MIT", "vram_mb": 2500},
    "vision": {"base": "qwen3-vl:4b", "license": "Apache-2.0", "vram_mb": 2800},
}


@dataclass
class ModelCorpsEntry:
    role: str
    tag: str                 # the aria-<role>:latest tag actually loaded
    base: str
    license: str
    vram_mb: int
    persona_version: str     # short hash of the role's current persona text
    last_verified: str

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class RegistrySnapshot:
    snapshot_id: str
    ts: str
    entries: list[ModelCorpsEntry] = field(default_factory=list)

    def as_dict(self) -> dict:
        d = asdict(self)
        return d


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _new_id() -> str:
    from ulid import ULID

    return f"mcr-{str(ULID())[:12]}"


def _ledger_path(data_dir: Path | None) -> Path:
    if data_dir is None:
        from sovereign_agent.config import SETTINGS

        data_dir = SETTINGS.paths.data_dir
    p = Path(data_dir) / "model_corps"
    p.mkdir(parents=True, exist_ok=True)
    return p / "registry.ndjson"


def _persona_version(role: str) -> str:
    """A short, stable hash of the role's current persona text — changes the
    moment GOD_TIER_STANDARD.md ratchets or the role paragraph is edited, so
    a drift check can tell "same persona as last snapshot" from "regenerated
    since." Never raises: an import/parse failure just yields a fixed
    sentinel string rather than crashing a snapshot."""
    try:
        from sovereign_agent.model_corps import build_role_persona

        text = build_role_persona(role)
    except Exception:  # noqa: BLE001 — a persona bug must not break a snapshot
        return "unavailable"
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def record_registry_snapshot(data_dir: Path | None = None) -> RegistrySnapshot:
    """Snapshot the declared ROSTER (with each role's live persona hash),
    append ONE fsync'd record. Does not itself query `ollama list` — that
    live-vs-declared comparison is the sentinel's job (`model_corps_
    sentinel.py`), so a snapshot always succeeds even if the daemon is down."""
    entries = [
        ModelCorpsEntry(
            role=role,
            tag=f"aria-{role}:latest",
            base=str(spec["base"]),
            license=str(spec["license"]),
            vram_mb=int(spec["vram_mb"]),
            persona_version=_persona_version(role),
            last_verified=_now(),
        )
        for role, spec in ROSTER.items()
    ]
    snapshot = RegistrySnapshot(snapshot_id=_new_id(), ts=_now(), entries=entries)
    path = _ledger_path(data_dir)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(snapshot.as_dict(), separators=(",", ":")) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    try:
        from sovereign_agent.events import emit_event

        emit_event("model-corps-registry-d", plane="control",
                   trace_id=snapshot.snapshot_id,
                   payload={"roles": [e.role for e in entries]})
    except Exception:  # noqa: BLE001
        pass
    return snapshot


def latest_registry(data_dir: Path | None = None) -> dict | None:
    """The most recent registry snapshot, or None if none has ever run."""
    from sovereign_agent.read_repair import read_ndjson_tolerant

    records = read_ndjson_tolerant(_ledger_path(data_dir), store="model_corps_registry",
                                   emit=False).records
    return records[-1] if records else None


__all__ = ["ALLOWED_LICENSES", "ROSTER", "ModelCorpsEntry", "RegistrySnapshot",
          "record_registry_snapshot", "latest_registry"]
