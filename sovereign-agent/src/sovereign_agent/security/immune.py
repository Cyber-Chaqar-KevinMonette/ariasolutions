"""security/immune.py — Aria's immune system (diamond armor on her crown jewels).

DEFENSIVE ONLY. This is incident-response for Aria's OWN machine: watch her most critical files,
detect tampering instantly, alert, quarantine a suspect for analysis, and REVERSIBLY heal from a
verified backup — then she is stronger than before. There is NO offensive capability here: no malware,
no exploits, no attack tooling. Defending one's own workstation is legal and legitimate.

Crown jewels (highest priority, tightest checks): the charter (SIGNAL.md — READ-ONLY, never edited),
the authority gate, mos_canon, the seal, and the quantum brain/vault state. The charter is only
HASHED (read) for tamper detection; healing RESTORES a tampered file to its known-good version.

Safety: detect→alert→propose by default. Healing/quarantine are reversible and human-approved by
default; the emergency reversible-only path is for genuine no-human-present incidents. Fully logged.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


def _repo_root() -> Path:
    # security/ is under src/sovereign_agent/ → repo root is 3 parents up from this file's package
    here = Path(__file__).resolve()
    for p in here.parents:
        if (p / "pyproject.toml").exists():
            return p
    return here.parents[3]


def crown_jewels(repo_root: Path | None = None) -> list[Path]:
    """The most critical files — protected with the tightest integrity checks."""
    r = repo_root or _repo_root()
    candidates = [
        r / "SIGNAL.md",                                        # the charter (READ-ONLY)
        r / "src/sovereign_agent/authority.py",                 # the authority gate
        r / "src/sovereign_agent/mos_canon.py",                 # the canon
        r / "src/sovereign_agent/seal.py",                      # the seal
        r / "src/sovereign_agent/aegis/vault.py",               # the vault
        r / "src/sovereign_agent/quantum/globe.py",             # the brain (globe)
        r / "src/sovereign_agent/quantum/brain.py",             # the learning brain
    ]
    return [c for c in candidates if c.exists()]


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _immune_dir(data_dir: Path) -> Path:
    d = Path(data_dir) / "immune"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _baseline_path(data_dir: Path) -> Path:
    return _immune_dir(data_dir) / "crown_baseline.json"


def record_baseline(data_dir: Path, repo_root: Path | None = None) -> dict:
    """Snapshot the known-good hashes of the crown jewels (the integrity reference)."""
    jewels = crown_jewels(repo_root)
    baseline = {str(p): _sha256(p) for p in jewels}
    rec = {"recorded_at": _now(), "count": len(baseline), "hashes": baseline}
    _baseline_path(data_dir).write_text(json.dumps(rec, indent=1), encoding="utf-8")
    return {"recorded_at": rec["recorded_at"], "crown_jewels": len(baseline)}


def check_integrity(data_dir: Path, repo_root: Path | None = None) -> dict:
    """Re-hash crown jewels, compare to baseline. Detect tampering. Read-only."""
    bp = _baseline_path(data_dir)
    if not bp.exists():
        return {"status": "no_baseline", "note": "record a baseline first (immune_baseline)",
                "crown_jewels": len(crown_jewels(repo_root))}
    baseline = json.loads(bp.read_text()).get("hashes", {})
    breaches, ok, missing = [], 0, []
    for p in crown_jewels(repo_root):
        sp = str(p)
        cur = _sha256(p)
        if sp not in baseline:
            missing.append(sp)               # new crown jewel not yet baselined
        elif cur != baseline[sp]:
            breaches.append({"file": sp, "expected": baseline[sp][:12], "found": cur[:12]})
        else:
            ok += 1
    status = "BREACH" if breaches else ("drift" if missing else "intact")
    return {
        "status": status,
        "intact": ok,
        "breaches": breaches,
        "unbaselined": missing,
        "checked_at": _now(),
        "alert": bool(breaches),
        "guidance": (
            "Crown-jewel tamper detected — alert the operator immediately, quarantine the suspect, and "
            "heal by restoring the known-good file from a verified backup." if breaches else
            "All crown jewels intact." if status == "intact" else
            "New crown jewels present — re-record the baseline when you confirm they're legitimate."
        ),
    }


def quarantine(data_dir: Path, suspect_path: str) -> dict:
    """Move a suspicious artifact into an isolated, inert quarantine dir for analysis. Reversible.

    Defensive forensics only: we ISOLATE and record metadata (size, hash, where it was) so damage can be
    scoped and the system healed. We never execute or weaponize it.
    """
    src = Path(suspect_path)
    if not src.exists() or not src.is_file():
        return {"ok": False, "error": f"not_found: {suspect_path}"}
    qdir = _immune_dir(data_dir) / "quarantine"
    qdir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    dest = qdir / f"{ts}__{src.name}"
    meta = {
        "quarantined_at": _now(),
        "original_path": str(src),
        "size_bytes": src.stat().st_size,
        "sha256": _sha256(src),
        "quarantine_path": str(dest),
    }
    shutil.move(str(src), str(dest))
    (qdir / f"{dest.name}.meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    return {"ok": True, **meta,
            "note": "Isolated for analysis (inert). Restore original from backup if it was a crown jewel."}


def heal_from_backup(data_dir: Path, file_path: str, *, backup_root: Path | None = None) -> dict:
    """Restore a tampered file to its known-good version from a verified backup snapshot. Reversible.

    Restoration only — never destructive. Returns a proposal if no verified snapshot is available.
    """
    target = Path(file_path)
    try:
        from sovereign_agent import backup as _bk
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"backup module unavailable: {exc!r}"}
    # Take a fresh safety snapshot of current state first (so the heal itself is reversible).
    # The reversibility CLAIM below must match what actually happened — a swallowed snapshot
    # failure must never be reported as "the heal is reversible".
    pre_heal_snapshot_ok = True
    snapshot_error = ""
    try:
        _bk.snapshot(label="pre-heal-safety", data_dir=Path(data_dir))
    except Exception as exc:  # noqa: BLE001
        pre_heal_snapshot_ok = False
        snapshot_error = repr(exc)
    if pre_heal_snapshot_ok:
        note = ("A pre-heal safety snapshot was taken (the heal is reversible). To restore the known-good "
                "version, run backup.restore on the latest verified snapshot containing this file. By "
                "default this awaits operator approval; the emergency reversible-only path applies only "
                "when no human responds and the file is a confirmed-tampered crown jewel.")
    else:
        note = (f"Pre-heal safety snapshot FAILED ({snapshot_error}) — this heal is NOT automatically "
                "reversible. Take a manual snapshot (backup.snapshot) before restoring. To restore the "
                "known-good version, run backup.restore on the latest verified snapshot containing this "
                "file. By default this awaits operator approval.")
    return {
        "ok": True,
        "action": "proposed",
        "target": str(target),
        "pre_heal_snapshot_ok": pre_heal_snapshot_ok,
        "note": note,
    }
