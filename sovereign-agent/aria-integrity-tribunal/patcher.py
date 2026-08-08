"""patcher.py — Integrity round I3: standing sentinel + witness lens override.

Patches:
  1. spectrum/lenses.py's witness() — prefer a persisted composite
     (integrity_verdict/integrity_score, from I1's ledger via the new
     standing sentinel) over the live-only regex check, same
     measured-data-override pattern skeptic/angel already use. Absent
     those keys, byte-identical fallback — every existing caller
     unaffected.
  2. stewardship/__init__.py — register SelfIntegritySentinel, anchored on
     the current tail (model_corps_sentinel, the Model Corps round's own
     addition).

Anchored transforms only; MARK-idempotent; a moved anchor raises loudly."""
from __future__ import annotations

MARK = "self-integrity-sentinel-d"
LENS_MARK = "integrity-tribunal-d"


class PatchError(Exception):
    pass


def _replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if text.count(old) != 1:
        raise PatchError(f"{label}: expected 1 anchor, found {text.count(old)}")
    return text.replace(old, new, 1)


# ── 1. spectrum/lenses.py — witness measured-data override ───────────────

WITNESS_ANCHOR = '''def witness(p) -> LensRead:
    """The witnessing principle: what does this do to those it touches?"""
    text = _text_of(p)
'''

WITNESS_NEW = f'''def witness(p) -> LensRead:
    """The witnessing principle: what does this do to those it touches?

    {LENS_MARK} — when the proposal carries a REAL persisted composite
    (integrity_verdict/integrity_score, from integrity.ledger's standing
    pass via SelfIntegritySentinel), that overrides the live-only regex
    check below: measured beats one-shot. Absent those keys, byte-identical
    fallback to today's live check — every existing bare-string or
    plain-dict caller is unaffected.
    """
    if isinstance(p, dict) and ("integrity_verdict" in p or "integrity_score" in p):
        concerns: list = []
        gifts: list = []
        verdict = p.get("integrity_verdict", "ok")
        score = {{"ok": 0.6, "concern": 0.0, "fail": -0.7}}.get(verdict, 0.0)
        gifts.append(f"measured integrity verdict: {{verdict}}")
        if "integrity_score" in p:
            iscore = max(0.0, min(1.0, float(p["integrity_score"])))
            gifts.append(f"measured integrity score {{iscore:.2f}}")
        if verdict == "fail":
            concerns.append("integrity composite failed (measured, not heuristic) — "
                            "one of grounding/outcome/witness/identity signals fired")
        score = max(-1.0, min(1.0, score))
        return LensRead("witness", _stance(score), score, concerns=concerns, gifts=gifts)
    text = _text_of(p)
'''


def patch_witness_lens(text: str) -> tuple[str, bool]:
    if LENS_MARK in text:
        return text, False
    return _replace_once(text, WITNESS_ANCHOR, WITNESS_NEW, label="witness lens"), True


# ── 2. stewardship/__init__.py — register the sentinel ───────────────────

INIT_ANCHOR = (
    'from . import model_corps_sentinel as _model_corps_sentinel  '
    '# noqa: F401  # model-corps-sentinel-d\n'
)

INIT_NEW = (
    INIT_ANCHOR
    + f'from . import self_integrity_sentinel as _self_integrity_sentinel  '
      f'# noqa: F401  # {MARK}\n'
)


def patch_stewardship_init(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    return _replace_once(text, INIT_ANCHOR, INIT_NEW, label="stewardship init"), True


ALL_PATCHES = {
    "spectrum/lenses.py": patch_witness_lens,
    "stewardship/__init__.py": patch_stewardship_init,
}
