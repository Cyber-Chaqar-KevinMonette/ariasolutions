"""apply_ledger — bookkeeping so the apply system never re-applies blindly.

Kevin's ask: "Make sure the apply system has a record/bookkeeping system so
it does not apply something more than once unless a newer version, or
invariant, or update."

The mechanism is a content **fingerprint** + a durable **ledger**:

- `module_fingerprint(module_dir)` — a sha256 over the files that actually
  determine what an apply DOES (the payload, any patch_*.py, and the
  apply_*.sh). Same content → same fingerprint; any change (a newer
  version, a changed invariant, an updated payload) → a different one.
- `ApplyLedger` — an append-history JSON at `<data>/apply_ledger.json`
  recording every apply {module, fingerprint, version, applied_at}.
- `should_apply(module, fingerprint, force)` — the decision the wrapper
  asks before applying: first-ever → yes; fingerprint changed → yes
  (newer/updated); unchanged → **no** (already applied); force → yes.

Pure decision logic + a thin durable store, so the reliability-critical
part is trivially testable. A CLI (`python -m sovereign_agent.apply_ledger
...`) lets the bash apply wrapper use it.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

__all__ = [
    "module_fingerprint",
    "ApplyLedger",
    "ApplyDecision",
    "should_apply",
    "default_ledger_path",
]

# The files whose content determines what an apply actually does.
_FINGERPRINT_GLOBS = (
    "payload/**/*.py",
    "payload/**/*.sql",
    "payload/**/*.sh",
    "patch_*.py",
    "patcher.py",
    "apply_*.sh",
)


def module_fingerprint(module_dir: Path) -> str:
    """A stable sha256 over the apply-determining files of a module.

    Deterministic: files are hashed in sorted path order, each prefixed by
    its repo-relative name, so a rename or content change moves the digest
    but re-running on identical content does not. Empty module → a stable
    'empty' digest (still comparable)."""
    module_dir = Path(module_dir)
    h = hashlib.sha256()
    seen: list[Path] = []
    for pat in _FINGERPRINT_GLOBS:
        seen.extend(sorted(module_dir.glob(pat)))
    # de-dup while preserving deterministic order
    uniq = sorted(set(p for p in seen if p.is_file()), key=lambda p: str(p))
    for p in uniq:
        rel = p.relative_to(module_dir).as_posix()
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        try:
            h.update(p.read_bytes())
        except Exception:  # noqa: BLE001 — unreadable file: fold its name only
            h.update(b"<unreadable>")
        h.update(b"\0")
    return h.hexdigest()


def default_ledger_path(data_dir: Path | None = None) -> Path:
    if data_dir is None:
        try:
            from sovereign_agent.config import SETTINGS
            data_dir = SETTINGS.paths.data_dir
        except Exception:  # noqa: BLE001
            data_dir = Path.home() / ".local" / "share" / "sovereign-agent"
    return Path(data_dir) / "apply_ledger.json"


@dataclass(frozen=True)
class ApplyDecision:
    apply: bool
    reason: str          # machine tag: first-apply | changed | unchanged | forced
    prior_fingerprint: str | None = None


def should_apply(
    module: str, fingerprint: str, *, prior: dict | None, force: bool = False
) -> ApplyDecision:
    """Pure decision: should this apply proceed? `prior` is the last ledger
    entry for the module (or None)."""
    if force:
        return ApplyDecision(True, "forced", (prior or {}).get("fingerprint"))
    if prior is None:
        return ApplyDecision(True, "first-apply", None)
    prev = prior.get("fingerprint")
    if prev != fingerprint:
        return ApplyDecision(True, "changed", prev)   # newer version / update / invariant change
    return ApplyDecision(False, "unchanged", prev)     # already applied, identical → skip


class ApplyLedger:
    """Durable append-history record of applies, keyed by module (latest wins
    for the decision; full history retained for audit)."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path else default_ledger_path()

    def _load(self) -> list[dict]:
        if not self.path.is_file():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception:  # noqa: BLE001 — a corrupt ledger must never block an apply
            return []

    def last(self, module: str) -> dict | None:
        """The most recent entry for `module`, or None."""
        entries = [e for e in self._load() if e.get("module") == module]
        return entries[-1] if entries else None

    def decide(self, module: str, fingerprint: str, *, force: bool = False) -> ApplyDecision:
        return should_apply(module, fingerprint, prior=self.last(module), force=force)

    def record(self, module: str, fingerprint: str, *, version: str = "") -> dict:
        """Append an apply record. Atomic (temp + replace)."""
        entries = self._load()
        entry = {
            "module": module,
            "fingerprint": fingerprint,
            "version": version,
            "applied_at": datetime.now(timezone.utc).isoformat(),
        }
        entries.append(entry)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(entries, indent=2), encoding="utf-8")
        tmp.replace(self.path)
        return entry

    def history(self, module: str | None = None) -> list[dict]:
        entries = self._load()
        return [e for e in entries if module is None or e.get("module") == module]


# ── CLI (used by the bash apply wrapper) ─────────────────────────────────
def _main(argv: list[str]) -> int:
    if not argv:
        print("usage: apply_ledger {fingerprint DIR | decide MODULE DIR [--force] | record MODULE DIR [VERSION]}",
              file=sys.stderr)
        return 2
    cmd = argv[0]
    if cmd == "fingerprint":
        print(module_fingerprint(Path(argv[1])))
        return 0
    if cmd == "decide":
        module, mdir = argv[1], Path(argv[2])
        force = "--force" in argv[3:]
        fp = module_fingerprint(mdir)
        d = ApplyLedger().decide(module, fp, force=force)
        # exit 0 = apply, exit 10 = skip (unchanged); reason to stdout
        print(d.reason)
        return 0 if d.apply else 10
    if cmd == "record":
        module, mdir = argv[1], Path(argv[2])
        version = argv[3] if len(argv) > 3 else ""
        fp = module_fingerprint(mdir)
        ApplyLedger().record(module, fp, version=version)
        print(f"recorded {module} @ {fp[:12]}")
        return 0
    print(f"unknown command: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
