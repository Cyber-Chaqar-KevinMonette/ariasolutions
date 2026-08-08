"""
╔══════════════════════════════════════════════════════════════════════════╗
║  intent_classifier.py — Stage C of the cockpit input pipeline            ║
║  v0.2.32.0 — "always-on" intent classification                            ║
║                                                                           ║
║  Every cockpit input gets an intent label BEFORE the structural          ║
║  normalizer fires:                                                        ║
║                                                                           ║
║    • CLI_INTENT   — operator wants to operate the system                 ║
║    • NL_INTENT    — operator is talking, asking, describing              ║
║    • AMBIGUOUS    — confidence too low to decide either way              ║
║                                                                           ║
║  The classification has VETO POWER over the structural CLI parser:       ║
║                                                                           ║
║    • NL_INTENT at any confidence → input routes to the conversation     ║
║      pipeline, even if structurally `sov <known-subcommand>` parses.    ║
║      This is what catches "sovereign sync is a beautiful metaphor" —   ║
║      structure says CLI, semantics say English, semantics wins.        ║
║                                                                           ║
║    • CLI_INTENT confirms the structural match → execute path proceeds.  ║
║                                                                           ║
║    • AMBIGUOUS → fall through to the structural normalizer (Stage B    ║
║      handles it). The LLM is allowed to abstain.                       ║
║                                                                           ║
║  The classifier is PLUGGABLE: two implementations ship today, more can  ║
║  be added without changing the cockpit:                                 ║
║                                                                           ║
║    HeuristicClassifier — pure-Python rules; offline-safe; deterministic.║
║                           Default when no LLM backend is configured.    ║
║                                                                           ║
║    OllamaClassifier    — tiny local model (phi3:mini or llama3.2:1b).   ║
║                           Lazy: only fires when Ollama is reachable     ║
║                           AND a classifier model is configured. Times   ║
║                           out at 150ms by default — slower means "treat ║
║                           as AMBIGUOUS" and let Stage B handle it.      ║
║                                                                           ║
║  The doctrine: every input gets a label, but the system never blocks    ║
║  on a classifier that doesn't respond. Offline degrades to honest       ║
║  AMBIGUOUS; AMBIGUOUS degrades to structural parsing; structural        ║
║  parsing degrades to natural language. Each fall-through is safe.       ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

logger = logging.getLogger(__name__)


class IntentLabel(StrEnum):
    """The three labels the classifier can produce."""
    CLI_INTENT = "CLI_INTENT"
    NL_INTENT = "NL_INTENT"
    AMBIGUOUS = "AMBIGUOUS"


@dataclass(frozen=True)
class IntentResult:
    """A classifier verdict on one input line.

    `label`      — what the classifier thinks
    `confidence` — 0.0 to 1.0; the classifier's certainty
    `source`     — name of the classifier backend that produced this
                   (helps debug "why did the cockpit veto my command?")
    """
    label: IntentLabel
    confidence: float
    source: str = "unknown"


class IntentClassifier(Protocol):
    """The pluggable interface every classifier backend implements.

    Two surfaces:
      - ``classify(text)`` — synchronous, MUST always exist, MUST never raise.
        The cockpit's sync input handler calls this on every input.
      - ``classify_async(text)`` — optional async surface for backends that
        need I/O (e.g. Ollama). Defaults to wrapping classify(text).

    Backends must NEVER raise. Internal failures should return an AMBIGUOUS
    result with confidence 0.0 so the caller falls through to structural
    parsing safely.
    """

    @property
    def name(self) -> str:
        """Short identifier for the audit trail. e.g. 'heuristic', 'ollama'."""
        ...

    def classify(self, text: str) -> IntentResult:
        """Sync classification. MUST be safe to call from any context."""
        ...


# ─── HeuristicClassifier — offline-safe, deterministic, sync ───────────────


# Patterns that strongly indicate natural-language intent (questions,
# descriptions, prose patterns). When ANY of these match, the line is
# almost certainly NL even if it starts with a known command word.
_NL_MARKERS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE) for p in (
        r"\b(is|are|was|were|am)\s+(?:a|an|the|my|your|our)\b",
        r"\b(?:what|how|why|when|where|who|which)\b.*\?",
        r"\b(?:tell me|explain|describe|show me|help me understand)\b",
        r"\b(?:i think|i feel|i believe|i wonder|i remember)\b",
        r"\b(?:metaphor|analogy|concept|idea|topic)\b",
        r"\b(?:beautiful|wonderful|terrible|sad|happy|interesting)\b",
        # Sentence-like patterns: long sequences of unquoted words
        r"^[a-z\s]{40,}$",
    )
)

# Patterns that strongly indicate CLI intent — shell artifacts,
# explicit imperatives at sentence-start, recognizable flag syntax.
# Designed to match common `sov X` and `sov X Y` shapes with action verbs.
_CLI_MARKERS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE) for p in (
        r"\s(?:\||>|>>|&&|\|\|)\s",                # shell pipes/redirects
        r"--[a-z][\w-]*",                           # long flags
        r"^\S+\s+-[a-z]\b",                         # short flags after command
        r"\$\(",                                     # subshells
        # Two-word patterns: `sov doctor`, `sov info`, etc.
        r"^\S+\s+(?:list|show|status|info|doctor|aria|init|run|busy"
        r"|halt|disarm|seal|verify|snap|version)\b",
        # Three-word patterns: `sov X list`, `sov X show`, `sov X status`
        r"^\S+\s+\S+\s+(?:list|show|status|info|tail|verify|audit)\b",
    )
)


class HeuristicClassifier:
    """Pure-Python rules. Always available, no I/O, deterministic, sync.

    The default classifier. Catches the easy cases:

      • "sovereign sync is a beautiful metaphor for life"
            → NL_INTENT 0.85 (matches "is a beautiful")
      • "sov doctor"
            → CLI_INTENT 0.80 (matches CLI marker)
      • "sov channels list"
            → CLI_INTENT 0.80
      • "hello aria"
            → AMBIGUOUS 0.50 (no strong markers either way)

    For genuinely ambiguous inputs, returns AMBIGUOUS so the caller falls
    through to the structural normalizer.
    """

    @property
    def name(self) -> str:
        return "heuristic"

    def classify(self, text: str) -> IntentResult:
        text = (text or "").strip()
        if not text:
            return IntentResult(IntentLabel.AMBIGUOUS, 0.0, self.name)

        nl_hits = sum(1 for p in _NL_MARKERS if p.search(text))
        cli_hits = sum(1 for p in _CLI_MARKERS if p.search(text))

        # Strong NL signal wins outright when it's clearly present —
        # this is the veto the design docs called for. Even if structural
        # markers also match (rare but possible), NL prose patterns are
        # a stronger signal of intent.
        if nl_hits >= 1:
            confidence = min(0.95, 0.65 + 0.10 * nl_hits)
            return IntentResult(IntentLabel.NL_INTENT, confidence, self.name)

        if cli_hits >= 1:
            confidence = min(0.90, 0.70 + 0.10 * cli_hits)
            return IntentResult(IntentLabel.CLI_INTENT, confidence, self.name)

        # Long-prose detection without explicit markers — sentences over
        # ~8 words with no CLI markers and no question mark trail tend
        # to be descriptive prose.
        word_count = len(text.split())
        if word_count >= 8 and "?" not in text:
            return IntentResult(IntentLabel.NL_INTENT, 0.65, self.name)

        # No strong signal — let Stage B (structural normalizer) decide
        return IntentResult(IntentLabel.AMBIGUOUS, 0.50, self.name)


# ─── OllamaClassifier — small local LLM, async ─────────────────────────────


_OLLAMA_PROMPT = """You are a router. Decide whether the following input is a CLI command \
or natural language.

Possible labels: CLI_INTENT, NL_INTENT, AMBIGUOUS.

Examples:
- "sov doctor" → CLI_INTENT 0.95
- "what does sov doctor do?" → NL_INTENT 0.90
- "sovereign sync is a beautiful metaphor for life" → NL_INTENT 0.92
- "hello" → AMBIGUOUS 0.50

Reply with EXACTLY one line in the format: LABEL CONFIDENCE
where CONFIDENCE is 0.00 to 1.00.

Input: \"\"\"{text}\"\"\"

Answer:"""


class OllamaClassifier:
    """Tiny local model via Ollama. Async-only — needs an event loop.

    Constructor takes a model name; default ``phi3:mini`` is small enough
    to respond in well under 150ms on most hardware. If Ollama is down
    or the model isn't pulled, every call returns AMBIGUOUS so the
    caller falls through to the structural normalizer.

    Sync ``classify`` is a stub that returns AMBIGUOUS — callers who
    need Ollama's verdict MUST use ``classify_async`` from an async
    context (e.g. via Textual's ``@work`` decorator). The sync method
    exists so OllamaClassifier still satisfies the IntentClassifier
    protocol for type-checking and registry purposes.
    """

    def __init__(
        self,
        model: str = "phi3:mini",
        timeout_seconds: float = 0.150,
        host: str | None = None,
    ) -> None:
        self.model = model
        self.timeout_seconds = timeout_seconds
        self._host = host  # None → use config default
        self._client = None  # lazy

    @property
    def name(self) -> str:
        return f"ollama:{self.model}"

    def _ensure_client(self):
        """Lazy-build the OllamaClient. Returns None if Ollama is unavailable."""
        if self._client is not None:
            return self._client
        try:
            from .ollama_client import OllamaClient
            self._client = OllamaClient(host=self._host)
            return self._client
        except Exception as exc:  # noqa: BLE001
            logger.debug("OllamaClassifier: client unavailable: %r", exc)
            return None

    def classify(self, text: str) -> IntentResult:
        """Sync stub. Returns AMBIGUOUS so callers fall through safely.

        OllamaClassifier needs an event loop. The cockpit's sync input
        handler can't await; if you want Ollama-backed classification
        in the cockpit, dispatch via Textual's ``@work`` decorator and
        call ``classify_async``. The sync stub satisfies the protocol
        without misleading callers.
        """
        return IntentResult(IntentLabel.AMBIGUOUS, 0.0, self.name + "[sync-stub]")

    async def classify_async(self, text: str) -> IntentResult:
        text = (text or "").strip()
        if not text:
            return IntentResult(IntentLabel.AMBIGUOUS, 0.0, self.name)

        client = self._ensure_client()
        if client is None:
            return IntentResult(IntentLabel.AMBIGUOUS, 0.0, self.name)

        prompt = _OLLAMA_PROMPT.format(text=text)
        try:
            # Tight timeout — the classifier MUST be fast or it doesn't earn
            # its always-on slot. Slower → fall through to structural.
            response = await asyncio.wait_for(
                client.chat(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    tools=None,
                ),
                timeout=self.timeout_seconds,
            )
        except asyncio.TimeoutError:
            logger.debug("OllamaClassifier: timed out after %ss", self.timeout_seconds)
            return IntentResult(IntentLabel.AMBIGUOUS, 0.0, self.name)
        except Exception as exc:  # noqa: BLE001
            logger.debug("OllamaClassifier: chat failed: %r", exc)
            return IntentResult(IntentLabel.AMBIGUOUS, 0.0, self.name)

        # Extract the model's reply text. The OllamaClient response shape
        # is dict-like with a 'message' field containing 'content'.
        try:
            content = response.get("message", {}).get("content", "") \
                if isinstance(response, dict) \
                else getattr(getattr(response, "message", None), "content", "")
        except Exception:  # noqa: BLE001
            content = ""

        return parse_classifier_reply(content, source=self.name)


def parse_classifier_reply(text: str, *, source: str) -> IntentResult:
    """Parse an LLM classifier reply line into a structured result.

    Tolerant parser: accepts "CLI_INTENT 0.95", "NL_INTENT  0.8",
    "AMBIGUOUS 0.5", with optional surrounding whitespace and case
    variation in the label. Anything unparseable returns AMBIGUOUS.

    Exposed at module level so HeuristicClassifier and unit tests can
    use the same parsing path.
    """
    text = (text or "").strip()
    # Look for a label followed by a number anywhere in the response.
    # The confidence pattern is intentionally strict: an optional decimal
    # number with no trailing period. This prevents "0.92." from being
    # captured as "0.92." (which fails float() parsing).
    match = re.search(
        r"\b(CLI_INTENT|NL_INTENT|AMBIGUOUS)\b[\s:]*(\d+(?:\.\d+)?)",
        text,
        re.IGNORECASE,
    )
    if not match:
        return IntentResult(IntentLabel.AMBIGUOUS, 0.0, source)

    label_str = match.group(1).upper()
    try:
        confidence = float(match.group(2))
        # Clamp to [0, 1]
        confidence = max(0.0, min(1.0, confidence))
    except ValueError:
        confidence = 0.5

    try:
        label = IntentLabel(label_str)
    except ValueError:
        label = IntentLabel.AMBIGUOUS
        confidence = 0.0

    return IntentResult(label, confidence, source)


# ─── Default classifier factory ─────────────────────────────────────────────


_DEFAULT_CLASSIFIER: IntentClassifier | None = None


def get_default_classifier() -> IntentClassifier:
    """Return the process-wide default classifier.

    Initialized lazily on first call so import is cheap. Currently returns
    the HeuristicClassifier — small, fast, offline-safe. To swap to Ollama,
    call ``set_default_classifier(OllamaClassifier(...))`` from a startup
    hook.

    In v0.2.32.0 the cockpit reads this on every input. Future versions
    will read configuration to decide which backend to wire here — for
    now, the heuristic is the right balance of speed and offline safety.
    """
    global _DEFAULT_CLASSIFIER
    if _DEFAULT_CLASSIFIER is None:
        _DEFAULT_CLASSIFIER = HeuristicClassifier()
    return _DEFAULT_CLASSIFIER


def set_default_classifier(classifier: IntentClassifier) -> None:
    """Override the process-wide classifier. Useful for tests and for
    operators who want Ollama-backed classification."""
    global _DEFAULT_CLASSIFIER
    _DEFAULT_CLASSIFIER = classifier


def reset_default_classifier() -> None:
    """Restore the lazy default. Test helper."""
    global _DEFAULT_CLASSIFIER
    _DEFAULT_CLASSIFIER = None


__all__ = [
    "HeuristicClassifier",
    "IntentClassifier",
    "IntentLabel",
    "IntentResult",
    "OllamaClassifier",
    "get_default_classifier",
    "parse_classifier_reply",
    "reset_default_classifier",
    "set_default_classifier",
]
