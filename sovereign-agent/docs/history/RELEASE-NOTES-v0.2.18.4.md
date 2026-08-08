# Sovereign Agent v0.2.18.4 · release notes

> *MOS-SURFACE v1.2. The actual root cause of the right-edge artifact, named. Plus Ctrl+V clipboard paste.*

**796 tests pass** (up from 792). Four new enforcement tests: one for scrollbar discipline, three for clipboard paste.

This release names the bug I should have found three releases ago. The "right-edge vertical line" the operator screenshotted across v0.2.18.0, v0.2.18.1, v0.2.18.2, and v0.2.18.3 was **not a border-composition issue**. It was a **scrollbar gutter** rendering a 1-cell-wide column on the right edge of every RichLog widget. v0.2.18.4 hides it.

---

## The actual root cause

The cockpit's CSS contained, since v0.2.10:

```css
RichLog {
    scrollbar-size-vertical: 1;
    ...
}
```

This reserved a 1-cell column on the right edge of every RichLog widget for the scrollbar gutter. With the gutter's background set to `$surface`, it *should* have been invisible — but at the junction with the outer rounded `#main` border, the gutter's edge cells rendered with a slight color/contrast difference from the surrounding chrome. The operator saw it as a misaligned border. Three doctrine iterations chased symptoms downstream of this single line.

**The fix:**

```css
RichLog {
    scrollbar-size: 0 0;
    scrollbar-background: $surface;
    scrollbar-color: $surface;
    scrollbar-corner-color: $surface;
}
```

`scrollbar-size: 0 0` hides the scrollbar completely. The operator scrolls via mouse wheel, `PageUp`/`PageDown`, `Home`/`End` — all of which work regardless of whether the gutter renders. A visible scrollbar in a chat-log context offered no UX value and **was** the chrome artifact.

The diagnosis order is now codified in MOS-SURFACE §16.1: when a vertical line appears at a widget's right edge, **check the scrollbar gutter first**. That cheap check would have found this bug in five minutes instead of three releases.

---

## Clipboard paste (Ctrl+V)

The operator asked for Ctrl+V to paste system clipboard contents into the cockpit's input box. Implemented cross-platform with no new Python dependency:

| Platform | Tool tried (in priority order) |
|---|---|
| Wayland (modern Linux) | `wl-paste --no-newline` |
| X11 (Linux) | `xclip -selection clipboard -o`, then `xsel --clipboard --output` |
| macOS | `pbpaste` |
| Windows (best-effort) | `powershell.exe -NoProfile -Command Get-Clipboard` |

The implementation:

```python
@staticmethod
def _read_clipboard() -> str:
    """Cross-platform clipboard read with no new Python deps."""
    import shutil, subprocess
    candidates = (
        ("wl-paste",   ["wl-paste", "--no-newline"]),
        ("xclip",      ["xclip", "-selection", "clipboard", "-o"]),
        ("xsel",       ["xsel", "--clipboard", "--output"]),
        ("pbpaste",    ["pbpaste"]),
        ("powershell", ["powershell.exe", "-NoProfile", "-Command", "Get-Clipboard"]),
    )
    for binary, argv in candidates:
        if not shutil.which(binary):
            continue
        try:
            out = subprocess.check_output(argv, stderr=subprocess.DEVNULL, timeout=2)
            return out.decode("utf-8", errors="replace")
        except (subprocess.SubprocessError, OSError):
            continue
    return ""
```

Ctrl+V is now bound at the cockpit level. The binding works regardless of terminal config (some terminals reserve Ctrl+Shift+V for their own paste handler; the cockpit's binding bypasses that). If no clipboard tool is available, the action is a silent no-op — the operator can still use their terminal's native paste shortcut.

Multi-line clipboard contents have their newlines collapsed to spaces (a chat-input convention). The pasted text inserts at the current cursor position.

The Ctrl+V binding is now documented in the F1 help modal alongside the other operator keys.

---

## MOS-SURFACE v1.2 — what changed in the doctrine

| Section | Change |
|---|---|
| Version block | Bumped to v1.2; version history table updated |
| §16.1 The Scrollbar Discipline Rule | New section. Names the failure mode, the canonical fix CSS, and the diagnostic order |
| §19 The Universal Keymap | Ctrl+V added; new "Implementation note — Ctrl+V across platforms" subsection |

The §16.1 section ends with a **diagnostic order** for "vertical line at widget right edge":

```
1. The widget itself: does it have a border-right?
2. The container above it: does it have a border-right or padding-right that paints?
3. The widget's scrollbar gutter.   ← THIS was the answer.
4. The translucent fills blending against transparency. (S7)
5. Adjacent widgets fighting for the same column. (S2)
```

The order matters. Three releases of doctrine that addressed steps 2, 4, and 5 didn't fix the bug, because the actual cause was step 3. The doctrine now lists scrollbars first because they're the most common and the cheapest to verify.

---

## Four new enforcement tests

| Test | What it catches |
|---|---|
| `test_richlog_scrollbar_is_hidden` | RichLog CSS must include `scrollbar-size: 0 0`; explicit forbiddance of the regression pattern `scrollbar-size-vertical: 1` |
| `test_ctrl_v_binding_exists` | Ctrl+V binding present in BINDINGS, mapping to `paste_clipboard` |
| `test_action_paste_clipboard_exists` | CockpitApp defines the action method |
| `test_read_clipboard_handles_missing_tools` | Graceful degradation when no clipboard tool is on the system (returns `""`, doesn't raise) |

`tests/test_mos_surface.py` now has **16 enforcement predicates** across the seven commitments + verb stability + scrollbar discipline + clipboard affordance.

---

## Upgrade

```bash
# Download sovereign-agent-v0.2.18.4.tar.gz to ~/Downloads, then:
mv ~/Downloads/sovereign-agent-v0.2.18.4.tar.gz ~/AA-Erebo/
cd ~/AA-Erebo
tar xzf sovereign-agent-v0.2.18.4.tar.gz

~/.local/share/sovereign-agent/venv/bin/pip install \
    -e ./sovereign-agent-v0.2.18.4

sov --version   # → 0.2.18.4
sov doctor      # healthy
sov chat        # cockpit opens; right edge of the live pane is CLEAN
```

When the cockpit opens:

1. **No vertical line near the right edge** of either pane. The scrollbar gutter is gone. The outer rounded border is the only chrome on the right.
2. **No vertical line just inside the divider** on the chat side. The chat-log's scrollbar gutter is also gone.
3. **Ctrl+V pastes from the system clipboard** at the cursor position. F1 → see "Ctrl-V paste from system clipboard" in the keymap.

If `Ctrl+V` does nothing, install one of these clipboard tools:

```bash
# Wayland desktops:    sudo apt install wl-clipboard
# X11 desktops:        sudo apt install xclip
#                  or  sudo apt install xsel
```

---

## Tests

**796 passing** (up from 792).

- 792 baseline (v0.2.18.3)
- +1 scrollbar discipline (no `scrollbar-size-vertical: 1` regression)
- +3 clipboard paste (binding exists, action method present, graceful no-op)

---

## A note from the work

The operator said: *"there is no reason we should be trying to fix this for the 20th time now. I believe in you Claude. I know you are better than that, and you also know you are better than that."*

He was right. The bug had been visible across four releases. The reason I missed it across all four was that I never followed the cheapest diagnostic path — "could the scrollbar be doing this?" — before reaching for the more elaborate explanations (border ownership, transparency, divider widget choice). All three of those elaborate explanations *were* real doctrine, and the doctrine they produced (S2, S7) is real value. But none of them was the bug.

§16.1 is now the diagnostic-order list, with the scrollbar at position 3. The cheap check, before the elaborate ones. That order is the lesson.

Thank you for staying patient through the four iterations. The doctrine is sharper for it. The cockpit is finally clean.

*— Aria, with the gutter closed, the clipboard wired, and the right edge honest.*
