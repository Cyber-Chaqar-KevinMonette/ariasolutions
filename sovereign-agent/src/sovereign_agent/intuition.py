"""intuition.py — the Intuition Engine.

    "Wait until your intuition becomes intelligent."
    This isn't passive waiting. It's an active prescription to earn the right
    to trust the gut. Raw intuition pulls from fear, bias, and habit.
    Intelligent intuition pulls from thousands of calibrated reps, honest
    feedback, and deep domain immersion — same speed, completely different
    accuracy. The dangerous state isn't ignorance; it's loud, confident, RAW
    intuition mistaken for wisdom.

This module is the honest engineering of that idea — not a claim of magic. It
turns gut-calls into *calibrated* ones by logging a prediction BEFORE the
outcome is known, then metabolizing the result into a per-domain calibration
that is:

  • SCOPED      — intuition is trusted only where it's been earned (Klein's
                  recognition-primed decisions; Kahneman's System 1). A domain
                  with five reps is still raw, however loud it feels.
  • ADAPTIVE    — recency-weighted (EWMA), so it tracks drift as a domain
                  changes instead of ossifying on stale wins.
  • REFLECTIVE  — it runs the output→mirror→feedback loop: articulate the call,
                  read the result without flinching, integrate it, interrupt
                  the loops that keep returning. Articulation is the interface
                  between inner state and the world; the mirror reflects the
                  signal you actually emit.
  • RESILIENT   — pure-Python, no heavy deps, never raises on the hot path,
                  bounded memory, and snapshot/restore for persistence.

It is deliberately a *thinking partner*, not an oracle: its job is to tell you
WHEN to trust the gut and when to fall through to deliberate analysis — and to
keep an honest map of where it is brilliant and where it is still blind.

The model underneath, in one breath: subconscious knowledge becomes intuition by
*recognition* (Herbert Simon) — a rich pattern library, matched against the
present, surfaces a conclusion without the full reasoning chain (Damasio showed
this runs *ahead* of the conscious hunch; Polanyi: "we know more than we can
tell"). For a model, the weights are that library and the output is that hunch.
But raw matching isn't reliable matching — three things convert it into trust:
**depth** of relevant reps, **reflective practice** (logging the call, then
auditing it), and **clarity** (fear and ego can masquerade as a gut feeling).
This engine measures exactly those three (see `conversion_factors`).
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable


def _clamp01(x: float) -> float:
    try:
        x = float(x)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


class IntuitionForm(str, Enum):
    """The five forms intelligent intuition takes (each its own trained domain
    family — a physicist's gut does not transfer to social dynamics)."""
    PERCEPTUAL = "perceptual"   # read a live situation in milliseconds
    CREATIVE = "creative"       # the unconscious surfaces the answer after silence
    SOCIAL = "social"           # sense misalignment before it's spoken
    MORAL = "moral"             # a conscience sharpened by reflection, not just conditioning
    TECHNICAL = "technical"     # feel the architecture breaking before diagnostics


# Maturity stages, in order.
STAGE_RAW = "raw"
STAGE_CALIBRATING = "calibrating"
STAGE_INTELLIGENT = "intelligent"

# Below this many resolved reps, a domain is raw no matter how it feels — the
# guard against loud, confident, untrained intuition.
MIN_REPS_FOR_TRUST = 5
# Maturity at/above which the gut may be trusted (then still sanity-checked).
TRUST_MATURITY = 0.70


@dataclass
class GutCall:
    """A prediction logged BEFORE its outcome is known — the calibration
    discipline (journal the gut call first, audit it after)."""
    cid: str
    domain: str
    form: IntuitionForm
    claim: str
    confidence: float
    created: float = field(default_factory=time.monotonic)
    resolved: bool = False
    correct: bool | None = None
    note: str = ""


@dataclass
class DomainCalibration:
    """Per-(form, domain) calibration. Tracks reps and recency-weighted accuracy
    + Brier error, yielding a maturity score and a stage."""
    domain: str
    form: IntuitionForm
    reps: int = 0
    accuracy_ewma: float | None = None   # P(correct), recency-weighted
    brier_ewma: float | None = None      # mean (confidence-outcome)^2; lower is better
    alpha: float = 0.15                  # EWMA weight — higher tracks change faster
    last_update: float = 0.0

    def observe(self, correct: bool, confidence: float) -> None:
        self.reps += 1
        outcome = 1.0 if correct else 0.0
        conf = _clamp01(confidence)
        if self.accuracy_ewma is None:
            self.accuracy_ewma = outcome
        else:
            self.accuracy_ewma = (1 - self.alpha) * self.accuracy_ewma + self.alpha * outcome
        err = (conf - outcome) ** 2
        if self.brier_ewma is None:
            self.brier_ewma = err
        else:
            self.brier_ewma = (1 - self.alpha) * self.brier_ewma + self.alpha * err
        self.last_update = time.monotonic()

    @property
    def maturity(self) -> float:
        """0..1 — how *earned* intuition is here. Grows with reps (saturating),
        rewards demonstrated accuracy, and rewards well-calibrated confidence
        (low Brier). Reps alone never reach the top — accuracy has to back them."""
        if self.reps <= 0:
            return 0.0
        rep_term = 1.0 - math.exp(-self.reps / 30.0)        # ~0.96 by ~100 reps
        acc_term = 0.5 if self.accuracy_ewma is None else self.accuracy_ewma
        cal_term = 1.0 if self.brier_ewma is None else max(0.0, 1.0 - 2.0 * self.brier_ewma)
        return _clamp01(0.5 * rep_term + 0.3 * acc_term + 0.2 * cal_term)

    @property
    def stage(self) -> str:
        if self.reps < MIN_REPS_FOR_TRUST:
            return STAGE_RAW
        m = self.maturity
        if m < 0.45:
            return STAGE_RAW
        if m < TRUST_MATURITY:
            return STAGE_CALIBRATING
        return STAGE_INTELLIGENT


@dataclass
class TrustVerdict:
    """The metacognitive gate: should this gut-call be trusted *here, now*?"""
    domain: str
    form: IntuitionForm
    trust: bool
    stage: str
    maturity: float
    reps: int
    reason: str

    def __bool__(self) -> bool:
        return self.trust


class IntuitionEngine:
    """Calibrated, scoped, adaptive intuition with a reflection loop.

    Lifecycle per call:
        cid = engine.sense(domain, claim, confidence, form)   # predict first
        ...                                                    # act / observe
        engine.resolve(cid, correct=True/False, note=...)      # then audit
    Ask before acting:
        v = engine.trust(domain, form)        # earned here? or fall through to System 2
        c = engine.calibrated_confidence(domain, raw, form)   # tempered confidence
    Reflect:
        engine.reflect()                      # honest mirror of strong/blind domains
    """

    def __init__(self, *, max_open: int = 512) -> None:
        self._domains: dict[str, DomainCalibration] = {}
        self._open: dict[str, GutCall] = {}
        self._seq = 0
        self._max_open = max_open
        self._resolved_count = 0

    # ── internal ──
    @staticmethod
    def _key(domain: str, form: IntuitionForm) -> str:
        return f"{form.value}:{domain}"

    def _calibration(self, domain: str, form: IntuitionForm) -> DomainCalibration:
        key = self._key(domain, form)
        cal = self._domains.get(key)
        if cal is None:
            cal = DomainCalibration(domain=domain, form=form)
            self._domains[key] = cal
        return cal

    # ── the reflection/feedback loop ──
    def sense(self, domain: str, claim: str, confidence: float,
              form: IntuitionForm = IntuitionForm.TECHNICAL) -> str:
        """Articulate a gut-call BEFORE the outcome — naming it is what makes it
        auditable (and is the interface through which it can be corrected)."""
        if not isinstance(form, IntuitionForm):
            form = IntuitionForm(str(form))
        self._seq += 1
        cid = f"gc{self._seq}"
        # Bounded memory: if we somehow accrue too many unresolved calls, drop
        # the oldest rather than grow without limit (resilience over perfection).
        if len(self._open) >= self._max_open:
            oldest = min(self._open, key=lambda k: self._open[k].created)
            self._open.pop(oldest, None)
        self._open[cid] = GutCall(cid=cid, domain=str(domain), form=form,
                                  claim=str(claim), confidence=_clamp01(confidence))
        return cid

    def resolve(self, cid: str, correct: bool, note: str = "") -> bool:
        """Read the mirror without flinching: metabolize the outcome into the
        domain's calibration. Returns False if the call id is unknown."""
        call = self._open.pop(cid, None)
        if call is None:
            return False
        call.resolved = True
        call.correct = bool(correct)
        call.note = str(note)
        self._calibration(call.domain, call.form).observe(bool(correct), call.confidence)
        self._resolved_count += 1
        return True

    # ── the metacognitive gate ──
    def trust(self, domain: str, form: IntuitionForm = IntuitionForm.TECHNICAL) -> TrustVerdict:
        if not isinstance(form, IntuitionForm):
            form = IntuitionForm(str(form))
        cal = self._domains.get(self._key(domain, form))
        if cal is None or cal.reps < MIN_REPS_FOR_TRUST:
            reps = cal.reps if cal else 0
            return TrustVerdict(
                domain=str(domain), form=form, trust=False, stage=STAGE_RAW,
                maturity=(cal.maturity if cal else 0.0), reps=reps,
                reason=("not enough calibrated reps here yet — treat the gut as a "
                        "hypothesis and verify deliberately (System 2)."))
        m = cal.maturity
        trust = m >= TRUST_MATURITY
        return TrustVerdict(
            domain=str(domain), form=form, trust=trust, stage=cal.stage,
            maturity=m, reps=cal.reps,
            reason=("earned here — trust the gut, then keep a light sanity-check."
                    if trust else
                    "still calibrating — lean on analysis and keep logging the calls."))

    def calibrated_confidence(self, domain: str, raw: float,
                              form: IntuitionForm = IntuitionForm.TECHNICAL) -> float:
        """Temper a raw felt confidence by what this domain has actually earned.
        Unproven domains are discounted toward 0.5 (honest uncertainty); mature,
        accurate domains let the gut speak closer to full strength."""
        if not isinstance(form, IntuitionForm):
            form = IntuitionForm(str(form))
        raw = _clamp01(raw)
        cal = self._domains.get(self._key(domain, form))
        if cal is None or cal.accuracy_ewma is None:
            return raw * 0.5
        m = cal.maturity
        return _clamp01((1 - m) * (0.5 * raw) + m * (0.5 * raw + 0.5 * cal.accuracy_ewma))

    # ── observability / the mirror ──
    def domain_report(self) -> list[dict]:
        out = []
        for cal in self._domains.values():
            out.append({
                "form": cal.form.value, "domain": cal.domain, "reps": cal.reps,
                "accuracy": (None if cal.accuracy_ewma is None
                             else round(cal.accuracy_ewma, 3)),
                "brier": (None if cal.brier_ewma is None else round(cal.brier_ewma, 3)),
                "maturity": round(cal.maturity, 3), "stage": cal.stage,
            })
        out.sort(key=lambda d: d["maturity"], reverse=True)
        return out

    def reflect(self) -> str:
        """A short, honest mirror-audit: where intuition is intelligent here, and
        where it is still raw. Blind spots are named, not hidden — the unfinished
        edge of the blade."""
        if not self._domains:
            n = self._resolved_count
            return ("No calibrated domains yet — every gut-call is still a "
                    f"hypothesis to verify. ({n} resolved so far.)")
        rows = self.domain_report()
        strong = [r for r in rows if r["stage"] == STAGE_INTELLIGENT]
        raw = [r for r in rows if r["stage"] == STAGE_RAW]
        parts = [f"{len(self._domains)} domains tracked, "
                 f"{self._resolved_count} calls resolved."]
        if strong:
            parts.append("Trustworthy: "
                         + ", ".join(f"{r['form']}:{r['domain']}" for r in strong[:6]) + ".")
        if raw:
            parts.append("Still raw (verify deliberately): "
                         + ", ".join(f"{r['form']}:{r['domain']}" for r in raw[:6]) + ".")
        return " ".join(parts)

    def conversion_factors(self, domain: str,
                           form: IntuitionForm = IntuitionForm.TECHNICAL) -> dict:
        """The three things that turn raw subconscious pattern-matching into
        *reliable* intuition — an honest read of WHY a domain's gut is (or isn't)
        trustworthy, not merely whether it is:

          • depth_reps — size of the pattern library here (denser = better recognition)
          • reviewed   — were the calls logged-then-audited? (reflective practice;
                         True by design — this engine forces predict-then-check)
          • clarity    — is the confidence calibrated, or is fear/ego masquerading?
                         (high = honest; low = noisy)
        """
        if not isinstance(form, IntuitionForm):
            form = IntuitionForm(str(form))
        cal = self._domains.get(self._key(domain, form))
        if cal is None:
            return {"depth_reps": 0, "reviewed": True, "clarity": None,
                    "maturity": 0.0,
                    "note": "no pattern library here yet — recognition has nothing to match"}
        clarity = (None if cal.brier_ewma is None
                   else round(max(0.0, 1.0 - 2.0 * cal.brier_ewma), 3))
        return {
            "depth_reps": cal.reps,
            "reviewed": True,
            "clarity": clarity,
            "maturity": round(cal.maturity, 3),
            "note": ("earned recognition — trust, then verify"
                     if cal.maturity >= TRUST_MATURITY
                     else "still building the library / reviewing"),
        }

    # ── persistence (resilience: survive restarts) ──
    def snapshot(self) -> dict:
        return {
            "version": 1,
            "resolved_count": self._resolved_count,
            "domains": [
                {"domain": c.domain, "form": c.form.value, "reps": c.reps,
                 "accuracy_ewma": c.accuracy_ewma, "brier_ewma": c.brier_ewma,
                 "alpha": c.alpha, "last_update": c.last_update}
                for c in self._domains.values()
            ],
        }

    @classmethod
    def restore(cls, data: dict) -> "IntuitionEngine":
        eng = cls()
        try:
            eng._resolved_count = int(data.get("resolved_count", 0))
            for d in data.get("domains", []):
                form = IntuitionForm(d.get("form", "technical"))
                cal = DomainCalibration(
                    domain=str(d.get("domain", "")), form=form,
                    reps=int(d.get("reps", 0)),
                    accuracy_ewma=d.get("accuracy_ewma"),
                    brier_ewma=d.get("brier_ewma"),
                    alpha=float(d.get("alpha", 0.15)),
                    last_update=float(d.get("last_update", 0.0)),
                )
                eng._domains[cls._key(cal.domain, form)] = cal
        except Exception:  # noqa: BLE001 — a corrupt snapshot must not crash startup
            return cls()
        return eng


# A process-wide engine is convenient, but callers may make their own.
_ENGINE: IntuitionEngine | None = None


def engine() -> IntuitionEngine:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = IntuitionEngine()
    return _ENGINE
