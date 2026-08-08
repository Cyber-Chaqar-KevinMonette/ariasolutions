"""Smoke tests for the charter (SIGNAL.md) integrity contract.

These tests lock in Article V: "the doctor's verdict binds." If any of these
break, the kill switch's binding force is broken too.
"""
from __future__ import annotations

import textwrap

import pytest

from sovereign_agent import charter


def test_charter_file_exists_in_source_tree():
    """SIGNAL.md must ship at the install root, beside ARIA.md."""
    path = charter.find_charter_path()
    assert path is not None, "SIGNAL.md not found in source tree"
    assert path.is_file()
    assert path.name == "SIGNAL.md"


def test_canonical_charter_passes_integrity():
    """The shipped charter must seal cleanly — no kill switch on a fresh install."""
    verdict = charter.check_integrity()
    assert verdict.level == "ok", (
        f"shipped charter failed integrity check: {verdict.summary}\n"
        f"detail: {verdict.detail}"
    )
    assert verdict.kill_switch_active is False
    assert verdict.version is not None


def test_hash_excludes_hash_line_itself():
    """The chicken-and-egg sidestep: hashing must skip the hash line.

    Otherwise no charter could ever be self-consistent.
    """
    text = "header\ncharter-hash:    sha256:DEADBEEF\nbody\n"
    stripped = charter._strip_hash_line_for_hashing(text)
    assert "sha256:DEADBEEF" not in stripped
    assert "<EXCLUDED-FROM-HASH>" in stripped
    # Hash must be stable regardless of what's in the hash line
    other = "header\ncharter-hash:    sha256:CAFEBABE\nbody\n"
    assert charter.compute_content_hash(text) == charter.compute_content_hash(other)


def test_hash_changes_when_body_changes():
    """Changing literally any content outside the hash line must change the hash."""
    a = "header\ncharter-hash:    sha256:PENDING\nbody-A\n"
    b = "header\ncharter-hash:    sha256:PENDING\nbody-B\n"
    assert charter.compute_content_hash(a) != charter.compute_content_hash(b)


def test_rewrite_hash_in_text_is_round_trip():
    """rewrite_hash_in_text → compute_content_hash must produce a sealed file."""
    text = "x\ncharter-hash:    sha256:PENDING\ny\n"
    new_hash = charter.compute_content_hash(text)
    sealed = charter.rewrite_hash_in_text(text, new_hash)
    assert charter.extract_recorded_hash(sealed) == new_hash
    assert charter.compute_content_hash(sealed) == new_hash


def test_tamper_is_detected(tmp_path, monkeypatch):
    """Edit the charter without amending → integrity check must fail with kill switch."""
    fake = tmp_path / "SIGNAL.md"
    # Create a minimal valid charter
    body = textwrap.dedent("""\
        # Test charter
        <!--
        charter-version: 0.0.1
        charter-hash:    sha256:PENDING
        -->
        ## I. one
        ## II. two
        ```yaml
        charter:
          version: "0.0.1"
          max_articles: 7
          articles:
            - {id: I, slug: one}
            - {id: II, slug: two}
        ```
    """)
    h = charter.compute_content_hash(body)
    fake.write_text(charter.rewrite_hash_in_text(body, h), encoding="utf-8")
    monkeypatch.setattr(charter, "find_charter_path", lambda: fake)

    # Sealed → ok
    v = charter.check_integrity()
    assert v.level == "ok"
    assert v.kill_switch_active is False

    # Tamper → error + kill switch
    fake.write_text(fake.read_text().replace("## I. one", "## I. tampered"), encoding="utf-8")
    v = charter.check_integrity()
    assert v.level == "error"
    assert v.kill_switch_active is True
    assert "MISMATCH" in v.summary


def test_article_count_exceeding_max_is_rejected(tmp_path, monkeypatch):
    """Adding an 8th article must trip the kill switch — charter inflation guard."""
    body = textwrap.dedent("""\
        # T
        <!--
        charter-version: 0.0.1
        charter-hash:    sha256:PENDING
        -->
        ## I. one
        ## II. two
        ## III. three
        ## IV. four
        ## V. five
        ## VI. six
        ## VII. seven
        ## VIII. eight
        ```yaml
        charter:
          version: "0.0.1"
          max_articles: 7
          articles:
            - {id: I, slug: one}
            - {id: II, slug: two}
            - {id: III, slug: three}
            - {id: IV, slug: four}
            - {id: V, slug: five}
            - {id: VI, slug: six}
            - {id: VII, slug: seven}
            - {id: VIII, slug: eight}
        ```
    """)
    h = charter.compute_content_hash(body)
    fake = tmp_path / "SIGNAL.md"
    fake.write_text(charter.rewrite_hash_in_text(body, h), encoding="utf-8")
    monkeypatch.setattr(charter, "find_charter_path", lambda: fake)
    v = charter.check_integrity()
    assert v.level == "error"
    assert v.kill_switch_active is True
    assert "exceeds max_articles" in v.summary


def test_prose_yaml_mismatch_is_rejected(tmp_path, monkeypatch):
    """If YAML says 7 articles and prose only has 5, that's a charter lying to itself."""
    body = textwrap.dedent("""\
        # T
        <!--
        charter-version: 0.0.1
        charter-hash:    sha256:PENDING
        -->
        ## I. one
        ## II. two
        ```yaml
        charter:
          version: "0.0.1"
          max_articles: 7
          articles:
            - {id: I, slug: one}
            - {id: II, slug: two}
            - {id: III, slug: three}
        ```
    """)
    h = charter.compute_content_hash(body)
    fake = tmp_path / "SIGNAL.md"
    fake.write_text(charter.rewrite_hash_in_text(body, h), encoding="utf-8")
    monkeypatch.setattr(charter, "find_charter_path", lambda: fake)
    v = charter.check_integrity()
    assert v.level == "error"
    assert "prose" in v.summary.lower() and "yaml" in v.summary.lower()


def test_absent_charter_is_warning_not_error(tmp_path, monkeypatch):
    """Pre-charter operators (no SIGNAL.md yet) must not be killed by the switch."""
    monkeypatch.setattr(charter, "find_charter_path", lambda: None)
    v = charter.check_integrity()
    assert v.level == "warning"
    assert v.kill_switch_active is False


def test_glyphs_audit_catches_diamond():
    """The lesson Kevin diagnosed lives in code: ◈ is flagged as unsafe for layout."""
    from sovereign_agent import glyphs
    bad = glyphs.audit_string("◈ chat ◈ memory ◈ live")
    assert len(bad) == 3, "should flag all three diamonds"
    for pos, ch, eaw in bad:
        assert ch == "\u25C8"
        assert eaw == "A"


def test_severity_glyphs_are_layout_safe():
    """Aliases used in banner code must all pass the audit."""
    from sovereign_agent import glyphs
    for name in ("SEVERITY_OK", "SEVERITY_WARNING", "SEVERITY_ERROR",
                 "SEVERITY_INFO", "SEVERITY_BULLET"):
        ch = getattr(glyphs, name)
        bad = glyphs.audit_string(ch)
        assert not bad, f"{name} = {ch!r} flagged unsafe: {bad}"
