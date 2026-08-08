"""engineering_playbook.py — an index over the wondelai/skills software-engineering
skills (Clean Code, Refactoring Patterns, DDIA, System Design, etc.), deterministic
and keyword-routed like business_playbook.py / consumer_law_companion.py.

This is deliberately an INDEX, not a reproduction: each entry carries the skill's own
"Core Principle" sentence and its numbered discipline list (both taken verbatim from the
skill's SKILL.md frontmatter/body, MIT licensed, github.com/wondelai/skills), plus the
skill's slug so a caller can go get full depth. It does not duplicate the multi-page body
of each skill (worked examples, code tables, scoring rubrics) — that content lives in the
actual skill, installed as the wondelai-skills marketplace's code-craftsmanship and
systems-architecture plugin bundles (see ~/.claude/settings.json). Invoke it directly via
`Skill wondelai-skills:<slug>` for the full framework; this module exists so Aria can
recall and cite the right framework by name without a human having invoked it first.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


__all__ = ["Principle", "SOURCE_REPO", "PRINCIPLES", "CATEGORIES", "find_principles"]

SOURCE_REPO = "wondelai/skills (MIT) — github.com/wondelai/skills"


@dataclass(frozen=True)
class Principle:
    name: str
    category: str
    skill_slug: str
    core_principle: str
    disciplines: tuple[str, ...]
    keywords: tuple[str, ...]

    @property
    def source(self) -> str:
        return (f"Source: {SOURCE_REPO}, '{self.skill_slug}' skill. This is an index, not the "
                f"full framework — for full depth, invoke Skill wondelai-skills:{self.skill_slug}.")


PRINCIPLES: tuple[Principle, ...] = (
    Principle(
        name="Clean Code",
        category="code-craftsmanship",
        skill_slug="clean-code",
        core_principle="Code is read far more often than it is written — optimize for the reader.",
        disciplines=("Meaningful Names", "Functions", "Comments and Formatting", "Error Handling",
                     "Unit Testing", "Code Smells and Heuristics"),
        keywords=("clean code", "naming", "readability", "code smell", "single responsibility",
                  "boy scout rule"),
    ),
    Principle(
        name="Refactoring Patterns",
        category="code-craftsmanship",
        skill_slug="refactoring-patterns",
        core_principle=("Refactoring is not rewriting. It is a sequence of small, "
                        "behavior-preserving transformations, each backed by tests."),
        disciplines=("Code Smells as Triggers", "Composing Methods", "Moving Features Between Objects",
                     "Organizing Data", "Simplifying Conditional Logic", "Safe Refactoring Workflow"),
        keywords=("refactor", "refactoring", "extract method", "technical debt", "move method"),
    ),
    Principle(
        name="A Philosophy of Software Design",
        category="code-craftsmanship",
        skill_slug="software-design-philosophy",
        core_principle=("The greatest limitation in writing software is our ability to understand "
                        "the systems we are creating — minimize unnecessary complexity and "
                        "concentrate the necessary kind where it can be managed."),
        disciplines=("Complexity and Its Causes", "Deep vs Shallow Modules",
                     "Information Hiding and Leakage", "General-Purpose vs Special-Purpose Modules",
                     "Comments as Design Documentation", "Strategic vs Tactical Programming"),
        keywords=("module design", "deep module", "shallow module", "complexity", "information leakage",
                  "over-engineered"),
    ),
    Principle(
        name="The Pragmatic Programmer",
        category="code-craftsmanship",
        skill_slug="pragmatic-programmer",
        core_principle=("Care about your craft: avoid duplication ruthlessly, keep components "
                        "orthogonal, and treat every line of code as a living asset that must "
                        "earn its place."),
        disciplines=("DRY (Don't Repeat Yourself)", "Orthogonality", "Tracer Bullets and Prototypes",
                     "Design by Contract and Assertive Programming", "The Broken Window Theory",
                     "Reversibility and Flexibility", "Estimation and Knowledge Portfolio"),
        keywords=("dry", "orthogonality", "tracer bullet", "broken windows", "pragmatic",
                  "best practices"),
    ),
    Principle(
        name="Domain-Driven Design",
        category="code-craftsmanship",
        skill_slug="domain-driven-design",
        core_principle=("The model is the code; the code is the model — software should embody a "
                        "deep, shared understanding of the business domain."),
        disciplines=("Ubiquitous Language", "Bounded Contexts and Context Mapping",
                     "Entities, Value Objects, and Aggregates", "Domain Events",
                     "Repositories and Factories", "Strategic Design and Distillation"),
        keywords=("ddd", "domain driven design", "bounded context", "aggregate root",
                  "ubiquitous language", "anti-corruption layer"),
    ),
    Principle(
        name="Working Effectively with Legacy Code",
        category="code-craftsmanship",
        skill_slug="working-with-legacy-code",
        core_principle=("Legacy code is simply code without tests — the craft is breaking "
                        "dependencies just enough to get tests in place before changing anything: "
                        "cover and modify, never edit and pray."),
        disciplines=("The Legacy Code Dilemma and Change Algorithm", "Seams: Where to Pry Code Apart",
                     "Characterization Tests", "Sprout and Wrap", "Dependency-Breaking Techniques",
                     "Untangling and Understanding"),
        keywords=("legacy code", "untested code", "characterization test", "seams", "sprout method",
                  "afraid to change this code"),
    ),
    Principle(
        name="Designing Data-Intensive Applications",
        category="systems-architecture",
        skill_slug="ddia-systems",
        core_principle=("Data outlives code — prioritize the long-term correctness, durability, and "
                        "evolvability of the data layer."),
        disciplines=("Data Models and Query Languages", "Storage Engines", "Replication",
                     "Partitioning", "Transactions and Consistency", "Batch and Stream Processing",
                     "Reliability and Fault Tolerance"),
        keywords=("database choice", "replication lag", "partitioning strategy", "consistency",
                  "eventual consistency", "acid transactions"),
    ),
    Principle(
        name="System Design",
        category="systems-architecture",
        skill_slug="system-design",
        core_principle=("Start with requirements, not solutions — scalable systems are assembled "
                        "from well-understood building blocks, sized with estimates, with every "
                        "choice carrying an owned tradeoff."),
        disciplines=("The Four-Step Process", "Back-of-the-Envelope Estimation", "Building Blocks",
                     "Database Design and Scaling", "Common System Designs",
                     "Reliability and Operations"),
        keywords=("system design", "scale this", "high availability", "rate limiter",
                  "capacity planning", "distributed architecture"),
    ),
    Principle(
        name="Clean Architecture",
        category="systems-architecture",
        skill_slug="clean-architecture",
        core_principle=("Source code dependencies must point inward, toward higher-level policies "
                        "— business rules stay independent of frameworks, databases, and delivery "
                        "mechanisms."),
        disciplines=("Dependency Rule and Concentric Circles", "Entities and Use Cases",
                     "Interface Adapters and Frameworks", "Component Principles", "SOLID Principles",
                     "Boundaries and Boundary Anatomy"),
        keywords=("clean architecture", "dependency rule", "hexagonal architecture",
                  "ports and adapters", "onion architecture", "solid"),
    ),
    Principle(
        name="Release It!",
        category="systems-architecture",
        skill_slug="release-it",
        core_principle=("Every system will eventually be pushed beyond its design limits — the "
                        "question is whether it degrades gracefully or collapses catastrophically."),
        disciplines=("Stability Anti-Patterns", "Stability Patterns", "Capacity and Availability",
                     "Deployment and Release", "Health Checks and Observability",
                     "Adaptation and Chaos Engineering"),
        keywords=("circuit breaker", "production outage", "bulkhead", "retry storm", "health checks",
                  "cascading failures", "chaos engineering"),
    ),
    Principle(
        name="High Performance Browser Networking",
        category="systems-architecture",
        skill_slug="high-perf-browser",
        core_principle=("Latency, not bandwidth, is the bottleneck — most web performance problems "
                        "stem from too many round trips, not too little throughput."),
        disciplines=("Network Fundamentals", "HTTP Protocol Evolution",
                     "Resource Loading and Critical Rendering Path", "Caching Strategies",
                     "Core Web Vitals Optimization", "Real-Time Communication"),
        keywords=("web performance", "core web vitals", "http/2", "http/3", "render blocking",
                  "network latency", "critical rendering path"),
    ),
    Principle(
        name="Team Topologies",
        category="systems-architecture",
        skill_slug="team-topologies",
        core_principle=("The team is the unit of delivery, and organizations ship their "
                        "communication structure — team boundaries and interactions must be "
                        "designed as deliberately as the software itself."),
        disciplines=("Conway's Law and the Inverse Conway Maneuver", "The Four Fundamental Team Types",
                     "The Three Interaction Modes", "Team Cognitive Load and Team-Sized Software",
                     "Fracture Planes: Splitting Software for Team Ownership",
                     "Platform as a Product and Sensing/Evolving"),
        keywords=("team topologies", "conway's law", "platform team", "stream-aligned team",
                  "cognitive load", "team boundaries", "reorg"),
    ),
)

CATEGORIES: frozenset[str] = frozenset(p.category for p in PRINCIPLES)


def _contains_phrase(haystack: str, needle: str) -> bool:
    """Whole-word/phrase containment, not raw substring — see business_playbook.py's
    identical helper for the false-positive class this avoids (e.g. "ego" inside
    "negotiation"); the same risk applies to short keywords here (e.g. "ddd")."""
    if not needle:
        return False
    return re.search(r"\b" + re.escape(needle) + r"\b", haystack) is not None


def find_principles(query: str, category: str | None = None) -> list[Principle]:
    """Keyword-match query against principle names/keywords, optionally filtered by category.

    Returns every match. An empty query with a category set browses that whole category.
    No match returns an empty list — the caller decides how to say so.

    Raises ValueError for an unrecognized category."""
    if category is not None and category not in CATEGORIES:
        raise ValueError(f"unknown category {category!r} — valid categories: {sorted(CATEGORIES)}")
    lowered = (query or "").lower().strip()
    out = []
    for p in PRINCIPLES:
        if category and p.category != category:
            continue
        if not lowered:
            if category:
                out.append(p)
            continue
        if (any(_contains_phrase(lowered, kw) or _contains_phrase(kw, lowered) for kw in p.keywords)
                or _contains_phrase(p.name.lower(), lowered) or _contains_phrase(lowered, p.skill_slug)):
            out.append(p)
    return out
