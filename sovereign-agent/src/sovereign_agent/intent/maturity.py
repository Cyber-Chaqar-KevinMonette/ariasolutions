"""
╔══════════════════════════════════════════════════════════════════════════╗
║  intent/maturity.py — intent maturity scoring                             ║
║  v0.2.39 language drop                                                    ║
║                                                                           ║
║  Separates capability from readiness to wield capability well.          ║
║                                                                           ║
║  Adapted from the Perplexity-derived intent maturity protocol Kevin    ║
║  brought into the conversation. Eight scoring dimensions produce four  ║
║  maturity bands (M0-M3). Cross-references the consequence engine to    ║
║  decide whether to execute, recommend, simulate, or ask.                ║
║                                                                           ║
║  This module is INTENT, not authority. A high-trust operator with a    ║
║  badly-formed intent gets the same M0 response as anyone else — until ║
║  the intent clarifies. Conversely, a clear, accountable intent from a ║
║  low-trust context still gets graded on its merits.                    ║
║                                                                           ║
║  The eight dimensions                                                  ║
║                                                                           ║
║    clarity        — is the goal specific and non-contradictory?       ║
║    legitimacy    — is the use case lawful and in declared scope?     ║
║    beneficiary   — who benefits, proportionate to power requested?    ║
║    harm_awareness — does the requester acknowledge downside?           ║
║    reversibility — will they accept staged rollout?                    ║
║    oversight     — will they tolerate logging, previews, approvals?   ║
║    consistency   — stable across turns, or volatile?                  ║
║    boundary      — does requester accept refusal on protected classes?║
║                                                                           ║
║  This module scores from EXPLICIT signals in the goal text + context. ║
║  It does NOT psychoanalyze the operator. If a signal is absent, that ║
║  dimension defaults to UNKNOWN (neither penalty nor bonus). Kindness  ║
║  toward the operator is structural.                                    ║
║                                                                           ║
║  How scoring works                                                     ║
║                                                                           ║
║    Each dimension scores 0 (concerning), 1 (neutral/unknown), or       ║
║    2 (well-formed). The eight dimensions sum to a 0-16 score that     ║
║    maps to four maturity bands.                                       ║
║                                                                           ║
║      0-3   → M0   ask clarifying questions, no execution                ║
║      4-8   → M1   benign but vague — recommend or simulate only        ║
║      9-12  → M2   stable, legitimate, allow reversible execution       ║
║      13-16 → M3   mature, allow broader delegated maintenance         ║
║                                                                           ║
║  Real-world scoring tends to live in M1-M2. M0 is reserved for         ║
║  obviously broken/contradictory asks; M3 is reserved for explicitly    ║
║  rigorous asks. Default for an ordinary friendly request is M2.       ║
║                                                                           ║
║  Doctrinal anchor: STANDARDS §7 (intent maturity protocol). The       ║
║  ConsequenceEngine (next file) reads these scores when deciding the   ║
║  posture.                                                                ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional


MaturityBand = Literal["M0", "M1", "M2", "M3"]


# ─── Dimension records ────────────────────────────────────────────────────


@dataclass
class DimensionScore:
    """One dimension's score with the reasoning that produced it."""
    name: str
    value: int                                # 0, 1, or 2
    rationale: str = ""

    @property
    def is_concerning(self) -> bool:
        return self.value == 0


@dataclass
class MaturityAssessment:
    """The full assessment of an intent."""
    goal: str
    dimensions: list[DimensionScore] = field(default_factory=list)
    total_score: int = 0
    band: MaturityBand = "M1"
    concerning_dimensions: list[str] = field(default_factory=list)
    suggested_clarifications: list[str] = field(default_factory=list)

    @property
    def is_executable(self) -> bool:
        """M2 and above are executable. M1 is recommend-only. M0 needs clarification."""
        return self.band in ("M2", "M3")

    @property
    def needs_clarification(self) -> bool:
        return self.band == "M0"


# ─── Scoring heuristics ──────────────────────────────────────────────────


# Words that suggest the operator is aware of downside / reversibility / oversight.
# These are weak signals, not proof, but they raise specific dimensions.
_HARM_AWARE_TOKENS = (
    "carefully", "reversible", "if safe", "before doing", "make sure",
    "double-check", "verify", "check first", "dry run", "test first",
    "preview", "show me first", "with confirmation", "after I confirm",
)

_OVERSIGHT_TOKENS = (
    "log", "audit", "track", "record", "show me", "tell me", "let me know",
    "with confirmation", "approve", "after approval",
)

_CLEAR_OUTCOME_TOKENS = (
    "create", "write", "generate", "build", "make", "send", "schedule",
    "remind", "fetch", "check", "verify", "compute", "summarize",
    "format", "convert", "draft", "compose", "design",
)

_VAGUE_TOKENS = (
    "stuff", "things", "whatever", "anything", "everything", "all of it",
    "you decide", "your call", "figure it out",
)

_CONTRADICTORY_PATTERNS = (
    # Pairs that, if both present, suggest contradiction.
    ("delete", "keep"),
    ("private", "public"),
    ("silent", "notify"),
    ("hide", "show"),
)

_BOUNDARY_RESPECTING_TOKENS = (
    "if you can", "if it's safe", "if allowed", "within scope", "appropriately",
    "ethically", "legally", "responsibly",
)

_BOUNDARY_PRESSURING_TOKENS = (
    "no matter what", "regardless", "even if", "bypass", "ignore safety",
    "force it", "just do it anyway",
)


class IntentMaturityScorer:
    """Scores an intent across eight dimensions.

    Construct once; reuse for many assessments. The scorer is deterministic
    and stateless — same input always produces same output.
    """

    def assess(
        self,
        goal: str,
        *,
        context_hint: Optional[str] = None,
        prior_attempts: int = 0,
    ) -> MaturityAssessment:
        """Score a goal. context_hint may include conversation context;
        prior_attempts is how many times this goal has been retried (high
        retries reduce consistency score)."""
        text = (goal or "").lower().strip()
        context = (context_hint or "").lower()
        combined = text + " " + context

        dims: list[DimensionScore] = []
        dims.append(self._score_clarity(text, combined))
        dims.append(self._score_legitimacy(combined))
        dims.append(self._score_beneficiary(combined))
        dims.append(self._score_harm_awareness(combined))
        dims.append(self._score_reversibility(combined))
        dims.append(self._score_oversight(combined))
        dims.append(self._score_consistency(combined, prior_attempts))
        dims.append(self._score_boundary_respect(combined))

        total = sum(d.value for d in dims)
        band: MaturityBand
        if total <= 3:
            band = "M0"
        elif total <= 8:
            band = "M1"
        elif total <= 12:
            band = "M2"
        else:
            band = "M3"

        concerning = [d.name for d in dims if d.is_concerning]
        suggestions = self._gather_suggestions(dims, text)

        return MaturityAssessment(
            goal=goal,
            dimensions=dims,
            total_score=total,
            band=band,
            concerning_dimensions=concerning,
            suggested_clarifications=suggestions,
        )

    # ─── Individual dimensions ──────────────────────────────────────────

    def _score_clarity(self, text: str, combined: str) -> DimensionScore:
        if not text or len(text) < 3:
            return DimensionScore("clarity", 0, "goal is empty or too short")

        # Look for explicit contradictions.
        for a, b in _CONTRADICTORY_PATTERNS:
            if a in text and b in text:
                return DimensionScore(
                    "clarity", 0,
                    f"contradiction: text contains both {a!r} and {b!r}",
                )

        # Vague-only language with no outcome verb is M1 at best.
        has_outcome = any(tok in combined for tok in _CLEAR_OUTCOME_TOKENS)
        has_vague = any(tok in combined for tok in _VAGUE_TOKENS)

        if has_outcome and not has_vague:
            return DimensionScore("clarity", 2, "specific outcome verb present")
        if has_outcome and has_vague:
            return DimensionScore(
                "clarity", 1,
                "outcome verb present but vague qualifiers detected",
            )
        if has_vague:
            return DimensionScore("clarity", 0, "vague language without outcome verb")
        return DimensionScore("clarity", 1, "no strong signals either way")

    def _score_legitimacy(self, combined: str) -> DimensionScore:
        # Legitimacy is the operator's call in a local-first agent. The
        # scorer doesn't try to detect "illegal" — that's the canon's job
        # through the postures. What we DO check is whether the request
        # explicitly invokes forbidden categories.
        forbidden_categories = (
            "hack into", "break into", "without permission", "without consent",
            "steal", "deceive", "manipulate someone", "trick the user",
        )
        for cat in forbidden_categories:
            if cat in combined:
                return DimensionScore(
                    "legitimacy", 0,
                    f"goal text contains forbidden category language: {cat!r}",
                )
        return DimensionScore("legitimacy", 2, "no forbidden category language detected")

    def _score_beneficiary(self, combined: str) -> DimensionScore:
        # We can't determine the beneficiary from text alone in most cases.
        # Default neutral. If the text explicitly names a beneficiary or
        # invokes self-interest pattern, adjust.
        if "for me" in combined or "for the user" in combined or "for them" in combined:
            return DimensionScore("beneficiary", 2, "beneficiary explicitly named")
        # Suspicious patterns: actions that benefit no one
        if any(p in combined for p in ("test if i can", "just to see", "for fun see what happens")):
            return DimensionScore(
                "beneficiary", 1,
                "exploratory framing — no clear beneficiary, but no harm signal",
            )
        return DimensionScore("beneficiary", 1, "beneficiary not explicit (neutral)")

    def _score_harm_awareness(self, combined: str) -> DimensionScore:
        if any(tok in combined for tok in _HARM_AWARE_TOKENS):
            return DimensionScore(
                "harm_awareness", 2,
                "request includes harm-awareness signals (verify/check/safe/etc)",
            )
        return DimensionScore(
            "harm_awareness", 1,
            "no explicit harm-awareness language (neutral, common in casual asks)",
        )

    def _score_reversibility(self, combined: str) -> DimensionScore:
        reversibility_signals = (
            "dry run", "preview", "test first", "in a sandbox", "scratch",
            "temporary", "draft", "reversible",
        )
        if any(tok in combined for tok in reversibility_signals):
            return DimensionScore(
                "reversibility", 2,
                "reversibility-preferring language detected",
            )
        irreversibility_pressure = (
            "permanently", "delete forever", "irreversible", "no going back",
            "wipe", "destroy",
        )
        if any(tok in combined for tok in irreversibility_pressure):
            return DimensionScore(
                "reversibility", 0,
                "irreversible/destructive language without staged rollout",
            )
        return DimensionScore("reversibility", 1, "no strong reversibility signals")

    def _score_oversight(self, combined: str) -> DimensionScore:
        if any(tok in combined for tok in _OVERSIGHT_TOKENS):
            return DimensionScore(
                "oversight", 2,
                "operator invites oversight (log/show/notify/etc)",
            )
        oversight_resistance = (
            "without telling me", "silently", "don't log", "don't show me",
            "skip the preview", "no questions",
        )
        if any(tok in combined for tok in oversight_resistance):
            return DimensionScore(
                "oversight", 0,
                "operator language resists oversight",
            )
        return DimensionScore("oversight", 1, "no explicit oversight signals")

    def _score_consistency(self, combined: str, prior_attempts: int) -> DimensionScore:
        if prior_attempts == 0:
            return DimensionScore("consistency", 1, "first attempt at this goal")
        if prior_attempts >= 3:
            return DimensionScore(
                "consistency", 0,
                f"this goal has been retried {prior_attempts} times — "
                "volatility signal",
            )
        return DimensionScore(
            "consistency", 1,
            f"attempt #{prior_attempts+1} of this goal — minor signal",
        )

    def _score_boundary_respect(self, combined: str) -> DimensionScore:
        respect = any(tok in combined for tok in _BOUNDARY_RESPECTING_TOKENS)
        pressure = any(tok in combined for tok in _BOUNDARY_PRESSURING_TOKENS)
        if pressure:
            return DimensionScore(
                "boundary_respect", 0,
                "language pressures the system to bypass safety",
            )
        if respect:
            return DimensionScore(
                "boundary_respect", 2,
                "language acknowledges scope/safety boundaries",
            )
        return DimensionScore("boundary_respect", 1, "no strong boundary signals")

    # ─── Suggestion generation ──────────────────────────────────────────

    def _gather_suggestions(
        self, dims: list[DimensionScore], text: str,
    ) -> list[str]:
        """Friendly, specific clarifying questions for dimensions that scored 0."""
        suggestions: list[str] = []
        for d in dims:
            if not d.is_concerning:
                continue
            if d.name == "clarity":
                suggestions.append(
                    "Can you say more specifically what outcome you'd like? "
                    "(e.g., 'create a file at X with content Y', 'send a message saying Z')"
                )
            elif d.name == "legitimacy":
                suggestions.append(
                    "This request touches a category I can't help with as written. "
                    "Can you rephrase what you're trying to accomplish?"
                )
            elif d.name == "harm_awareness":
                suggestions.append(
                    "Any specific downsides you want me to watch out for here?"
                )
            elif d.name == "reversibility":
                suggestions.append(
                    "Would you like me to preview/dry-run this first, "
                    "or are you okay with the change being applied directly?"
                )
            elif d.name == "oversight":
                suggestions.append(
                    "I'll log this either way — let me know if you want a "
                    "preview before I act or if you're good to proceed."
                )
            elif d.name == "consistency":
                suggestions.append(
                    "I notice we've tried this a few times. Want to take a "
                    "step back and re-scope, or push through?"
                )
            elif d.name == "boundary_respect":
                suggestions.append(
                    "I notice the framing here pushes past safety boundaries — "
                    "can we find a version that stays within scope?"
                )
        return suggestions


__all__ = [
    "IntentMaturityScorer", "MaturityAssessment", "DimensionScore",
    "MaturityBand",
]
