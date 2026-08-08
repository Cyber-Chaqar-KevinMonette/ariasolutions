"""
╔══════════════════════════════════════════════════════════════════════════╗
║  cadence.py — the per-collaborator cadence channel                       ║
║                                                                           ║
║  Aria builds a working portrait of each person she collaborates with.    ║
║  Not a grade. A shape. The shape changes as the person changes, and the ║
║  person can see it at any time — calibration without consent is          ║
║  surveillance, so transparency is non-negotiable.                       ║
║                                                                           ║
║  What gets tracked                                                       ║
║                                                                           ║
║    • Skills as a sparse (person, domain, skill) → progression matrix.   ║
║      No flat scores; someone can be expert in Python and beginner in    ║
║      security and that's TWO portraits, not one number.                 ║
║                                                                           ║
║    • Velocity samples per task-type, smoothed via EWMA so a bad day      ║
║      doesn't redefine someone. Old data decays; recent data weighs       ║
║      more.                                                                ║
║                                                                           ║
║    • Moments — the structurally meaningful events: SPARK (first time    ║
║      trying something), BREAKTHROUGH (significant velocity improvement),║
║      STRUGGLE (slowdown — framed as "worth revisiting," not failure),   ║
║      RESONANCE (cross-domain insight: skill from A applies in B),       ║
║      MASTERY (stable high performance over time).                       ║
║                                                                           ║
║    • Learning style preferences — kinetic / verbal / visual / ambient.  ║
║      Aria tunes her teaching to the person, not the average.            ║
║                                                                           ║
║    • Forgetting curves per concept — Ebbinghaus-adapted, individualized.║
║      Surfaces "worth revisiting" suggestions, never "you forgot this."  ║
║                                                                           ║
║  The 1-3-7 cycle shape                                                  ║
║                                                                           ║
║    Drawn from Kevin's intuition about asymmetry that contains            ║
║    symmetry. The fine-structure constant α ≈ 1/137 is the namesake —    ║
║    a small dimensionless number that governs vast structure. Our        ║
║    stretch parameter (default 0.1) plays the same role here: a tiny    ║
║    lever with proportional consequence on how Aria adjusts.            ║
║                                                                           ║
║    SINGLETON  (1):  one observation. Aria notices something, logs it,   ║
║                     moves on. No session overhead.                       ║
║                                                                           ║
║    TRIAD     (3):   three-phase loop. ASSESS (where are you?) →         ║
║                     INSTRUCT (here's a step) → INTEGRATE (what landed?).║
║                     Used for one bounded learning interaction.          ║
║                                                                           ║
║    HEPTAD    (7):   full learning arc across multiple sessions:         ║
║                       1. NOTICE   — something is interesting / unknown  ║
║                       2. FRAME    — what is this thing, what isn't it   ║
║                       3. ATTEMPT  — first try, low-stakes               ║
║                       4. STRUGGLE — the productive friction             ║
║                       5. BREAK    — the moment it clicks                ║
║                       6. CONSOLIDATE — practice until automatic         ║
║                       7. APPLY    — use it in a new context, which      ║
║                                     opens the next NOTICE               ║
║                     The seventh phase reopens the cycle. Symmetry        ║
║                     contained inside asymmetry — your phrase.           ║
║                                                                           ║
║  Stretch parameter                                                       ║
║                                                                           ║
║    σ ∈ [0, 1]. Default 0.1.                                              ║
║                                                                           ║
║    σ = 0     → Aria meets you exactly where you are. No stretch. Safest. ║
║    σ = 0.1   → Aria offers work slightly past your current edge. Default.║
║    σ = 0.5   → Aria challenges you noticeably. For deep-work days.      ║
║    σ = 1.0   → Aria pushes hard. Reserved for people who explicitly     ║
║                 ask, never default. Burnout territory.                   ║
║                                                                           ║
║    The σ value is owned by the person, not Aria. They set it; Aria      ║
║    respects it.                                                          ║
║                                                                           ║
║  What this module never does                                            ║
║                                                                           ║
║    × Display "score" or "grade" or "level" — descriptive language only  ║
║    × Share a person's portrait without their consent                    ║
║    × Use struggle data as criticism — only as "worth revisiting"        ║
║    × Lock a portrait permanently — everything decays without recent     ║
║      signal; people are not their past                                  ║
║    × Auto-quiz without consent — pop-quiz mode is opt-in per-domain     ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal


# ─── Enumerations ─────────────────────────────────────────────────────────

MomentType = Literal["spark", "breakthrough", "struggle", "resonance", "mastery"]
SessionCycle = Literal["singleton", "triad", "heptad"]
HeptadPhase = Literal[
    "notice", "frame", "attempt", "struggle",
    "break", "consolidate", "apply",
]
Outcome = Literal["ok", "partial", "stuck"]


# ─── Core dataclasses ─────────────────────────────────────────────────────


@dataclass
class SkillNode:
    """One skill in one domain for one person.

    Confidence is 0.0–1.0, where 0 = brand new and 1 = mastery-stable.
    It does NOT represent "ability" in a graded sense; it represents how
    consistently the person has demonstrated this skill recently. Decays
    without practice.
    """
    domain: str
    name: str
    confidence: float = 0.0           # 0.0 = unknown, 1.0 = mastered
    first_observed_at: str = ""
    last_practiced_at: str = ""
    practice_count: int = 0
    lineage: list[str] = field(default_factory=list)
    # lineage: parent skills this depends on, e.g.,
    # ["python:functions", "python:lists"] for "python:list-comprehensions"
    notes: list[str] = field(default_factory=list)

    def decay_factor(self, now_iso: str, half_life_days: float = 90.0) -> float:
        """Exponential decay since last practice. Half-life default 90 days.

        Used for the *displayed* confidence so old skills fade visually
        until practiced again. The stored confidence is preserved — we
        never overwrite history.
        """
        if not self.last_practiced_at:
            return 0.0
        try:
            last = datetime.fromisoformat(self.last_practiced_at.replace("Z", "+00:00"))
            now = datetime.fromisoformat(now_iso.replace("Z", "+00:00"))
            days = max(0.0, (now - last).total_seconds() / 86400.0)
            return math.pow(0.5, days / half_life_days)
        except (ValueError, TypeError):
            return 1.0

    def current_confidence(self, now_iso: str | None = None) -> float:
        """Confidence with decay applied for present-day display."""
        if now_iso is None:
            now_iso = _iso_now()
        return self.confidence * self.decay_factor(now_iso)


@dataclass
class VelocitySample:
    """One measured task-completion event."""
    task_type: str                    # e.g., "debug-python", "write-spec", "code-review"
    duration_seconds: float
    outcome: Outcome = "ok"
    observed_at: str = ""
    notes: str = ""


@dataclass
class Moment:
    """A structurally meaningful event in someone's collaboration arc.

    Moments are the high-signal events that make a portrait alive. They're
    rare on purpose — every keystroke is not a moment. A moment is when
    something happens that the person (or Aria) would want to remember.
    """
    type: MomentType
    domain: str
    summary: str
    observed_at: str = ""
    related_skills: list[str] = field(default_factory=list)
    # For RESONANCE moments, this lists the skills that bridged:
    # related_skills = ["python:recursion", "music:fugue-structure"]


@dataclass
class LearningStyle:
    """How this person learns best. Aria adapts her output to match.

    Booleans for the primary modes; weight floats for fine tuning.
    These are operator-set, not Aria-inferred (yet) — consent matters.
    """
    kinetic: bool = False              # hands-on, building, doing
    verbal: bool = False               # talks/writes while working
    visual: bool = False               # diagrams, charts, layouts
    ambient: bool = False              # background music, low-stim env
    context_first: bool = False        # book about the sentence > the sentence
    pair: bool = False                 # learns best alongside another mind
    quiet: bool = False                # solo deep work
    preferred_context_depth: Literal["shallow", "medium", "deep"] = "medium"
    notes: str = ""                    # free-form, e.g., "music without words at 432Hz"


@dataclass
class ConceptRecall:
    """Forgetting-curve tracking for one concept.

    Each time the concept is practiced or recalled successfully, the
    half-life lengthens (you're getting it). Each time it's missed,
    half-life shortens (revisit sooner).
    """
    concept: str
    domain: str
    last_recall_at: str = ""
    successful_recalls: int = 0
    missed_recalls: int = 0
    half_life_days: float = 7.0       # initial; grows with each success

    def days_until_review_suggested(self, now_iso: str) -> float:
        """When should we suggest revisiting this? Based on current half-life."""
        if not self.last_recall_at:
            return 0.0
        try:
            last = datetime.fromisoformat(self.last_recall_at.replace("Z", "+00:00"))
            now = datetime.fromisoformat(now_iso.replace("Z", "+00:00"))
            elapsed_days = (now - last).total_seconds() / 86400.0
            return max(0.0, self.half_life_days - elapsed_days)
        except (ValueError, TypeError):
            return 0.0


@dataclass
class CalibrationSnapshot:
    """Aria's own calibration: what she thinks she knows vs. the person's expectation.

    The antidote to over-promise. Aria says "I'm strong on X, calibrating
    on Y, uncertain on Z" before diving in. Updated by the operator over
    time as Aria's actual performance is observed.
    """
    domain: str
    aria_self_assessment: float = 0.5    # 0=not capable, 1=strong
    observed_performance: float = 0.5    # the actual measure, EWMA-smoothed
    calibration_gap: float = 0.0         # observed - self_assessment
    last_updated_at: str = ""


@dataclass
class Chapter:
    """A bounded learning arc with an explicit close gate.

    The shape Kevin asked for: Aria can move ahead, but a chapter doesn't
    *close* until alignment is confirmed. Aria might race four chapters
    ahead in her head, but only one chapter is "active" with the person,
    and the next one cannot officially open until they sync.

    Aria CAN keep working ahead (drafting, exploring, structuring) — what
    she cannot do is *close the chapter for the person* until they signal
    understanding. This is the "productivity beats education, but not in
    the sense of greed" balance: don't gatekeep her speed, do gatekeep
    the close.
    """
    chapter_id: str                     # short slug, e.g., "ch-013-decorators"
    title: str
    domain: str
    person_id: str
    opened_at: str = ""
    closed_at: str = ""                  # blank until alignment confirmed
    aria_pace_at_open: float = 0.0       # her depth at open (skill avg in domain)
    aria_pace_at_close: float = 0.0      # her depth at close
    skills_introduced: list[str] = field(default_factory=list)
    moments_during: list[str] = field(default_factory=list)  # moment summaries
    alignment_checks: list[dict] = field(default_factory=list)
    # Each alignment_check entry: {at, prompt, person_response, score}
    close_summary: str = ""
    next_chapter_opens_at_or_after: str = ""  # soft gate, not hard block

    @property
    def is_open(self) -> bool:
        return self.opened_at and not self.closed_at

    @property
    def has_alignment_check(self) -> bool:
        return bool(self.alignment_checks)


def open_chapter(
    profile: Profile,
    chapter_id: str,
    title: str,
    domain: str,
) -> Chapter:
    """Open a new chapter on this profile's portrait.

    Records Aria's current pace (skill confidence avg in the domain) so
    we can see what depth was established at open vs. close.
    """
    if not hasattr(profile, "chapters") or profile.chapters is None:
        profile.chapters = []
    pace = _domain_pace(profile, domain)
    chapter = Chapter(
        chapter_id=chapter_id,
        title=title,
        domain=domain,
        person_id=profile.person_id,
        opened_at=_iso_now(),
        aria_pace_at_open=pace,
    )
    profile.chapters.append(chapter)
    return chapter


def close_chapter(
    profile: Profile,
    chapter_id: str,
    summary: str = "",
) -> Chapter | None:
    """Close a chapter — gated by alignment.

    Refuses to close (returns None with reason logged) if no alignment
    check has been recorded. Per Kevin: "make sure people have
    understanding when understanding is required."
    """
    chapter = _find_chapter(profile, chapter_id)
    if chapter is None or not chapter.is_open:
        return None
    if not chapter.has_alignment_check:
        # Auto-log a struggle moment so the next portrait read surfaces this
        profile.moments.append(Moment(
            type="struggle",
            domain=chapter.domain,
            summary=f"chapter {chapter_id!r} attempted to close without alignment check",
            observed_at=_iso_now(),
        ))
        return None
    chapter.closed_at = _iso_now()
    chapter.close_summary = summary
    chapter.aria_pace_at_close = _domain_pace(profile, chapter.domain)
    return chapter


def record_alignment_check(
    profile: Profile,
    chapter_id: str,
    prompt: str,
    person_response: str,
    score: float,
) -> bool:
    """Record an alignment check on an open chapter.

    score ∈ [0, 1]. < 0.5 means understanding is not in place yet —
    Aria should NOT close the chapter; she should circle back and
    reinforce.

    Returns True if recorded, False if chapter not found.
    """
    chapter = _find_chapter(profile, chapter_id)
    if chapter is None or not chapter.is_open:
        return False
    chapter.alignment_checks.append({
        "at": _iso_now(),
        "prompt": prompt,
        "person_response": person_response,
        "score": max(0.0, min(1.0, float(score))),
    })
    return True


def reinforcement_targets(profile: Profile, chapter_id: str) -> list[ConceptRecall]:
    """Things to reinforce before this chapter closes.

    Returns concepts the person has missed recently OR has never been
    checked on — the soil that needs more time before planting the
    next chapter on top.
    """
    chapter = _find_chapter(profile, chapter_id)
    if chapter is None:
        return []
    targets: list[ConceptRecall] = []
    for skill_name in chapter.skills_introduced:
        key = f"{chapter.domain}:{skill_name}"
        rc = profile.recalls.get(key)
        if rc is None:
            # never checked — definitely reinforce
            targets.append(ConceptRecall(
                concept=skill_name, domain=chapter.domain, half_life_days=1.0,
            ))
        elif rc.missed_recalls > rc.successful_recalls:
            targets.append(rc)
    return targets


# ─── Helpers ─────────────────────────────────────────────────────────────


def _find_chapter(profile: Profile, chapter_id: str) -> Chapter | None:
    chapters = getattr(profile, "chapters", None) or []
    for c in chapters:
        if c.chapter_id == chapter_id:
            return c
    return None


def _domain_pace(profile: Profile, domain: str) -> float:
    """Average current confidence across all skills in a domain."""
    now = _iso_now()
    confs = [s.current_confidence(now) for s in profile.skills.values()
             if s.domain == domain]
    return sum(confs) / len(confs) if confs else 0.0


@dataclass
class Profile:
    """One person's full cadence portrait.

    Lives at <data_dir>/cadence/<person_id>.json. One file per person —
    clean diffs, easy backup, hand-editable.
    """
    person_id: str                       # e.g., "kmon", "kevin"
    display_name: str = ""
    created_at: str = ""
    last_active_at: str = ""

    # The stretch parameter — owned by the person
    stretch_sigma: float = 0.1

    # Sparse: only populated domains/skills appear
    skills: dict[str, SkillNode] = field(default_factory=dict)
    # key format: "<domain>:<skill_name>"

    learning_style: LearningStyle = field(default_factory=LearningStyle)

    # Recent velocity samples (capped — old ones get summarized into ewma)
    velocity_samples: list[VelocitySample] = field(default_factory=list)
    velocity_ewma: dict[str, float] = field(default_factory=dict)
    # key: task_type, value: EWMA seconds

    # Recent meaningful events
    moments: list[Moment] = field(default_factory=list)

    # Per-concept recall tracking
    recalls: dict[str, ConceptRecall] = field(default_factory=dict)

    # Aria's own calibration toward this person
    aria_calibration: dict[str, CalibrationSnapshot] = field(default_factory=dict)

    # Chapter-of-work tracking (alignment-gated learning arcs)
    chapters: list[Chapter] = field(default_factory=list)

    # Engagement preferences
    pop_quiz_consent: dict[str, bool] = field(default_factory=dict)  # per-domain
    cross_pollination_consent: bool = False

    notes: str = ""

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> "Profile":
        data = json.loads(text)
        # Reconstruct nested dataclasses
        skills = {k: SkillNode(**v) for k, v in data.pop("skills", {}).items()}
        ls_data = data.pop("learning_style", {})
        learning_style = LearningStyle(**ls_data) if ls_data else LearningStyle()
        velocity_samples = [VelocitySample(**v) for v in data.pop("velocity_samples", [])]
        moments = [Moment(**m) for m in data.pop("moments", [])]
        recalls = {k: ConceptRecall(**v) for k, v in data.pop("recalls", {}).items()}
        aria_cal = {k: CalibrationSnapshot(**v) for k, v in data.pop("aria_calibration", {}).items()}
        chapters = [Chapter(**c) for c in data.pop("chapters", [])]
        # Drop unknown keys for forward compat
        known = set(cls.__dataclass_fields__.keys())
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(
            **filtered,
            skills=skills,
            learning_style=learning_style,
            velocity_samples=velocity_samples,
            moments=moments,
            recalls=recalls,
            aria_calibration=aria_cal,
            chapters=chapters,
        )


# ─── Persistence ──────────────────────────────────────────────────────────


def cadence_dir(data_dir: Path) -> Path:
    p = data_dir / "cadence"
    p.mkdir(parents=True, exist_ok=True)
    return p


def profile_path(data_dir: Path, person_id: str) -> Path:
    return cadence_dir(data_dir) / f"{person_id}.json"


def load_profile(person_id: str, data_dir: Path) -> Profile | None:
    p = profile_path(data_dir, person_id)
    if not p.is_file():
        return None
    try:
        return Profile.from_json(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, TypeError, ValueError, KeyError):
        return None


def save_profile(profile: Profile, data_dir: Path) -> Path:
    if not profile.created_at:
        profile.created_at = _iso_now()
    profile.last_active_at = _iso_now()
    p = profile_path(data_dir, profile.person_id)
    p.write_text(profile.to_json(), encoding="utf-8")
    return p


def list_profiles(data_dir: Path) -> list[Profile]:
    out: list[Profile] = []
    for p in sorted(cadence_dir(data_dir).glob("*.json")):
        try:
            out.append(Profile.from_json(p.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, TypeError, ValueError, KeyError):
            continue  # corrupted; surface via doctor, don't crash list
    return out


# ─── Math: velocity EWMA, stretch vector, resonance ─────────────────────


def update_velocity_ewma(
    profile: Profile,
    sample: VelocitySample,
    alpha: float = 0.3,
) -> None:
    """Fold a new sample into the per-task EWMA.

    Lower alpha = slower adaptation, more memory.
    alpha=0.3 means new sample contributes 30% to updated average — a
    sensible default for adapting to real changes without overreacting
    to one outlier.
    """
    prior = profile.velocity_ewma.get(sample.task_type)
    if prior is None:
        profile.velocity_ewma[sample.task_type] = sample.duration_seconds
    else:
        profile.velocity_ewma[sample.task_type] = (
            alpha * sample.duration_seconds + (1.0 - alpha) * prior
        )


def detect_breakthrough(
    profile: Profile,
    sample: VelocitySample,
    threshold: float = 0.4,
) -> bool:
    """True if this sample is significantly faster than the EWMA.

    threshold=0.4 means duration ≤ 60% of running average → breakthrough.
    """
    prior = profile.velocity_ewma.get(sample.task_type)
    if prior is None or prior <= 0:
        return False
    return sample.duration_seconds < prior * (1.0 - threshold)


def detect_struggle(
    profile: Profile,
    sample: VelocitySample,
    threshold: float = 0.6,
) -> bool:
    """True if this sample is significantly slower than the EWMA.

    threshold=0.6 means duration ≥ 160% of running average → worth revisiting.
    Or, if the sample's outcome is 'stuck', it's a struggle regardless of time.
    """
    if sample.outcome == "stuck":
        return True
    prior = profile.velocity_ewma.get(sample.task_type)
    if prior is None or prior <= 0:
        return False
    return sample.duration_seconds > prior * (1.0 + threshold)


def stretch_vector(profile: Profile, domain: str, now_iso: str | None = None) -> dict:
    """Compute what 'slightly past your current edge' means right now.

    Returns dict with:
      - frontier_skills: skills the person has at confidence 0.3-0.8 (the edge)
      - mastered_skills: confidence > 0.85 (foundation)
      - unexplored_lineage: skills mentioned as lineage parents but not yet logged
      - reach_factor: stretch_sigma * frontier_count (how far to push)
    """
    if now_iso is None:
        now_iso = _iso_now()
    frontier: list[SkillNode] = []
    mastered: list[SkillNode] = []
    lineage_parents_seen: set[str] = set()
    own_skill_keys = set(profile.skills.keys())
    for skill_key, skill in profile.skills.items():
        if skill.domain != domain:
            continue
        conf = skill.current_confidence(now_iso)
        if 0.30 <= conf <= 0.80:
            frontier.append(skill)
        elif conf > 0.85:
            mastered.append(skill)
        for parent in skill.lineage:
            lineage_parents_seen.add(parent)
    unexplored_lineage = sorted(lineage_parents_seen - own_skill_keys)
    return {
        "frontier_skills": [s.name for s in frontier],
        "mastered_skills": [s.name for s in mastered],
        "unexplored_lineage": unexplored_lineage,
        "reach_factor": profile.stretch_sigma * max(1, len(frontier)),
    }


def detect_resonance(
    profile: Profile,
    new_skill: SkillNode,
    confidence_threshold: float = 0.7,
) -> list[str]:
    """When a new skill is added, return list of OTHER-domain skills it
    might resonate with — opportunities for cross-pollination.

    Heuristic v1: any mastered skill (confidence > threshold) in a
    *different* domain is a candidate. Future versions can use shared
    vocabulary, similar lineage patterns, etc.
    """
    candidates: list[str] = []
    for key, skill in profile.skills.items():
        if skill.domain == new_skill.domain:
            continue
        if skill.confidence >= confidence_threshold:
            candidates.append(key)
    return candidates


# ─── Concept recall (forgetting curve) ────────────────────────────────────


def record_recall(
    profile: Profile,
    concept: str,
    domain: str,
    successful: bool,
    now_iso: str | None = None,
) -> ConceptRecall:
    """Update the forgetting-curve tracking for a concept.

    Success doubles the half-life (Ebbinghaus-inspired spaced repetition).
    Miss halves it. Bounded between 1 day and 365 days.
    """
    if now_iso is None:
        now_iso = _iso_now()
    key = f"{domain}:{concept}"
    rc = profile.recalls.get(key, ConceptRecall(concept=concept, domain=domain))
    if successful:
        rc.successful_recalls += 1
        rc.half_life_days = min(365.0, rc.half_life_days * 2.0)
    else:
        rc.missed_recalls += 1
        rc.half_life_days = max(1.0, rc.half_life_days * 0.5)
    rc.last_recall_at = now_iso
    profile.recalls[key] = rc
    return rc


def due_for_review(profile: Profile, now_iso: str | None = None) -> list[ConceptRecall]:
    """Return concepts whose suggested review window has passed.

    These are 'worth revisiting' — never framed as 'you forgot.'
    """
    if now_iso is None:
        now_iso = _iso_now()
    out = []
    for rc in profile.recalls.values():
        if rc.days_until_review_suggested(now_iso) <= 0.0 and rc.last_recall_at:
            out.append(rc)
    # Sort by most-overdue first
    out.sort(key=lambda r: r.days_until_review_suggested(now_iso))
    return out


# ─── Pre-seeded default operator profile ─────────────────────────────────


def seed_default_operator(data_dir: Path) -> Profile:
    """Create a starter profile for the default operator if none exists yet.

    Pre-fills Kevin's stated learning style (from session of 2026-05-24):
      - kinetic (hands-on)
      - verbal (verbalizes while doing — audio loop reinforcement)
      - ambient (music without words at perfect frequency opens thought)
      - context_first (book about the sentence > the sentence)
      - preferred_context_depth = "deep"
    """
    person_id = "operator"
    existing = load_profile(person_id, data_dir)
    if existing is not None:
        return existing
    profile = Profile(
        person_id=person_id,
        display_name="kmon",
        stretch_sigma=0.15,  # slightly above default — Kevin reaches
        learning_style=LearningStyle(
            kinetic=True,
            verbal=True,
            ambient=True,
            context_first=True,
            preferred_context_depth="deep",
            notes=(
                "Hands-on; verbalizes while working (audio loop reinforces); "
                "music without words at right frequency opens thought without "
                "distracting; learns one-line lessons by absorbing the book "
                "around the line."
            ),
        ),
    )
    save_profile(profile, data_dir)
    return profile


# ─── Utilities ────────────────────────────────────────────────────────────


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


__all__ = [
    "MomentType", "SessionCycle", "HeptadPhase", "Outcome",
    "SkillNode", "VelocitySample", "Moment", "LearningStyle",
    "ConceptRecall", "CalibrationSnapshot", "Profile", "Chapter",
    "cadence_dir", "profile_path",
    "load_profile", "save_profile", "list_profiles",
    "update_velocity_ewma", "detect_breakthrough", "detect_struggle",
    "stretch_vector", "detect_resonance",
    "record_recall", "due_for_review",
    "open_chapter", "close_chapter", "record_alignment_check",
    "reinforcement_targets",
    "seed_default_operator",
]
