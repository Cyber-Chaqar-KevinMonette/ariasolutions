"""F12 — the diff view: green-add/red-remove, theme-aware, editable."""
from __future__ import annotations

from sovereign_agent.diff_view import (
    DiffColors, build_diff, load_colors)


def test_add_and_remove_counted_and_colored():
    before = "line one\nline two\nline three\n"
    after = "line one\nline TWO changed\nline three\nline four\n"
    view = build_diff("foo.py", before, after)
    assert view.removed == 1              # "line two" removed
    assert view.added == 2                # changed line + "line four"
    rendered = "\n".join(view.render())
    assert "[green]+ line TWO changed" in rendered
    assert "[red]- line two" in rendered


def test_pure_addition():
    view = build_diff("new.py", "", "a\nb\n")
    assert view.added == 2 and view.removed == 0


def test_pure_deletion():
    view = build_diff("gone.py", "a\nb\n", "")
    assert view.removed == 2 and view.added == 0


def test_no_change_is_empty():
    view = build_diff("same.py", "x\ny\n", "x\ny\n")
    assert view.is_empty
    assert "no changes" in view.summary()


def test_classic_defaults_are_green_red():
    c = DiffColors()
    assert c.add == "green" and c.remove == "red"


def test_theme_mode_maps_success_and_error():
    class _Theme:
        success = "spring_green3"
        error = "deep_pink2"
        text_muted = "grey50"
        accent = "gold1"
    c = DiffColors.from_theme(_Theme())
    assert c.add == "spring_green3" and c.remove == "deep_pink2"


def test_editable_overrides_win(tmp_path):
    (tmp_path / "diff_theme.json").write_text('{"add": "cyan", "remove": "magenta"}')
    c = load_colors(tmp_path)
    assert c.add == "cyan" and c.remove == "magenta"


def test_overrides_win_even_over_theme(tmp_path):
    class _Theme:
        success = "green4"; error = "red3"; text_muted = "grey"; accent = "blue"
    (tmp_path / "diff_theme.json").write_text('{"add": "yellow"}')
    c = load_colors(tmp_path, mode="theme", theme=_Theme())
    assert c.add == "yellow"              # override beats theme
    assert c.remove == "red3"             # un-overridden falls to theme


def test_bad_override_file_never_breaks(tmp_path):
    (tmp_path / "diff_theme.json").write_text("{not valid json")
    c = load_colors(tmp_path)             # falls back to defaults, no raise
    assert c.add == "green"


def test_binary_safe():
    view = build_diff("blob.bin", "a\x00b", "c\x00d")
    assert "binary" in "\n".join(view.render()).lower()
    assert view.is_empty                  # no line counts on binary


def test_ledger_roundtrip_is_replayable():
    view = build_diff("x.py", "a\n", "a\nb\n")
    led = view.to_ledger()
    assert led["added"] == 1 and led["path"] == "x.py"
    assert any(l["kind"] == "add" and l["text"] == "b" for l in led["lines"])
