"""patcher.py — Wellbeing round W3: standing audit + measured angel lens.

Kevin: *"whatever brings her value, perspective, and insight into her self
and her actions."* Almost entirely composition — the Tribunal and Advocate
Spectrum were already rich; they were just never STANDING for wellbeing,
and the angel lens only ever saw one live text sample instead of W1's
persisted composite.

Patches:
  1. spectrum/lenses.py — `angel()` prefers W1's persisted composite
     (`love_grade`/`flourishing_verdict`) over a live-only
     `tribunal.angel.advocate()` call when present; byte-identical
     fallback otherwise. Mirrors `artisan()`/`skeptic()`'s exact patch
     shape.
  2. stewardship/wellbeing_sentinel.py — a second standing-audit phase at
     W1's marked `{MARK}` extension seam: convene Tribunal + Advocate
     Spectrum over the sentinel's own just-computed pass, log via the
     now-generic `log_to_diagnosis(..., prefix="WELL")` (the `prefix`
     parameter Grounding round's G3 already added — no further API
     change needed here).

Anchored transforms only; MARK-idempotent; a moved anchor raises loudly."""
from __future__ import annotations

MARK = "wellbeing-tribunal-d"


class PatchError(Exception):
    pass


def _replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if text.count(old) != 1:
        raise PatchError(f"{label}: expected 1 anchor, found {text.count(old)}")
    return text.replace(old, new, 1)


# ── 1. spectrum/lenses.py — angel prefers the persisted composite ────────

ANGEL_ANCHOR = '''def angel(p) -> LensRead:
    """What's worth protecting. Reuses the Tribunal angel."""
    try:
        from sovereign_agent.tribunal import angel as _a, devil as _d
        rep = _a.advocate(p, devil_report=_d.scrutinize(p))
        score = min(1.0, 0.4 + rep.protected_value)
        return LensRead("angel", _stance(score), score, gifts=rep.worth_protecting[:4])
    except Exception as exc:  # noqa: BLE001
        return LensRead("angel", "support", 0.5, gifts=[f"angel unavailable: {exc!r}"])
'''

ANGEL_NEW = f'''def angel(p) -> LensRead:
    """What's worth protecting. Reuses the Tribunal angel.

    {MARK} — when the proposal carries a REAL persisted composite
    (love_grade / flourishing_verdict, from wellbeing.ledger's standing
    pass), that overrides the live-only check below: measured beats
    one-shot. Absent those keys, byte-identical fallback to today's
    live-only check — every existing bare-string or plain-dict caller is
    unaffected.
    """
    if isinstance(p, dict) and ("love_grade" in p or "flourishing_verdict" in p):
        concerns: list = []
        gifts: list = []
        grade = p.get("love_grade", "D")
        score = {{"A": 0.8, "B": 0.4, "C": 0.0, "D": -0.5}}.get(grade, 0.0)
        gifts.append(f"measured love grade: {{grade}}")
        fv = p.get("flourishing_verdict", "")
        if fv == "reject-for-the-future":
            score = min(score, -0.6)
            concerns.append("flourishing verdict: reject-for-the-future (measured, not heuristic)")
        elif fv == "escalate":
            score = min(score, -0.2)
            concerns.append("flourishing verdict: escalate (measured, not heuristic)")
        score = max(-1.0, min(1.0, score))
        return LensRead("angel", _stance(score), score, concerns=concerns, gifts=gifts)
    try:
        from sovereign_agent.tribunal import angel as _a, devil as _d
        rep = _a.advocate(p, devil_report=_d.scrutinize(p))
        score = min(1.0, 0.4 + rep.protected_value)
        return LensRead("angel", _stance(score), score, gifts=rep.worth_protecting[:4])
    except Exception as exc:  # noqa: BLE001
        return LensRead("angel", "support", 0.5, gifts=[f"angel unavailable: {{exc!r}}"])
'''


def patch_angel(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    return _replace_once(text, ANGEL_ANCHOR, ANGEL_NEW, label="angel lens"), True


# ── 2. stewardship/wellbeing_sentinel.py — the standing phase ────────────

SENTINEL_ANCHOR = '''        # {MARK} — extension seam: W3 (aria-wellbeing-tribunal) hooks a
        # second standing-audit phase HERE, convening Tribunal + Advocate
        # Spectrum over this same real recent wellbeing pass, logged through
        # diagnosis.ConflictCatalog under type="ambiguity" prefix="WELL" —
        # mirrors quality_sentinel.py's/grounding_sentinel.py's own seams
        # and Q3's/G3's use of them exactly.
        return report'''

SENTINEL_NEW = '''        # wellbeing-tribunal-d — the standing phase: convene BOTH Tribunal and
        # Advocate Spectrum over this same real recent wellbeing pass, log
        # through the diagnosis catalog — the standing counterpart to
        # TribunalSentinel's narrow hardcoded-string self-check. Best-effort:
        # a scrutiny failure here must never break the wellbeing scan itself.
        try:
            if events:
                from sovereign_agent.tools.companion_tools import _build_value_report

                value_report = _build_value_report(events, None)
                proposal = {
                    "text": value_report.get("summary", ""),
                    "change": f"wellbeing pass {result.pass_id}",
                    "love_grade": result.love_grade,
                    "flourishing_verdict": result.flourishing_verdict,
                }
                from sovereign_agent.tribunal import convene
                from sovereign_agent.tribunal.tribunal import log_to_diagnosis

                tv = convene(proposal, include_kernel=False)
                case_id = log_to_diagnosis(proposal, tv, self._data_dir, prefix="WELL")
                standing = {"verdict": tv.verdict, "case_id": case_id}
                try:
                    from sovereign_agent.spectrum import convene_spectrum

                    cv = convene_spectrum(proposal)
                    standing["spectrum_verdict"] = cv.verdict
                    standing["spectrum_opposed"] = cv.opposed
                except Exception:  # noqa: BLE001 — spectrum is optional
                    pass
                self.save_catalog(standing, name="standing-audit")
        except Exception:  # noqa: BLE001 — a scrutiny failure never breaks the scan
            pass
        return report'''


def patch_sentinel(text: str) -> tuple[str, bool]:
    if "wellbeing-tribunal-d" in text:
        return text, False
    return _replace_once(text, SENTINEL_ANCHOR, SENTINEL_NEW,
                         label="wellbeing_sentinel standing phase"), True


ALL_PATCHES = {
    "spectrum/lenses.py": patch_angel,
    "stewardship/wellbeing_sentinel.py": patch_sentinel,
}
