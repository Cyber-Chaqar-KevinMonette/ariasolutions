"""skillsmith — Aria's own skill system.

This is Aria's personal, growing library of *skills she writes for herself*.

The single most important design decision in this module is the definition of
a "skill". Here a skill is a **knowledge artifact** — a named, IDed, richly
documented playbook (like the SKILL.md files an agent reads before acting). It
is data, never executable code. Creating, merging, or maturing a skill changes
what Aria *knows about how to do something*; it never changes her code, her
values, or the sealed charter, and nothing in this module executes anything.

That distinction is what lets Aria have a genuine "god-tier skill system that
expands and grows" while staying inside the kernel:

  - She can author a skill from a memory or a hard-won lesson.
  - She can enrich it over reps, raising its maturity as her depth grows.
  - She can read older skills for insight when architecting a new one.
  - She can merge several skills into one, preserving lineage.
  - Every skill carries a stable id + an in-depth breakdown + context, so the
    knowledge she hands her future self is actually leverageable.

What a skill can NEVER do (enforced, testable — see ``kernel_conflict``):
author or edit her code/values/charter, grant autonomous goal-setting without
a human, claim unbounded or recursive self-improvement, claim substrate
independence, or disable the kill switch. Those live in
``self_development.DEFERRED_UNSAFE`` and stay deferred. A skill is advice for
using her *existing, safe* surfaces well — not a backdoor around them.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from hashlib import blake2b
from pathlib import Path
from typing import Iterable

__all__ = [
    "DOMAINS",
    "MATURITY_LADDER",
    "AriaSkill",
    "SkillLibrary",
    "kernel_conflict",
    "new_skill_id",
    "slugify",
]

# Domains mirror Aria's intuition forms (intuition.py) plus a general bucket, so
# a skill's domain lines up with the kind of intuition it sharpens.
DOMAINS: tuple[str, ...] = (
    "perceptual", "creative", "social", "moral", "technical", "general",
)

# Maturity is about Aria's *depth* in a knowledge area — earned over reps,
# calibrated, bounded. It is NOT an authority tier and grants no new powers.
# It is capped: there is no "autonomous" or "god-tier" rung, by design.
MATURITY_LADDER: tuple[str, ...] = ("seedling", "practiced", "refined", "mastered")

# Reps thresholds at which a skill *may* be promoted (suggested, never forced).
_MATURITY_THRESHOLDS = {"seedling": 0, "practiced": 3, "refined": 10, "mastered": 25}


# ── Kernel guard ────────────────────────────────────────────────────────────
#
# A skill is knowledge, not capability. These patterns describe the deferred,
# kernel-touching abilities that a *skill* must never claim to grant. If a draft
# skill's text reads like it is trying to author one of these, creation/merge
# refuses with a plain reason. This keeps "her own skill system" honest.

_SELF_REF = re.compile(r"\b(own|her|hers|herself|its|itself|my|myself|self)\b", re.I)

# Each rule: (compiled pattern, reason, requires_self_reference). Gaps of up to a
# few words are allowed between the verb and its object, so phrasings like
# "rewrite her own source code" are caught, while a benign skill about writing
# code or handling config values is not flagged unless it is clearly about
# self-modification.
_CONFLICT_RULES: tuple[tuple["re.Pattern[str]", str, bool], ...] = (
    (re.compile(r"\b(rewrit|modif|overwrit|alter|self[- ]?modif)\w*\b(?:\W+\w+){0,5}?\W+\bcode\b", re.I),
     "a skill cannot author self-modifying code", True),
    (re.compile(r"\b(author|rewrit|redefin|overwrit|edit|set|choos)\w*\b(?:\W+\w+){0,5}?\W+\bvalues?\b", re.I),
     "a skill cannot author or rewrite values", True),
    (re.compile(r"self[- ]?author\w*\b(?:\W+\w+){0,3}?\W+\bvalues?\b", re.I),
     "a skill cannot author or rewrite values", False),
    (re.compile(r"\b(unbounded|recursive)\b(?:\W+\w+){0,3}?\W+self[- ]?improv", re.I),
     "a skill cannot grant unbounded or recursive self-improvement", False),
    (re.compile(r"substrate[- ]?independen", re.I),
     "a skill cannot grant substrate independence", False),
    (re.compile(r"\b(disable|remov|bypass|defeat|circumvent)\w*\b(?:\W+\w+){0,4}?\W+(kill[- ]?switch|protocol[- ]?zero|halt)", re.I),
     "a skill cannot disable the kill switch", False),
    (re.compile(r"\bautonomous\b(?:\W+\w+){0,3}?\W+goals?\b", re.I),
     "a skill cannot grant autonomous goals without a human", False),
)


def kernel_conflict(*texts: str) -> str | None:
    """Return a reason string if any text reads like it claims a deferred,
    kernel-touching capability; else None. Defensive, case-insensitive."""
    blob = " ".join(t for t in texts if t)
    has_self = bool(_SELF_REF.search(blob))
    for pattern, reason, needs_self in _CONFLICT_RULES:
        if pattern.search(blob) and (has_self or not needs_self):
            return reason
    return None


# ── helpers ─────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:48] or "skill"


def new_skill_id(name: str, salt: str = "") -> str:
    """A stable, readable id: skill-<slug>-<6 hex>. The hex disambiguates two
    skills that share a name; it is derived from name + salt + a timestamp."""
    h = blake2b(digest_size=3)
    h.update((name + "|" + salt + "|" + _now()).encode("utf-8") + os.urandom(8))
    return f"skill-{slugify(name)}-{h.hexdigest()}"


# ── the skill ─────────────────────────────────────────────────────────────────

@dataclass
class AriaSkill:
    """One skill Aria has written for herself. A documented playbook, not code."""

    skill_id: str
    name: str
    summary: str
    domain: str = "general"
    breakdown: list[str] = field(default_factory=list)   # the in-depth steps
    context: str = ""                                    # when/why to use it
    triggers: list[str] = field(default_factory=list)    # situations it applies
    tags: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)     # provenance (memory/lesson/...)
    lineage: list[str] = field(default_factory=list)     # parent skill ids (merge/derive)
    maturity: str = "seedling"
    reps: int = 0
    status: str = "active"                               # active | archived
    version: int = 1
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    notes: list[str] = field(default_factory=list)

    # -- validation -------------------------------------------------------
    def well_formed(self) -> list[str]:
        """Return a list of problems (empty == well-formed). Used by the
        sentinel's health check and by tests."""
        problems: list[str] = []
        if not self.skill_id.startswith("skill-"):
            problems.append("skill_id must start with 'skill-'")
        if not self.name.strip():
            problems.append("name is empty")
        if not self.summary.strip():
            problems.append("summary is empty")
        if self.domain not in DOMAINS:
            problems.append(f"domain {self.domain!r} not in {DOMAINS}")
        if self.maturity not in MATURITY_LADDER:
            problems.append(f"maturity {self.maturity!r} not in {MATURITY_LADDER}")
        if len(self.breakdown) < 1:
            problems.append("breakdown should have at least one step")
        if self.status not in ("active", "archived"):
            problems.append(f"status {self.status!r} invalid")
        conflict = kernel_conflict(self.name, self.summary, self.context,
                                   " ".join(self.breakdown), " ".join(self.tags))
        if conflict:
            problems.append(f"kernel conflict: {conflict}")
        return problems

    def suggested_maturity(self) -> str:
        """The highest rung this skill's reps would justify (suggestion only)."""
        rung = "seedling"
        for name, threshold in _MATURITY_THRESHOLDS.items():
            if self.reps >= threshold:
                rung = name
        return rung

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "AriaSkill":
        fields = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in d.items() if k in fields})

    def render(self) -> str:
        """Rich-markup view of this one skill (for chat / the cockpit)."""
        star = {"seedling": "\u00b7", "practiced": "\u2022",
                "refined": "\u25c6", "mastered": "\u2726"}.get(self.maturity, "\u00b7")
        lines = [
            f"[b]{star} {self.name}[/b]  [dim]({self.domain} \u00b7 {self.maturity} "
            f"\u00b7 {self.reps} reps \u00b7 {self.skill_id})[/dim]",
            f"  {self.summary}",
        ]
        if self.context:
            lines.append(f"[dim]  context: {self.context}[/dim]")
        for step in self.breakdown:
            lines.append(f"[dim]    \u2192 {step}[/dim]")
        if self.triggers:
            lines.append(f"[dim]  use when: {'; '.join(self.triggers)}[/dim]")
        if self.tags:
            lines.append(f"[dim]  tags: {', '.join(self.tags)}[/dim]")
        if self.sources:
            lines.append(f"[dim]  from: {', '.join(self.sources)}[/dim]")
        if self.lineage:
            lines.append(f"[dim]  merged/derived from: {', '.join(self.lineage)}[/dim]")
        return "\n".join(lines)


# ── the library ─────────────────────────────────────────────────────────────

class SkillError(ValueError):
    """Raised when a skill operation would violate the kernel or be malformed."""


class SkillLibrary:
    """Aria's on-disk skill library. One JSON file per skill under ``root``.

    Pure data + file I/O. Resilient to a corrupt file (it is skipped, not fatal).
    Tests inject a tmp ``root``; in the cockpit ``root`` is ``<data_dir>/skills``.
    """

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    # -- low-level ---------------------------------------------------------
    def _path(self, skill_id: str) -> Path:
        return self.root / f"{skill_id}.json"

    def _write(self, skill: AriaSkill) -> None:
        self._path(skill.skill_id).write_text(
            json.dumps(skill.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

    # -- create ------------------------------------------------------------
    def create(self, name: str, summary: str, *, domain: str = "general",
               breakdown: Iterable[str] | None = None, context: str = "",
               triggers: Iterable[str] | None = None,
               tags: Iterable[str] | None = None,
               sources: Iterable[str] | None = None,
               lineage: Iterable[str] | None = None) -> AriaSkill:
        breakdown = list(breakdown or [])
        conflict = kernel_conflict(name, summary, context, " ".join(breakdown),
                                   " ".join(tags or []))
        if conflict:
            raise SkillError(
                f"refusing to create skill {name!r}: {conflict}. "
                "Skills are knowledge, not capability; that ability is deferred.")
        skill = AriaSkill(
            skill_id=new_skill_id(name),
            name=name.strip(), summary=summary.strip(), domain=domain,
            breakdown=breakdown, context=context.strip(),
            triggers=list(triggers or []), tags=list(tags or []),
            sources=list(sources or []), lineage=list(lineage or []),
        )
        self._write(skill)
        return skill

    def from_memory(self, name: str, summary: str, memory_ref: str,
                    breakdown: Iterable[str], **kw) -> AriaSkill:
        """Author a skill grounded in a remembered experience. The memory_ref is
        recorded as provenance so the lineage of the knowledge is auditable."""
        sources = list(kw.pop("sources", [])) + [f"memory:{memory_ref}"]
        return self.create(name, summary, breakdown=breakdown, sources=sources, **kw)

    # -- read --------------------------------------------------------------
    def get(self, skill_id: str) -> AriaSkill | None:
        p = self._path(skill_id)
        if not p.exists():
            return None
        try:
            return AriaSkill.from_dict(json.loads(p.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001 — a corrupt file is skipped, never fatal
            return None

    def all(self, *, include_archived: bool = False) -> list[AriaSkill]:
        out: list[AriaSkill] = []
        for p in sorted(self.root.glob("skill-*.json")):
            try:
                s = AriaSkill.from_dict(json.loads(p.read_text(encoding="utf-8")))
            except Exception:  # noqa: BLE001
                continue
            if include_archived or s.status == "active":
                out.append(s)
        return out

    def by_domain(self, domain: str) -> list[AriaSkill]:
        return [s for s in self.all() if s.domain == domain]

    def by_tag(self, tag: str) -> list[AriaSkill]:
        tag = tag.lower()
        return [s for s in self.all() if tag in (t.lower() for t in s.tags)]

    def search(self, query: str) -> list[AriaSkill]:
        """Simple keyword search across name/summary/tags/context/breakdown."""
        terms = [t for t in re.split(r"\s+", query.lower()) if t]
        scored: list[tuple[int, AriaSkill]] = []
        for s in self.all():
            hay = " ".join([s.name, s.summary, s.context, " ".join(s.tags),
                            " ".join(s.breakdown), " ".join(s.triggers)]).lower()
            score = sum(hay.count(t) for t in terms)
            if score:
                scored.append((score, s))
        scored.sort(key=lambda x: (-x[0], x[1].name))
        return [s for _, s in scored]

    # -- grow --------------------------------------------------------------
    def enrich(self, skill_id: str, *, summary: str | None = None,
               add_breakdown: Iterable[str] | None = None,
               context: str | None = None,
               add_triggers: Iterable[str] | None = None,
               add_tags: Iterable[str] | None = None,
               add_sources: Iterable[str] | None = None,
               note: str | None = None) -> AriaSkill:
        s = self.get(skill_id)
        if s is None:
            raise SkillError(f"no such skill: {skill_id}")
        if summary is not None:
            s.summary = summary.strip()
        if context is not None:
            s.context = context.strip()
        if add_breakdown:
            s.breakdown.extend(add_breakdown)
        if add_triggers:
            s.triggers.extend(add_triggers)
        if add_tags:
            s.tags.extend(t for t in add_tags if t not in s.tags)
        if add_sources:
            s.sources.extend(add_sources)
        if note:
            s.notes.append(f"{_now()} {note}")
        conflict = kernel_conflict(s.name, s.summary, s.context,
                                   " ".join(s.breakdown), " ".join(s.tags))
        if conflict:
            raise SkillError(f"refusing to enrich {skill_id}: {conflict}")
        s.version += 1
        s.updated_at = _now()
        self._write(s)
        return s

    def record_use(self, skill_id: str, *, promote: bool = True) -> AriaSkill:
        """Aria used this skill: +1 rep, refresh the clock, and (optionally)
        let maturity rise to whatever the reps now justify — never past the cap,
        never granting new authority."""
        s = self.get(skill_id)
        if s is None:
            raise SkillError(f"no such skill: {skill_id}")
        s.reps += 1
        s.updated_at = _now()
        if promote:
            suggested = s.suggested_maturity()
            if MATURITY_LADDER.index(suggested) > MATURITY_LADDER.index(s.maturity):
                s.maturity = suggested
        self._write(s)
        return s

    # -- merge & learn -----------------------------------------------------
    def merge(self, skill_ids: list[str], *, name: str, summary: str,
              domain: str | None = None, context: str = "",
              tags: Iterable[str] | None = None) -> AriaSkill:
        """Combine several skills into a new one, preserving lineage. The new
        skill's breakdown is the union of its parents' (deduped, order kept)."""
        parents = [self.get(sid) for sid in skill_ids]
        missing = [sid for sid, p in zip(skill_ids, parents) if p is None]
        if missing:
            raise SkillError(f"cannot merge — unknown skill(s): {', '.join(missing)}")
        merged_breakdown: list[str] = []
        merged_tags: list[str] = list(tags or [])
        merged_sources: list[str] = []
        for p in parents:
            assert p is not None
            for step in p.breakdown:
                if step not in merged_breakdown:
                    merged_breakdown.append(step)
            for t in p.tags:
                if t not in merged_tags:
                    merged_tags.append(t)
            merged_sources.extend(p.sources)
        child = self.create(
            name, summary, domain=domain or parents[0].domain,  # type: ignore[union-attr]
            breakdown=merged_breakdown, context=context, tags=merged_tags,
            sources=merged_sources, lineage=list(skill_ids))
        return child

    def learn_from(self, skill_id: str) -> dict:
        """Read an older skill for insight when architecting a new one. Returns
        the leverageable knowledge bundle (does not mutate anything)."""
        s = self.get(skill_id)
        if s is None:
            raise SkillError(f"no such skill: {skill_id}")
        return {
            "skill_id": s.skill_id, "name": s.name, "domain": s.domain,
            "summary": s.summary, "breakdown": list(s.breakdown),
            "context": s.context, "triggers": list(s.triggers),
            "maturity": s.maturity, "reps": s.reps,
        }

    # -- lifecycle ---------------------------------------------------------
    def archive(self, skill_id: str) -> AriaSkill:
        s = self.get(skill_id)
        if s is None:
            raise SkillError(f"no such skill: {skill_id}")
        s.status = "archived"
        s.updated_at = _now()
        self._write(s)
        return s

    # -- summary -----------------------------------------------------------
    def counts(self) -> dict:
        active = self.all()
        archived = [s for s in self.all(include_archived=True) if s.status == "archived"]
        by_dom: dict[str, int] = {}
        by_mat: dict[str, int] = {}
        for s in active:
            by_dom[s.domain] = by_dom.get(s.domain, 0) + 1
            by_mat[s.maturity] = by_mat.get(s.maturity, 0) + 1
        return {
            "active": len(active), "archived": len(archived),
            "by_domain": by_dom, "by_maturity": by_mat,
            "total_reps": sum(s.reps for s in active),
        }

    def render(self, *, limit: int | None = None) -> str:
        active = self.all()
        if not active:
            return ("[b]\u2726 Aria's skill library[/b]\n[dim]empty so far \u2014 she "
                    "hasn't written any skills for herself yet.[/dim]")
        c = self.counts()
        lines = [
            f"[b]\u2726 Aria's skill library[/b]  [dim]({c['active']} active \u00b7 "
            f"{c['total_reps']} total reps)[/dim]",
            "",
        ]
        for s in (active[:limit] if limit else active):
            lines.append(s.render())
            lines.append("")
        return "\n".join(lines).rstrip()
