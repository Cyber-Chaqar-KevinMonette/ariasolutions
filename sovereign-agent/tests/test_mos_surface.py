"""MOS-SURFACE enforcement tests — the doctrine, as predicates.

These tests catch the bug classes that MOS-SURFACE names:
  S1: cell-truth (no width-2 glyphs in chrome)
  S2: one frame, one owner (the cockpit's #main border is the only one
       in its region; #live-pane carries no border-left)
  S4: color is a token (no hardcoded hex colors in CSS rules outside
       semantic class definitions)
  Version consistency (no hardcoded version strings anywhere except
  the package's __init__.py)
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import pytest

SRC_DIR = Path(__file__).parent.parent / "src" / "sovereign_agent"


# ════════════════════════════════════════════════════════════════════════════
# Version consistency — MOS-SURFACE S4 / Appendix C
# ════════════════════════════════════════════════════════════════════════════


class TestVersionConsistency:
    """No source file under src/ may hardcode a version string different
    from the canonical __version__.

    The previous failure mode: cockpit.app had `SUB_TITLE = "0.2.15.3"`
    for three releases while __version__ was 0.2.16.0, 0.2.17.0, 0.2.18.0.
    The cockpit's title bar lied. This test catches that class of bug.
    """

    def test_canonical_version_exists(self):
        from sovereign_agent import __version__
        assert __version__
        assert re.match(r"^\d+\.\d+\.\d+(\.\d+)?$", __version__), (
            f"__version__ must be a semver-ish string, got {__version__!r}"
        )

    def test_no_hardcoded_version_in_runtime_code(self, all_src_python_files):
        """Scan every .py file in src/ for hardcoded version strings.

        Allowed: __init__.py (the canonical source of __version__).
        Allowed: ``introduced_in="X.Y.Z"`` — historical metadata, permanent
                 fact of when a channel/feature was introduced.
        Allowed: ``help="...e.g. vX.Y.Z..."`` — typer/argparse example text.
        Allowed: docstring lines.
        Forbidden: runtime-displayed strings like ``SUB_TITLE = "X.Y.Z"``.
        """
        from sovereign_agent import __version__
        version_re = re.compile(r'["\']\d+\.\d+\.\d+(\.\d+)?["\']')
        # Lines containing these substrings carry historical or example
        # metadata; the version literal is semantically frozen there.
        ALLOWED_CONTEXTS = (
            "introduced_in=",
            "introduced_in =",
            "introduced_in:",        # dataclass field with type annotation
            "version:",              # function arg / field with type annotation
            "version =",
            "# Example",
            "e.g. v0.",
            "e.g., v0.",
            "(e.g. v",
            "applied')",
            "# v0.",
            "v0.2.10",
            # socket / network calls — IPv4 addresses match the version regex
            "socket",
            "create_connection",
            "inet_",
            "localhost",
            ".0.0.1",                # common IPs: 127.0.0.1, 0.0.0.1
            "1.1.1.1",
            "0.0.0.0",
        )

        violations: list[tuple[str, int, str]] = []
        for path in all_src_python_files:
            if path.name == "__init__.py" and path.parent == SRC_DIR:
                continue
            for lineno, line in enumerate(path.read_text().splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if stripped.startswith('"') or stripped.startswith("'"):
                    if "=" not in line.split("#")[0]:
                        continue
                if any(g in line for g in "║╔╗╚╝═"):
                    continue
                if any(ctx in line for ctx in ALLOWED_CONTEXTS):
                    continue
                match = version_re.search(line)
                if not match:
                    continue
                value = match.group(0).strip("\"'")
                if value != __version__:
                    violations.append((str(path.relative_to(SRC_DIR)),
                                       lineno, line.rstrip()))

        if violations:
            msg = "\n".join(
                f"  {p}:{ln}: {line}" for p, ln, line in violations
            )
            pytest.fail(
                f"\nHardcoded version strings found that don't match "
                f"__version__ ({__version__}):\n{msg}\n\n"
                f"Use `from .. import __version__` and interpolate. "
                f"Or, if it's historical metadata (e.g. introduced_in), "
                f"add the context to ALLOWED_CONTEXTS in this test."
            )

    def test_cockpit_sub_title_matches_version(self):
        """The cockpit's title bar must show the live package version."""
        from sovereign_agent import __version__
        from sovereign_agent.cockpit.app import CockpitApp
        assert CockpitApp.SUB_TITLE == __version__


# ════════════════════════════════════════════════════════════════════════════
# Border ownership — MOS-SURFACE S2
# ════════════════════════════════════════════════════════════════════════════


class TestBorderOwnership:
    """The "one frame, one owner" rule. Two widgets must not share a
    chrome column. The most common violation: outer `border: round` plus
    inner `border-left: solid` on a sibling pane.
    """

    def test_cockpit_uses_dedicated_divider(self):
        """The cockpit's compose() must yield divider widgets.

        v0.2.25.0: there are now two dividers (#divider-1, #divider-2)
        separating chat | memory | live panes. The doctrine point
        (dedicated divider widgets rather than border-left hacks)
        remains; the names changed.
        """
        path = SRC_DIR / "cockpit" / "app.py"
        src = path.read_text()
        # At least one divider widget must be present
        has_divider = (
            'id="divider"' in src
            or 'id="divider-1"' in src
            or 'id="divider-2"' in src
        )
        assert has_divider, (
            "cockpit compose() must yield Rule widget(s) as dedicated "
            "separators between panes. See MOS-SURFACE §29 + §31."
        )

    def test_live_pane_has_no_border_left(self):
        """The live pane must NOT have border-left in its CSS.

        That was the bug: border-left on #live-pane fought with
        border: round on #main, producing seams.
        """
        path = SRC_DIR / "cockpit" / "app.py"
        src = path.read_text()
        # Match the main CSS block (the class-attribute `CSS = """..."""`),
        # NOT DEFAULT_CSS or any other suffix. The word boundary in front
        # of CSS, plus the preceding whitespace, ensures this.
        css_match = re.search(r'(?:^|\W)CSS\s*=\s*"""(.*?)"""', src, re.DOTALL)
        assert css_match, "main CSS block not found in cockpit app.py"
        css = css_match.group(1)
        # Find the #live-pane rule block
        live_rule = re.search(r"#live-pane\s*\{([^}]*)\}", css)
        assert live_rule, "#live-pane CSS rule not found"
        body = live_rule.group(1)
        assert "border-left" not in body, (
            "#live-pane must not declare border-left. "
            "Use the dedicated #divider widget. See MOS-SURFACE S2."
        )


# ════════════════════════════════════════════════════════════════════════════
# Glyph width discipline — MOS-SURFACE S1
# ════════════════════════════════════════════════════════════════════════════


# Width-2 glyphs that have appeared in past code and would break alignment.
# This is not exhaustive — wcwidth is the source of truth — but it catches
# the common cases that AI-assisted edits introduce.
FORBIDDEN_IN_CHROME = frozenset({
    "❤", "❤️", "💖", "🌅", "🏠", "✨", "🎉", "📊", "📈", "🚀",
    "🔴", "🟡", "🟢",   # status emoji — width-2; use ● ○ ◯ instead
})


class TestGlyphDiscipline:
    """No width-2 glyphs in chrome. Box-drawing, separators, titles,
    status bars all use width-1 glyphs from the canonical reference
    (MOS-SURFACE Appendix A).
    """

    def test_no_forbidden_emoji_in_cockpit_chrome(self):
        """Emoji in the cockpit's chrome-defining code (CSS, compose,
        labels) would break column alignment."""
        path = SRC_DIR / "cockpit" / "app.py"
        src = path.read_text()
        # Scan ONLY the CSS block and the compose() / on_mount() bodies
        # (the labels and titles that appear in chrome)
        # For simplicity, scan the whole file but allow emoji in docstring
        # bodies (header). The CSS and string literals are the risk surface.
        chrome_lines = []
        in_docstring_block = False
        triple = '"""'
        depth = 0
        for line in src.splitlines():
            count = line.count(triple)
            if count % 2 == 1:
                depth += 1
            in_docstring_block = (depth % 2 == 1)
            if not in_docstring_block:
                chrome_lines.append(line)
        chrome_text = "\n".join(chrome_lines)
        found = [g for g in FORBIDDEN_IN_CHROME if g in chrome_text]
        if found:
            pytest.fail(
                f"Width-2 emoji found in cockpit chrome: {found!r}. "
                f"See MOS-SURFACE S1 + Appendix A. Use width-1 glyphs."
            )


# ════════════════════════════════════════════════════════════════════════════
# Theme token discipline — MOS-SURFACE S4
# ════════════════════════════════════════════════════════════════════════════


# Hex colors that ARE allowed because they're tied to named semantic classes.
# (Aria's voice color, operator's voice color — the personal palette.)
ALLOWED_HEX_CONTEXTS = (
    ".aria",
    ".you",
)


class TestThemeTokens:
    """Color discipline. Hex codes only in semantic class definitions
    where the class name documents the meaning of the color.
    """

    def test_cockpit_css_uses_tokens(self):
        """Scan the cockpit's CSS for hex codes outside allowed contexts."""
        path = SRC_DIR / "cockpit" / "app.py"
        src = path.read_text()
        css_match = re.search(r'(?:^|\W)CSS\s*=\s*"""(.*?)"""', src, re.DOTALL)
        assert css_match, "main CSS block not found"
        css = css_match.group(1)
        hex_re = re.compile(r"#[0-9A-Fa-f]{3,8}\b")

        violations = []
        for lineno, line in enumerate(css.splitlines(), 1):
            # A selector-opener line (e.g. "#add-time-btn {  /* comment */")
            # is a widget ID, never a color VALUE -- hex-looking text here
            # (an ID that happens to start with letters a-f, like
            # "add-time-btn") is a false positive, not a hardcoded color.
            # Real hex colors only ever appear on a "property: value;"
            # line, which never contains a brace in this codebase's CSS.
            if "{" in line:
                continue
            if not hex_re.search(line):
                continue
            # Is this line part of an allowed context?
            allowed = any(ctx in line for ctx in ALLOWED_HEX_CONTEXTS)
            if not allowed:
                violations.append((lineno, line.strip()))

        if violations:
            msg = "\n".join(f"  line {ln}: {line}" for ln, line in violations)
            pytest.fail(
                f"\nHex color codes found outside allowed contexts in CSS:\n"
                f"{msg}\n\nUse theme tokens ($primary, $accent, ...) instead. "
                f"See MOS-SURFACE §12 + Appendix B."
            )


# ════════════════════════════════════════════════════════════════════════════
# Opacity is structure — MOS-SURFACE S7
# ════════════════════════════════════════════════════════════════════════════


class TestOpacityIsStructure:
    """S7: every container in the chrome composition declares an explicit
    background. No transparent links in the chain.

    The failure mode this catches: a translucent fill (e.g. $primary 15%)
    blending against an inherited / unset / transparent parent background,
    causing the terminal-default to leak through as a black strip at
    junction cells (the "black leak" bug).
    """

    # Every selector listed here is part of the cockpit's chrome
    # composition and MUST declare a background in its rule body.
    # v0.2.25.0: #memory-pane and #divider-1, #divider-2 replace the
    # single #divider as the cockpit grows to three panes.
    CHROME_SELECTORS = (
        "#main",
        "#chat-pane",
        "#memory-pane",
        "#live-pane",
        "#inbox-pane",
        "#divider-1",
        "#divider-3",
        ".pane-title",
        "#chat-log",
        "#events-log",
        "#inbox-log",
        "#input-box",
    )

    def test_every_chrome_container_has_explicit_background(self):
        path = SRC_DIR / "cockpit" / "app.py"
        src = path.read_text()
        css_match = re.search(r'(?:^|\W)CSS\s*=\s*"""(.*?)"""', src, re.DOTALL)
        assert css_match, "main CSS block not found"
        css = css_match.group(1)

        missing: list[str] = []
        for selector in self.CHROME_SELECTORS:
            # Escape special CSS-selector characters for regex.
            esc = re.escape(selector)
            # Match the FIRST rule body for this selector (the canonical
            # definition; secondary rules like :focus or .breathing-N
            # variants don't have to redeclare background).
            rule = re.search(esc + r"\s*\{([^}]*)\}", css)
            assert rule, f"selector {selector!r} not found in CSS"
            body = rule.group(1)
            if "background:" not in body:
                missing.append(selector)

        if missing:
            pytest.fail(
                f"\nThe following chrome selectors are missing explicit "
                f"`background:` declarations:\n  "
                + "\n  ".join(missing)
                + f"\n\nSee MOS-SURFACE S7. Every container in the chrome "
                f"composition MUST declare a solid background (typically "
                f"$surface) to prevent translucent fills from blending "
                f"against terminal-default (the 'black leak' bug)."
            )

    def test_divider_uses_canonical_rule_widget(self):
        """Divider widgets must be Textual's Rule, not a Static-with-
        newlines hack. v0.2.25.0: there are now two dividers; both
        must use Rule."""
        path = SRC_DIR / "cockpit" / "app.py"
        src = path.read_text()
        # Look for at least one Rule constructor with a divider id
        ok = bool(re.search(
            r'Rule\s*\([^)]*id\s*=\s*["\']divider(?:-[12])?["\']',
            src,
        ))
        assert ok, (
            "Divider widgets must be constructed via "
            "Rule(orientation='vertical', id='divider-1' | 'divider-2'). "
            "The Static-with-newlines pattern is forbidden — it causes "
            "centering artifacts in tall terminals. See MOS-SURFACE §6.1."
        )

    def test_no_static_newline_divider_pattern(self):
        """The fragile Static('│\\n' * N, ...) pattern must not appear
        anywhere in cockpit chrome code."""
        path = SRC_DIR / "cockpit" / "app.py"
        src = path.read_text()
        # The pattern: Static(\"│\\n\" * N, id=\"divider\")
        # Detect it by looking for "│\n" * N with an id of divider nearby.
        bad_pattern = re.search(
            r'Static\s*\(\s*["\']\s*│\s*\\n["\']\s*\*\s*\d+',
            src,
        )
        assert bad_pattern is None, (
            "Forbidden pattern detected: Static('│\\n' * N). "
            "Use Rule(orientation='vertical') instead. See MOS-SURFACE §6.1."
        )


# ════════════════════════════════════════════════════════════════════════════
# Verb stability — MOS-SURFACE S5 applied to CLI verbs
# ════════════════════════════════════════════════════════════════════════════


class TestVerbStability:
    """S5 says keybindings are contracts. The same rule applies to CLI
    verbs: once `sov chat` (bare) launched the cockpit, that contract
    cannot quietly change. v0.2.18.0 broke it; v0.2.18.3 restores it.
    """

    def test_bare_chat_invocation_is_supported(self):
        """The `chat` sub-Typer must be configured to accept bare
        invocation (no subcommand). Without this, `sov chat` errors
        with 'Missing command.' — which it did in v0.2.18.0-v0.2.18.2."""
        from sovereign_agent.cli import chat_app
        assert chat_app.info.invoke_without_command is True, (
            "chat sub-Typer must have invoke_without_command=True to "
            "preserve the bare `sov chat` cockpit-launcher contract. "
            "See MOS-SURFACE S5."
        )

    def test_chat_subcommands_still_route(self):
        """Adding the invoke_without_command callback must not break
        the existing subcommands (`status`, `request`, `cancel`,
        `resume`)."""
        from typer.testing import CliRunner
        from sovereign_agent.cli import app
        runner = CliRunner()
        result = runner.invoke(app, ["chat", "--help"])
        assert result.exit_code == 0
        for sub in ("status", "request", "cancel", "resume"):
            assert sub in result.stdout, (
                f"chat subcommand {sub!r} not listed in `sov chat --help`"
            )


# ════════════════════════════════════════════════════════════════════════════
# Scrollbar discipline — MOS-SURFACE §16.1
# ════════════════════════════════════════════════════════════════════════════


class TestScrollbarDiscipline:
    """A visible scrollbar gutter on a RichLog reserves a 1-cell column
    on the widget's right edge. At the junction with the outer rounded
    border, that gutter renders as a faint vertical line that LOOKS LIKE
    a misaligned border. This is the bug the operator saw across
    v0.2.18.0 through v0.2.18.3.

    RichLog scrollbars must be hidden (size 0 0). Operators scroll via
    mouse wheel or PageUp/PageDown — a visible gutter in chat-log /
    events-log contexts has no UX value and IS the chrome artifact.
    """

    def test_richlog_scrollbar_is_hidden(self):
        path = SRC_DIR / "cockpit" / "app.py"
        src = path.read_text()
        css_match = re.search(r'(?:^|\W)CSS\s*=\s*"""(.*?)"""', src, re.DOTALL)
        assert css_match, "main CSS block not found"
        css = css_match.group(1)
        rule = re.search(r"RichLog\s*\{([^}]*)\}", css)
        assert rule, "RichLog CSS rule not found"
        body = rule.group(1)
        # The canonical fix: scrollbar-size: 0 0 (both dimensions hidden)
        assert "scrollbar-size: 0 0" in body, (
            "RichLog must declare `scrollbar-size: 0 0` to hide the "
            "scrollbar gutter. Forbidden patterns include "
            "`scrollbar-size-vertical: 1` which reserves a 1-cell "
            "column that renders as a visible artifact at the right "
            "edge of every RichLog. See MOS-SURFACE §16.1."
        )
        # Specifically forbid the regression pattern
        assert "scrollbar-size-vertical: 1" not in body, (
            "scrollbar-size-vertical: 1 is the exact regression pattern "
            "that produced the right-edge vertical-line artifact through "
            "v0.2.18.3. See MOS-SURFACE §16.1."
        )


# ════════════════════════════════════════════════════════════════════════════
# Clipboard paste — operator affordance
# ════════════════════════════════════════════════════════════════════════════


class TestClipboardPaste:
    """The cockpit must respond to Ctrl+V by pasting the system
    clipboard contents into the focused input. The implementation
    must be cross-platform (Linux Wayland, Linux X11, macOS, Windows)
    via subprocess calls to the platform's native tooling — no new
    Python dependencies.
    """

    def test_ctrl_v_binding_exists(self):
        from sovereign_agent.cockpit.app import CockpitApp
        ctrl_v = [b for b in CockpitApp.BINDINGS
                  if getattr(b, "key", None) == "ctrl+v"]
        assert ctrl_v, "Ctrl+V binding missing from CockpitApp.BINDINGS"
        action = getattr(ctrl_v[0], "action", None)
        assert action == "paste_clipboard", (
            f"Ctrl+V should map to action 'paste_clipboard', got {action!r}"
        )

    def test_action_paste_clipboard_exists(self):
        from sovereign_agent.cockpit.app import CockpitApp
        assert hasattr(CockpitApp, "action_paste_clipboard"), (
            "CockpitApp must define action_paste_clipboard()"
        )

    def test_read_clipboard_handles_missing_tools(self, monkeypatch):
        """If no clipboard tool is available, _read_clipboard returns ''
        rather than raising. The cockpit must degrade gracefully."""
        from sovereign_agent.cockpit.app import CockpitApp
        import shutil
        # Force shutil.which to return None for every binary
        monkeypatch.setattr(shutil, "which", lambda _name: None)
        result = CockpitApp._read_clipboard()
        assert result == "", (
            f"_read_clipboard() should return '' when no clipboard tool "
            f"is present; got {result!r}"
        )


# ════════════════════════════════════════════════════════════════════════════
# Rule-margin discipline — MOS-SURFACE §6.2 (introduced v1.3)
# ════════════════════════════════════════════════════════════════════════════


class TestRuleMarginDiscipline:
    """Textual's Rule widget ships with `margin: 0 2` baked into its
    DEFAULT_CSS for vertical orientation. That default reserves two
    cells of horizontal margin on EACH SIDE of the line — four cells
    of dead space the Rule does not paint, which then leak as a faint
    seam at the divider's top and bottom edges where they meet the
    rounded outer border of #main.

    This was the actual cause of the "leaking blackness near the middle
    border" the operator screenshotted through v0.2.18.0 → v0.2.18.4.
    Three earlier doctrine iterations (S2 border-ownership, S7 opacity,
    §16.1 scrollbar) addressed adjacent failure modes but missed this
    one because none of them named the Rule widget's DEFAULT_CSS.

    The fix is one CSS line on #divider: `margin: 0;`. This test
    enforces it so the regression cannot recur silently.
    """

    def test_divider_explicitly_overrides_rule_default_margin(self):
        path = SRC_DIR / "cockpit" / "app.py"
        src = path.read_text()
        css_match = re.search(r'(?:^|\W)CSS\s*=\s*"""(.*?)"""', src, re.DOTALL)
        assert css_match, "main CSS block not found"
        css = css_match.group(1)
        # v0.2.25.0: two divider rules (#divider-1, #divider-2). Both
        # must declare margin: 0. The doctrine point — overriding
        # Textual Rule's DEFAULT_CSS `margin: 0 2` — applies to every
        # divider in the cockpit.
        for selector in ("#divider-1", "#divider-2"):
            rule = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", css)
            assert rule, f"{selector} CSS rule not found"
            body = rule.group(1)
            assert re.search(r"\bmargin\s*:\s*0\b", body), (
                f"{selector} must explicitly declare `margin: 0;` to "
                f"override Textual's Rule.-vertical DEFAULT_CSS "
                f"`margin: 0 2`. Without this override, four cells of "
                f"unpainted margin surround the divider, leaking the "
                f"parent compositor's background at the top edge and "
                f"producing the 'misaligned border' artifact. "
                f"See MOS-SURFACE §6.2."
            )

    def test_textual_rule_default_margin_is_still_two(self):
        """Sanity check: if Textual ever changes Rule's default margin,
        we want to know about it. This test pins the assumption the
        §6.2 rule was written against. If this test fails on a
        Textual upgrade, re-verify §6.2 is still correct and update
        the assertion."""
        from textual.widgets import Rule
        # The DEFAULT_CSS for vertical is the failure mode we override.
        # If Textual ships a different default (e.g. margin: 0 0), the
        # §6.2 rule is unchanged but its rationale block should note
        # the version that introduced the change.
        assert "margin: 0 2" in Rule.DEFAULT_CSS, (
            "Textual's Rule.DEFAULT_CSS no longer contains "
            "`margin: 0 2`. Verify MOS-SURFACE §6.2 is still applicable "
            "to the new default before relaxing the #divider override."
        )


# ════════════════════════════════════════════════════════════════════════════
# Binding priority discipline — MOS-SURFACE §19.1 (introduced v1.3)
# ════════════════════════════════════════════════════════════════════════════


class TestBindingPriority:
    """The Textual `Input` widget — the cockpit's focused widget on
    launch — ships with internal BINDINGS for ctrl+v (paste), ctrl+d
    (delete_right), ctrl+a, ctrl+e, ctrl+w, ctrl+u, ctrl+k, ctrl+x,
    most marked show=False.

    Without `priority=True`, an app-level binding for the same key is
    consumed by the focused Input before it reaches the app's action.
    Worse: the Input's binding has show=False, so the Footer hides the
    key entirely — the operator sees neither the action firing nor the
    key in the footer hint row.

    This is exactly the failure mode that hid `^v paste` and `^d disarm`
    from the v0.2.18.4 footer and broke Ctrl+V paste. The fix is
    `priority=True` on every Ctrl+* binding at the app level. This
    test enforces it so a future maintainer adding a new Ctrl+* binding
    without priority=True is caught at CI time.
    """

    SHADOWED_KEYS = {"ctrl+v", "ctrl+d", "ctrl+a", "ctrl+e",
                     "ctrl+w", "ctrl+u", "ctrl+k", "ctrl+x"}

    def test_ctrl_v_binding_has_priority(self):
        from sovereign_agent.cockpit.app import CockpitApp
        ctrl_v = next(
            (b for b in CockpitApp.BINDINGS
             if getattr(b, "key", None) == "ctrl+v"),
            None,
        )
        assert ctrl_v is not None, "Ctrl+V binding missing"
        assert getattr(ctrl_v, "priority", False) is True, (
            "Ctrl+V binding must have priority=True to override the "
            "Textual Input widget's internal ctrl+v → paste binding. "
            "Without priority, the operator presses Ctrl+V, the Input "
            "consumes it, the app's paste_clipboard never runs, and the "
            "footer hides ^v entirely. See MOS-SURFACE §19.1."
        )

    def test_ctrl_d_binding_has_priority(self):
        from sovereign_agent.cockpit.app import CockpitApp
        ctrl_d = next(
            (b for b in CockpitApp.BINDINGS
             if getattr(b, "key", None) == "ctrl+d"),
            None,
        )
        assert ctrl_d is not None, "Ctrl+D binding missing"
        assert getattr(ctrl_d, "priority", False) is True, (
            "Ctrl+D binding must have priority=True. The Input widget's "
            "internal `delete,ctrl+d` → delete_right binding shadows it "
            "otherwise. See MOS-SURFACE §19.1."
        )

    def test_all_ctrl_bindings_marked_priority(self):
        """Every Ctrl+* binding on CockpitApp must be priority=True.
        This is a forward-looking enforcement: if a future maintainer
        adds, e.g., Ctrl+K for some new action, it would otherwise be
        silently shadowed by the Input's ctrl+k → delete_right_all."""
        from sovereign_agent.cockpit.app import CockpitApp
        violations = []
        for b in CockpitApp.BINDINGS:
            key = getattr(b, "key", "")
            if key.startswith("ctrl+"):
                if not getattr(b, "priority", False):
                    violations.append(key)
        assert not violations, (
            f"These Ctrl+* bindings on CockpitApp lack priority=True: "
            f"{violations}. The Textual Input widget's internal "
            f"BINDINGS shadow several Ctrl+* keys (paste, cut, delete, "
            f"word-motion); only priority bindings reliably fire. "
            f"See MOS-SURFACE §19.1."
        )


# ════════════════════════════════════════════════════════════════════════════
# Slash-command argument-name regression — concrete bug from v0.2.18.4
# ════════════════════════════════════════════════════════════════════════════


class TestSlashCommandArgumentName:
    """The v0.2.18.4 _handle_slash() introduced a NameError: the
    variable was named `arg` at the top of the function, but
    `/drafts`, `/draft`, and `/marketing` branches referenced an
    undefined `rest`. The branches crashed at runtime for any
    operator who used those commands.

    This test scans _handle_slash for the regression pattern.
    """

    def test_handle_slash_uses_consistent_arg_name(self):
        from sovereign_agent.cockpit import app as app_mod
        import ast
        import inspect
        import textwrap
        src = textwrap.dedent(
            inspect.getsource(app_mod.CockpitApp._handle_slash))
        # The function's local variable is `arg`. Any reference to a
        # bare `rest` IDENTIFIER inside _handle_slash would be a
        # NameError at runtime. String literals (the `/rest` slash verb,
        # resume-spine-d) are not references — check real AST Names so
        # the guard can't false-positive on them. (one-truth round: the
        # original regex matched `verb == "rest"` and cried wolf.)
        tree = ast.parse(src)
        bare_rest = [n for n in ast.walk(tree)
                     if isinstance(n, ast.Name) and n.id == "rest"]
        assert not bare_rest, (
            f"_handle_slash() references undefined name `rest` "
            f"({len(bare_rest)} occurrences). The local variable is "
            f"`arg`; rename all `rest` references. This crashed "
            f"`/drafts`, `/draft`, and `/marketing` at runtime in "
            f"v0.2.18.4."
        )

    def test_drafts_branch_uses_arg(self):
        """The `/drafts` branch must use the local `arg` variable, not
        any undefined name. This is a more specific regression test."""
        from sovereign_agent.cockpit import app as app_mod
        import inspect
        src = inspect.getsource(app_mod.CockpitApp._handle_slash)
        # Find the /drafts branch (verb == "drafts")
        drafts_match = re.search(
            r'verb\s*==\s*"drafts".*?(?=elif verb|else:)',
            src, re.DOTALL,
        )
        assert drafts_match, "could not locate /drafts branch"
        drafts_block = drafts_match.group(0)
        # The branch must reference `arg` (the parsed argument).
        assert re.search(r"\barg\b", drafts_block), (
            "/drafts branch must reference the `arg` local variable"
        )


# ════════════════════════════════════════════════════════════════════════════
# Interactive subprocess discipline — MOS-SURFACE §19.2 (introduced v1.4)
# ════════════════════════════════════════════════════════════════════════════


class TestInteractiveSubprocessDiscipline:
    """Through v0.2.18.5, the cockpit launched `sovereign do` with
    stdout piped but stdin NOT piped. When the planner asked a
    clarifying question (`input("  > ")` in cli.py), the subprocess
    inherited the controlling TTY's stdin — which Textual owns — and
    blocked forever waiting for input that could never reach it. The
    cockpit's `_busy` flag never cleared and every subsequent operator
    submission was rejected with "aria is still working". The operator
    appeared unable to type at all.

    The fix has three parts, each enforced here:

    1. Directive subprocesses launch with `stdin=PIPE`, allowing the
       cockpit to forward operator input.
    2. The cockpit defines `_answer_subprocess`, called when the
       operator submits non-slash input while `_busy=True`.
    3. The cockpit defines `action_cancel_directive` and routes
       `/cancel`, `/abort`, and `/stop` slash commands to it,
       providing a guaranteed escape hatch.
    """

    def test_directive_worker_uses_stdin_pipe(self):
        """The worker must launch the subprocess with stdin piped."""
        from sovereign_agent.cockpit import app as app_mod
        import inspect
        src = inspect.getsource(app_mod.CockpitApp._run_directive_worker)
        assert "stdin=asyncio.subprocess.PIPE" in src, (
            "_run_directive_worker must launch the subprocess with "
            "`stdin=asyncio.subprocess.PIPE`. Without this, "
            "`sovereign do` blocks on `input()` and the cockpit "
            "deadlocks when the planner asks a clarifying question. "
            "See MOS-SURFACE §19.2."
        )

    def test_directive_worker_sets_pythonunbuffered(self):
        """The subprocess must run with PYTHONUNBUFFERED=1 so its
        prompt output isn't block-buffered when stdout is a pipe.
        Without this, Python switches to block buffering and the
        `  > ` prompt from `input()` never reaches the operator."""
        from sovereign_agent.cockpit import app as app_mod
        import inspect
        src = inspect.getsource(app_mod.CockpitApp._run_directive_worker)
        assert "PYTHONUNBUFFERED" in src, (
            "_run_directive_worker must set PYTHONUNBUFFERED=1 in "
            "the subprocess environment so input prompts flush "
            "immediately. See MOS-SURFACE §19.2."
        )

    def test_directive_worker_tracks_proc_on_self(self):
        """The worker must store the running subprocess on `self._proc`
        so the operator can answer it via _answer_subprocess and cancel
        it via action_cancel_directive."""
        from sovereign_agent.cockpit import app as app_mod
        import inspect
        src = inspect.getsource(app_mod.CockpitApp._run_directive_worker)
        assert "self._proc = proc" in src, (
            "_run_directive_worker must assign the running subprocess "
            "to `self._proc` so /cancel and _answer_subprocess can "
            "find it. See MOS-SURFACE §19.2."
        )

    def test_directive_worker_clears_proc_in_finally(self):
        """The worker's finally block must clear `self._proc` before
        clearing `self._busy`, to prevent a race where an operator
        submission sees `_busy=True` and routes to a stale subprocess."""
        from sovereign_agent.cockpit import app as app_mod
        import inspect
        src = inspect.getsource(app_mod.CockpitApp._run_directive_worker)
        # Find the finally block
        finally_match = re.search(r"finally:\s*\n(.*?)(?=\n\s{0,4}\S|\Z)",
                                  src, re.DOTALL)
        assert finally_match, "could not locate finally block"
        finally_body = finally_match.group(1)
        proc_idx = finally_body.find("self._proc = None")
        busy_idx = finally_body.find("self._busy = False")
        assert proc_idx != -1, (
            "finally block must clear self._proc = None"
        )
        assert busy_idx != -1, (
            "finally block must clear self._busy = False"
        )
        assert proc_idx < busy_idx, (
            "self._proc must be cleared BEFORE self._busy in the "
            "finally block. Reversing the order opens a race where a "
            "racing submission sees `_busy=False` AND a non-None "
            "_proc, or `_busy=True` AND a None _proc — both states "
            "are surprising. See MOS-SURFACE §19.2."
        )

    def test_answer_subprocess_method_exists(self):
        from sovereign_agent.cockpit.app import CockpitApp
        assert hasattr(CockpitApp, "_answer_subprocess"), (
            "CockpitApp must define _answer_subprocess() to forward "
            "operator input to the running subprocess's stdin. "
            "See MOS-SURFACE §19.2."
        )

    def test_action_cancel_directive_exists(self):
        from sovereign_agent.cockpit.app import CockpitApp
        assert hasattr(CockpitApp, "action_cancel_directive"), (
            "CockpitApp must define action_cancel_directive() so "
            "the operator has a guaranteed way to escape a stuck "
            "directive. See MOS-SURFACE §19.2."
        )

    def test_on_input_submitted_routes_when_busy(self):
        """When _busy=True and the input is non-slash, the router
        must forward to _answer_subprocess, NOT to _dispatch_directive
        (which would just write the 'wait a moment' message and lose
        the input)."""
        from sovereign_agent.cockpit import app as app_mod
        import inspect
        src = inspect.getsource(app_mod.CockpitApp.on_input_submitted)
        assert "_answer_subprocess" in src, (
            "on_input_submitted must route to _answer_subprocess "
            "when busy. Otherwise operator input is lost while a "
            "directive is mid-flight. See MOS-SURFACE §19.2."
        )
        assert "_busy" in src, (
            "on_input_submitted must check _busy to know whether to "
            "answer the running subprocess or dispatch a new directive."
        )

    def test_slash_cancel_routes_to_action(self):
        """`/cancel`, `/abort`, `/stop` must all route to
        action_cancel_directive."""
        from sovereign_agent.cockpit import app as app_mod
        import inspect
        src = inspect.getsource(app_mod.CockpitApp._handle_slash)
        # The cancel/abort/stop tuple must appear AND the action call
        # must appear within that elif branch. We don't require them
        # on adjacent lines — comments may intervene.
        tuple_match = re.search(
            r'verb\s+in\s+\(\s*"cancel"\s*,\s*"abort"\s*,\s*"stop"\s*\)',
            src,
        )
        assert tuple_match, (
            "_handle_slash must include `elif verb in (\"cancel\", "
            "\"abort\", \"stop\"):` so all three aliases route to the "
            "same handler. See MOS-SURFACE §19.2."
        )
        # The branch body (between the tuple match and the next elif/else)
        # must call action_cancel_directive.
        after_tuple = src[tuple_match.end():]
        next_branch = re.search(r"\n\s*(elif\s|else:)", after_tuple)
        branch_body = after_tuple[: next_branch.start()] if next_branch else after_tuple
        assert "action_cancel_directive" in branch_body, (
            "the cancel/abort/stop slash branch must call "
            "self.action_cancel_directive(). See MOS-SURFACE §19.2."
        )

    def test_placeholder_constants_exist(self):
        """The cockpit must define both PLACEHOLDER_IDLE and
        PLACEHOLDER_BUSY so the input box reflects the operator's
        current mode (initiating a directive vs answering one)."""
        from sovereign_agent.cockpit.app import CockpitApp
        assert hasattr(CockpitApp, "PLACEHOLDER_IDLE"), (
            "CockpitApp must define PLACEHOLDER_IDLE"
        )
        assert hasattr(CockpitApp, "PLACEHOLDER_BUSY"), (
            "CockpitApp must define PLACEHOLDER_BUSY"
        )
        assert "cancel" in CockpitApp.PLACEHOLDER_BUSY.lower(), (
            "PLACEHOLDER_BUSY must mention `/cancel` so the operator "
            "knows the escape hatch when a directive is running"
        )
