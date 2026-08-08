"""
╔══════════════════════════════════════════════════════════════════════════╗
║  stewardship/glyph_sentinel.py — Aria measures, catalogs, and guards    ║
║                                  the glyphs in her own source tree.      ║
║                                                                           ║
║  The visual identity of the system has weight. Every glyph that ships    ║
║  in a banner, a panel header, or a doctor verdict must render to one     ║
║  cell on every terminal the operator might use. Get that wrong and the   ║
║  whole layout shifts — like the diamond bug Kevin caught from a          ║
║  screenshot, where ◈ (Unicode East-Asian-Width = Ambiguous) rendered as ║
║  two cells in his terminal and pulled every right-border one column      ║
║  left of where the layout code predicted.                                ║
║                                                                           ║
║  The sentinel runs the scan, persists a catalog of every non-ASCII       ║
║  glyph found, classifies each as SAFE / BORDERLINE / UNSAFE, and         ║
║  proposes replacements where unsafe glyphs leak into user-facing code.   ║
║                                                                           ║
║  Tier discipline (per the charter, Article VI):                          ║
║                                                                           ║
║    • Tier 1 only: the sentinel scans, catalogs, and writes proposals.   ║
║      It NEVER edits source files automatically.                          ║
║    • Operators see proposals and choose what to apply.                  ║
║    • All actions emit events to events.jsonl for the audit trail.       ║
║                                                                           ║
║  Storage:                                                                 ║
║                                                                           ║
║    Catalog persists at  <data_dir>/glyph_catalog.json                   ║
║    Updates emit         flag=glyph_catalog_update on events.jsonl       ║
║                                                                           ║
║  When the sentinel runs:                                                 ║
║                                                                           ║
║    • Operator-triggered:    sov glyphs scan                             ║
║    • Doctor consults the catalog:  sov doctor                           ║
║    • Future (v0.2.34+): post-PR-merge hook in CI / pre-release          ║
║                                                                           ║
║  Anti-patterns explicitly avoided:                                      ║
║                                                                           ║
║    × Don't propose changes to docstring comments (decorative; not       ║
║      rendered to terminals)                                              ║
║    × Don't propose for tests or glyphs.py itself (those contain         ║
║      unsafe glyphs on purpose to test/document them)                    ║
║    × Don't flag glyphs already proven de-facto-narrow in the operator's ║
║      installed terminals (the whitelist)                                ║
║    × Don't claim a replacement is "safe" without checking EAW         ║
╚══════════════════════════════════════════════════════════════════════════╝

Kill switch: SOV_NO_GLYPHS_SENTINEL=1 (honored via Sentinel.is_enabled() on the GlyphSentinel class; master: SOV_NO_SENTINELS=1). The module's free functions are not gated.
"""
from __future__ import annotations

import json
import re
import unicodedata
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from .. import glyphs as _g
from .base import HealthStatus, Sentinel, SentinelReport  # glyph-sentinel-migration-d
from .registry import register_sentinel  # glyph-sentinel-migration-d

# ─── Catalog data model ───────────────────────────────────────────────────

Classification = Literal["safe", "borderline", "unsafe"]

# Glyphs we've manually verified replace specific unsafe glyphs while
# preserving visual identity. When the sentinel finds an unsafe glyph
# from this map, it proposes the replacement. Empty proposal = "no
# automatic replacement; operator judgement needed."
KNOWN_REPLACEMENTS: dict[str, str] = {
    "\u25C8": "\u25CA",   # ◈ WHITE DIAMOND CONTAINING BLACK DIAMOND → ◊ LOZENGE
    "\u25C6": "\u25CA",   # ◆ BLACK DIAMOND → ◊ LOZENGE
    "\u25C7": "\u25CA",   # ◇ WHITE DIAMOND → ◊ LOZENGE
    "\u2666": "\u25CA",   # ♦ BLACK DIAMOND SUIT → ◊ LOZENGE
    "\u26D4": "[!]",      # ⛔ NO ENTRY → ASCII bracketed bang
    "\u26A0": "[!]",      # ⚠ WARNING SIGN → ASCII bracketed bang
    "\u2B50": "*",        # ⭐ WHITE MEDIUM STAR → asterisk
    "\u2705": _g.CHECK,   # ✅ WHITE HEAVY CHECK MARK → ✓ regular check
    "\u274C": _g.CROSS,   # ❌ CROSS MARK → ✗ regular ballot X
    "\U0001F39A": _g.LOZENGE,  # 🎚 LEVEL SLIDER → ◊ LOZENGE  # glyph-hardening-d
    "\u23F8": _g.CROSS,        # ⏸ PAUSE → ✗ CROSS
}

# Files we never propose changes to — they contain unsafe glyphs on purpose
PROTECTED_RELATIVE_PATHS = frozenset({
    "src/sovereign_agent/glyphs.py",
    "src/sovereign_agent/stewardship/glyph_sentinel.py",
    "tests/test_charter.py",
    "tests/test_glyph_sentinel.py",
})


@dataclass
class GlyphEntry:
    """One glyph in the catalog. Indexed by codepoint."""
    codepoint: str          # "U+25C8"
    char: str               # "◈"
    name: str               # "WHITE DIAMOND CONTAINING BLACK SMALL DIAMOND"
    east_asian_width: str   # "A", "N", "W", "F", "H", "Na"
    classification: Classification
    de_facto_narrow: bool   # True if on glyphs.audit_string whitelist
    proposed_replacement: str | None = None  # from KNOWN_REPLACEMENTS, if any
    appearances: dict[str, int] = field(default_factory=dict)
    # appearances: { "src/sovereign_agent/cli.py": 110, ... }

    @property
    def total_occurrences(self) -> int:
        return sum(self.appearances.values())


@dataclass
class GlyphCatalog:
    """The full catalog. Serializes to / from JSON."""
    generated_at: str
    source_root: str
    total_files_scanned: int
    glyphs: dict[str, GlyphEntry] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(
            {
                "generated_at": self.generated_at,
                "source_root": self.source_root,
                "total_files_scanned": self.total_files_scanned,
                "glyphs": {k: asdict(v) for k, v in self.glyphs.items()},
            },
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )

    @classmethod
    def from_json(cls, text: str) -> "GlyphCatalog":
        data = json.loads(text)
        cat = cls(
            generated_at=data["generated_at"],
            source_root=data["source_root"],
            total_files_scanned=data["total_files_scanned"],
        )
        for k, v in data.get("glyphs", {}).items():
            cat.glyphs[k] = GlyphEntry(**v)
        return cat

    # ── Summary metrics ─────────────────────────────────────────────────

    @property
    def safe_count(self) -> int:
        return sum(1 for g in self.glyphs.values() if g.classification == "safe")

    @property
    def borderline_count(self) -> int:
        return sum(1 for g in self.glyphs.values() if g.classification == "borderline")

    @property
    def unsafe_count(self) -> int:
        return sum(1 for g in self.glyphs.values() if g.classification == "unsafe")

    @property
    def replaceable_unsafe(self) -> list[GlyphEntry]:
        return [
            g for g in self.glyphs.values()
            if g.classification == "unsafe" and g.proposed_replacement
        ]


# ─── Scanner ──────────────────────────────────────────────────────────────


_GLYPH_RE = re.compile(r"[^\x00-\x7E]")  # any non-ASCII char (incl. extended)


def _classify(char: str, eaw: str) -> tuple[Classification, bool]:  # glyph-hardening-d
    """Decide a glyph's status given its East Asian Width property.

    Returns (classification, de_facto_narrow).

    Rules:
      eaw in {N, Na, H}    → safe, UNLESS is_emoji_risk() flags it → unsafe
                               (EAW alone misses missing-font-coverage bugs
                               like \U0001F39A/\u23f8 -- both EAW=Neutral,
                               both rendered as tofu on Kevin's terminal;
                               see glyphs.py's is_emoji_risk() docstring)
      eaw in {W, F}        → unsafe      (Unicode says wide; no exceptions)
      eaw == A             → depends on the de-facto-narrow whitelist:
                               in whitelist → borderline (works in practice)
                               not in whitelist → unsafe (real risk)
    """
    if eaw in ("N", "Na", "H"):
        if _g.is_emoji_risk(char):
            return ("unsafe", False)
        return ("safe", False)
    if eaw in ("W", "F"):
        return ("unsafe", False)
    # eaw == "A"
    on_whitelist = not _g.audit_string(char)
    if on_whitelist:
        return ("borderline", True)
    return ("unsafe", False)


def find_source_root() -> Path:
    """Walk up from this module to find the source tree root (where SIGNAL.md sits)."""
    here = Path(__file__).resolve()
    for parent in [here, *here.parents]:
        if (parent / "SIGNAL.md").is_file() or (parent / "pyproject.toml").is_file():
            # The src/sovereign_agent/stewardship/ → src/sovereign_agent/ → src/ → ROOT
            if (parent / "pyproject.toml").is_file():
                return parent
    return Path(__file__).parent.parent.parent.parent  # fallback


def scan_source_tree(source_root: Path | None = None) -> GlyphCatalog:
    """Walk the source tree, catalog every non-ASCII glyph, return the result.

    File-type filter: .py / .md / .sh / .tcss / .css / .toml — anything that
    might end up rendered or shipped.

    Excludes: .venv, __pycache__, docs/history, Archive, dist, build.
    """
    if source_root is None:
        source_root = find_source_root()
    source_root = source_root.resolve()

    catalog = GlyphCatalog(
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        source_root=str(source_root),
        total_files_scanned=0,
    )

    EXTENSIONS = {".py", ".md", ".sh", ".tcss", ".css", ".toml"}
    EXCLUDE_DIRS = {".venv", "venv", "__pycache__", "Archive", "dist", "build",
                    ".git", "node_modules", "history"}

    counts_per_glyph: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for path in source_root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix not in EXTENSIONS:
            continue
        if any(part in EXCLUDE_DIRS for part in path.parts):
            continue

        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        catalog.total_files_scanned += 1
        rel = str(path.relative_to(source_root))

        for ch in _GLYPH_RE.findall(text):
            counts_per_glyph[ch][rel] += 1

    # Build GlyphEntry records
    for ch, file_counts in counts_per_glyph.items():
        codepoint = f"U+{ord(ch):04X}"
        try:
            name = unicodedata.name(ch)
        except ValueError:
            name = "<unnamed>"
        eaw = unicodedata.east_asian_width(ch)
        classification, de_facto_narrow = _classify(ch, eaw)
        catalog.glyphs[codepoint] = GlyphEntry(
            codepoint=codepoint,
            char=ch,
            name=name,
            east_asian_width=eaw,
            classification=classification,
            de_facto_narrow=de_facto_narrow,
            proposed_replacement=KNOWN_REPLACEMENTS.get(ch),
            appearances=dict(file_counts),
        )

    return catalog


# ─── Persistence ──────────────────────────────────────────────────────────


def catalog_path(data_dir: Path) -> Path:
    return data_dir / "glyph_catalog.json"


def load_catalog(data_dir: Path) -> GlyphCatalog | None:
    p = catalog_path(data_dir)
    if not p.is_file():
        return None
    try:
        return GlyphCatalog.from_json(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        return None


def save_catalog(catalog: GlyphCatalog, data_dir: Path) -> Path:
    p = catalog_path(data_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(catalog.to_json(), encoding="utf-8")
    return p


# ─── Proposals ────────────────────────────────────────────────────────────


@dataclass
class ReplacementProposal:
    """One actionable proposal: 'in <file>, consider replacing <unsafe> with <safe>'."""
    codepoint: str
    char: str
    proposed_replacement: str
    file_path: str
    occurrences: int


def generate_proposals(catalog: GlyphCatalog) -> list[ReplacementProposal]:
    """Walk the unsafe-with-known-replacement glyphs and emit per-file proposals.

    Skips files in PROTECTED_RELATIVE_PATHS — those contain unsafe glyphs on
    purpose (docs / tests of the bug class itself).

    Also skips comment-only appearances when we can — but file-level
    granularity is enough for the first pass; operator inspects context
    before applying.
    """
    proposals: list[ReplacementProposal] = []
    for entry in catalog.replaceable_unsafe:
        for file_path, count in entry.appearances.items():
            if file_path in PROTECTED_RELATIVE_PATHS:
                continue
            proposals.append(ReplacementProposal(
                codepoint=entry.codepoint,
                char=entry.char,
                proposed_replacement=entry.proposed_replacement or "",
                file_path=file_path,
                occurrences=count,
            ))
    return proposals


# ─── Gap detection: where could we do better ─────────────────────────────


@dataclass
class CoverageGap:
    """A semantic role that has no safe glyph alias yet.

    For example: if the codebase uses ⭐ in 3 places to mean 'starred /
    prioritized', and ⭐ is unsafe but has no replacement in
    KNOWN_REPLACEMENTS, that's a gap — we should pick a safe alias for
    'starred' and add it to glyphs.py.
    """
    char: str
    codepoint: str
    name: str
    occurrences: int
    files: list[str]
    note: str  # human-readable suggestion


def detect_coverage_gaps(catalog: GlyphCatalog) -> list[CoverageGap]:
    """Find unsafe glyphs that DON'T have a known replacement.

    These are the genuine gaps: glyphs the operator clearly wants for
    visual identity, but for which the system has no safe alternative
    registered. The right action is to pick a safe glyph, add it to
    glyphs.py's brand-marker section, and add the mapping to
    KNOWN_REPLACEMENTS — so future scans propose it automatically.
    """
    gaps: list[CoverageGap] = []
    for entry in catalog.glyphs.values():
        if entry.classification != "unsafe":
            continue
        if entry.proposed_replacement:
            continue
        # Skip glyphs that only appear in protected files
        non_protected = {f: c for f, c in entry.appearances.items()
                         if f not in PROTECTED_RELATIVE_PATHS}
        if not non_protected:
            continue
        gaps.append(CoverageGap(
            char=entry.char,
            codepoint=entry.codepoint,
            name=entry.name,
            occurrences=sum(non_protected.values()),
            files=sorted(non_protected.keys()),
            note=(
                f"used in {len(non_protected)} file(s); "
                "no safe alias registered. Consider adding one to "
                "glyphs.KNOWN_REPLACEMENTS so future scans propose it."
            ),
        ))
    return sorted(gaps, key=lambda g: -g.occurrences)


# ─── Public API ──────────────────────────────────────────────────────────


# ─── The Sentinel ──────────────────────────────────────────────────────── glyph-sentinel-migration-d


@register_sentinel
class GlyphSentinel(Sentinel):  # glyph-sentinel-migration-d
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


__all__ = [
    "Classification",
    "GlyphEntry",
    "GlyphCatalog",
    "ReplacementProposal",
    "CoverageGap",
    "KNOWN_REPLACEMENTS",
    "PROTECTED_RELATIVE_PATHS",
    "scan_source_tree",
    "find_source_root",
    "load_catalog",
    "save_catalog",
    "catalog_path",
    "generate_proposals",
    "detect_coverage_gaps",
]
