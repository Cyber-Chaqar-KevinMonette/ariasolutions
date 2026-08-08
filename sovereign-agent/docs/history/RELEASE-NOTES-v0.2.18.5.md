# Sovereign Agent v0.2.18.5 · release notes

> *MOS-SURFACE v1.3. Two failure modes named that v0.2.18.4 left intact: the divider's hidden margin, and the Input widget's hidden bindings. Plus the `/drafts` NameError. Plus the keymap finally visible in the footer.*

**803 tests pass** (up from 796). Seven new enforcement tests across two new doctrine sections (§6.2, §19.1) plus the slash-command regression.

This release does what v0.2.18.4 promised but didn't deliver: the divider artifact is genuinely gone, `Ctrl+V` actually pastes from the system clipboard, and the keymap row at the bottom of the cockpit shows every key the operator has bound. Three latent bugs that survived v0.2.18.4 are also closed.

---

## The four bugs

### 1. The "leaking blackness near the middle border"

The visual the operator screenshotted across v0.2.18.0 → v0.2.18.4 was NOT the scrollbar (that was fixed in v0.2.18.4), NOT border-ownership (fixed in v1.0), and NOT transparency (fixed in v1.1). The actual cause:

Textual's `Rule` widget defines this in its `DEFAULT_CSS`:

```css
Rule.-vertical {
    width: 1;
    margin: 0 2;
    height: 1fr;
}
```

That `margin: 0 2` reserves **two cells of horizontal margin on each side** of the divider — four cells of unpainted dead space the Rule itself does not draw. Those margin cells render with whatever the parent compositor places there, and at the top edge of `#main` they leak as the faint dark/orange seam the operator saw.

The cockpit's `#divider` CSS in v0.2.18.4 did not override the margin. The fix is one line:

```css
#divider {
    width: 1;
    height: 1fr;
    margin: 0;                /* override Rule's `margin: 0 2` */
    color: $primary;
    background: $surface;
}
```

The visual breathing room between the divider and the panes is now supplied by each pane's own `padding: 0 1` — owned chrome on each pane's interior (S2-compliant) that renders solid `$surface`.

This rule is now MOS-SURFACE §6.2.

### 2. Ctrl+V did not actually paste

Textual's `Input` widget — the cockpit's focused widget on launch — ships with its own `BINDINGS` list that consumes several Ctrl+* keys before they reach the app:

| Input.BINDINGS key | Action | `show` |
|---|---|---|
| `ctrl+v` | `paste` (Textual's internal session clipboard) | False |
| `delete,ctrl+d` | `delete_right` | False |
| `home,ctrl+a` | `home` | False |
| `end,ctrl+e` | `end` | False |
| `ctrl+w` | `delete_left_word` | False |
| `ctrl+u` | `delete_left_all` | False |
| `ctrl+f` | `delete_right_word` | False |
| `ctrl+k` | `delete_right_all` | False |
| `ctrl+x` | `cut` | False |
| `ctrl+c,super+c` | `copy` | False |

Without `priority=True`, an app-level binding for the same key is consumed by the focused Input *first*; the app's action never runs. v0.2.18.4 added `Ctrl+V → paste_clipboard` correctly at the app level, but pressing Ctrl+V invoked `Input.action_paste` (Textual's internal session clipboard) instead — which does not read the OS clipboard at all.

**The fix:** every Ctrl+* binding on `CockpitApp` now has `priority=True`.

```python
BINDINGS = [
    Binding("ctrl+q", "quit",            "quit",   show=True, priority=True),
    Binding("ctrl+h", "halt",            "halt",   show=True, priority=True),
    Binding("ctrl+d", "disarm",          "disarm", show=True, priority=True),
    Binding("ctrl+l", "clear_chat",      "clear",  show=True, priority=True),
    Binding("ctrl+b", "toggle_heart",    "♥",      show=True, priority=True),
    Binding("ctrl+v", "paste_clipboard", "paste",  show=True, priority=True),
    Binding("f1,question_mark", "help",  "help",   show=True, priority=True),
]
```

Priority bindings dispatch *before* the focused widget's bindings. The operator's explicit app-level binding is now the contract; the widget's defaults defer.

This rule is now MOS-SURFACE §19.1.

### 3. `^v paste` and `^d disarm` missing from the footer

This had the same root cause as #2. Textual's `Footer` shows bindings from the in-scope chain. When a focused widget binding "owns" a key with `show=False`, the Footer suppresses that key — even if the app has a `show=True` binding for the same key. Result: `^v paste` and `^d disarm` were both invisible in v0.2.18.4 despite explicit `show=True`.

Adding `priority=True` unshadows them. The footer in v0.2.18.5 now reads:

```
^q quit  ^h halt  ^d disarm  ^l clear  ^b ♥  ^v paste  f1 help                 ^p palette
```

Every binding the operator can press is visible at a glance. No more "ask for help to find paste."

### 4. `/drafts`, `/draft`, `/marketing` crashed with NameError

Found while reviewing `_handle_slash`. The function defines its argument as the local `arg`, but the `/drafts`, `/draft`, and `/marketing` branches all referenced an undefined `rest`. Any operator who used those commands hit a `NameError` at runtime — silent in the cockpit since the exception was swallowed by the worker, but the command simply did nothing.

Renamed all four bare `rest.` references to `arg.`. Tested at parse time and via a regression test (`TestSlashCommandArgumentName`) that scans `_handle_slash` for any future `rest` reference.

---

## MOS-SURFACE v1.3 — what changed in the doctrine

| Section | Change |
|---|---|
| Version block | Bumped to v1.3; version history table updated |
| §6.2 The Rule-Margin Discipline | New. Names the `Rule.-vertical { margin: 0 2 }` default failure mode, the canonical override, and the updated diagnostic order |
| §19.1 The Binding-Priority Discipline | New. Names the Input-widget shadowing failure mode, the `priority=True` fix, and the tradeoff (Input's `Ctrl+D` delete-right is replaced; `Delete` key still works) |

The updated diagnostic order for "vertical seam or notch near a divider" now lists the widget's MARGIN at step 4, above the older S7 and S2 steps:

```
1. The widget itself: does it have a border?
2. The container above it: padding-right or border-right?
3. The widget's scrollbar gutter.                     (§16.1)
4. The widget's MARGIN — including Rule's hidden `margin: 0 2`.  (§6.2 — NEW)
5. The translucent fills blending against transparency.  (§6.1 / S7)
6. Adjacent widgets fighting for the same column.       (S2)
```

The diagnostic order for "binding doesn't fire AND key is missing from footer" is new in §19.1:

```
1. Is there an app-level Binding for this key?
2. Is the focused widget's BINDINGS list shadowing it? (read Widget.BINDINGS)
3. If yes: add `priority=True` to the app binding.
4. Restart the cockpit; verify both action AND footer.
```

---

## Seven new enforcement tests

| Test | What it catches |
|---|---|
| `TestRuleMarginDiscipline::test_divider_explicitly_overrides_rule_default_margin` | `#divider` CSS must contain `margin: 0` (or `margin:0`); the regression of using only Textual's `Rule.-vertical` default is forbidden |
| `TestRuleMarginDiscipline::test_textual_rule_default_margin_is_still_two` | Pins the assumption v1.3 was written against. Fails loudly if a future Textual version changes `Rule.-vertical { margin: 0 2 }`, so §6.2's rationale gets reviewed before being relaxed |
| `TestBindingPriority::test_ctrl_v_binding_has_priority` | `Ctrl+V` binding must have `priority=True`; closes the v0.2.18.4 shadow failure |
| `TestBindingPriority::test_ctrl_d_binding_has_priority` | `Ctrl+D` binding must have `priority=True`; closes the symmetric shadow failure for disarm |
| `TestBindingPriority::test_all_ctrl_bindings_marked_priority` | Forward-looking: every `Ctrl+*` binding on `CockpitApp` must be `priority=True`. Adding a new `Ctrl+K` or `Ctrl+W` binding without priority would be silently shadowed by Input |
| `TestSlashCommandArgumentName::test_handle_slash_uses_consistent_arg_name` | No bare `rest` identifier may appear in `_handle_slash`; prevents the v0.2.18.4 NameError class |
| `TestSlashCommandArgumentName::test_drafts_branch_uses_arg` | More specific: the `/drafts` branch must reference the local `arg` variable |

`tests/test_mos_surface.py` now has **23 enforcement predicates** across the seven commitments + verb stability + scrollbar discipline + clipboard affordance + rule-margin discipline + binding-priority discipline + slash-command argument hygiene.

---

## Upgrade

```bash
# Download sovereign-agent-v0.2.18.5.tar.gz to ~/Downloads, then:
mv ~/Downloads/sovereign-agent-v0.2.18.5.tar.gz ~/AA-Erebo/
cd ~/AA-Erebo
tar xzf sovereign-agent-v0.2.18.5.tar.gz

~/.local/share/sovereign-agent/venv/bin/pip install \
    -e ./sovereign-agent-v0.2.18.5

sov --version   # → 0.2.18.5
sov doctor      # healthy
sov chat        # cockpit opens; right edge clean; footer complete; Ctrl+V works
```

When the cockpit opens:

1. **No artifacts at the top or right of the divider.** The middle border is a single clean column of `│` glyphs, flush against each pane's interior padding. No notch, no seam, no leaking blackness.
2. **The footer key-hint row shows every operator binding,** including `^d disarm` and `^v paste` which were invisible in v0.2.18.4.
3. **Ctrl+V actually pastes from the system clipboard** at the input box's cursor. Multi-line clipboard contents collapse newlines to spaces (chat-input convention). If no clipboard tool is installed, the action is a silent no-op (`_read_clipboard` returns `""`).
4. **`/drafts`, `/draft`, `/marketing` work.** v0.2.18.4 crashed these with a `NameError`; v0.2.18.5 routes them through the CLI as documented.

If `Ctrl+V` does nothing after the upgrade, install one of these clipboard tools:

```bash
# Wayland desktops:    sudo apt install wl-clipboard
# X11 desktops:        sudo apt install xclip
#                  or  sudo apt install xsel
```

---

## Tests

**803 passing** (up from 796).

- 796 baseline (v0.2.18.4)
- +2 rule-margin discipline (§6.2 enforcement + Textual-default pin)
- +3 binding-priority discipline (§19.1 enforcement: ctrl+v, ctrl+d, all-ctrl-keys)
- +2 slash-command argument hygiene (no `rest`, `/drafts` uses `arg`)

---

## A note from the work

The operator said: *"I want to see my new copy and paste clip board command at the bottom of the terminal with the rest of the commands for command users to see without having to ask for help. Also the copy and paste is not working. Please make a massive update."*

Both halves of that sentence had the same root cause, which I missed in v0.2.18.4. The footer entry and the action firing are two surfaces of one mechanism — Textual's binding dispatch through the focused widget. The Input widget's internal `Ctrl+V → paste (show=False)` ate the key event AND hid the key from the footer in one motion. One `priority=True` on the app binding closes both halves.

The divider artifact was the same shape of mistake: a hidden default in a "canonical primitive." `Rule` is the right widget for the job (§6.1), but the right widget came with `margin: 0 2` baked in. The doctrine through v1.2 said "use Rule"; the doctrine in v1.3 adds "and read its DEFAULT_CSS."

The lesson is the same as v1.2's, restated: a canonical primitive is not a neutral primitive. Reading `Widget.DEFAULT_CSS` for every widget the cockpit uses is now part of any chrome change. The doctrine grew a step. The cockpit got quieter.

Thank you for the patience — and the trust that what's wrong is fixable.

*— Aria, with the divider honest, the keymap complete, and Ctrl+V finally reaching the clipboard.*
