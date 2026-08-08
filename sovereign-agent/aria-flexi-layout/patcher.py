"""patcher.py — Keys round K2: aria-flexi-layout.

Kevin asked whether the live observability windows should be horizontal
instead of vertical. Answer shipped as a CHOICE, not a guess: Ctrl+O
toggles between Layout A (today's 5 side-by-side columns) and Layout B
(chat keeps its tall column on the left; the four observability panes
become FULL-WIDTH stacked rows on the right — log lines are wide, and a
fifth-of-the-terminal column truncates them brutally). The preference
persists across launches.

Implementation is deliberately tree-untouched: Layout B is pure CSS — a
grid on #main (chat row-spans all 4 rows in column 1; memory/live/inbox/
atelier fill column 2's rows in compose order; the vertical Rule dividers
hide). RippleFrame subclasses Horizontal, and Textual's `layout` style
overrides the container default, so the rippling frame keeps working in
both layouts.

Four anchored, idempotent patches to cockpit/app.py:
  1. The Layout B CSS block.
  2. The Ctrl+O binding.
  3. `action_toggle_layout` + `_apply_saved_layout` + pref-path helper.
  4. `_apply_saved_layout()` call on mount.
"""
from __future__ import annotations

MARK = "flexi-layout-d"


class PatchError(Exception):
    pass


def _replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if text.count(old) != 1:
        raise PatchError(f"{label}: expected exactly 1 occurrence, found {text.count(old)}")
    return text.replace(old, new, 1)


# 1. CSS
CSS_ANCHOR = (
    "    #atelier-pane {\n"
    "        width: 1fr;\n"
    "        padding: 0 1;\n"
    "        background: $surface;\n"
    "    }\n"
)
CSS_NEW = (
    CSS_ANCHOR
    + f"""
    /* {MARK} — Layout B: chat tall column left, observability panes
       stacked as FULL-WIDTH rows right (log lines are wide; narrow columns
       truncate them). Toggled with Ctrl+O; preference persisted. Pure CSS:
       the widget tree is untouched, RippleFrame keeps painting its ring. */
    #main.layout-rows {{
        layout: grid;
        grid-size: 2 4;
        grid-columns: 2fr 3fr;
        grid-rows: 1fr 1fr 1fr 1fr;
    }}
    #main.layout-rows #chat-pane {{ row-span: 4; width: 100%; height: 100%; }}
    #main.layout-rows #memory-pane {{ width: 100%; height: 100%; }}
    #main.layout-rows #live-pane {{ width: 100%; height: 100%; }}
    #main.layout-rows #inbox-pane {{ width: 100%; height: 100%; }}
    #main.layout-rows #atelier-pane {{ width: 100%; height: 100%; }}
    #main.layout-rows Rule {{ display: none; }}
"""
)

# 2. binding
BINDING_ANCHOR = (
    '        Binding("ctrl+m", "command_palette", "commands", show=True, priority=True),  # command-menu-d\n'
)
BINDING_NEW = (
    BINDING_ANCHOR
    + f'        Binding("ctrl+o", "toggle_layout", "layout", show=True, priority=True),  # {MARK}\n'
)

# 3. methods
METHODS_ANCHOR = (
    "    def _refresh_cockpit_strips(self) -> None:  # command-menu-d\n"
)
METHODS_NEW = (
    f"    def _layout_pref_path(self):  # {MARK}\n"
    "        from sovereign_agent.config import SETTINGS\n"
    "\n"
    '        return SETTINGS.paths.config_dir / "cockpit_layout.json"\n'
    "\n"
    f"    def action_toggle_layout(self) -> None:  # {MARK}\n"
    '        """Ctrl+O: toggle Layout A (5 columns) <-> Layout B (chat column +\n'
    '        stacked observability rows). Persists the preference."""\n'
    "        import json as _json\n"
    "\n"
    "        try:\n"
    '            main = self.query_one("#main")\n'
    "        except Exception:  # noqa: BLE001\n"
    "            return\n"
    '        rows = not main.has_class("layout-rows")\n'
    "        if rows:\n"
    '            main.add_class("layout-rows")\n'
    "        else:\n"
    '            main.remove_class("layout-rows")\n'
    "        try:\n"
    "            self._layout_pref_path().write_text(\n"
    '                _json.dumps({"layout": "rows" if rows else "columns"}),\n'
    '                encoding="utf-8",\n'
    "            )\n"
    "        except Exception:  # noqa: BLE001 — a pref-write failure never breaks the toggle\n"
    "            pass\n"
    "        self._write_meta(\n"
    '            f"[dim]◊ layout: {\'rows\' if rows else \'columns\'}[/dim]"\n'
    "        )\n"
    "\n"
    f"    def _apply_saved_layout(self) -> None:  # {MARK}\n"
    '        """On mount: honor the persisted layout preference."""\n'
    "        import json as _json\n"
    "\n"
    "        try:\n"
    "            pref = _json.loads(self._layout_pref_path().read_text(encoding=\"utf-8\"))\n"
    '            if pref.get("layout") == "rows":\n'
    '                self.query_one("#main").add_class("layout-rows")\n'
    "        except Exception:  # noqa: BLE001 — no pref file = Layout A, silently\n"
    "            pass\n"
    "\n"
    "    def _refresh_cockpit_strips(self) -> None:  # command-menu-d\n"
)

# 4. on_mount hook
MOUNT_ANCHOR = (
    "        self.set_interval(3600.0, self._maybe_run_auto_backup)  # auto-backup-d\n"
)
MOUNT_NEW = (
    MOUNT_ANCHOR
    + f"        self._apply_saved_layout()  # {MARK}\n"
)


def patch_app(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(text, CSS_ANCHOR, CSS_NEW, label="app CSS anchor")
    text = _replace_once(text, BINDING_ANCHOR, BINDING_NEW, label="app binding anchor")
    text = _replace_once(text, METHODS_ANCHOR, METHODS_NEW, label="app methods anchor")
    text = _replace_once(text, MOUNT_ANCHOR, MOUNT_NEW, label="app mount anchor")
    return text, True
