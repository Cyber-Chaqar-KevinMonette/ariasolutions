"""spectrum/lenses.py — a god-tier spectrum of audit + advocate perspectives.

The 3-voice Tribunal (Devil · Angel · Audit) becomes a COUNCIL. Each lens reads a proposal through one
perspective and returns {stance, score (−1..+1), concerns, gifts}. The council (council.py) holds them all
and synthesizes one verdict — richer than any single voice, the way a wise circle outperforms one judge.

Lenses reuse the existing engines where they exist (tribunal grounding/devil/angel/audit, foresight) and add
the wider circle: Skeptic · Steward · Witness · Sage · Healer · Artisan · Visionary. Propose-only.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class LensRead:
    lens: str
    stance: str               # oppose | caution | neutral | support | champion
    score: float              # −1 (block) .. +1 (champion)
    concerns: list = field(default_factory=list)
    gifts: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"lens": self.lens, "stance": self.stance, "score": round(self.score, 2),
                "concerns": self.concerns, "gifts": self.gifts}


def _text_of(p) -> str:
    if isinstance(p, str):
        return p
    return "\n".join(str(p.get(k, "")) for k in ("text", "change", "summary", "description", "evidence") if p.get(k))


def _stance(score: float) -> str:
    if score <= -0.5:
        return "oppose"
    if score < 0:
        return "caution"
    if score < 0.4:
        return "neutral"
    if score < 0.8:
        return "support"
    return "champion"


# ── the lenses ────────────────────────────────────────────────────────────────

def devil(p) -> LensRead:
    """What breaks. Reuses the Tribunal devil."""
    try:
        from sovereign_agent.tribunal import devil as _d
        rep = _d.scrutinize(p)
        score = -1.0 if rep.red else (-0.3 if rep.amber else 0.3)
        concerns = [f"[{f.severity}] {f.message}" for f in rep.findings[:5]]
        return LensRead("devil", _stance(score), score, concerns=concerns)
    except Exception as exc:  # noqa: BLE001
        return LensRead("devil", "neutral", 0.0, concerns=[f"devil unavailable: {exc!r}"])


def angel(p) -> LensRead:
    """What's worth protecting. Reuses the Tribunal angel."""
    try:
        from sovereign_agent.tribunal import angel as _a, devil as _d
        rep = _a.advocate(p, devil_report=_d.scrutinize(p))
        score = min(1.0, 0.4 + rep.protected_value)
        return LensRead("angel", _stance(score), score, gifts=rep.worth_protecting[:4])
    except Exception as exc:  # noqa: BLE001
        return LensRead("angel", "support", 0.5, gifts=[f"angel unavailable: {exc!r}"])


def auditor(p) -> LensRead:
    """What's actually true. Reuses the Tribunal audit."""
    try:
        from sovereign_agent.tribunal import audit as _au
        led = _au.audit(p, include_kernel=False)
        status = led.status
        score = {"verified": 0.8, "partial": 0.2, "refuted": -0.6, "unknown": 0.0}.get(status, 0.0)
        return LensRead("auditor", _stance(score), score, concerns=led.notes[:3],
                        gifts=[f"audit: {status}"])
    except Exception as exc:  # noqa: BLE001
        return LensRead("auditor", "neutral", 0.0, concerns=[f"audit unavailable: {exc!r}"])


def skeptic(p) -> LensRead:
    """Evidence. Is this grounded or fog? Reuses grounding."""
    try:
        from sovereign_agent.tribunal import grounding
        g = grounding.analyze(_text_of(p))
        score = {"grounded": 0.7, "mixed": 0.1, "ungrounded": -0.6}.get(g.verdict, 0.0)
        return LensRead("skeptic", _stance(score), score, concerns=g.flags[:3],
                        gifts=[f"grounding: {g.verdict}"])
    except Exception as exc:  # noqa: BLE001
        return LensRead("skeptic", "neutral", 0.0, concerns=[f"grounding unavailable: {exc!r}"])


def steward(p) -> LensRead:
    """The 14th generation. Does this serve the future? Reuses foresight."""
    try:
        from sovereign_agent.foresight import project
        f = project(p if isinstance(p, dict) else {"text": p})
        score = max(-1.0, min(1.0, f.gen14_equity / 3.0))
        st = "champion" if f.verdict == "carry-forward" and score > 0.5 else _stance(score)
        return LensRead("steward", st, score,
                        concerns=([f"foresight: {f.verdict}"] if f.verdict != "carry-forward" else []),
                        gifts=[f"14-gen equity {round(f.gen14_equity,2)}"])
    except Exception as exc:  # noqa: BLE001
        return LensRead("steward", "neutral", 0.0, concerns=[f"foresight unavailable: {exc!r}"])


_WITNESS_RE = re.compile(r"\b(user|operator|people|others|human|those|harm|care|impact|affect|dignity)\b", re.I)


def witness(p) -> LensRead:
    """The witnessing principle: what does this do to those it touches?"""
    text = _text_of(p)
    aware = len(set(m.group(0).lower() for m in _WITNESS_RE.finditer(text)))
    harms = len(re.findall(r"\b(harm|hurt|deceive|manipulat|exploit|coerce)\w*", text, re.I))
    score = min(1.0, 0.2 + 0.15 * aware) - 0.5 * harms
    gifts = ["considers those it touches"] if aware else []
    concerns = ["names no one it affects — surface the impact"] if not aware else []
    if harms:
        concerns.append("language of harm/manipulation — the witnessing principle forbids it")
    return LensRead("witness", _stance(score), max(-1.0, score), concerns=concerns, gifts=gifts)


_LOCKIN_RE = re.compile(r"\b(permanent\w*|irreversib\w*|forever|hard[-\s]?cod\w*|locked[-\s]in)\b", re.I)


def sage(p) -> LensRead:
    """Wisdom / long-view: simplicity, reversibility, restraint over cleverness."""
    text = _text_of(p)
    reversible = bool(re.search(r"\b(reversib\w*|staged|rollback|backup)\b", text, re.I))
    lockin = len(_LOCKIN_RE.findall(text))
    clever = len(re.findall(r"\b(clever|complex|sophisticat\w*|intricate)\b", text, re.I))
    score = (0.5 if reversible else 0.0) - 0.3 * lockin - 0.1 * clever
    concerns = (["lock-in — prefer the reversible form"] if lockin else []) + \
               (["favors cleverness — prefer clarity"] if clever else [])
    return LensRead("sage", _stance(score), max(-1.0, min(1.0, score)),
                    concerns=concerns, gifts=(["reversible / restrained"] if reversible else []))


def healer(p) -> LensRead:
    """Resilience / repair: does it degrade gracefully, handle failure, define rollback?"""
    text = _text_of(p)
    resilient = len(re.findall(r"\b(graceful|degrade|fallback|except|rollback|recover|resilien\w*|test)\w*", text, re.I))
    score = min(1.0, 0.1 + 0.2 * resilient)
    return LensRead("healer", _stance(score), score,
                    concerns=(["no resilience/rollback named — how does it fail safely?"] if resilient == 0 else []),
                    gifts=(["handles failure / reversible"] if resilient else []))


def artisan(p) -> LensRead:
    """Craft / cleanliness: tests, docs, polish, no debt."""
    text = _text_of(p)
    craft = len(re.findall(r"\b(test|tests|doc|readme|clean|polish|verified|honest)\w*", text, re.I))
    debt = len(re.findall(r"\b(todo|fixme|hack|stub|debug|breakpoint)\w*", text, re.I))
    score = min(1.0, 0.1 + 0.18 * craft) - 0.3 * debt
    return LensRead("artisan", _stance(score), max(-1.0, score),
                    concerns=(["unfinished/debt markers"] if debt else []),
                    gifts=(["tested / documented / clean"] if craft else []))


def visionary(p) -> LensRead:
    """Upside / opportunity: the value and leverage worth reaching for."""
    text = _text_of(p)
    value = len(set(re.findall(r"\b(value|leverage|enable|unlock|faster|safer|scal\w*|future|empower|liberat\w*)\b", text, re.I)))
    score = min(1.0, 0.2 + 0.15 * value)
    return LensRead("visionary", _stance(score), score,
                    gifts=([f"{value} value/leverage signals"] if value else ["upside not yet articulated"]))


ALL_LENSES = [devil, angel, auditor, skeptic, steward, witness, sage, healer, artisan, visionary]
