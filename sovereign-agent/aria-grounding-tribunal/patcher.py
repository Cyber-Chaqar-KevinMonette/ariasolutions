"""patcher.py — Grounding round G3: standing audit + measured skeptic lens.

Kevin: *"how to be a scientist, and when to be genuinely grounded."*
Almost entirely composition — the Tribunal and Advocate Spectrum were
already rich; they were just never STANDING for grounding, and the
skeptic lens only ever saw one live text sample instead of G1's richer
persisted composite (which also folds in belief confidence and
hypothesis track record).

Patches:
  1. tribunal/tribunal.py — `log_to_diagnosis()` gains an optional
     `prefix` parameter (default "TRIB", unchanged for every existing
     caller) so a standing grounding case can log under "GRND" instead —
     distinguishing origin in the case-ID namespace without adding a new
     `diagnosis.CONFLICT_TYPES` member (same "ambiguity" type either way,
     per the convention this file's own docstring already states).
  2. spectrum/lenses.py — `skeptic()` prefers G1's persisted composite
     (`grounding_verdict`/`epistemic_score`) over a live-only
     `grounding.analyze()` call when present; byte-identical fallback
     otherwise. Mirrors `artisan()`'s measured-data patch exactly.
  3. stewardship/grounding_sentinel.py — a second standing-audit phase at
     G1's marked `{MARK}` extension seam: convene Tribunal + Advocate
     Spectrum over the sentinel's own just-computed pass, log through the
     now-prefix-aware `log_to_diagnosis()` under `prefix="GRND"`.

Anchored transforms only; MARK-idempotent; a moved anchor raises loudly."""
from __future__ import annotations

MARK = "grounding-tribunal-d"


class PatchError(Exception):
    pass


def _replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if text.count(old) != 1:
        raise PatchError(f"{label}: expected 1 anchor, found {text.count(old)}")
    return text.replace(old, new, 1)


# ── 1. tribunal/tribunal.py — log_to_diagnosis gains an optional prefix ──

LOG_TO_DIAGNOSIS_ANCHOR = '''def log_to_diagnosis(proposal: dict | str, verdict: Verdict, data_dir: Path, *, actor: str = "aria") -> str | None:
    """Record a tribunal case in the diagnosis catalog (Conflict → Diagnosis → Resolution)."""
    try:
        from sovereign_agent.diagnosis import ConflictCatalog
        cat = ConflictCatalog(Path(data_dir) / "diagnosis")
        title = (proposal.get("change") if isinstance(proposal, dict) else str(proposal))[:80]
        # quality-tribunal-d — 'tribunal-review' is not a valid diagnosis.CONFLICT_TYPES
        # member; open_conflict() raised CatalogError every time, silently
        # swallowed below. 'ambiguity' is real (a tribunal convenes
        # precisely when something is uncertain enough to need review);
        # prefix keeps the 'tribunal-review' identity in the case-ID
        # namespace (TRIB-001) instead of the invalid type field.
        case = cat.open_conflict(type="ambiguity", prefix="TRIB", trigger_event=f"tribunal convened on: {title}", actor=actor)'''

LOG_TO_DIAGNOSIS_NEW = f'''def log_to_diagnosis(proposal: dict | str, verdict: Verdict, data_dir: Path, *,
                     actor: str = "aria", prefix: str = "TRIB") -> str | None:
    """Record a tribunal case in the diagnosis catalog (Conflict → Diagnosis → Resolution).

    {MARK} — `prefix` distinguishes WHO convened the tribunal in the
    case-ID namespace (e.g. "GRND" for the standing grounding audit)
    without adding a new diagnosis.CONFLICT_TYPES member — every existing
    caller keeps its default "TRIB" prefix, byte-identical."""
    try:
        from sovereign_agent.diagnosis import ConflictCatalog
        cat = ConflictCatalog(Path(data_dir) / "diagnosis")
        title = (proposal.get("change") if isinstance(proposal, dict) else str(proposal))[:80]
        # quality-tribunal-d — 'tribunal-review' is not a valid diagnosis.CONFLICT_TYPES
        # member; open_conflict() raised CatalogError every time, silently
        # swallowed below. 'ambiguity' is real (a tribunal convenes
        # precisely when something is uncertain enough to need review);
        # prefix keeps the 'tribunal-review' identity in the case-ID
        # namespace (TRIB-001) instead of the invalid type field.
        case = cat.open_conflict(type="ambiguity", prefix=prefix, trigger_event=f"tribunal convened on: {{title}}", actor=actor)'''


def patch_tribunal(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    return _replace_once(text, LOG_TO_DIAGNOSIS_ANCHOR, LOG_TO_DIAGNOSIS_NEW,
                         label="log_to_diagnosis prefix param"), True


# ── 2. spectrum/lenses.py — skeptic prefers the persisted composite ──────

SKEPTIC_ANCHOR = '''def skeptic(p) -> LensRead:
    """Evidence. Is this grounded or fog? Reuses grounding."""
    try:
        from sovereign_agent.tribunal import grounding
        g = grounding.analyze(_text_of(p))
        score = {"grounded": 0.7, "mixed": 0.1, "ungrounded": -0.6}.get(g.verdict, 0.0)
        return LensRead("skeptic", _stance(score), score, concerns=g.flags[:3],
                        gifts=[f"grounding: {g.verdict}"])
    except Exception as exc:  # noqa: BLE001
        return LensRead("skeptic", "neutral", 0.0, concerns=[f"grounding unavailable: {exc!r}"])
'''

SKEPTIC_NEW = f'''def skeptic(p) -> LensRead:
    """Evidence. Is this grounded or fog? Reuses grounding.

    {MARK} — when the proposal carries a REAL persisted composite
    (grounding_verdict / epistemic_score, from grounding.ledger's
    standing pass — richer than one live text sample: it also folds in
    belief confidence and hypothesis track record), that overrides the
    live-only check below: measured beats one-shot. Absent those keys,
    byte-identical fallback to today's live grounding.analyze() call —
    every existing bare-string or plain-dict caller is unaffected.
    """
    if isinstance(p, dict) and ("grounding_verdict" in p or "epistemic_score" in p):
        concerns: list = []
        gifts: list = []
        verdict = p.get("grounding_verdict", "mixed")
        score = {{"grounded": 0.7, "mixed": 0.1, "ungrounded": -0.6}}.get(verdict, 0.0)
        gifts.append(f"measured grounding verdict: {{verdict}}")
        if "epistemic_score" in p:
            es = max(0.0, min(1.0, float(p["epistemic_score"])))
            gifts.append(f"measured epistemic score {{es:.2f}}")
        if not p.get("qa_calibration_ok", True):
            score = min(score, -0.6)
            concerns.append("qa-uncertainty calibration join broken (measured, not heuristic)")
        score = max(-1.0, min(1.0, score))
        return LensRead("skeptic", _stance(score), score, concerns=concerns, gifts=gifts)
    try:
        from sovereign_agent.tribunal import grounding
        g = grounding.analyze(_text_of(p))
        score = {{"grounded": 0.7, "mixed": 0.1, "ungrounded": -0.6}}.get(g.verdict, 0.0)
        return LensRead("skeptic", _stance(score), score, concerns=g.flags[:3],
                        gifts=[f"grounding: {{g.verdict}}"])
    except Exception as exc:  # noqa: BLE001
        return LensRead("skeptic", "neutral", 0.0, concerns=[f"grounding unavailable: {{exc!r}}"])
'''


def patch_skeptic(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    return _replace_once(text, SKEPTIC_ANCHOR, SKEPTIC_NEW, label="skeptic lens"), True


# ── 3. stewardship/grounding_sentinel.py — the standing phase ────────────

SENTINEL_ANCHOR = '''        # {MARK} — extension seam: G3 (aria-grounding-tribunal) hooks a
        # second standing-audit phase HERE, convening Tribunal + Advocate
        # Spectrum over this same real recent grounding pass, logged through
        # diagnosis.ConflictCatalog under type="ambiguity" prefix="GRND" —
        # mirrors quality_sentinel.py's own seam and Q3's use of it exactly.
        return report'''
# Note: no .replace() on "{MARK}" here — the live file's comment is literal
# text (a plain .py comment, never an f-string), so the braces are never
# substituted; matching it literally, as written above, is correct.

SENTINEL_NEW = '''        # grounding-tribunal-d — the standing phase: convene BOTH Tribunal and
        # Advocate Spectrum over this same real recent grounding pass, log
        # through the diagnosis catalog — the standing counterpart to
        # TribunalSentinel's narrow hardcoded-string self-check. Best-effort:
        # a scrutiny failure here must never break the grounding scan itself.
        try:
            if texts:
                joined = "\\n\\n".join(t for _src, t in texts)[:8000]
                proposal = {
                    "text": joined,
                    "change": f"grounding pass {result.pass_id}",
                    "grounding_verdict": result.verdict,
                    "epistemic_score": result.value,
                    "qa_calibration_ok": result.qa_calibration_ok,
                }
                from sovereign_agent.tribunal import convene
                from sovereign_agent.tribunal.tribunal import log_to_diagnosis

                tv = convene(proposal, include_kernel=False)
                case_id = log_to_diagnosis(proposal, tv, self._data_dir, prefix="GRND")
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
    if "grounding-tribunal-d" in text:
        return text, False
    return _replace_once(text, SENTINEL_ANCHOR, SENTINEL_NEW,
                         label="grounding_sentinel standing phase"), True


ALL_PATCHES = {
    "tribunal/tribunal.py": patch_tribunal,
    "spectrum/lenses.py": patch_skeptic,
    "stewardship/grounding_sentinel.py": patch_sentinel,
}
