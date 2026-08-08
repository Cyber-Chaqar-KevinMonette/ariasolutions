"""quality/review.py — pick real recent work, build a proposal dict.
(Quality round · Q3)

The Tribunal + Advocate Spectrum are rich but were only ever convened
ONE-SHOT, pre-apply, over a module's own README. `TribunalSentinel`
(the only standing use) re-checks a hardcoded safety string, never
Aria's actual completed work. This is the shared "what should a
STANDING audit look at" logic: the most recently applied module (newest
`.applied_ok`) or the most recently changed live file, plus its quality
score if one exists — feeding the SAME `{"text": ...}` shape `convene()`
and `convene_spectrum()` already accept, extended with the measured
`quality_score`/`hardening_critical_ok` keys the `artisan` lens now reads.
"""
from __future__ import annotations

from pathlib import Path


def _project_root(src_root: Path) -> Path | None:
    """Mirrors quality_sentinel.py's own walk-up-for-pyproject.toml —
    NOT `git rev-parse --show-toplevel`, which returns the wrong (outer)
    root in a nested checkout. Kept as a private, independent copy here
    rather than importing from stewardship (sentinels are the consumer of
    this module, not the other way around — no import cycle)."""
    cur = src_root.parent
    for _ in range(8):
        if (cur / "pyproject.toml").is_file():
            return cur
        cur = cur.parent
    return None


def _newest_applied_module(project_root: Path) -> tuple[str, Path] | None:
    """(module_slug, readme_path) for the most recently applied staged
    module, or None if none exist yet."""
    candidates = sorted(
        project_root.glob("aria-*/.applied_ok"),
        key=lambda p: p.stat().st_mtime, reverse=True,
    )
    if not candidates:
        return None
    mod_dir = candidates[0].parent
    return mod_dir.name, mod_dir / "README.md"


def build_review_proposal(data_dir: Path | None = None) -> dict | None:
    """The proposal dict for a standing quality-tribunal pass: the newest
    applied module's own README as `text`, plus its measured quality
    score (from Q1's ledger, if one was ever recorded) folded in as
    `quality_score`/`hardening_critical_ok` — real data, not just prose.
    None when there's nothing to review yet (fresh install)."""
    import sovereign_agent

    src_root = Path(sovereign_agent.__file__).parent
    project_root = _project_root(src_root)
    if project_root is None:
        return None
    found = _newest_applied_module(project_root)
    if found is None:
        return None
    slug, readme = found

    text = readme.read_text(encoding="utf-8", errors="ignore") if readme.exists() else f"module {slug}"
    proposal: dict = {"text": text, "change": slug}

    try:
        from sovereign_agent.quality import latest_quality

        latest = latest_quality(data_dir)
    except Exception:  # noqa: BLE001 — a review proposal without a score is still valid
        latest = None
    if latest:
        proposal["quality_score"] = latest.get("value", 0.0)
        proposal["hardening_critical_ok"] = latest.get("critical_ok", True)
    return proposal


__all__ = ["build_review_proposal"]
