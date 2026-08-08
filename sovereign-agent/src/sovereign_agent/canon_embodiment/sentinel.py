"""sentinel.py — CanonEmbodimentSentinel: the Sentinel-contract wrapper around
mapper.py's find_references(). Tier 1, propose-only — it reports orphaned
clauses; it never edits doctrine or code."""
from __future__ import annotations

import json
from pathlib import Path

from sovereign_agent.canon_embodiment.mapper import find_references
from sovereign_agent.stewardship.base import HealthStatus, Sentinel, SentinelReport
from sovereign_agent.stewardship.registry import register_sentinel


def _iso_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


@register_sentinel
class CanonEmbodimentSentinel(Sentinel):
    """Maps every mos_canon.py clause to where (if anywhere) it's actually
    cited outside its own declaration — doctrine's own gap-finder."""

    @property
    def id(self) -> str:
        return "canon-embodiment"

    @property
    def title(self) -> str:
        return "Canon Embodiment — is the doctrine actually lived?"

    @property
    def tier(self) -> int:
        return 1

    def articles(self) -> list[str]:
        return [
            "I. I map every mos_canon.py clause id to every place it is cited "
            "outside the canon file itself.",
            "II. A clause with zero outside citations is orphaned — declared "
            "but not (yet, traceably) lived. This is a signal for review, "
            "never an automatic judgment on the clause's worth.",
            "III. I do not edit mos_canon.py or any code. I report; a human "
            "decides whether an orphaned clause needs a citation added, or is "
            "genuinely embodied in spirit without literal citation.",
            "IV. Propose-only, Tier 1.",
        ]

    def _repo_root(self) -> Path:
        # sentinel_dir is <data_dir>/sentinels/<id>; walk up to find the repo
        # root the same way other sentinels resolve it — via the installed
        # package location, three parents up from src/sovereign_agent/.
        import sovereign_agent
        return Path(sovereign_agent.__file__).resolve().parents[2]

    def _catalog_path(self) -> Path:
        d = self.sentinel_dir / "catalogs"
        d.mkdir(parents=True, exist_ok=True)
        return d / "canon_embodiment.json"

    def scan(self) -> SentinelReport:
        report = find_references(self._repo_root())
        catalog_path = self._catalog_path()
        catalog_path.write_text(json.dumps(report.as_dict(), indent=2), encoding="utf-8")
        return SentinelReport(
            sentinel_id=self.id,
            observed_at=_iso_now(),
            catalog_name="canon_embodiment",
            findings_count=len(report.orphaned),
            summary=report.summary(),
            catalog_path=str(catalog_path),
            details=report.as_dict(),
        )

    def health_status(self) -> HealthStatus:  # cockpit-hardening-d
        """Reads the last CACHED catalog -- never re-scans fresh. Before this
        fix, health_status() called find_references() (a full repo walk --
        222 aria-*/ folders, ~1,400 files, every clause id checked per
        line) on EVERY call. gather_health() runs this every 5s in a
        background thread (cockpit/app.py's _refresh_status_worker) --
        diagnosed live via py-spy on a hung cockpit (2026-07-20) as the
        actual cause of an apparent freeze, holding the GIL long enough to
        starve the whole app. Matches the fix stewardship/glyph_sentinel.py
        already applies to itself for the identical reason. Call scan()
        explicitly (`sov sentinels scan`) to refresh the cache."""
        catalog_path = self._catalog_path()
        if not catalog_path.is_file():
            return HealthStatus(
                sentinel_id=self.id, level="ok",
                summary="not yet scanned — run `sov sentinels scan` for a first pass",
                observed_at=_iso_now(),
            )
        try:
            data = json.loads(catalog_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return HealthStatus(
                sentinel_id=self.id, level="ok",
                summary="cached catalog unreadable — run `sov sentinels scan`",
                observed_at=_iso_now(),
            )
        orphaned = data.get("orphaned", [])
        embodied = data.get("embodied", {})
        total = len(embodied) + len(orphaned)
        if not embodied:
            level, summary = "error", "no clauses cited anywhere outside mos_canon.py"
        elif orphaned:
            level = "warning"
            summary = f"{len(orphaned)}/{total} clauses orphaned"
        else:
            level, summary = "ok", "all clauses cited at least once"
        return HealthStatus(sentinel_id=self.id, level=level, summary=summary, observed_at=_iso_now())
