"""patcher.py — Quality round Q3: advocates and audits, made standing.

Kevin: *"Or quality advocates and audits."* Three patches, almost entirely
composition + one real bug fix:

  (a) tribunal/tribunal.py's log_to_diagnosis() has NEVER successfully
      run — it opens a conflict with type="tribunal-review", which isn't
      a valid diagnosis.CONFLICT_TYPES member; the CatalogError this
      raises is silently swallowed by a blanket except. Fixed to use the
      real "ambiguity" type + the existing (unused) `prefix` param to
      keep the "tribunal-review" identity in the case-ID namespace.
  (b) spectrum/lenses.py's artisan() lens scored craft/cleanliness from
      PROSE heuristics only. When the proposal carries real measured
      data (quality_score / hardening_critical_ok, from Q1's ledger),
      it now overrides the heuristic — real data outranks pattern-matched
      prose, but every existing bare-string/plain-dict caller keeps
      working unchanged (the override only fires when those keys exist).
  (c) stewardship/quality_sentinel.py's marked extension seam — Q1 left
      it there deliberately — gets a second scan phase: convene BOTH
      Tribunal and Spectrum over the same real recent work QualitySentinel
      just scored, logged through the now-fixed log_to_diagnosis(), into
      the SAME diagnosis.ConflictCatalog Tribunal already uses. The
      standing counterpart to TribunalSentinel's narrow hardcoded-string
      self-check — this one audits real work.

Anchored transforms only; MARK-idempotent; a moved anchor raises loudly."""
from __future__ import annotations

MARK = "quality-tribunal-d"


class PatchError(Exception):
    pass


def _replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if text.count(old) != 1:
        raise PatchError(f"{label}: expected 1 anchor, found {text.count(old)}")
    return text.replace(old, new, 1)


# ── (a) tribunal/tribunal.py — the dormant bug ───────────────────────────

TRIBUNAL_ANCHOR = (
    'case = cat.open_conflict(type="tribunal-review", '
    'trigger_event=f"tribunal convened on: {title}", actor=actor)\n'
)

TRIBUNAL_NEW = (
    f"# {MARK} — 'tribunal-review' is not a valid diagnosis.CONFLICT_TYPES\n"
    f"        # member; open_conflict() raised CatalogError every time, silently\n"
    f"        # swallowed below. 'ambiguity' is real (a tribunal convenes\n"
    f"        # precisely when something is uncertain enough to need review);\n"
    f"        # prefix keeps the 'tribunal-review' identity in the case-ID\n"
    f"        # namespace (TRIB-001) instead of the invalid type field.\n"
    '        case = cat.open_conflict(type="ambiguity", prefix="TRIB", '
    'trigger_event=f"tribunal convened on: {title}", actor=actor)\n'
)


def patch_tribunal(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    return _replace_once(text, TRIBUNAL_ANCHOR, TRIBUNAL_NEW,
                         label="log_to_diagnosis bug fix"), True


# ── (b) spectrum/lenses.py — measured data over prose ────────────────────

ARTISAN_ANCHOR = '''def artisan(p) -> LensRead:
    """Craft / cleanliness: tests, docs, polish, no debt."""
    text = _text_of(p)
    craft = len(re.findall(r"\\b(test|tests|doc|readme|clean|polish|verified|honest)\\w*", text, re.I))
    debt = len(re.findall(r"\\b(todo|fixme|hack|stub|debug|breakpoint)\\w*", text, re.I))
    score = min(1.0, 0.1 + 0.18 * craft) - 0.3 * debt
    return LensRead("artisan", _stance(score), max(-1.0, score),
                    concerns=(["unfinished/debt markers"] if debt else []),
                    gifts=(["tested / documented / clean"] if craft else []))
'''

ARTISAN_NEW = f'''def artisan(p) -> LensRead:
    """Craft / cleanliness: tests, docs, polish, no debt.

    {MARK} — when the proposal carries REAL measured data (quality_score /
    hardening_critical_ok, from quality.ledger), that overrides the prose
    heuristic below: measured beats pattern-matched. Absent those keys,
    byte-identical fallback to the original heuristic — every existing
    bare-string or plain-dict caller is unaffected.
    """
    if isinstance(p, dict) and ("quality_score" in p or "hardening_critical_ok" in p):
        concerns: list = []
        gifts: list = []
        score = 0.0
        if "quality_score" in p:
            qs = max(0.0, min(100.0, float(p["quality_score"])))
            score = (qs / 100.0) * 2.0 - 1.0
            gifts.append(f"measured quality score {{qs:.1f}}/100")
        if not p.get("hardening_critical_ok", True):
            score = min(score, -0.6)
            concerns.append("critical hardening check failed (measured, not heuristic)")
        score = max(-1.0, min(1.0, score))
        return LensRead("artisan", _stance(score), score, concerns=concerns, gifts=gifts)
    text = _text_of(p)
    craft = len(re.findall(r"\\b(test|tests|doc|readme|clean|polish|verified|honest)\\w*", text, re.I))
    debt = len(re.findall(r"\\b(todo|fixme|hack|stub|debug|breakpoint)\\w*", text, re.I))
    score = min(1.0, 0.1 + 0.18 * craft) - 0.3 * debt
    return LensRead("artisan", _stance(score), max(-1.0, score),
                    concerns=(["unfinished/debt markers"] if debt else []),
                    gifts=(["tested / documented / clean"] if craft else []))
'''


def patch_artisan(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    return _replace_once(text, ARTISAN_ANCHOR, ARTISAN_NEW, label="artisan lens"), True


# ── (c) quality/__init__.py — export the review helper ───────────────────

INIT_ANCHOR = "from .gate import QualityGateVerdict, gate  # quality-gate-d\n"
INIT_NEW = (
    INIT_ANCHOR
    + f"from .review import build_review_proposal  # {MARK}\n"
)

INIT_ALL_ANCHOR = '    "record_quality_pass", "QualityGateVerdict", "gate",  # quality-gate-d\n'
INIT_ALL_NEW = (
    INIT_ALL_ANCHOR
    + f'    "build_review_proposal",  # {MARK}\n'
)


def patch_quality_init(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(text, INIT_ANCHOR, INIT_NEW, label="quality init import")
    text = _replace_once(text, INIT_ALL_ANCHOR, INIT_ALL_NEW, label="quality init __all__")
    return text, True


# ── (c cont'd) stewardship/quality_sentinel.py — the standing phase ─────

# The live comment literally reads "{MARK}" (braces included) — Q1 wrote
# it as plain text inside a regular .py file, not inside an f-string, so
# it was never substituted. Match it exactly, don't re-substitute it.
SENTINEL_ANCHOR = """        # {MARK} — extension seam: Q3 (aria-quality-tribunal) hooks a
        # second standing-audit phase HERE (Tribunal + Advocate Spectrum
        # convened over this same real recent work, logged through the
        # diagnosis catalog) — this scan() returns right after; Q3's patch
        # inserts its phase between the notify() above and this return.
        return report
"""

SENTINEL_NEW = f'''        # {MARK} — the standing phase: convene BOTH Tribunal and Advocate
        # Spectrum over this same real recent work, log through the
        # diagnosis catalog — the standing counterpart to TribunalSentinel's
        # narrow hardcoded-string self-check. Best-effort: a scrutiny
        # failure here must never break the quality scan itself.
        try:
            from sovereign_agent.quality.review import build_review_proposal

            proposal = build_review_proposal(self._data_dir)
            if proposal is not None:
                from sovereign_agent.tribunal import convene
                from sovereign_agent.tribunal.tribunal import log_to_diagnosis

                verdict = convene(proposal, include_kernel=False)
                case_id = log_to_diagnosis(proposal, verdict, self._data_dir)
                standing = {{"verdict": verdict.verdict, "case_id": case_id}}
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
        return report
'''


def patch_sentinel(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    return _replace_once(text, SENTINEL_ANCHOR, SENTINEL_NEW,
                         label="sentinel extension seam"), True


ALL_PATCHES = {
    "tribunal/tribunal.py": patch_tribunal,
    "spectrum/lenses.py": patch_artisan,
    "quality/__init__.py": patch_quality_init,
    "stewardship/quality_sentinel.py": patch_sentinel,
}
