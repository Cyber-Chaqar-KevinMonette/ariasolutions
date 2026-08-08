#!/usr/bin/env bash
# apply_cockpit_god.sh — M46: God-Tier Cockpit Upgrade
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo "==> M46 cockpit-god: $REPO"

python3 - "$REPO" <<'PYEOF'
import sys
from pathlib import Path

repo = Path(sys.argv[1])

def patch(path, old, new, marker):
    src = path.read_text()
    if marker in src:
        print(f"  SKIP {path.name} — already patched ({marker})")
        return False
    if old not in src:
        print(f"  ERROR {path.name} — anchor not found for {marker}", file=sys.stderr)
        print(f"  Searched for: {old[:80]!r}", file=sys.stderr)
        sys.exit(1)
    path.write_text(src.replace(old, new, 1))
    print(f"  OK   {path.name} ({marker})")
    return True

app = repo / "src/sovereign_agent/cockpit/app.py"

# ── 1. _TOOL_BUTTON_MAP before CommandButton class ───────────────────────────
patch(app,
    old='class CommandButton(RippleBorderMixin, Button):',
    new='''\
# Aria-to-palette animation map: when Aria uses these tools, the matching  # cockpit-god-d
# palette button gets the aria-active CSS class for visual feedback.
_TOOL_BUTTON_MAP: dict[str, str] = {
    "aria_status":            "aria",
    "vessel_comfort":         "status",
    "mode_status":            "status",
    "read_session":           "info",
    "read_lessons":           "doctor",
    "session_resume_audit":   "inbox",
    "read_checkpoints":       "inbox",
    "list_objectives":        "parked",
    "get_emotions":           "aria",
    "emotion_report":         "aria",
    "research_queue":         "parked",
    "vision_capture":         "caps",
    "leverage_audit":         "parked",
    "session_brief_read":     "channels",
    "auto_status":            "status",
}


class CommandButton(RippleBorderMixin, Button):''',
    marker="cockpit-god-d",
)

# ── 2. Button animation on tool-start-d ──────────────────────────────────────
patch(app,
    old='            self._render_status_bar()\n            return\n        if flag == "token-usage-d":',
    new='''\
            self._render_status_bar()
            # cockpit-god-button-d — pulse matching palette button
            _btn_key = _TOOL_BUTTON_MAP.get(self._last_tool)
            if _btn_key:
                try:
                    _btn = self.query_one(f"#palette-{_btn_key}", CommandButton)
                    _btn.add_class("aria-active")
                    self.set_timer(2.5, lambda b=_btn: b.remove_class("aria-active"))
                except Exception:  # noqa: BLE001
                    pass
            return
        if flag == "token-usage-d":''',
    marker="cockpit-god-button-d",
)

# ── 3. New slash commands: /emotion /vision /auto /brief ──────────────────────
patch(app,
    old='        # vitality-display-d\n        # command-invariants-slash-d',
    new='''\
        elif verb == "emotion":
            # cockpit-god-slash-d
            self._dispatch_directive(
                "call get_emotions() and report my current emotional state "
                "with all 8 dimensions and narrative"
            )
        elif verb == "vision":
            self._dispatch_directive(
                "call vision_capture() to capture the screen, then tell me "
                "what you see and what I appear to be working on"
            )
        elif verb == "brief":
            self._dispatch_directive(
                "call session_brief_read(limit=3) and summarize the last "
                "session briefs — what was accomplished and what's pending"
            )
        elif verb == "auto":
            _auto_arg = arg.strip()
            if _auto_arg.lower() in ("stop", "cancel"):
                self._dispatch_directive(
                    "call stop_auto(reason='operator cancelled via /auto stop') "
                    "to end the autonomous session"
                )
            elif _auto_arg:
                try:
                    _auto_h = float(_auto_arg)
                    self._dispatch_directive(
                        f"call start_auto(duration_hours={_auto_h}, "
                        f"reason='operator requested /auto {_auto_h}h')"
                    )
                except ValueError:
                    self._write_meta("[yellow]usage: /auto <hours> | /auto stop[/yellow]")
            else:
                self._dispatch_directive("call auto_status() to show autonomous session status")
        # vitality-display-d
        # command-invariants-slash-d''',
    marker="cockpit-god-slash-d",
)

# ── 4. Auto timer in status bar ───────────────────────────────────────────────
patch(app,
    old='        obs_suffix = "  │  " + "  ".join(obs_parts) if obs_parts else ""',
    new='''\
        obs_suffix = "  │  " + "  ".join(obs_parts) if obs_parts else ""
        # cockpit-god-statusbar-d — auto timer
        _auto_suffix = ""
        try:
            import json as _jjson, time as _tt
            _ac_path = SETTINGS.paths.data_dir / "auto_crown.json"
            if _ac_path.exists():
                _ac = _jjson.loads(_ac_path.read_text())
                if _ac.get("status") == "active":
                    _rem_s = max(0, _ac.get("expires_at", 0) - _tt.time())
                    _rem_m = int(_rem_s / 60)
                    _c = "red" if _rem_m < 2 else "yellow" if _rem_m < 10 else "cyan"
                    _auto_suffix = f"  │  [{_c}]⏱ {_rem_m}m[/{_c}]"
        except Exception:  # noqa: BLE001
            pass''',
    marker="cockpit-god-statusbar-d",
)

# ── 5. Use _auto_suffix in status bar update ──────────────────────────────────
patch(app,
    old='            f"{metrics}{obs_suffix}"\n        )',
    new='''\
            f"{metrics}{obs_suffix}{_auto_suffix}"
        )''',
    marker="cockpit-god-autosuffix-d",
)

# ── 6. CSS for aria-active buttons ────────────────────────────────────────────
patch(app,
    old='    /* CSS class applied while a matching subprocess is running */',
    new='''\
    /* cockpit-god-d — Aria active: button glows when Aria uses the mapped tool */
    #palette-row CommandButton.aria-active,
    #palette-row-2 CommandButton.aria-active,
    #palette-row-3 CommandButton.aria-active {
        border: round $warning;
        background: $warning 20%;
        color: $warning;
    }
    /* CSS class applied while a matching subprocess is running */''',
    marker="cockpit-god-css-d",
)

print("M46 cockpit-god: all patches applied.")
PYEOF

cp "$REPO/aria-cockpit-god/tests/test_cockpit_god.py" "$REPO/tests/test_cockpit_god.py"
echo "==> M46 done. Run: .venv/bin/python -m pytest tests/test_cockpit_god.py -q"
