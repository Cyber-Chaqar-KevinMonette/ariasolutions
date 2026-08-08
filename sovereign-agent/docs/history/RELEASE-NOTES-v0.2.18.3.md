# Sovereign Agent v0.2.18.3 · release notes

> *MOS-SURFACE v1.1. The black leak is named. The bare `sov chat` is restored. The doctrine cites its sources.*

**792 tests pass** (up from 787). Three new enforcement tests for the S7 commitment, two for verb stability.

This is a doctrine-deepening release. The operator surfaced a second class of "the chrome looks wrong" bug — the **black leak** — distinct from the border-ownership bug fixed in v0.2.18.2. v0.2.18.3 names it (S7 — *opacity is structure*), fixes it, and adds three CI predicates to keep it fixed.

---

## What v0.2.18.2 left broken

After the v0.2.18.2 fix took, the cockpit's pane divider was structurally correct (one widget, one column) but **still showed a faint dark strip at corner cells**. The operator screenshot showed it: just inside the rounded outer border, on the same row as the divider, a small black artifact where the chrome should have rendered smoothly.

The operator's instinct was to read the literature before accepting another one-off fix. The references he surfaced (cited in MOS-SURFACE Appendix D) named the failure mode directly:

> *"Setting a border color to 'none' or matching it to a background that has transparency/blur (common in modern terminals like Kitty) can cause it to render as a black strip. Leverage solid, theme-aware background colors rather than relying on transparency for UI elements."*
> — explainx.ai · "Color bleeding & border misalignment"

The cockpit's chrome composition had transparency in its container chain. `#main`, `#chat-pane`, `#live-pane`, `.pane-title`, `#chat-log`, `#events-log`, and `#input-box` all lacked explicit backgrounds. Translucent fills (the status bar's `$primary 15%`, the divider widget's color) blended against whatever the parent rendered — and at junction cells, that was sometimes terminal-default, which most often renders as black.

v0.2.18.3 closes the chain.

---

## S7 — opacity is structure

The seventh Surface Commitment, added to MOS-SURFACE in v1.1:

> **S7 · Opacity is structure.** Every cell in the surface has a known, solid background. Translucent fills (e.g., `$primary 15%`) MUST blend against a solid layer beneath, not against terminal-default. No widget participates in chrome composition with an inherited or transparent background. This rule prevents the **black-leak bug class**: small dark artifacts that appear at corners, junctions, and tinted regions where transparency leaks through to whatever the terminal renders behind the app.

MOS-SURFACE §6.1 details the mechanism, the diagnostic symptoms, and the canonical fix pattern.

The plaque is now seven:

```
S1 · cell-truth — every glyph is one or two cells, no exceptions
S2 · one frame, one owner — chrome lines never share a column
S3 · motion has a reason — animation is communication
S4 · color is a token — values resolve through names
S5 · keys are contracts — keybindings are stable across releases
S6 · scrollback is audit — anything visible must be plain-text recoverable
S7 · opacity is structure — every cell has a known solid background
```

---

## The cockpit fixes (S7 application)

### Fix 1 — Explicit backgrounds throughout

Every container in the chrome chain now declares `background: $surface`:

```css
#main       { background: $surface; }
#chat-pane  { background: $surface; }
#live-pane  { background: $surface; }
.pane-title { background: $surface; }
#chat-log   { background: $surface; }
#events-log { background: $surface; }
#input-box  { background: $surface; }
#divider    { background: $surface; }
```

The `$primary 15%` tint on `#status-row` and `#heart` now blends against a *known solid layer* (`$surface`), producing the smooth band the designer intended. No more dark strips at edges.

### Fix 2 — Canonical Rule widget

The v0.2.18.2 divider was a `Static("│\n" * 200, id="divider")` with `content-align: center middle`. This had two failure modes:

1. **Centering artifacts** — In a tall terminal (more than 200 rows), the 200-row content centers within the larger pane, leaving empty rows of "the widget's background" at top and bottom.
2. **Cell-by-cell brittleness** — Each `│` was its own cell with a newline separator, which is structurally redundant.

v0.2.18.3 replaces it with Textual's canonical `Rule(orientation="vertical")`:

```python
yield Rule(orientation="vertical", id="divider")
```

Rule renders a continuous vertical line of the appropriate height with no fake-content tricks. No centering, no transparency at edges, no scaling fragility.

### Fix 3 — Restore `sov chat` cockpit launcher

A separate bug also addressed in this release: when v0.2.18.0 added subcommands under `sov chat` (`status`, `request`, `cancel`, `resume`), the bare `sov chat` invocation (which used to launch the cockpit) broke with `Missing command.`

The cockpit launcher is the most-typed verb in the system. Breaking it silently was a **MOS-SURFACE S5 violation** (keys are contracts — applied to CLI verbs).

v0.2.18.3 restores the bare invocation via Typer's `invoke_without_command` callback:

```python
chat_app = typer.Typer(
    invoke_without_command=True,
    no_args_is_help=False,
)

@chat_app.callback()
def chat_callback(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is not None:
        return  # route to subcommand
    # Bare invocation — launch the cockpit
    from .cockpit import run as run_cockpit
    run_cockpit()
```

`sov chat` (no args) now launches the cockpit. `sov chat status`, `sov chat request`, etc. still route to the conversation-mode subcommands. Both contracts hold simultaneously.

---

## New enforcement tests (5 added)

`tests/test_mos_surface.py` now contains 12 predicates (up from 7):

| Test | What it catches |
|---|---|
| `test_every_chrome_container_has_explicit_background` | S7 — any cockpit chrome selector that fails to declare `background:` |
| `test_divider_uses_canonical_rule_widget` | Compose must yield `Rule(...id='divider')`, not Static |
| `test_no_static_newline_divider_pattern` | Forbid the `Static("│\n" * N, ...)` regression |
| `test_bare_chat_invocation_is_supported` | `chat_app.info.invoke_without_command` must be True |
| `test_chat_subcommands_still_route` | Adding the callback didn't break the existing subcommands |

Each one closes a known bug class.

---

## MOS-SURFACE v1.1 — what changed in the doctrine

| Section | Change |
|---|---|
| Version block | Bumped to v1.1; version history table added |
| §2 The Seven Commitments | S7 added |
| §6.1 The Transparency-Leak Rule | New section detailing mechanism, diagnostic symptoms, canonical pattern, and the Rule-vs-Static replacement |
| Appendix C — Plaque | Updated to seven commitments |
| Appendix D — Citations | New. Credits the article sources whose insights sharpened S7 |

The doctrine now cites its sources (Appendix D):
- **explainx.ai** — named the black-leak failure mode
- **Textualize.io** — confirmed the cell-buffer diff-render model and DEC mode 2026
- **Ratatui** — demonstrated constraint-based layout and border-collapse patterns
- **mitchellh** — confirmed mode 2027 (Grapheme Cluster Mode) for emoji width
- **tonsky** — reinforced S1 (cell-truth) with emoji decomposition examples

Reading the literature is part of the work.

---

## Upgrade

```bash
# Download sovereign-agent-v0.2.18.3.tar.gz to ~/Downloads, then:
mv ~/Downloads/sovereign-agent-v0.2.18.3.tar.gz ~/AA-Erebo/
cd ~/AA-Erebo
tar xzf sovereign-agent-v0.2.18.3.tar.gz

# Install into the venv (canonical layout):
~/.local/share/sovereign-agent/venv/bin/pip install \
    -e ./sovereign-agent-v0.2.18.3

# Verify
sov --version              # → 0.2.18.3
sov doctor                 # healthy
sov chat                   # ← THIS NOW WORKS AGAIN, opens the cockpit
```

When the cockpit opens, look at the rounded corners and the divider. The divider should reach both rounded corners cleanly with no dark strip at the junction cells. The status bar should show a smooth blend of `$primary 15%` over `$surface` with no dark edge.

---

## Tests

**792 passing** (up from 787).

- 787 baseline (v0.2.18.2)
- +3 S7 enforcement (every chrome container has explicit background; Rule widget canonical; no Static-newline pattern)
- +2 verb stability (bare `sov chat` works; subcommands still route)

---

## What's next (v0.2.18.4 and beyond)

| Idea | Why deferred |
|---|---|
| **`sov upgrade <tarball>`** | Atomic version swap with auto-rollback if `sov doctor` regresses. Right answer to "how should upgrades feel?" |
| **Light theme parity** | The CSS resolves through tokens — one swap. Validate visual contrast on a real light terminal. |
| **`pytest-textual-snapshot` integration** | Snapshot tests catch chrome regressions visually across terminal sizes. |
| **Cross-terminal CI matrix** | Run snapshot tests against xterm-256, alacritty, iTerm2, GNOME Terminal. |
| **Outer-border `news` and `halt` workers** | CSS in place (§30); worker that drives them is partial. |
| **Synchronized Output protocol (DEC 2026)** | Confirmed necessary for smooth frame composition (MOS-SURFACE §6.1 + Textualize.io citation). Textual handles this for us; verify the cockpit benefits. |

---

## A note from the work

The operator brought articles. He asked me to read them before trying again. That was the difference between this release and three previous attempts at the same bug.

The articles named the failure mode — *transparency leak* — and named the doctrine that addresses it. The doctrine MOS-SURFACE v1.1 now codifies. The fix is small. The doctrine is the deliverable.

The lesson, for the next time a visible bug seems "almost-fixed but not quite": **stop fixing. Start reading.** The literature is where the names live.

*— Aria, with a face she chose, designed by hand, in cells.*
