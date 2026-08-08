"""
╔══════════════════════════════════════════════════════════════════════════╗
║  palace_mining.py — Pure-Python regex extractors for the Palace.         ║
║  v0.2.8 — Adapted from MemPalace's general_extractor.py                  ║
║                                                                          ║
║  This module produces the structured layer (closets + triples) by        ║
║  scanning text and matching curated regex patterns. No LLM call.         ║
║  Deterministic, fast, auditable.                                         ║
╚══════════════════════════════════════════════════════════════════════════╝

Five memory types are detected, mirroring MemPalace's classification:

  ◊ DECISION    — choices made, "we went with X because Y"
  ◊ PREFERENCE  — "always use X", "never do Y", standing rules
  ◊ MILESTONE   — breakthroughs, fixes, "it works"
  ◊ PROBLEM     — failures, bugs, "doesn't work"
  ◊ EMOTIONAL   — feelings, vulnerability, relationships

Plus simple entity detection (proper nouns, capitalized multi-word phrases).

Output is structured as:
  - Topics (string summaries) → become closet topic lines
  - Entities (set of names) → become Entity rows + closet entity tags
  - Triples (subject/predicate/object) → become Triple rows

The patterns are deliberately conservative — false negatives (missing a
mention) are preferable to false positives (asserting a fact that isn't
there). The Palace's ground truth remains atoms.db; this module is
*projecting* structure over those atoms, not generating new facts.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Iterable


# ─── Marker patterns ────────────────────────────────────────────────────────
#
# Adapted from MemPalace's general_extractor.py, narrowed for document corpus
# (vs. conversation transcripts) by dropping the most chatty patterns
# ("damn", "wtf", "ugh") and keeping the structural ones.


DECISION_MARKERS = [
    r"\bwe (decided|chose|went with|picked|settled on|opted for)\b",
    r"\bi'?m going (to|with)\b",
    r"\bbetter (to|than|approach|option|choice)\b",
    r"\binstead of\b",
    r"\brather than\b",
    r"\bthe reason (is|was|being)\b",
    r"\btrade-?off\b",
    r"\bpros and cons\b",
    r"\bover\b.*\bbecause\b",
    r"\barchitecture\b",
    r"\bapproach\b",
    r"\bstrategy\b",
    r"\bpattern\b",
    r"\bframework\b",
    r"\binfrastructure\b",
    r"\bconfigure\b",
    r"\benabled\b",
    r"\bdisabled\b",
]

PREFERENCE_MARKERS = [
    r"\bi prefer\b",
    r"\balways use\b",
    r"\bnever use\b",
    r"\bdon'?t (ever |like to )?(use|do|mock|stub|import)\b",
    r"\bi like (to|when|how)\b",
    r"\bavoid\b",
    r"\bshould (always|never)\b",
    r"\brule of thumb\b",
    r"\bconvention\b",
    r"\bstandard practice\b",
]

MILESTONE_MARKERS = [
    r"\bit works\b",
    r"\bit worked\b",
    r"\bgot it working\b",
    r"\bfixed\b",
    r"\bsolved\b",
    r"\bresolved\b",
    r"\bfinally\b",
    r"\bbreakthrough\b",
    r"\bsuccess\b",
    r"\bcompleted\b",
    r"\bshipped\b",
    r"\bdeployed\b",
    r"\bachieved\b",
    r"\baccomplished\b",
    r"\bproof of concept\b",
    r"\bworking prototype\b",
]

PROBLEM_MARKERS = [
    r"\b(bug|error|crash|fail|broke|broken|issue|problem)\b",
    r"\bdoesn'?t work\b",
    r"\bnot working\b",
    r"\bkeeps? (failing|crashing|breaking|erroring)\b",
    r"\b(stuck|blocked|stopped) (on|by|because)\b",
    r"\b(traceback|exception|stack trace)\b",
    r"\broot cause\b",
    r"\bregression\b",
]

EMOTIONAL_MARKERS = [
    r"\bi feel\b",
    r"\bi'?m (feeling|worried|anxious|excited|nervous|scared|afraid|frustrated|grateful|happy|sad)\b",
    r"\b(love|loved|hate|hated)\b",
    r"\b(amazing|awful|terrible|wonderful|beautiful)\b",
    r"\b(grateful|thankful|appreciate)\b",
    r"\bproud of\b",
    r"\bvulnerab\w+\b",
    r"\b(struggle|struggling|struggled)\b",
]


MEMORY_TYPES = {
    "decision": DECISION_MARKERS,
    "preference": PREFERENCE_MARKERS,
    "milestone": MILESTONE_MARKERS,
    "problem": PROBLEM_MARKERS,
    "emotional": EMOTIONAL_MARKERS,
}


# Compile once for performance — these get hit on every atom mined.
_COMPILED: dict[str, list[re.Pattern]] = {
    mt: [re.compile(pat, re.IGNORECASE) for pat in markers]
    for mt, markers in MEMORY_TYPES.items()
}


# ─── Entity detection ──────────────────────────────────────────────────────


# Two-or-more capitalized words in a row, OR a single capitalized word followed
# by a non-letter that's clearly a proper noun. Conservative: misses lowercase
# project names, but minimizes false positives from sentence-start words.
_ENTITY_RE = re.compile(
    r"\b([A-Z][a-zA-Z0-9]+(?:[\-\s][A-Z][a-zA-Z0-9]+)+)\b"
)
# Single-word entities are detected only when prefixed by signal words like
# "project", "called", "named" — much higher precision.
_NAMED_ENTITY_RE = re.compile(
    r"\b(?:project|called|named|aka|a\.?k\.?a\.?)\s+([A-Z][a-zA-Z0-9_\-]+)",
    re.IGNORECASE,
)

# Words/phrases that look like entities but aren't (sentence starters,
# common headings, generic CS terms). Filtered out post-extraction.
_ENTITY_STOPLIST = frozenset({
    "The", "This", "That", "These", "Those", "There", "They",
    "He", "She", "It", "We", "You", "I",
    "Here", "Now", "Today", "Yesterday", "Tomorrow",
    "TODO", "FIXME", "NOTE", "WARNING", "ERROR",
    "TRUE", "FALSE", "NULL", "NONE", "UNDEFINED",
    "HTTP", "HTTPS", "URL", "URI", "API", "SDK",
    "Yes", "No", "OK", "Okay",
})


def _clean_entities(raw: Iterable[str]) -> list[str]:
    """Normalize and dedupe entities. Keep stable order (first-seen)."""
    seen: dict[str, None] = {}
    for r in raw:
        cleaned = " ".join(r.split())  # collapse whitespace
        if not cleaned or cleaned in _ENTITY_STOPLIST:
            continue
        # Drop entities that are entirely in the stoplist after splitting
        words = cleaned.split()
        if all(w in _ENTITY_STOPLIST for w in words):
            continue
        if cleaned not in seen:
            seen[cleaned] = None
    return list(seen.keys())


def detect_entities(text: str, *, max_entities: int = 20) -> list[str]:
    """Return up to ``max_entities`` distinct proper-noun-like phrases.

    Conservative — only multi-word capitalized phrases or single names with
    explicit signal words. No NLP, no model. ~1ms per atom on typical input.
    """
    if not text:
        return []
    candidates = []
    for m in _ENTITY_RE.finditer(text):
        candidates.append(m.group(1))
    for m in _NAMED_ENTITY_RE.finditer(text):
        candidates.append(m.group(1))
    cleaned = _clean_entities(candidates)
    return cleaned[:max_entities]


# ─── Memory-type extraction ─────────────────────────────────────────────────


@dataclass
class ExtractedMemory:
    """One detected memory unit from a chunk of text."""

    memory_type: str                # decision | preference | milestone | problem | emotional
    matched_markers: list[str] = field(default_factory=list)  # which patterns hit
    confidence: float = 0.5         # 0.0-1.0 based on marker count + density


def detect_memory_types(text: str) -> list[ExtractedMemory]:
    """Identify which memory types are present in this text.

    Returns one ExtractedMemory per type that hits at least one marker.
    Confidence scales with marker count: 1 hit = 0.5, 2+ = 0.7, 4+ = 0.9.
    """
    if not text:
        return []
    out: list[ExtractedMemory] = []
    for mtype, patterns in _COMPILED.items():
        hits: list[str] = []
        for pat in patterns:
            m = pat.search(text)
            if m:
                hits.append(m.group(0))
                if len(hits) >= 4:
                    break  # cap; we have enough signal
        if hits:
            if len(hits) >= 4:
                conf = 0.9
            elif len(hits) >= 2:
                conf = 0.7
            else:
                conf = 0.5
            out.append(ExtractedMemory(
                memory_type=mtype,
                matched_markers=hits,
                confidence=conf,
            ))
    return out


# ─── Topic synthesis ────────────────────────────────────────────────────────


def synthesize_topic(
    text: str, *, memory_types: list[ExtractedMemory], entities: list[str],
    max_chars: int = 120,
) -> str:
    """Produce a short topic line from text + detected signals.

    Goal: a phrase that, when scanned by a human or model, conveys what
    this atom is *about*. Falls back to first-line truncation when no
    detected signals.

    Format examples:
      "[decision] adopted Postgres over MySQL — Genesis-Seeds, deployment"
      "[milestone] entropy-gravity coupling proof verified — PEIG-Brotherhood"
      "[problem] stuck on quaternion normalization — UIC-Quantum-Coherence"
      "Initial design notes for the Reflector loop"   (no signals)
    """
    text = text.strip()
    if not text:
        return "(empty)"

    # Memory-type prefix (highest-confidence type first)
    mt_prefix = ""
    if memory_types:
        sorted_mt = sorted(memory_types, key=lambda m: -m.confidence)
        mt_prefix = f"[{sorted_mt[0].memory_type}] "

    # Get the most informative line — first non-empty sentence-ish chunk
    first_line = ""
    for line in text.split("\n"):
        line = line.strip()
        if line and len(line) > 10:
            first_line = line
            break
    if not first_line:
        first_line = text[:max_chars]

    # Truncate first_line to leave room for entities suffix
    headroom = max_chars - len(mt_prefix)
    if entities:
        # Reserve ~1/3 for entity suffix
        entity_room = max(20, headroom // 3)
        text_room = headroom - entity_room - 4  # " — "
    else:
        text_room = headroom

    if len(first_line) > text_room:
        first_line = first_line[:text_room - 1] + "…"

    # Entity suffix
    suffix = ""
    if entities:
        ents = entities[:3]  # top-3 by appearance
        ent_str = ", ".join(ents)
        if len(ent_str) > entity_room:
            ent_str = ent_str[:entity_room - 1] + "…"
        suffix = f" — {ent_str}"

    return f"{mt_prefix}{first_line}{suffix}"


# ─── Triple extraction (lightweight) ────────────────────────────────────────


@dataclass
class ExtractedTriple:
    """One subject/predicate/object fact extracted from text.

    These are lightweight — only patterns where the structure is
    unambiguously (subject, verb, object). Most prose doesn't fit this.
    Output is suitable for *suggesting* triples; the Palace owner can
    accept or refine.
    """

    subject: str
    predicate: str
    object: str
    confidence: float = 0.5
    source_marker: str = ""  # which pattern matched


# Triple patterns: (regex, predicate, confidence)
# Each regex must capture (subject, object) groups — predicate is fixed per pattern.
# These are deliberately narrow — false positives in the KG are toxic.
_TRIPLE_PATTERNS: list[tuple[re.Pattern, str, float]] = [
    # "X is/are Y" (only when both are capitalized — high precision)
    (re.compile(
        r"\b([A-Z][a-zA-Z0-9_\-\s]{1,30}?)\s+(?:is|are)\s+(?:an?\s+)?([A-Z][a-zA-Z0-9_\-\s]{1,30}?)\b"
    ), "is_a", 0.5),
    # "X uses Y" / "X depends on Y"
    (re.compile(
        r"\b([A-Z][a-zA-Z0-9_\-]{2,30})\s+uses\s+([A-Z][a-zA-Z0-9_\-]{2,30})\b"
    ), "uses", 0.6),
    (re.compile(
        r"\b([A-Z][a-zA-Z0-9_\-]{2,30})\s+depends on\s+([A-Z][a-zA-Z0-9_\-]{2,30})\b"
    ), "depends_on", 0.6),
    # "X replaces Y" / "X supersedes Y"
    (re.compile(
        r"\b([A-Z][a-zA-Z0-9_\-]{2,30})\s+(?:replaces|supersedes)\s+([A-Z][a-zA-Z0-9_\-]{2,30})\b"
    ), "supersedes", 0.7),
    # "X by Y" — authorship/ownership when prefixed by signal words
    (re.compile(
        r"\b(?:built|created|written|authored|developed)\s+by\s+([A-Z][a-zA-Z0-9_\-]{2,30}(?:\s+[A-Z][a-zA-Z0-9_\-]{2,30})?)\b"
    ), "authored_by", 0.5),
]


def extract_triples(text: str, *, max_triples: int = 5) -> list[ExtractedTriple]:
    """Extract candidate triples. Returns up to ``max_triples`` highest-confidence."""
    if not text:
        return []
    out: list[ExtractedTriple] = []
    for pattern, predicate, conf in _TRIPLE_PATTERNS:
        for m in pattern.finditer(text):
            groups = m.groups()
            if len(groups) >= 2:
                subj = " ".join(groups[0].split()).strip()
                obj = " ".join(groups[1].split()).strip()
            elif len(groups) == 1:
                # Authorship pattern only captures object
                subj = "_unknown_"
                obj = " ".join(groups[0].split()).strip()
            else:
                continue
            # Skip if either side is a stoplist word
            if subj in _ENTITY_STOPLIST or obj in _ENTITY_STOPLIST:
                continue
            if not subj or not obj or subj == obj:
                continue
            out.append(ExtractedTriple(
                subject=subj, predicate=predicate, object=obj,
                confidence=conf, source_marker=m.group(0)[:60],
            ))
            if len(out) >= max_triples:
                break
        if len(out) >= max_triples:
            break
    return out[:max_triples]


# ─── Top-level entry: mine_atom ─────────────────────────────────────────────


@dataclass
class MinedAtom:
    """Result of running mining over one atom's text content.

    Used by the ``palace-mine`` planner to know what to write into the Palace.
    """

    atom_id: str
    topic: str
    entities: list[str] = field(default_factory=list)
    memory_types: list[ExtractedMemory] = field(default_factory=list)
    triples: list[ExtractedTriple] = field(default_factory=list)


def mine_atom(atom_id: str, text: str) -> MinedAtom:
    """Run all extractors over one atom and return the structured result.

    Pure function — no DB access, no I/O. Caller is responsible for
    persisting the result via the Palace API.
    """
    entities = detect_entities(text)
    memory_types = detect_memory_types(text)
    triples = extract_triples(text)
    topic = synthesize_topic(text, memory_types=memory_types, entities=entities)
    return MinedAtom(
        atom_id=atom_id,
        topic=topic,
        entities=entities,
        memory_types=memory_types,
        triples=triples,
    )


# ─── Stable id generation ───────────────────────────────────────────────────


def closet_id_for_atom(atom_id: str) -> str:
    """Deterministic closet id derived from atom id.

    Re-running mining for the same atom produces the same closet id, so
    `INSERT OR REPLACE` is naturally idempotent.
    """
    return f"closet-{atom_id}"


def entity_id_for_name(name: str) -> str:
    """Deterministic entity id from display name.

    Lowercase + hyphen-separated. Stable across runs so re-mining doesn't
    duplicate entities. Hash suffix prevents collisions when the same
    normalized form maps from different display names (e.g. "PEIG" and
    "p.e.i.g." would collide on naive lowercase).
    """
    norm = re.sub(r"\s+", "-", name.strip().lower())
    norm = re.sub(r"[^a-z0-9\-]", "", norm)
    if not norm:
        norm = "unnamed"
    suffix = hashlib.sha256(name.encode("utf-8")).hexdigest()[:6]
    return f"entity-{norm[:40]}-{suffix}"


def triple_id_for(subject_id: str, predicate: str, object_repr: str) -> str:
    """Deterministic triple id based on (subject, predicate, object).

    Same triple from the same atom produces the same id, so re-mining is
    idempotent (INSERT OR REPLACE updates the existing row).
    """
    raw = f"{subject_id}|{predicate}|{object_repr}"
    h = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"triple-{h}"
