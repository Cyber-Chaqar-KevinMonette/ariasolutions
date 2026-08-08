"""Property-based tests (Hypothesis) for Aria's scanner/parser surfaces —
Gym round #10. `hypothesis>=6.100` sat in pyproject.toml with ZERO imports
anywhere; the whole point of a scanner is catching inputs nobody thought
to hand-write, so the scanners themselves get fuzzed first.

Bounded per project discipline: max_examples≈50, deadline=None (CI-safe:
no flaky time-based failures).
"""
from __future__ import annotations

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

_BOUNDED = settings(
    max_examples=50, deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)

# Arbitrary text including path-ish shapes, newlines, and raw unicode.
_texts = st.text(
    alphabet=st.characters(codec="utf-8"),
    max_size=2000,
)
_pathish = st.one_of(
    _texts,
    st.from_regex(r"(/[a-zA-Z0-9_.\-]{1,12}){1,6}\n?", fullmatch=True),
    st.from_regex(r'p = "(tests|tmp|/tmp|payload)/[a-z_/.]{0,30}"\n', fullmatch=True),
)


# ── path_scan.scanner.scan_text ───────────────────────────────────────────


@_BOUNDED
@given(text=_pathish, allow=st.booleans())
def test_scan_text_never_raises_and_findings_are_well_formed(text, allow):
    from sovereign_agent.path_scan.scanner import scan_text

    findings = scan_text(text, module="aria-fuzz", rel_path="payload/x.py",
                         allow_test_refs=allow)
    for f in findings:
        assert f.severity in ("block", "warn", "info")
        assert f.module == "aria-fuzz"
        assert isinstance(f.kind, str) and f.kind
        assert isinstance(f.line, int) and f.line >= 0


@_BOUNDED
@given(text=_pathish)
def test_scan_text_allow_test_refs_is_monotonic(text):
    """Allowing test refs must never CREATE findings — the allowed run's
    findings are always a subset (by count per kind) of the strict run's."""
    from collections import Counter

    from sovereign_agent.path_scan.scanner import scan_text

    strict = Counter(f.kind for f in scan_text(
        text, module="m", rel_path="payload/x.py", allow_test_refs=False))
    allowed = Counter(f.kind for f in scan_text(
        text, module="m", rel_path="payload/x.py", allow_test_refs=True))
    for kind, n in allowed.items():
        assert n <= strict.get(kind, 0), (
            f"allow_test_refs=True created {kind} findings out of nothing"
        )


# ── scanner_tier_a text scanners ──────────────────────────────────────────


@_BOUNDED
@given(text=_texts)
def test_tier_a_text_scanners_never_raise(text):
    from sovereign_agent.scanner_tier_a.scanner import (
        scan_authority_tier_drift, scan_bare_except, scan_mutable_defaults,
        scan_secrets,
    )

    for fn in (scan_secrets, scan_bare_except, scan_mutable_defaults,
               scan_authority_tier_drift):
        findings = fn(text, rel_path="fuzz.py")
        for f in findings:
            assert f.severity in ("block", "warn", "info")


@_BOUNDED
@given(text=_texts)
def test_tier_a_all_exports_never_raises(text):
    from sovereign_agent.scanner_tier_a.scanner import scan_all_exports

    scan_all_exports(text)  # arbitrary (possibly non-Python) text: no crash


# ── glyph classification ──────────────────────────────────────────────────


@_BOUNDED
@given(ch=st.characters(codec="utf-8"))
def test_glyph_classify_total_and_closed(ch):
    """_classify is a total function over unicode: every char gets exactly
    one known classification and a boolean, never an exception."""
    import unicodedata

    from sovereign_agent.stewardship.glyph_sentinel import _classify

    eaw = unicodedata.east_asian_width(ch)
    classification, de_facto_narrow = _classify(ch, eaw)
    assert classification in ("safe", "borderline", "unsafe")
    assert isinstance(de_facto_narrow, bool)


# ── aria_lm clean_prose ───────────────────────────────────────────────────


@_BOUNDED
@given(text=_texts)
def test_clean_prose_never_raises_and_is_idempotent(text):
    """clean(clean(x)) == clean(x): cleaning already-clean prose must be a
    fixed point, or repeated corpus builds would drift."""
    from sovereign_agent.aria_lm.data import clean_prose

    once = clean_prose(text)
    assert isinstance(once, str)
    assert clean_prose(once) == once


# ── prompt_diet section parsing (this round's own new parser) ─────────────


@_BOUNDED
@given(
    names=st.lists(st.text(alphabet=st.characters(codec="utf-8",
                                                  exclude_characters="═\n"),
                           min_size=1, max_size=30).map(str.strip)
                   .filter(bool),
                   max_size=6),
    bodies=st.lists(st.text(alphabet=st.characters(codec="utf-8",
                                                   exclude_characters="═"),
                            max_size=200), max_size=6),
    preamble=st.text(alphabet=st.characters(codec="utf-8",
                                            exclude_characters="═"),
                     max_size=200),
)
def test_split_sections_round_trips_synthetic_templates(names, bodies, preamble):
    from sovereign_agent.prompt_diet import split_sections

    template = preamble
    for name, body in zip(names, bodies):
        template += f"═══ {name} ═══\n{body}"
    pre, sections = split_sections(template)
    assert pre + "".join(t for _, t in sections) == template
