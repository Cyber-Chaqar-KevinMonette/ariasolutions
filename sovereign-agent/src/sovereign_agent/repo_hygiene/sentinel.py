"""repo_hygiene/sentinel.py — the RepoHygieneSentinel.

Kill switch: SOV_NO_REPO_HYGIENE_SENTINEL=1 (honored via
Sentinel.is_enabled(); master: SOV_NO_SENTINELS=1).

scan() walks the repo root (~cheap — a single non-recursive glob, unlike
loose-threads' full AST pass) and caches the result via the base catalog,
same discipline; health_status() reads the cache only, never re-scans.
Health = the count of UNDISPOSITIONED stray scripts: warn when any exist,
ok when the root is clean.
"""
from __future__ import annotations

import sovereign_agent.stewardship  # noqa: F401 — resolve circularity first
from datetime import datetime, timezone
from pathlib import Path

from sovereign_agent.stewardship.base import HealthStatus, Sentinel, SentinelReport
from sovereign_agent.stewardship.registry import register_sentinel


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _repo_root() -> Path:
    import sovereign_agent
    # src/sovereign_agent/__init__.py -> src/sovereign_agent -> src -> repo root
    return Path(sovereign_agent.__file__).resolve().parent.parent.parent


@register_sentinel
class RepoHygieneSentinel(Sentinel):
    """Feels clutter: one-off scripts nobody archived."""

    @property
    def id(self) -> str:
        return "repo-hygiene"

    @property
    def title(self) -> str:
        return "Repo Hygiene — stray root-level script detection"

    @property
    def tier(self) -> int:
        return 1

    def articles(self) -> list[str]:
        return [
            "I. I scan her repo root for one-off Python scripts sitting "
            "outside every real home — src/, tests/, scripts/, aria-*/ "
            "staged modules, archive/ — her characteristic failure mode "
            "here is not broken code but forgotten scratch work.",
            "II. I never touch src/ — that's loose-threads' anatomy, not "
            "mine. I watch the doorstep, not the house.",
            "III. Every finding deserves a disposition — RETIRED (moved "
            "under archive/) or ACCEPTED with a written reason. I stop "
            "warning the moment a script is accounted for.",
            "IV. I propose, I never move a file myself — archiving is the "
            "operator's call, same as every Tier-1 sentinel here.",
        ]

    def scan(self) -> SentinelReport:
        from sovereign_agent.loose_threads import DispositionLedger
        from sovereign_agent.repo_hygiene.scanner import scan_repo_root

        repo_root = _repo_root()
        result = scan_repo_root(repo_root)
        ledger = DispositionLedger(root=self._data_dir / "repo_hygiene")
        open_scripts = ledger.undispositioned(result.scripts)
        blob = {
            "summary": result.summary(),
            "total": len(result.scripts),
            "undispositioned": len(open_scripts),
            "scripts": [s.as_dict() for s in open_scripts[:100]],
        }
        cat_path = self.save_catalog(blob, name="repo_hygiene")
        return SentinelReport(
            sentinel_id=self.id, observed_at=_now(),
            catalog_name="repo_hygiene",
            findings_count=len(open_scripts),
            summary=f"{result.summary()} · {len(open_scripts)} undispositioned",
            catalog_path=str(cat_path),
            details=blob,
        )

    def health_status(self) -> HealthStatus:
        cached = self.load_catalog(name="repo_hygiene")
        if cached is None:
            return HealthStatus(sentinel_id=self.id, level="ok",
                                summary="not yet scanned",
                                observed_at=_now())
        n = int(cached.get("undispositioned", 0))
        if n == 0:
            return HealthStatus(sentinel_id=self.id, level="ok",
                                summary="repo root is clean",
                                observed_at=_now())
        return HealthStatus(sentinel_id=self.id, level="warning",
                            summary=f"{n} stray script(s) await disposition",
                            observed_at=_now())

    def proposals(self, report: SentinelReport) -> list[dict]:
        # Shape matches work_suggestions._sentinel_suggestions()'s own
        # contract (reads "summary"/"remediation", falls back to "file") —
        # loose-threads' own proposals() (none implemented — it relies on
        # coverage_gaps() instead) doesn't set this precedent, so this was
        # verified directly against the consumer, not assumed.
        return [
            {
                "summary": f"stray script {s['symbol']!r} sits at the repo root, undispositioned",
                "remediation": "archive under archive/patch_scripts_<date>/ and disposition "
                              "RETIRED, or dispose ACCEPTED with a written reason",
                "file": s["path"],
            }
            for s in report.details.get("scripts", [])
        ]


__all__ = ["RepoHygieneSentinel"]
