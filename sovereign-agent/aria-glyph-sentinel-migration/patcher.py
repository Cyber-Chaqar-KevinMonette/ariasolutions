"""patcher.py — Workstream: migrate glyph_sentinel.py to the unified
@register_sentinel pattern.

`glyph_sentinel.py` is a functional module (free functions
`scan_source_tree`/`generate_proposals`/`detect_coverage_gaps`/
`load_catalog`/`save_catalog` over plain dataclasses), not an OOP
sentinel — confirmed invisible to `sov sentinels list`/`gather_health()`/
`scan_all()` entirely today. Researched via a dedicated Explore agent:
the catalog→proposals→gaps trio maps naturally onto
`scan()`/`proposals()`/`coverage_gaps()` — better than most sentinels,
since those exact names already exist as free functions.

The recommended, lowest-risk migration: add a NEW `GlyphSentinel(Sentinel)`
class INSIDE glyph_sentinel.py that *delegates* to the existing free
functions unchanged, registers via `@register_sentinel`, and writes its
OWN rollup catalog under the base class's own `sentinels/glyphs/catalogs/`
convention — the legacy `glyph_catalog.json` path and all 4 existing call
sites (doctor.py, cli.py, workflow/catalog.py, cosmic_fitness.py) stay
completely untouched.

A real design decision worth recording: `health_status()` does NOT call
`scan()` fresh (unlike `ConformanceSentinel`'s own equivalent, which
re-scans every call — cheap for a handful of rule checks, but
`scan_source_tree()` walks the full ~450-file source tree, the same cost
class (~3s) as J's Tier-A scan_tree() and H2's kernel-coherence scan).
`gather_health()` is called on the cockpit's 8s strip-refresh cadence in
4 places (confirmed via direct grep of app.py) — re-scanning fresh on
every health_status() call would reintroduce the EXACT GIL-contention
regression already root-caused and fixed three times this session
(security-strip-wire, vessel-health). health_status() reads the last
CACHED rollup catalog instead; scan() remains the (expensive, explicit,
on-demand) full walk, invoked only via `sov sentinels scan` / `scan_all()`.
"""
from __future__ import annotations

MARK = "glyph-sentinel-migration-d"


class PatchError(Exception):
    pass


def _replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if text.count(old) != 1:
        raise PatchError(f"{label}: expected exactly 1 occurrence, found {text.count(old)}")
    return text.replace(old, new, 1)


# ═══════════════════════════════════════════════════════════════════════
# stewardship/glyph_sentinel.py — the new GlyphSentinel(Sentinel) class
# ═══════════════════════════════════════════════════════════════════════

GLYPH_SENTINEL_IMPORT_ANCHOR = (
    "from .. import glyphs as _g\n"
)
GLYPH_SENTINEL_IMPORT_NEW = (
    "from .. import glyphs as _g\n"
    "from .base import HealthStatus, Sentinel, SentinelReport  # " + MARK + "\n"
    "from .registry import register_sentinel  # " + MARK + "\n"
)

GLYPH_SENTINEL_TAIL_ANCHOR = (
    '__all__ = [\n'
    '    "Classification",\n'
    '    "GlyphEntry",\n'
    '    "GlyphCatalog",\n'
    '    "ReplacementProposal",\n'
    '    "CoverageGap",\n'
    '    "KNOWN_REPLACEMENTS",\n'
    '    "PROTECTED_RELATIVE_PATHS",\n'
    '    "scan_source_tree",\n'
    '    "find_source_root",\n'
    '    "load_catalog",\n'
    '    "save_catalog",\n'
    '    "catalog_path",\n'
    '    "generate_proposals",\n'
    '    "detect_coverage_gaps",\n'
    ']\n'
)

_GLYPH_SENTINEL_CLASS = '''# ─── The Sentinel ──────────────────────────────────────────────────────── MARKER


@register_sentinel
class GlyphSentinel(Sentinel):  # MARKER
    """Wraps the existing scan/proposals/gaps free functions in the
    unified Sentinel contract — glyph health becomes visible in
    `sov sentinels list` / `gather_health()` / `scan_all()`, previously
    invisible to that loop entirely.

    Purely additive: the legacy `glyph_catalog.json` path (read/written
    directly by doctor.py/cli.py/cosmic_fitness.py) and all 4 existing
    call sites stay completely untouched. This sentinel writes its OWN
    rollup catalog under the base class's own sentinels/glyphs/catalogs/
    convention instead of duplicating or reading the legacy file.
    """

    @property
    def id(self) -> str:
        return "glyphs"

    @property
    def title(self) -> str:
        return "Glyph Safety — visual-identity glyph cataloging + unsafe-glyph proposals"

    @property
    def tier(self) -> int:
        return 1

    def articles(self) -> list[str]:
        return [
            "I. I scan the source tree for every non-ASCII glyph and classify each "
            "as safe / borderline / unsafe by Unicode East-Asian-Width.",
            "II. I propose replacements for unsafe glyphs that have a known-safe "
            "alternative registered in KNOWN_REPLACEMENTS — I never auto-apply them.",
            "III. I flag coverage gaps: unsafe glyphs genuinely in use with no "
            "known-safe alternative yet registered.",
            "IV. I never propose changes to protected files (glyphs.py itself, "
            "my own module, or tests that document the bug class on purpose).",
        ]

    def scan(self) -> SentinelReport:
        """The expensive, explicit, on-demand full source-tree walk.
        Deliberately NOT called by health_status() — see this module's
        own patcher.py docstring for why (GIL-contention precedent)."""
        catalog = scan_source_tree()
        proposals = generate_proposals(catalog)
        gaps = detect_coverage_gaps(catalog)

        blob = {
            "generated_at": catalog.generated_at,
            "source_root": catalog.source_root,
            "total_files_scanned": catalog.total_files_scanned,
            "safe_count": catalog.safe_count,
            "borderline_count": catalog.borderline_count,
            "unsafe_count": catalog.unsafe_count,
            "proposals": [asdict(p) for p in proposals],
            "coverage_gaps": [asdict(g) for g in gaps],
        }
        cat_path = self.save_catalog(blob, name="glyph_rollup")

        findings_count = len(proposals) + len(gaps)
        return SentinelReport(
            sentinel_id=self.id,
            observed_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            catalog_name="glyph_rollup",
            findings_count=findings_count,
            summary=(
                f"{catalog.total_files_scanned} files scanned; "
                f"{len(proposals)} actionable proposal(s), {len(gaps)} coverage gap(s); "
                f"{catalog.unsafe_count} unsafe / {catalog.borderline_count} borderline / "
                f"{catalog.safe_count} safe glyph(s) cataloged"
            ),
            catalog_path=str(cat_path),
            details={
                "proposals": [asdict(p) for p in proposals[:20]],
                "coverage_gaps": [asdict(g) for g in gaps[:20]],
            },
        )

    def health_status(self) -> HealthStatus:
        """Reads the last CACHED rollup catalog — never re-scans fresh.
        `gather_health()` runs on the cockpit's 8s strip-refresh cadence
        in 4 places; a fresh ~3s source-tree walk on every call would
        reintroduce the exact GIL-contention regression already found
        and fixed three times this session. Call scan() explicitly
        (via `sov sentinels scan` or scan_all()) to refresh the cache."""
        cached = self.load_catalog(name="glyph_rollup")
        if cached is None:
            return HealthStatus(
                sentinel_id=self.id, level="ok",
                summary="not yet scanned — run `sov sentinels scan` for a first pass",
                observed_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            )
        n_proposals = len(cached.get("proposals", []))
        n_gaps = len(cached.get("coverage_gaps", []))
        n = n_proposals + n_gaps
        if n == 0:
            level, summary = "ok", "no unsafe glyphs needing action"
        else:
            level, summary = "warning", f"{n_proposals} proposal(s), {n_gaps} coverage gap(s) to review"
        return HealthStatus(
            sentinel_id=self.id, level=level, summary=summary,
            observed_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        )

    def proposals(self, report: SentinelReport) -> list[dict]:
        return report.details.get("proposals", [])

    def coverage_gaps(self, report: SentinelReport) -> list[dict]:
        return report.details.get("coverage_gaps", [])


'''

GLYPH_SENTINEL_TAIL_NEW = (
    _GLYPH_SENTINEL_CLASS.replace("MARKER", MARK) + GLYPH_SENTINEL_TAIL_ANCHOR
)


def patch_glyph_sentinel(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(
        text, GLYPH_SENTINEL_IMPORT_ANCHOR, GLYPH_SENTINEL_IMPORT_NEW, label="glyph_sentinel import anchor"
    )
    text = _replace_once(
        text, GLYPH_SENTINEL_TAIL_ANCHOR, GLYPH_SENTINEL_TAIL_NEW, label="glyph_sentinel tail anchor"
    )
    return text, True


# ═══════════════════════════════════════════════════════════════════════
# stewardship/__init__.py — register the module (import for side effect)
# ═══════════════════════════════════════════════════════════════════════

STEWARDSHIP_INIT_ANCHOR = (
    "from sovereign_agent.path_scan.sentinel import PathSentinel as _path_sentinel  "
    "# noqa: F401  # path-sentinel-import-d\n"
)
STEWARDSHIP_INIT_NEW = (
    STEWARDSHIP_INIT_ANCHOR
    + "from . import glyph_sentinel as _glyph_sentinel  # noqa: F401  # " + MARK + "\n"
)


def patch_stewardship_init(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(
        text, STEWARDSHIP_INIT_ANCHOR, STEWARDSHIP_INIT_NEW, label="stewardship init anchor"
    )
    return text, True
