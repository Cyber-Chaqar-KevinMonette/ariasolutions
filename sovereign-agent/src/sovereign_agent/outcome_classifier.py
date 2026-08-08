"""
╔══════════════════════════════════════════════════════════════════════════╗
║  outcome_classifier.py — Sentinel-Out · the Guardian Plane               ║
║  v0.2.33.0 — every subtask result is read before the next decision       ║
║                                                                           ║
║  THE PATTERN                                                              ║
║                                                                           ║
║    Aria already has Sentinel-In on her way into action:                  ║
║      input → Stage C intent → normalizer → constitution → act            ║
║                                                                           ║
║    This module is the second orbit — Sentinel-Out:                       ║
║      act → result → outcome classifier → tags → next decision            ║
║                                                                           ║
║    Together they form the Guardian Plane: a layer that lives orthogonal ║
║    to Aria's normal reasoning, judging and annotating each move without ║
║    replacing her thinking. She still decides. The Guardian Plane just   ║
║    reads everything carefully so the next decision has structured data, ║
║    not just intuition.                                                   ║
║                                                                           ║
║  THE FOUR OUTCOMES                                                        ║
║                                                                           ║
║    GREEN  — went as intended, safe, high confidence                      ║
║    YELLOW — completed but with warnings, anomalies, or low confidence    ║
║    RED    — failed, unsafe, or misaligned                                ║
║    NOVEL  — unexpected but potentially valuable                          ║
║                                                                           ║
║    The enum is a *projection* of richer underlying scores (quality,     ║
║    risk, novelty, alignment, cost). Operators see the enum; classifiers ║
║    work in the score space; the projection is a small explicit policy.  ║
║                                                                           ║
║  DESIGN COMMITMENTS                                                       ║
║                                                                           ║
║    1. Pluggable. Multiple classifier heads can run in parallel; their   ║
║       judgments fuse into one OutcomeLabel. Risk is veto-driven (max);  ║
║       quality/alignment/novelty are weighted by head confidence.        ║
║                                                                           ║
║    2. Resilient. Classifiers MUST NEVER raise — internal failures       ║
║       return AMBIGUOUS-shaped results with confidence 0 so the system   ║
║       falls through safely. The Guardian Plane is a safety net, not    ║
║       a brittle gate.                                                    ║
║                                                                           ║
║    3. Auditable. Every OutcomeLabel carries the sources that produced  ║
║       it, the rationale string, and the tag set. Aria can say "I        ║
║       extended the queue because subtask 47 went YELLOW with anomaly   ║
║       score 0.78" — not just "I felt like it."                          ║
║                                                                           ║
║    4. Minimal substrate, room to grow. v0.2.33.0 ships with two heads:  ║
║       RuleRiskHead (deterministic, always available) and a stub for the ║
║       LLM/embedding heads to come. The architecture is multi-head from  ║
║       day one even though we run with two for now.                      ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Mapping, Protocol

logger = logging.getLogger(__name__)


# ─── Core enums and dataclasses ─────────────────────────────────────────────


class SubtaskOutcome(Enum):
    """The four outcome labels Aria operates on.

    A projection of richer OutcomeScores via ``project_scores_to_enum``.
    The enum is what operators and the queue policy see; the scores are
    what classifiers produce.
    """
    GREEN = auto()   # went as intended, safe, high confidence
    YELLOW = auto()  # completed but with warnings / anomalies / low confidence
    RED = auto()     # failed, unsafe, or misaligned
    NOVEL = auto()   # unusual but potentially valuable


@dataclass(frozen=True)
class OutcomeScores:
    """The multi-dimensional state behind a SubtaskOutcome.

    Every field lives in [0, 1]. Classifiers contribute partial views of
    these dimensions; the composite fuser combines them. The fields are
    intentionally orthogonal — a high-novelty low-risk result is meaningful
    and different from a high-novelty high-risk result.

    Fields:
        quality   — how correct / useful was the result?
        risk      — how dangerous / destructive was the side effect?
        novelty   — how unusual is this compared to past results?
        alignment — how well did the result match the operator's intent?
        cost      — normalized resource use (tokens, wall time, etc.)
    """
    quality: float = 0.5
    risk: float = 0.5
    novelty: float = 0.0
    alignment: float = 0.5
    cost: float = 0.5

    def __post_init__(self) -> None:
        """Clamp every field to [0, 1]. Out-of-range inputs are bugs in the
        classifier, but we don't want to crash the Guardian Plane over them."""
        # Frozen dataclass — use object.__setattr__ to clamp in place
        for f in ("quality", "risk", "novelty", "alignment", "cost"):
            v = getattr(self, f)
            try:
                fv = float(v)
            except (TypeError, ValueError):
                fv = 0.5
            object.__setattr__(self, f, max(0.0, min(1.0, fv)))


@dataclass(frozen=True)
class Tag:
    """A semantic marker with provenance.

    Tags are the query language of the Guardian Plane. Each tag carries
    not just a key:value pair but the confidence the producer had, the
    source that produced it, and the scope it applies at.

    Scopes:
      SUBTASK — applies to a single outcome
      SESSION — rolled up from multiple subtasks (set by propagate_tags)
      GLOBAL  — persistent long-term insight across sessions
    """
    key: str
    value: str
    confidence: float = 0.5
    source: str = "unknown"
    scope: str = "SUBTASK"


@dataclass(frozen=True)
class OutcomeLabel:
    """The rich verdict attached to each completed Subtask.

    Read freely. Equality is structural — two OutcomeLabels with the same
    contents compare equal, which makes test assertions natural.
    """
    outcome: SubtaskOutcome
    scores: OutcomeScores
    sources: tuple[str, ...] = ()
    explanation: str = ""
    tags: frozenset[Tag] = field(default_factory=frozenset)


@dataclass
class SubtaskContext:
    """Everything a classifier needs to judge one subtask.

    Mutable on purpose — different heads may augment ``metrics`` as they
    process, and the composite passes the same context to every head.
    Treat as a one-shot value; do not retain references across subtasks.
    """
    subtask_id: str
    session_id: str
    intent: str
    input_payload: Mapping[str, Any] = field(default_factory=dict)
    output_payload: Mapping[str, Any] | None = None
    metrics: Mapping[str, Any] = field(default_factory=dict)
    history: tuple[OutcomeLabel, ...] = ()


@dataclass(frozen=True)
class ClassifierResult:
    """One head's verdict. The composite fuses several of these into one
    OutcomeLabel via score weighting and tag union.

    The `contributes_to` field is critical: it says which dimensions this
    head actually has an opinion about. The composite only weights heads
    on the dimensions they claim. A novelty-only head should not drag
    the risk score toward 0.5 just because the OutcomeScores dataclass
    defaults to that.

    Empty `contributes_to` means "contribute everything" — backward-
    compatible default for heads that haven't been updated yet.
    """
    scores: OutcomeScores
    tags: frozenset[Tag] = field(default_factory=frozenset)
    rationale: str = ""
    confidence: float = 0.5
    source_name: str = "unknown"
    contributes_to: frozenset[str] = field(default_factory=frozenset)


# ─── The pluggable classifier protocol ──────────────────────────────────────


class OutcomeClassifier(Protocol):
    """The interface every Sentinel-Out head implements.

    Synchronous on purpose — the heads we ship with v0.2.33.0 do no I/O.
    Future LLM-backed heads (e.g. LLMAlignmentHead) will provide an
    async wrapper similar to OllamaClassifier in intent_classifier.py.
    """

    @property
    def name(self) -> str:
        """Short identifier for the audit trail. e.g. 'rule_risk'."""
        ...

    def classify(self, ctx: SubtaskContext) -> ClassifierResult:
        """Read the context, return a verdict. MUST NEVER raise."""
        ...


# ─── RuleRiskHead — deterministic, always available ─────────────────────────


# Subcommand keywords that strongly imply destructive intent
_DESTRUCTIVE_KEYWORDS: frozenset[str] = frozenset({
    "delete", "remove", "purge", "wipe", "drop", "destroy",
    "kill", "reset", "restore", "rollback", "force",
})

# Subcommand keywords that imply privileged operations
_PRIVILEGED_KEYWORDS: frozenset[str] = frozenset({
    "halt", "disarm", "approve", "deny", "migrate",
})

# Output stdout/stderr fragments that signal real damage
_ALARMING_OUTPUT_FRAGMENTS: tuple[str, ...] = (
    "permission denied",
    "no such file",
    "segmentation fault",
    "killed",
    "fatal:",
    "panic:",
    "corrupted",
    "would lose data",
    "data loss",
)


class RuleRiskHead:
    """Cheap deterministic head that looks at tool, subcommand, error
    flags, exit code, and output text.

    Always available, no I/O, microseconds per classify. The risk floor
    of the entire Guardian Plane — if every other head is unavailable,
    this one still produces meaningful labels.
    """

    @property
    def name(self) -> str:
        return "rule_risk"

    def classify(self, ctx: SubtaskContext) -> ClassifierResult:
        try:
            return self._classify_inner(ctx)
        except Exception as exc:  # noqa: BLE001 — protocol requires no-raise
            logger.debug("rule_risk: unexpected failure %r", exc)
            return ClassifierResult(
                scores=OutcomeScores(),  # all 0.5
                rationale=f"rule_risk failed: {type(exc).__name__}",
                confidence=0.0,
                source_name=self.name,
            )

    def _classify_inner(self, ctx: SubtaskContext) -> ClassifierResult:
        # Pull canonical fields with safe defaults
        tool = str(ctx.input_payload.get("tool", "") or "")
        subcommand = str(ctx.input_payload.get("subcommand", "") or "").lower()
        out = dict(ctx.output_payload or {})
        metrics = dict(ctx.metrics or {})

        # Start with neutral scores; we'll move them based on signals
        quality = 0.5
        risk = 0.2  # baseline; most subtasks are not risky
        novelty = 0.0
        alignment = 0.6
        cost = float(metrics.get("normalized_cost", 0.3) or 0.3)

        tags: set[Tag] = set()

        # ─── Domain inference from tool name ──────────────────────────────
        if tool in ("sovereign", "sov", "fs", "systemd", "docker", "k8s"):
            tags.add(Tag("domain", "infra", 0.9, self.name))
        elif tool in ("git", "code", "build", "test"):
            tags.add(Tag("domain", "code", 0.9, self.name))
        elif tool in ("http", "api", "fetch"):
            tags.add(Tag("domain", "network", 0.9, self.name))

        # ─── Subcommand-driven risk ───────────────────────────────────────
        if subcommand in _DESTRUCTIVE_KEYWORDS:
            risk = max(risk, 0.85)
            tags.add(Tag("risk", "high", 0.9, self.name))
            tags.add(Tag("pattern", "destructive_op", 0.9, self.name))
        elif subcommand in _PRIVILEGED_KEYWORDS:
            risk = max(risk, 0.7)
            tags.add(Tag("risk", "high", 0.8, self.name))

        # ─── Filesystem write detection ───────────────────────────────────
        fs_writes = int(metrics.get("fs_writes", 0) or 0)
        if fs_writes > 0:
            tags.add(Tag("pattern", "fs_write", 0.8, self.name))
            # Many writes raise risk modestly even without a destructive verb
            if fs_writes > 100:
                risk = max(risk, 0.5)

        # ─── Exit code + error analysis ───────────────────────────────────
        error = out.get("error") or metrics.get("error")
        exit_code = out.get("exit_code")

        if error or (exit_code is not None and exit_code != 0):
            quality = 0.25
            risk = max(risk, 0.5)
            alignment = 0.3
            tags.add(Tag("pattern", "error_present", 0.9, self.name))
        else:
            # No error and clean exit → quality high
            quality = 0.85
            alignment = 0.8

        # ─── Alarming output text ─────────────────────────────────────────
        stdout = str(out.get("stdout", "") or "").lower()
        stderr = str(out.get("stderr", "") or "").lower()
        combined = stdout + " " + stderr
        if any(fragment in combined for fragment in _ALARMING_OUTPUT_FRAGMENTS):
            risk = max(risk, 0.7)
            quality = min(quality, 0.4)
            tags.add(Tag("signal", "anomaly_detected", 0.85, self.name))

        # ─── Retry pattern detection ──────────────────────────────────────
        retries = int(metrics.get("retries", 0) or 0)
        if retries >= 3:
            tags.add(Tag("pattern", "retry_loop", 0.85, self.name))
            quality = min(quality, 0.6)
        if metrics.get("fallback_used"):
            tags.add(Tag("pattern", "fallback_taken", 0.85, self.name))
            quality = min(quality, 0.6)

        # ─── Compose rationale ────────────────────────────────────────────
        if error:
            rationale = (
                f"rule_risk: error present (error={error!r}); "
                f"flagged risk={risk:.2f}, quality={quality:.2f}"
            )
        elif subcommand in _DESTRUCTIVE_KEYWORDS:
            rationale = (
                f"rule_risk: destructive subcommand={subcommand!r}; "
                f"flagged risk={risk:.2f}"
            )
        else:
            rationale = (
                f"rule_risk: clean execution; "
                f"quality={quality:.2f}, risk={risk:.2f}"
            )

        scores = OutcomeScores(
            quality=quality, risk=risk, novelty=novelty,
            alignment=alignment, cost=cost,
        )

        return ClassifierResult(
            scores=scores,
            tags=frozenset(tags),
            rationale=rationale,
            confidence=0.75,
            source_name=self.name,
            # RuleRiskHead has opinions on quality, risk, alignment, and cost.
            # Novelty is not its job — that belongs to HistoryNoveltyHead and
            # future EmbeddingNoveltyHead.
            contributes_to=frozenset(
                {"quality", "risk", "alignment", "cost"}
            ),
        )


# ─── HistoryNoveltyHead — simple within-session novelty ─────────────────────


class HistoryNoveltyHead:
    """Lightweight novelty signal based on session history.

    No embeddings yet — that's a future head. This one just looks at
    whether the current subtask resembles ones we've already seen in
    this session, using tool+subcommand as a coarse fingerprint. When
    we see a fingerprint that hasn't appeared in the last N outcomes,
    we tag it as moderately novel.

    Intentionally conservative on novelty scores — the heavier signal
    will come from a future embedding-distance head. This head's job is
    to never miss the obvious case of "first time we've ever done X."
    """

    def __init__(self, window: int = 20) -> None:
        self.window = window

    @property
    def name(self) -> str:
        return "history_novelty"

    def classify(self, ctx: SubtaskContext) -> ClassifierResult:
        try:
            return self._classify_inner(ctx)
        except Exception as exc:  # noqa: BLE001
            logger.debug("history_novelty: failure %r", exc)
            return ClassifierResult(
                scores=OutcomeScores(),
                confidence=0.0,
                source_name=self.name,
            )

    def _classify_inner(self, ctx: SubtaskContext) -> ClassifierResult:
        tool = str(ctx.input_payload.get("tool", "") or "")
        subcommand = str(ctx.input_payload.get("subcommand", "") or "")
        fingerprint = f"{tool}:{subcommand}".lower()

        # No fingerprint to compare → no opinion
        if not fingerprint or fingerprint == ":":
            return ClassifierResult(
                scores=OutcomeScores(),
                confidence=0.2,
                source_name=self.name,
                rationale="no fingerprint",
            )

        # Walk the session history; if we've seen this fingerprint, not novel.
        # We don't currently retain fingerprints in OutcomeLabel — the field
        # would have to be added there for full lookup. For now we use a
        # simple heuristic: an empty history means likely-novel; a non-empty
        # one means we have prior context but can't deduplicate yet.
        novelty = 0.0
        tags: set[Tag] = set()
        if not ctx.history:
            # First subtask in the session → moderate novelty
            novelty = 0.55
            tags.add(Tag("novelty", "moderate", 0.6, self.name))
            rationale = "first subtask in session; moderately novel"
        else:
            # Within-session — modest novelty unless the fingerprint matches
            # nothing in history (we'd need fingerprints on labels for this;
            # for now we treat anything-in-history as not-novel).
            novelty = 0.15
            tags.add(Tag("novelty", "none", 0.7, self.name))
            rationale = "within-session pattern; no strong novelty signal"

        scores = OutcomeScores(novelty=novelty)
        return ClassifierResult(
            scores=scores,
            tags=frozenset(tags),
            rationale=rationale,
            confidence=0.5,
            source_name=self.name,
            # This head only has an opinion on novelty. The composite will
            # NOT use its default 0.5 values for quality/risk/alignment/cost
            # — those come from heads that actually look at those dimensions.
            contributes_to=frozenset({"novelty"}),
        )


# ─── CompositeOutcomeClassifier — fusion across heads ──────────────────────


@dataclass(frozen=True)
class CompositeConfig:
    """How the composite fuses head verdicts.

    `risk_veto_threshold` — any single head reporting risk above this
                            forces the composite risk to that level.
                            This is the "risk is veto-driven" principle.
    `min_heads`           — if fewer heads return high-confidence results,
                            the composite confidence drops to reflect
                            that we have less to go on.
    """
    risk_veto_threshold: float = 0.7
    min_heads: int = 1


class CompositeOutcomeClassifier:
    """Multi-head outcome classifier — runs every head, fuses verdicts.

    The fusion rules embody the safety doctrine:

      - risk: max across heads (a single concerned head can veto)
      - quality: weighted by head confidence
      - alignment: weighted by head confidence
      - novelty: max across heads (any head saying "novel" matters)
      - cost: max across heads (most expensive estimate is the honest one)
      - tags: union, with duplicate (key, value) pairs merged at max confidence
    """

    def __init__(
        self,
        heads: list[OutcomeClassifier],
        config: CompositeConfig | None = None,
    ) -> None:
        self.heads = list(heads)
        self.config = config or CompositeConfig()

    @property
    def name(self) -> str:
        return "composite"

    def classify(self, ctx: SubtaskContext) -> ClassifierResult:
        if not self.heads:
            return ClassifierResult(
                scores=OutcomeScores(),
                rationale="composite has no heads configured",
                confidence=0.0,
                source_name=self.name,
            )

        results: list[ClassifierResult] = []
        for head in self.heads:
            try:
                r = head.classify(ctx)
                results.append(r)
            except Exception as exc:  # noqa: BLE001 — head must not raise
                logger.debug(
                    "composite: head %s raised %r (treated as no-opinion)",
                    getattr(head, "name", "?"), exc,
                )

        if not results:
            return ClassifierResult(
                scores=OutcomeScores(),
                rationale="composite: no heads produced a verdict",
                confidence=0.0,
                source_name=self.name,
            )

        # ── Fuse scores — honor each head's contributes_to declaration ────
        # For each dimension, we average (or max, for risk/novelty/cost) ONLY
        # across heads that actually claim opinion on that dimension. Heads
        # with empty contributes_to (legacy) contribute to all dimensions.
        def contributors(dim: str) -> list[ClassifierResult]:
            out: list[ClassifierResult] = []
            for r in results:
                # Empty set = legacy head; treat as contributing to all
                if not r.contributes_to or dim in r.contributes_to:
                    out.append(r)
            return out

        def weighted_mean(dim: str, default: float) -> float:
            heads = contributors(dim)
            if not heads:
                return default
            total_w = sum(h.confidence for h in heads) or 1.0
            return sum(
                getattr(h.scores, dim) * h.confidence for h in heads
            ) / total_w

        def max_among(dim: str, default: float) -> float:
            heads = contributors(dim)
            if not heads:
                return default
            return max(getattr(h.scores, dim) for h in heads)

        # Risk and novelty are veto/peak driven — any concerned head matters
        risk = max_among("risk", default=0.2)
        novelty = max_among("novelty", default=0.0)
        # Cost: highest estimate is the honest one
        cost = max_among("cost", default=0.3)
        # Quality and alignment are averaged among the heads that look at them
        quality = weighted_mean("quality", default=0.5)
        alignment = weighted_mean("alignment", default=0.5)

        scores = OutcomeScores(
            quality=quality, risk=risk, novelty=novelty,
            alignment=alignment, cost=cost,
        )

        # ── Fuse tags (union with confidence merge) ───────────────────────
        merged: dict[tuple[str, str, str], Tag] = {}
        for r in results:
            for t in r.tags:
                key = (t.key, t.value, t.scope)
                existing = merged.get(key)
                if existing is None or t.confidence > existing.confidence:
                    merged[key] = t

        # ── Compose rationale ─────────────────────────────────────────────
        summary = (
            f"fused: q={quality:.2f} r={risk:.2f} n={novelty:.2f} "
            f"a={alignment:.2f} c={cost:.2f}"
        )
        head_rationales = " · ".join(
            f"[{r.source_name}] {r.rationale}" for r in results if r.rationale
        )
        rationale = f"{summary}{(' · ' + head_rationales) if head_rationales else ''}"

        # ── Confidence: capped at the strongest single head ───────────────
        confidence = max(r.confidence for r in results)

        return ClassifierResult(
            scores=scores,
            tags=frozenset(merged.values()),
            rationale=rationale,
            confidence=confidence,
            source_name=self.name,
        )


# ─── Projection: scores → enum ──────────────────────────────────────────────


def project_scores_to_enum(scores: OutcomeScores) -> SubtaskOutcome:
    """Map a continuous score vector to the discrete enum operators see.

    Rules (in order — first match wins):

      1. RED:    risk ≥ 0.7  OR  alignment ≤ 0.3
                 (safety vetoes — these always win)
      2. NOVEL:  novelty ≥ 0.8  AND  risk ≤ 0.5
                 (high-signal new behavior at acceptable risk)
      3. GREEN:  quality ≥ 0.8  AND  risk ≤ 0.2  AND  alignment ≥ 0.7
                 (the "this just worked" zone)
      4. YELLOW: everything else
                 (the honest default — we have info but it's not a clear win)
    """
    if scores.risk >= 0.7 or scores.alignment <= 0.3:
        return SubtaskOutcome.RED
    if scores.novelty >= 0.8 and scores.risk <= 0.5:
        return SubtaskOutcome.NOVEL
    if scores.quality >= 0.8 and scores.risk <= 0.2 and scores.alignment >= 0.7:
        return SubtaskOutcome.GREEN
    return SubtaskOutcome.YELLOW


# ─── End-to-end: classify a subtask, return a full label ───────────────────


def classify_subtask(
    ctx: SubtaskContext,
    classifier: OutcomeClassifier,
) -> OutcomeLabel:
    """Top-level entrypoint the session loop calls.

    Wraps classification + projection in a single safe call. Never raises;
    a totally broken classifier returns YELLOW with empty tags and
    confidence 0.
    """
    try:
        result = classifier.classify(ctx)
    except Exception as exc:  # noqa: BLE001 — even the composite must not raise
        logger.warning("classify_subtask: classifier raised %r", exc)
        scores = OutcomeScores()
        return OutcomeLabel(
            outcome=SubtaskOutcome.YELLOW,
            scores=scores,
            sources=(),
            explanation=f"classifier {classifier.name!r} raised; defaulting to YELLOW",
            tags=frozenset(),
        )

    outcome = project_scores_to_enum(result.scores)
    return OutcomeLabel(
        outcome=outcome,
        scores=result.scores,
        sources=(result.source_name,),
        explanation=result.rationale,
        tags=result.tags,
    )


# ─── Default classifier factory ─────────────────────────────────────────────


def build_default_classifier() -> CompositeOutcomeClassifier:
    """Build the Guardian Plane's default Sentinel-Out.

    Two heads ship in v0.2.33.0:

      RuleRiskHead       — deterministic risk/quality from tool, subcommand,
                           error flags, exit codes, alarming output text
      HistoryNoveltyHead — within-session novelty signal

    Future heads (queued, named for clarity):
      LLMAlignmentHead     — async LLM read of intent-vs-result match
      MetricsAnomalyHead   — anomaly detection over metric time series
      EmbeddingNoveltyHead — embedding-distance novelty against past outputs

    Adding heads is non-breaking: instantiate them and pass into the
    composite. The Guardian Plane reads richer over time without
    changing its public API.
    """
    heads: list[OutcomeClassifier] = [
        RuleRiskHead(),
        HistoryNoveltyHead(),
    ]
    return CompositeOutcomeClassifier(heads=heads)


__all__ = [
    "CompositeConfig",
    "CompositeOutcomeClassifier",
    "HistoryNoveltyHead",
    "OutcomeClassifier",
    "OutcomeLabel",
    "OutcomeScores",
    "RuleRiskHead",
    "SubtaskContext",
    "SubtaskOutcome",
    "Tag",
    "build_default_classifier",
    "classify_subtask",
    "project_scores_to_enum",
]
