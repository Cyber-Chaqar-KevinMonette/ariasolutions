"""path_scan/triage.py — status-aware classification of staged aria-* modules.

THE PROBLEM: the path sentinel scans every `aria-*/` folder forever, but
most staged modules are HISTORICAL — already applied to live `src/`, kept
as documentation/provenance. Their findings (a placeholder in a stale
payload copy, an apply script whose anchors have long since landed) are
not pending danger; they drowned the sentinel in a permanent error-level
count (32 blocks at the time this was built) that made real findings
invisible.

THE FIX: classify each module as `applied` / `pending` / `unknown` using
signals that already exist:
  1. MARK strings — a module's patcher.py declares `MARK = "...-d"`; if
     every declared MARK appears in live src/, the patches landed.
  2. Payload presence — for payload-only modules, every payload file
     existing at its mirrored live path means it was copied in.
  3. ApplyQueueStore history — an explicit `applied` status wins outright.

`scan_repo` (the fleet-wide view + the sentinel's source) downgrades
findings inside `applied` modules to warn-severity `historical/*` kinds.
`scan_one` — what safe_apply's step-0 gate calls on the module actually
being applied — is deliberately untouched: full block semantics, nothing
weakened where it matters.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

_MARK_RE = re.compile(r'^MARK\s*=\s*["\']([^"\']+)["\']', re.M)

Classification = str  # "applied" | "pending" | "unknown"


@dataclass
class SrcIndex:
    """One pass over live src/ so classifying ~100 modules doesn't re-read
    ~450 files per module."""

    src_root: Path
    blob: str = ""
    files: set[str] = field(default_factory=set)

    @classmethod
    def build(cls, src_root: Path) -> "SrcIndex":
        src_root = Path(src_root)
        texts: list[str] = []
        files: set[str] = set()
        if src_root.is_dir():
            for f in src_root.rglob("*.py"):
                if "__pycache__" in f.parts:
                    continue
                files.add(str(f.relative_to(src_root)))
                try:
                    texts.append(f.read_text(encoding="utf-8", errors="replace"))
                except OSError:
                    continue
        return cls(src_root=src_root, blob="\n".join(texts), files=files)


def _queue_status(module: str) -> str | None:
    """ApplyQueueStore's latest status for this slug, if any (best-effort)."""
    try:
        from sovereign_agent.apply_queue.store import ApplyQueueStore

        store = ApplyQueueStore()
        for item in store._state().values():  # reduction of the event log
            if item.slug in (module, module.removeprefix("aria-")):
                return item.status
    except Exception:  # noqa: BLE001 — the queue is a bonus signal, never a blocker
        return None
    return None


def declared_marks(mod_dir: Path) -> list[str]:
    """Every MARK string declared by the module's patcher.py (if present)."""
    patcher = Path(mod_dir) / "patcher.py"
    if not patcher.is_file():
        return []
    try:
        return _MARK_RE.findall(patcher.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return []


def payload_rel_files(mod_dir: Path) -> list[str]:
    """Payload .py files as live-src-relative paths."""
    payload = Path(mod_dir) / "payload" / "src" / "sovereign_agent"
    if not payload.is_dir():
        return []
    return [
        str(f.relative_to(payload))
        for f in payload.rglob("*.py")
        if "__pycache__" not in f.parts
    ]


def classify_module(mod_dir: Path, index: SrcIndex) -> Classification:
    """applied | pending | unknown — see module docstring for the signals."""
    mod_dir = Path(mod_dir)

    qstatus = _queue_status(mod_dir.name)
    if qstatus == "applied":
        return "applied"

    marks = declared_marks(mod_dir)
    payload = payload_rel_files(mod_dir)

    if marks:
        # Patcher-driven module: applied iff every declared MARK landed live.
        # (Payload files, if any, ride along with the same apply script.)
        return "applied" if all(m in index.blob for m in marks) else "pending"
    if payload:
        # Payload-only module: applied iff every payload file exists at its
        # mirrored live path (content may legitimately drift after apply —
        # live moves on; existence is the honest signal).
        return "applied" if all(rel in index.files for rel in payload) else "pending"
    return "unknown"


def triage_report(repo_root: Path) -> dict:
    """Classify every staged module. The operator-facing catalog."""
    repo_root = Path(repo_root)
    index = SrcIndex.build(repo_root / "src" / "sovereign_agent")
    out: dict[str, list[str]] = {"applied": [], "pending": [], "unknown": []}
    for mod_dir in sorted(repo_root.glob("aria-*")):
        if not mod_dir.is_dir():
            continue
        out[classify_module(mod_dir, index)].append(mod_dir.name)
    return {
        "counts": {k: len(v) for k, v in out.items()},
        **out,
    }
