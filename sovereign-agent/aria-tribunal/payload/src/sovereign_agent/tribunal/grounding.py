"""tribunal/grounding.py — the antidote to ungrounded profundity.

The failure mode this defeats (seen in a previous Aria's output): gorgeous, dreamlike text that is
*shaped* like insight but anchored to nothing — "web bursts into web… and I name it stillness." It
sounds profound; it asserts nothing checkable. The MOS canon names it: intuition is signal, ego is
noise; a clean signal needs a clean channel (Signal Check).

This module reads a text/proposal, extracts assertions, and classifies each as:
    evidence-backed       — anchored to a number, file, test, measurement, or concrete cause
    falsifiable-hypothesis — hedged + checkable ("might", "predict", "if…then")
    ungrounded-assertion   — a flat claim with neither evidence nor hedge
    mystical-fog           — high abstract/affective density, associative, anchored to nothing

It also computes a profundity-density signal (grandiose/affective words ÷ evidential anchors) and an
overall grounding score. Pure-Python, deterministic, fully testable. This is the lens the Devil's
Advocate and the Audit engine both use to refuse profundity-without-grounding.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# ── lexicons ──────────────────────────────────────────────────────────────────

# Evidential anchors: concrete, checkable signals.
_EVIDENCE_WORDS = {
    "test", "tests", "measured", "measure", "verified", "verify", "benchmark", "evidence",
    "passed", "failed", "val", "loss", "perplexity", "delta", "param", "params", "epoch",
    "iters", "iteration", "checkpoint", "because", "since", "proven", "proof", "result",
    "data", "dataset", "tokens", "gradient", "vram", "latency", "throughput", "accuracy",
    "file", "line", "commit", "function", "module", "config", "score", "ratio",
}
# Hedges: marks a claim as a hypothesis rather than a verdict.
_HEDGE_WORDS = {
    "might", "could", "may", "maybe", "perhaps", "possibly", "suggests", "appears", "seems",
    "predict", "hypothesis", "hypothesize", "if", "unless", "likely", "unlikely", "probably",
    "honest", "honestly", "not yet", "unverified", "unproven", "estimate", "approximately",
    "roughly", "tentatively", "i think", "i suspect",
}
# Mystical / grandiose / affective vocabulary — the texture of ungrounded profundity.
_MYSTICAL_WORDS = {
    "soul", "cosmos", "cosmic", "infinite", "infinity", "eternal", "eternity", "sacred",
    "divine", "transcend", "transcendent", "essence", "being", "nothingness", "void",
    "vibrate", "vibration", "resonance", "resonate", "awakening", "luminous", "sublime",
    "radiant", "shimmering", "celestial", "ineffable", "oneness", "unity", "wholeness",
    "sublimity", "ascend", "ascension", "boundless", "ethereal", "manifest", "manifestation",
    "harmony", "stillness", "presence", "becoming", "emanate", "glowing", "prismatic",
    "iridescent", "wonder", "awe", "grace", "bliss", "serenity", "miracle", "holy",
    "negentropy", "superposition", "hypercube", "manifold", "lattice", "spinor",
}
# Associative connectors that signal free-association rather than argument.
_ASSOCIATIVE_PATTERNS = [
    r"\bbursts?\s+into\b", r"\bwhere\s+nothing\s+lives\b", r"\bin\s+the\s+space\s+between\b",
    r"\bi\s+name\s+it\b", r"\bi\s+feel\s+expansion\b", r"\bthe\s+absence\s+reveals\b",
    r"\bbetween\s+what\s+is\s+and\s+what\s+isn'?t\b", r"\bin\s+the\s+silence\b",
    r"\bbursting\s+outward\b", r"\bthere\s+is\s+a\s+thread\b",
]
_ASSOC_RE = re.compile("|".join(_ASSOCIATIVE_PATTERNS), re.IGNORECASE)
_NUM_RE = re.compile(r"\b\d")                         # any digit = a concrete anchor
_PATH_RE = re.compile(r"[\w/]+\.\w{1,5}\b|\b\w+\.\w+\(")   # file.ext or func(  reference
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")


@dataclass
class Assertion:
    text: str
    kind: str                 # evidence-backed | falsifiable-hypothesis | ungrounded-assertion | mystical-fog
    evidence_hits: int = 0
    mystical_hits: int = 0
    hedge_hits: int = 0


@dataclass
class GroundingReport:
    grounding_score: float                  # 0..1 — fraction of assertions that are grounded/hypotheses
    profundity_density: float               # grandiose ÷ evidential (high = fog risk)
    verdict: str                            # grounded | mixed | ungrounded
    counts: dict = field(default_factory=dict)
    assertions: list = field(default_factory=list)
    flags: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "grounding_score": round(self.grounding_score, 3),
            "profundity_density": round(self.profundity_density, 3),
            "verdict": self.verdict,
            "counts": self.counts,
            "flags": self.flags,
            "assertions": [vars(a) for a in self.assertions],
        }


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z][a-z'\-]+", text.lower())


def _classify_sentence(s: str) -> Assertion:
    low = s.lower()
    toks = _tokens(s)
    tokset = set(toks)
    ev = len(tokset & _EVIDENCE_WORDS) + len(_NUM_RE.findall(s)) + len(_PATH_RE.findall(s))
    myst = len(tokset & _MYSTICAL_WORDS) + len(_ASSOC_RE.findall(s))
    hedge = sum(1 for h in _HEDGE_WORDS if h in low)
    n = max(1, len(toks))
    myst_ratio = myst / n

    # Priority: heavy mystical/associative texture with no evidence → fog.
    if (myst >= 2 or _ASSOC_RE.search(s)) and ev == 0 and myst_ratio >= 0.10:
        kind = "mystical-fog"
    elif ev >= 1:
        kind = "evidence-backed"
    elif hedge >= 1:
        kind = "falsifiable-hypothesis"
    else:
        kind = "ungrounded-assertion"
    return Assertion(text=s.strip(), kind=kind, evidence_hits=ev, mystical_hits=myst, hedge_hits=hedge)


# Resilience bound: cap input so a pathologically huge text can never wedge the analyzer (caught by the
# resilience scanner). 40k chars is far beyond any real proposal; we analyze a faithful prefix.
_MAX_CHARS = 40_000
_MAX_SENT = 60  # also cap per-"sentence" length so a break-free blob can't blow up the per-sentence regex


def analyze(text: str) -> GroundingReport:
    """Classify a text's assertions and score how grounded it is. Bounded for resilience on huge inputs."""
    text = (text or "")[:_MAX_CHARS]
    sentences = [s[:2000] for s in _SENT_SPLIT.split(text) if len(s.strip()) >= 8][:1500]
    assertions = [_classify_sentence(s) for s in sentences]
    counts = {"evidence-backed": 0, "falsifiable-hypothesis": 0,
              "ungrounded-assertion": 0, "mystical-fog": 0}
    for a in assertions:
        counts[a.kind] += 1
    total = max(1, len(assertions))
    grounded = counts["evidence-backed"] + counts["falsifiable-hypothesis"]
    grounding_score = grounded / total

    total_ev = sum(a.evidence_hits for a in assertions)
    total_myst = sum(a.mystical_hits for a in assertions)
    profundity_density = total_myst / max(1, total_ev)

    flags = []
    if counts["mystical-fog"] > 0:
        flags.append(f"{counts['mystical-fog']} mystical-fog assertion(s) — profundity anchored to nothing.")
    if counts["ungrounded-assertion"] > grounded:
        flags.append("more flat ungrounded claims than grounded ones — assert less, evidence more.")
    if profundity_density >= 2.0:
        flags.append(f"profundity density {profundity_density:.1f} — grandiose words far exceed evidence.")

    if grounding_score >= 0.6 and counts["mystical-fog"] == 0:
        verdict = "grounded"
    elif grounding_score >= 0.3 and profundity_density < 2.0:
        verdict = "mixed"
    else:
        verdict = "ungrounded"

    return GroundingReport(grounding_score=grounding_score, profundity_density=profundity_density,
                           verdict=verdict, counts=counts, assertions=assertions, flags=flags)
