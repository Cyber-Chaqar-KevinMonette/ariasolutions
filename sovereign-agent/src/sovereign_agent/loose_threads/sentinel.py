"""loose_threads/sentinel.py — the LooseThreadsSentinel.

Kill switch: SOV_NO_LOOSE_THREADS_SENTINEL=1 (honored via
Sentinel.is_enabled(); master: SOV_NO_SENTINELS=1).

scan() runs the full AST pass (~expensive — cached via the base catalog,
the standing strip discipline); health_status() reads the cache only.
Health = the count of UNDISPOSITIONED loose threads: warn when any exist,
ok when her anatomy is fully accounted for.
"""
from __future__ import annotations

import sovereign_agent.stewardship  # noqa: F401 — resolve circularity first
from datetime import datetime, timezone
from pathlib import Path

from sovereign_agent.stewardship.base import HealthStatus, Sentinel, SentinelReport
from sovereign_agent.stewardship.registry import register_sentinel


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


@register_sentinel
class LooseThreadsSentinel(Sentinel):
    """Feels disconnection: finished machinery nobody calls."""

    @property
    def id(self) -> str:
        return "loose-threads"

    @property
    def title(self) -> str:
        return "Loose Threads — orphaned wholeness detection (zero-caller public symbols)"

    @property
    def tier(self) -> int:
        return 1

    def articles(self) -> list[str]:
        return [
            "I. I scan her anatomy for public functions and classes nothing "
            "outside their own module references — her characteristic failure "
            "mode is not broken code but orphaned wholeness.",
            "II. I understand her own idioms (tool registries, sentinel "
            "decorators, CLI commands, UI dispatch) as real callers — I do "
            "not cry wolf about what the frameworks call.",
            "III. Every finding deserves a disposition — WIRED, RETIRED, or "
            "ACCEPTED with a written reason. I stop warning the moment a "
            "thread is accounted for; I never accept silence as an answer.",
            "IV. Tests are not callers. Tested-and-dead is still dead.",
        ]

    def scan(self) -> SentinelReport:
        import sovereign_agent
        from sovereign_agent.loose_threads import DispositionLedger, scan_threads

        src_root = Path(sovereign_agent.__file__).parent
        result = scan_threads(src_root)
        open_threads = DispositionLedger().undispositioned(result.threads)
        blob = {
            "summary": result.summary(),
            "total": len(result.threads),
            "undispositioned": len(open_threads),
            "threads": [t.as_dict() for t in open_threads[:100]],
        }
        cat_path = self.save_catalog(blob, name="loose_threads")
        return SentinelReport(
            sentinel_id=self.id, observed_at=_now(),
            catalog_name="loose_threads",
            findings_count=len(open_threads),
            summary=f"{result.summary()} · {len(open_threads)} undispositioned",
            catalog_path=str(cat_path),
            details=blob,
        )

    def health_status(self) -> HealthStatus:
        cached = self.load_catalog(name="loose_threads")
        if cached is None:
            return HealthStatus(sentinel_id=self.id, level="ok",
                                summary="not yet scanned — `sov threads scan`",
                                observed_at=_now())
        n = int(cached.get("undispositioned", 0))
        if n == 0:
            return HealthStatus(sentinel_id=self.id, level="ok",
                                summary="every thread accounted for",
                                observed_at=_now())
        return HealthStatus(sentinel_id=self.id, level="warning",
                            summary=f"{n} loose thread(s) await disposition",
                            observed_at=_now())
