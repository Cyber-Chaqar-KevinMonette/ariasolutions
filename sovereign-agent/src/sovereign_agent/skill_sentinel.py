"""skill_sentinel — a steward for Aria's skill library.

Kevin's brief, honored literally: the Sentinel does NOT block Aria from her
skills. It keeps them *managed* — organized, clean, and up to date — so that
when she wants a capability she can ask the Sentinel for the ids and context of
whatever skill sets fit, and get back exactly what she needs to leverage them.
She can always bypass the Sentinel and hit the library directly; working *with*
it just gives her more leverage and offloads the curation work.

So the Sentinel is a pure, read-only assistant over a ``SkillLibrary``:

  - find(query)        → ranked matches with a short "why", plus their ids
  - context_for(id)    → the full leverageable bundle for one skill
  - brief(query)       → "here are the skills + ids + context for X", ready to use
  - duplicates()       → near-duplicate clusters she might want to merge (clean)
  - suggest_merges()   → concrete merge candidates (offloads curation)
  - stale(days)        → skills she hasn't touched in a while (up to date)
  - malformed()        → skills failing well_formed (clean)
  - health()           → one report dict tying it all together

The contract that keeps it safe and faithful: **no method here mutates the
library or gates access.** It only reads, ranks, and advises.

Kill switch: none — predates the unified Sentinel registry; invoked directly by its callers, NOT gated by SOV_NO_SENTINELS or any per-sentinel SOV_NO_* env var.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher

from .skillsmith import AriaSkill, SkillLibrary

__all__ = ["SkillSentinel", "Match", "MergeCandidate"]


@dataclass
class Match:
    skill_id: str
    name: str
    domain: str
    maturity: str
    why: str

    def to_dict(self) -> dict:
        return {"skill_id": self.skill_id, "name": self.name,
                "domain": self.domain, "maturity": self.maturity, "why": self.why}


@dataclass
class MergeCandidate:
    skill_ids: list[str]
    names: list[str]
    similarity: float
    reason: str

    def to_dict(self) -> dict:
        return {"skill_ids": self.skill_ids, "names": self.names,
                "similarity": round(self.similarity, 3), "reason": self.reason}


def _age_days(iso_ts: str) -> float:
    try:
        then = datetime.fromisoformat(iso_ts)
    except ValueError:
        return 0.0
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - then).total_seconds() / 86400.0


def _similarity(a: AriaSkill, b: AriaSkill) -> float:
    """Cheap textual similarity over name+summary+tags. 0..1."""
    sa = " ".join([a.name, a.summary, " ".join(sorted(a.tags))]).lower()
    sb = " ".join([b.name, b.summary, " ".join(sorted(b.tags))]).lower()
    base = SequenceMatcher(None, sa, sb).ratio()
    shared = set(t.lower() for t in a.tags) & set(t.lower() for t in b.tags)
    return min(1.0, base + 0.1 * len(shared))


class SkillSentinel:
    """Read-only steward over a ``SkillLibrary``. Assists; never blocks."""

    def __init__(self, library: SkillLibrary):
        self.library = library

    # -- find / context (the core service Kevin described) -----------------
    def find(self, query: str, *, limit: int = 5) -> list[Match]:
        """Rank the library against a request and explain each hit briefly."""
        hits = self.library.search(query)[:limit]
        out: list[Match] = []
        for s in hits:
            why = f"{s.maturity} \u00b7 {s.reps} reps"
            if s.tags:
                why += f" \u00b7 tags: {', '.join(s.tags[:4])}"
            out.append(Match(s.skill_id, s.name, s.domain, s.maturity, why))
        return out

    def context_for(self, skill_id: str) -> dict | None:
        """The full leverageable bundle for one skill (ids + everything she
        needs to use the knowledge). Read-only."""
        s = self.library.get(skill_id)
        if s is None:
            return None
        return {
            "skill_id": s.skill_id, "name": s.name, "domain": s.domain,
            "maturity": s.maturity, "reps": s.reps, "summary": s.summary,
            "context": s.context, "breakdown": list(s.breakdown),
            "triggers": list(s.triggers), "tags": list(s.tags),
            "sources": list(s.sources), "lineage": list(s.lineage),
        }

    def brief(self, query: str, *, limit: int = 5) -> str:
        """'Here are the skills + ids + context for X' — ready to act on."""
        matches = self.find(query, limit=limit)
        if not matches:
            return (f"[dim]Sentinel: no skills yet for {query!r}. "
                    f"This looks like a good one for Aria to author.[/dim]")
        lines = [f"[b]Sentinel \u2014 skills for {query!r}[/b]"]
        for m in matches:
            lines.append(f"  [b]{m.name}[/b]  [dim]{m.skill_id} \u00b7 {m.why}[/dim]")
            ctx = self.context_for(m.skill_id) or {}
            if ctx.get("context"):
                lines.append(f"[dim]    {ctx['context']}[/dim]")
        lines.append("[dim]  (ask for context_for(<id>) to get the full breakdown; "
                     "you can also bypass me and read the library directly.)[/dim]")
        return "\n".join(lines)

    # -- keep clean --------------------------------------------------------
    def duplicates(self, *, threshold: float = 0.72) -> list[MergeCandidate]:
        skills = self.library.all()
        out: list[MergeCandidate] = []
        for i in range(len(skills)):
            for j in range(i + 1, len(skills)):
                sim = _similarity(skills[i], skills[j])
                if sim >= threshold:
                    out.append(MergeCandidate(
                        [skills[i].skill_id, skills[j].skill_id],
                        [skills[i].name, skills[j].name], sim,
                        "high textual overlap \u2014 candidate to merge"))
        out.sort(key=lambda c: -c.similarity)
        return out

    def suggest_merges(self, *, threshold: float = 0.72) -> list[MergeCandidate]:
        """Concrete merge suggestions (same data as duplicates; named for intent)."""
        return self.duplicates(threshold=threshold)

    def malformed(self) -> list[Match]:
        out: list[Match] = []
        for s in self.library.all(include_archived=True):
            problems = s.well_formed()
            if problems:
                out.append(Match(s.skill_id, s.name, s.domain, s.maturity,
                                 "; ".join(problems)))
        return out

    # -- keep up to date ---------------------------------------------------
    def stale(self, *, days: float = 60.0) -> list[Match]:
        out: list[Match] = []
        for s in self.library.all():
            age = _age_days(s.updated_at)
            if age >= days:
                out.append(Match(s.skill_id, s.name, s.domain, s.maturity,
                                 f"untouched {age:.0f} days"))
        out.sort(key=lambda m: m.name)
        return out

    # -- one report --------------------------------------------------------
    def health(self, *, stale_days: float = 60.0,
               dup_threshold: float = 0.72) -> dict:
        counts = self.library.counts()
        dupes = self.suggest_merges(threshold=dup_threshold)
        return {
            "counts": counts,
            "stale": [m.to_dict() for m in self.stale(days=stale_days)],
            "duplicate_clusters": [c.to_dict() for c in dupes],
            "malformed": [m.to_dict() for m in self.malformed()],
            "tidy": not dupes and not self.malformed(),
        }

    def tidy_report(self, **kw) -> str:
        h = self.health(**kw)
        c = h["counts"]
        lines = [
            f"[b]Sentinel \u2014 skill-library health[/b]",
            f"[dim]  {c['active']} active \u00b7 {c['archived']} archived \u00b7 "
            f"{c['total_reps']} total reps[/dim]",
        ]
        if h["stale"]:
            lines.append(f"  stale ({len(h['stale'])}): "
                         + ", ".join(m["name"] for m in h["stale"][:6]))
        if h["duplicate_clusters"]:
            lines.append(f"  merge candidates ({len(h['duplicate_clusters'])}): "
                         + "; ".join("+".join(c["names"]) for c in h["duplicate_clusters"][:4]))
        if h["malformed"]:
            lines.append(f"  [yellow]malformed ({len(h['malformed'])})[/yellow]: "
                         + ", ".join(m["name"] for m in h["malformed"][:6]))
        if h["tidy"]:
            lines.append("[dim]  library is tidy \u2014 nothing to clean up.[/dim]")
        return "\n".join(lines)
