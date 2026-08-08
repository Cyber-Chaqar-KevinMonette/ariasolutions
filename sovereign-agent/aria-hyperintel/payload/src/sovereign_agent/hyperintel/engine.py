"""engine.py — the HyperIntel research faculty's core logic: a bounded
QUESTION -> SCAN -> CROSS -> AUDIT -> DISTILL loop.

Three prompting postures over one process, not three separate agents:
  Scout      (divergent)  — SCAN: gather what's available, bounded.
  Auditor    (skeptical)  — CROSS + AUDIT: only trust claims corroborated by
                             ≥2 independent sources; name what's uncertain.
  Synthesist (integrative) — DISTILL: compress into one report.

Deliberately NOT an autonomous, self-re-querying loop — that would violate the
"no unbounded recursive research" doctrine. This is a single bounded pass over a
FIXED, caller-supplied source list (max_sources caps how many are read). It never
fetches new sources on its own initiative; the caller (a human, or Aria under a
human-approved turn) decides what evidence goes in.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

_STOPWORDS = frozenset((
    "the", "a", "an", "is", "are", "was", "were", "and", "or", "of", "to", "in",
    "on", "for", "with", "that", "this", "it", "as", "at", "by", "be", "has", "have",
))


def _keywords(line: str) -> set[str]:
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", line.lower())
    return {w for w in words if w not in _STOPWORDS}


@dataclass
class Source:
    name: str
    text: str


@dataclass
class Claim:
    text: str
    source_names: list[str]

    @property
    def convergent(self) -> bool:
        return len(self.source_names) >= 2


@dataclass
class HyperIntelReport:
    question: str
    sources_scanned: list[str] = field(default_factory=list)
    convergent_claims: list[Claim] = field(default_factory=list)
    single_source_claims: list[Claim] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    distillation: str = ""

    def to_markdown(self) -> str:
        lines = [
            f"# HyperIntel report — {self.question}",
            "",
            "## Scan",
            f"{len(self.sources_scanned)} source(s): " + ", ".join(self.sources_scanned) or "(none)",
            "",
            "## Cross-Validation",
            f"{len(self.convergent_claims)} convergent claim(s) (≥2 independent sources):",
        ]
        for c in self.convergent_claims:
            lines.append(f"  - {c.text}  [{', '.join(c.source_names)}]")
        lines.append(f"{len(self.single_source_claims)} single-source claim(s) (low confidence):")
        for c in self.single_source_claims:
            lines.append(f"  - {c.text}  [{', '.join(c.source_names)}] — unverified")
        lines += ["", "## Audit"]
        lines += [f"  - {r}" for r in self.risks] or ["  (no risks flagged)"]
        lines += ["", "## Distillation", self.distillation]
        return "\n".join(lines)


def scan(source_paths: list[str], *, max_sources: int) -> list[Source]:
    """Read up to max_sources files. Bounded — never reads more than the cap,
    regardless of how many paths are given."""
    out: list[Source] = []
    for path_str in source_paths[:max_sources]:
        p = Path(path_str)
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        out.append(Source(name=p.name, text=text))
    return out


def cross_validate(sources: list[Source]) -> tuple[list[Claim], list[Claim]]:
    """A claim (one line) is convergent if a line with substantial keyword
    overlap appears in ≥2 different sources; otherwise it's single-source.
    A simple, honest heuristic — not NLU, but never silently promotes an
    unverified claim to 'trusted'."""
    lines_by_source: dict[str, list[str]] = {
        s.name: [ln.strip() for ln in s.text.splitlines() if ln.strip()] for s in sources
    }

    claims: dict[str, set[str]] = {}
    for name, lines in lines_by_source.items():
        for line in lines:
            kws = _keywords(line)
            if len(kws) < 2:
                continue
            matched = False
            for existing_text, existing_sources in list(claims.items()):
                if name in existing_sources:
                    continue
                overlap = kws & _keywords(existing_text)
                if len(overlap) >= max(2, len(kws) // 2):
                    claims[existing_text].add(name)
                    matched = True
                    break
            if not matched:
                claims[line] = {name}

    convergent = [Claim(text=t, source_names=sorted(s)) for t, s in claims.items() if len(s) >= 2]
    single = [Claim(text=t, source_names=sorted(s)) for t, s in claims.items() if len(s) == 1]
    return convergent, single


def audit(sources: list[Source], convergent: list[Claim], single: list[Claim]) -> list[str]:
    """Explicitly name risk/uncertainty. Never blocks — this is a report, not
    a gate; the human reads the risks and decides."""
    risks: list[str] = []
    if len(sources) < 2:
        risks.append(
            f"only {len(sources)} source(s) scanned — cross-validation is impossible "
            "with fewer than 2; all claims below are necessarily single-source."
        )
    if single and convergent and len(single) > len(convergent) * 3:
        risks.append(
            f"{len(single)} single-source claims vs {len(convergent)} convergent — "
            "the evidence base may be too shallow for confident conclusions."
        )
    if not sources:
        risks.append("no sources were readable — report is empty by necessity, not by finding.")
    return risks


def distill(question: str, convergent: list[Claim], single: list[Claim], risks: list[str]) -> str:
    """Compress to one paragraph: what's trustworthy, what's not, and the
    single clearest next step."""
    if not convergent and not single:
        return f"No evidence available to answer {question!r}. Provide source material first."
    parts = []
    if convergent:
        parts.append(f"{len(convergent)} claim(s) corroborated by independent sources")
    if single:
        parts.append(f"{len(single)} claim(s) from a single source (treat as hypothesis, not fact)")
    body = " and ".join(parts) + "."
    if risks:
        body += f" {len(risks)} risk(s)/uncertaint{'y' if len(risks) == 1 else 'ies'} noted above."
    return body


def run(question: str, source_paths: list[str], *, max_sources: int = 8) -> HyperIntelReport:
    """The full bounded QUESTION -> SCAN -> CROSS -> AUDIT -> DISTILL pass.
    Single pass, deterministic, always terminates — no re-querying, no
    autonomous source discovery."""
    sources = scan(source_paths, max_sources=max_sources)
    convergent, single = cross_validate(sources)
    risks = audit(sources, convergent, single)
    distillation = distill(question, convergent, single, risks)
    return HyperIntelReport(
        question=question,
        sources_scanned=[s.name for s in sources],
        convergent_claims=convergent,
        single_source_claims=single,
        risks=risks,
        distillation=distillation,
    )
