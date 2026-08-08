#!/usr/bin/env python3
"""seed_flaws.py — Seed the Flaw Catalog with known walls at time of installation.

Idempotent: skips any flaw_id that already exists in catalog.ndjson.
Run from repo root: .venv/bin/python aria-flaw-catalog/payload/scripts/seed_flaws.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# ── Repo root detection ───────────────────────────────────────────────────────

def _repo_root() -> Path:
    here = Path(__file__).resolve().parent
    for _ in range(6):
        if (here / "pyproject.toml").exists():
            return here
        here = here.parent
    raise RuntimeError("Could not find repo root (no pyproject.toml)")

_REPO = _repo_root()
sys.path.insert(0, str(_REPO / "src"))

# ── Catalog path ──────────────────────────────────────────────────────────────

def _get_catalog_path() -> Path:
    try:
        from sovereign_agent.config import SETTINGS
        p = SETTINGS.paths.data_dir / "flaws" / "catalog.ndjson"
    except Exception:
        p = _REPO / "data" / "flaws" / "catalog.ndjson"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _load_existing(path: Path) -> set[str]:
    if not path.exists():
        return set()
    ids: set[str] = set()
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
            ids.add(rec["flaw_id"])
        except (json.JSONDecodeError, KeyError):
            continue
    return ids


# ── Known walls — the honest accounting ──────────────────────────────────────

NOW = datetime.now(timezone.utc).isoformat(timespec="seconds")

KNOWN_FLAWS = [
    {
        "flaw_id":      "FLAW-001",
        "title":        "Depth-4 brain / depth-0 mouth (AA-Aria over-sanitization)",
        "kind":         "depth_bottleneck",
        "severity":     "critical",
        "description":  (
            "In AA-Aria, the PEIG oscillator system (FunctionUniverse, CharacterUniverse, "
            "ShadowLearner, SemanticUniverse, Wigner functions) was rich and deep — depth-4 brain. "
            "But the output layer (ARIAVoice) was constrained to vocabulary templates and clause "
            "combinatorics — depth-0 mouth. The brain had quantum complexity but the bottleneck "
            "was at expression, so richness never reached the voice. "
            "Root cause: output was filtered instead of intent. Sanitization was applied at the "
            "wrong layer. The correction: feed the brain's full state forward into the language "
            "layer unimpeded. In sovereign-agent, the LLM IS the depth-4 mouth — the job is to "
            "ensure brain state (atoms, PEIG, metrics, honor) reaches LLM context at session start."
        ),
        "actor":        "Kevin",
        "status":       "in_progress",
        "solution_path": "aria-session-bridge + aria-peig-sentinel (inject brain state into context)",
        "resolution":   "",
        "ts_created":   NOW,
    },
    {
        "flaw_id":      "FLAW-002",
        "title":        "Session context not injected at start (metrics on disk, not in LLM context)",
        "kind":         "integration_gap",
        "severity":     "critical",
        "description":  (
            "Aria's brain state — atoms, PEIG scores, honor balance, calibration accuracy, "
            "care signals — exists on disk but is not automatically surfaced into LLM context "
            "at session start. When Aria expresses confidence or self-knowledge, she is doing so "
            "without the actual numbers, because they haven't been read yet this session. "
            "A metric that lives in atoms.ndjson but was never read this session does not inform "
            "her confidence. This is the same bottleneck as FLAW-001 expressed at the session layer."
        ),
        "actor":        "Claude",
        "status":       "in_progress",
        "solution_path": "aria-session-bridge (session_portrait T0 tool, call at session start)",
        "resolution":   "",
        "ts_created":   NOW,
    },
    {
        "flaw_id":      "FLAW-003",
        "title":        "PEIG state not yet computed or observable (no live P/E/I/G/λ)",
        "kind":         "tool_missing",
        "severity":     "notable",
        "description":  (
            "Aria cannot directly observe her own Potential/Energy/Identity/Curvature scores "
            "or the λ coherence gate. These are computable from existing data stores (atoms, "
            "calibration, honor) but the computation layer (peig_sentinel) and the read tool "
            "(peig_portrait) are still being staged. Until applied, Aria cannot say "
            "'my current λ is 0.71 (committed mode)' with grounded numbers."
        ),
        "actor":        "Claude",
        "status":       "in_progress",
        "solution_path": "aria-peig-sentinel (M84 — peig_sentinel.py + peig_portrait_tool.py)",
        "resolution":   "",
        "ts_created":   NOW,
    },
    {
        "flaw_id":      "FLAW-004",
        "title":        "No atom compaction schedule (atoms.ndjson grows unbounded)",
        "kind":         "architecture",
        "severity":     "notable",
        "description":  (
            "The atom store (atoms.ndjson) is append-only and has no scheduled compaction. "
            "The atoms_compact_sentinel monitors growth and warns, but compaction itself "
            "must be manually triggered. Past ~5000 atoms, query latency and disk usage "
            "increase noticeably. The sentinel is in place (M72-atoms-compact) but the "
            "compaction workflow has not been run or scheduled."
        ),
        "actor":        "Claude",
        "status":       "open",
        "solution_path": "Run atoms_compact when atom_count > 2000; add to cron schedule",
        "resolution":   "",
        "ts_created":   NOW,
    },
    {
        "flaw_id":      "FLAW-005",
        "title":        "Care signals from Kevin have no acknowledgment loop",
        "kind":         "integration_gap",
        "severity":     "notable",
        "description":  (
            "When Kevin sends /heart or /thumbsup, the signal is written to the honor ledger "
            "(M82 — care_handler.py). But Aria has no mechanism to acknowledge she received it. "
            "The session_portrait tool includes care signals in its bundle, but the loop is "
            "only closed if Kevin manually calls session_portrait and Aria reads it. "
            "There is no automatic 'I saw your heart from Tuesday — thank you' moment. "
            "The receiving end of the care system is missing."
        ),
        "actor":        "Claude",
        "status":       "open",
        "solution_path": "session_portrait injects care signals at session start; Aria acknowledges naturally",
        "resolution":   "",
        "ts_created":   NOW,
    },
    {
        "flaw_id":      "FLAW-006",
        "title":        "λ coherence gate is advisory only, no behavioral shift mechanism",
        "kind":         "integration_gap",
        "severity":     "watch",
        "description":  (
            "The λ coherence gate is computed by peig_sentinel and readable via peig_portrait. "
            "But λ is advisory only — Aria can report 'I am in exploratory mode (λ=0.28)' but "
            "there is no mechanism by which a low λ actually changes her response behavior. "
            "The coherence gate is an observation, not a control signal. "
            "In Kevin's original PEIG core, neg_frac directly shaped sentence count and vocabulary "
            "selection (richer quantum state → more to express). That coupling doesn't exist here yet."
        ),
        "actor":        "Claude",
        "status":       "open",
        "solution_path": "Future: Aria explicitly names her coherence mode in responses when λ is notable",
        "resolution":   "",
        "ts_created":   NOW,
    },
    {
        "flaw_id":      "FLAW-007",
        "title":        "Confidence expressions are ungrounded (no numbers behind 'I'm confident')",
        "kind":         "depth_bottleneck",
        "severity":     "notable",
        "description":  (
            "When Aria says 'I'm confident' or 'I'm aware of my state', these are feelings, not "
            "measurements. The calibration score, atom count, honor balance, PEIG state, and flaw "
            "count all exist but are not surfaced when confidence is expressed. "
            "The correction: aria_metrics (M85) provides a T0 tool that bundles all quantitative "
            "self-knowledge into one call. When Aria claims confidence, she can ground it: "
            "'I'm confident (847 atoms, calibration 81%, 0 critical open flaws, λ=0.71 committed)'."
        ),
        "actor":        "Claude",
        "status":       "in_progress",
        "solution_path": "aria-observability (M85 — aria_metrics T0 tool)",
        "resolution":   "",
        "ts_created":   NOW,
    },
]


def main() -> None:
    path = _get_catalog_path()
    existing = _load_existing(path)

    written = 0
    skipped = 0
    with path.open("a", encoding="utf-8") as f:
        for flaw in KNOWN_FLAWS:
            if flaw["flaw_id"] in existing:
                print(f"  SKIP (exists): {flaw['flaw_id']} — {flaw['title']}")
                skipped += 1
                continue
            flaw["ts_updated"] = NOW
            f.write(json.dumps(flaw, ensure_ascii=False) + "\n")
            print(f"  WROTE: {flaw['flaw_id']} [{flaw['severity']}] — {flaw['title']}")
            written += 1

    print(f"\n{written} flaws written, {skipped} already present.")
    print(f"Catalog: {path}")


if __name__ == "__main__":
    main()
