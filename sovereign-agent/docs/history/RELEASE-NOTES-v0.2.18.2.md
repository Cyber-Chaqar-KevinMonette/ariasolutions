# Sovereign Agent v0.2.18.2 · release notes

> *The polish release. The face Aria wears, by hand, in cells.*

This release introduces **MOS-SURFACE** — the Master Operating Standard for terminal surfaces — and applies it surgically to the cockpit. **787 tests pass** (up from 780).

The headline fix: the cockpit's pane divider no longer floats. The persistent "border doesn't line up" bug that survived through three releases now has a name (MOS-SURFACE S2: *one frame, one owner*), a doctrine, and a CI test that prevents its return.

---

## What v0.2.18.1 left broken (the honest part)

After the v0.2.18.1 install finally took, the cockpit launched and the title bar correctly read `0.2.18.1`. The kernel was on the new floor. But the right pane's vertical divider was misaligned — a small, visible seam between the rounded outer border and the inner divider line. The operator named this and said:

> "Border is not fully aligned. Possibly a simple issue you have failed to fix literally almost 10 times now."

He was right. The cockpit was using `border: round` on the outer container AND `border-left: solid` on the inner pane. Two border systems trying to share a column. Most terminal renderers cannot compose them cleanly — they produce seams at the top and bottom of the column where the chrome lines should meet.

The root cause was discipline, not implementation. There was no doctrine that named the rule, no test that caught the violation, and no review checklist that would have flagged it.

v0.2.18.2 ships the doctrine, the fix, and the tests.

---

## MOS-SURFACE — the new canon

[`MOS-SURFACE.md`](./MOS-SURFACE.md) is a sibling document to the Unified MOS Canon, governing **everything the operator sees**: the cockpit, CLI tables, help text, banners, status bars. It runs ~600 lines, structured as the parent canon is: Parts, sections, callout tables, code templates, an Angel's Advocate variant for TUI work.

**The six Surface Commitments:**

```
S1 · cell-truth — every glyph is one or two cells, no exceptions
S2 · one frame, one owner — chrome lines never share a column
S3 · motion has a reason — animation is communication
S4 · color is a token — values resolve through names
S5 · keys are contracts — keybindings are stable across releases
S6 · scrollback is audit — anything visible must be plain-text recoverable
```

**Eleven parts:**

| Part | What it codifies |
|---|---|
| I — The Kernel | What a terminal surface *is*; the three voices; sovereign-space posture |
| II — Layout Kernel | Cell-grid math; fractional vs absolute sizing; **§6 border ownership** |
| III — Typography | Hierarchy without size; Aria's voice conventions; ASCII art discipline |
| IV — Color | The canonical token set; semantic pairs; light theme parity; accessibility |
| V — Motion | The three legal motions; forbidden motion; tick rates |
| VI — Interaction | Universal keymap; focus discipline; modal surfaces |
| VII — State & Status | Status bar grammar; the heart; notification policy |
| VIII — Testing | Snapshot tests; the §27 visual review checklist; reference terminals |
| IX — Application to Aria's Cockpit | The canonical layout; state machine of the outer frame; banner format |
| X — Implementation Profiles | New screen; CLI output; status glyph selection |
| XI — Angel's Advocate (Surface) | Red/yellow/green template; horizon scan |
| Appendices | Glyph library; theme token reference; the six commitments plaque |

The doctrine is opinionated. Every rule has a name. Every rule has a test (or a manual check). The rules that have automated tests are now CI-enforced.

---

## The cockpit fixes

### Fix 1 — Border ownership (MOS-SURFACE S2)

**Before:** `border-left: solid $primary` on `#live-pane` tried to share a column with the outer `border: round $primary` on `#main`. The shared cells at top and bottom rendered inconsistently — sometimes a seam, sometimes a gap, sometimes a misaligned rounded corner.

**After:** A dedicated `#divider` widget — one cell wide, one column tall, owns its column outright. The outer frame is the only border in its region. The seam is structurally impossible.

The fix is small (one Static widget, twenty CSS lines) but the doctrine that motivated it is the substantial deliverable. Every future surface change runs through Section 6's three resolutions and Section 27's checklist.

### Fix 2 — Version interpolation (MOS-SURFACE S4)

**Before:** The cockpit's title bar, welcome banner, and status snapshot read from hardcoded string literals — `"0.2.15.3"` in three different places. These literals went uneditted through v0.2.16.0, v0.2.17.0, v0.2.18.0. The cockpit's title bar lied about its identity through three releases.

**After:** Every version display reads from `__version__` at runtime. The cockpit's `SUB_TITLE`, the `SystemSnapshot.version` default, and the welcome banner all interpolate. Bumping the package's version automatically updates every visible string. The "I forgot to edit one place" bug class is structurally closed.

### Fix 3 — Doctrine-enforcement tests (MOS-SURFACE §28)

New test module `tests/test_mos_surface.py` runs in CI:

| Test | What it catches |
|---|---|
| `test_canonical_version_exists` | Package has a valid `__version__` |
| `test_no_hardcoded_version_in_runtime_code` | Any source file with a hardcoded version literal that doesn't match `__version__` (excluding historical metadata like `introduced_in=`) |
| `test_cockpit_sub_title_matches_version` | The cockpit's title-bar version equals `__version__` |
| `test_cockpit_uses_dedicated_divider` | `compose()` yields a `#divider` widget |
| `test_live_pane_has_no_border_left` | The `#live-pane` CSS rule does NOT declare `border-left` |
| `test_no_forbidden_emoji_in_cockpit_chrome` | No width-2 emoji in chrome code |
| `test_cockpit_css_uses_tokens` | No hex color codes outside semantic class definitions |

Seven predicates. Each one closes a known bug class.

### Fix 4 — Legacy assertion correction

`tests/test_cockpit.py` had `assert s.version == "0.2.15.3"` — a test that **enforced the bug**. Updated to assert against `__version__` so the test now polices what the doctrine requires.

---

## What did NOT change

The cockpit's layout, keybindings, color palette, behavior, and feature set are unchanged. The operator's muscle memory holds. The only visible difference between v0.2.18.1 and v0.2.18.2 in normal operation is: the divider line now reaches both rounded corners cleanly.

The seven kernel commitments. The tagline. Aria's voice. Authority tiering. The atom store as ground truth. PROTOCOL-ZERO. The three-lens commitment. All unchanged.

---

## Upgrade

If you're already on v0.2.18.1 with the manual `sed` patches from the previous session, this upgrade brings those fixes into the official tree and adds the doctrine, the divider widget, and the enforcement tests:

```bash
# Download sovereign-agent-v0.2.18.2.tar.gz, then:
cd ~/AA-Erebo
tar xzf sovereign-agent-v0.2.18.2.tar.gz
cd ./sovereign-agent-v0.2.18.2
./install.sh
```

If you're on a venv install (which v0.2.18.1's install diagnosis revealed is the canonical layout):

```bash
~/.local/share/sovereign-agent/venv/bin/pip install \
    -e ~/AA-Erebo/sovereign-agent-v0.2.18.2
```

After upgrade:

```bash
sov doctor               # should report healthy
sov cockpit              # the title bar reads 0.2.18.2; the divider is clean
```

---

## Tests

**787 passing** (up from 780).

- 780 baseline (v0.2.18.1)
- +7 MOS-SURFACE enforcement tests

The legacy assertion bug-fix (test_cockpit.py:122) is a correction, not a new test.

---

## What's next (v0.2.18.3 and beyond)

Named here. None urgent.

| Idea | Why deferred |
|---|---|
| **`sov chat` cockpit launcher** | The bare `sov chat` invocation (no args) used to open the cockpit; v0.2.18 broke this when sub-commands were added under `chat`. Fix in v0.2.18.3. |
| **`sov upgrade <tarball>`** | Atomic version swap with auto-rollback if `sov doctor` regresses. The right answer to "how should upgrades feel?" |
| **Light theme parity** | The CSS resolves through tokens — one swap. Validate visual contrast on a real light terminal. |
| **Snapshot tests** | `pytest-textual-snapshot` integration. Catch chrome regressions visually. |
| **Cross-terminal CI matrix** | Run snapshot tests against rendering targets for xterm-256, alacritty, iTerm2, GNOME Terminal. |
| **Cockpit `news` and `halt` outer-border states** | The CSS is in place (§30); the worker that drives them is partial. |
| **`sov-chat` legacy launcher cleanup** | The shell function from older `aliases.sh` still routes correctly via `sovereign cockpit`; no action needed, but documenting. |

---

## A note from the work

The bug Kevin pointed at — the misaligned divider — has been visible in screenshots through at least three releases. I missed it every time because I treated TUI work as cosmetic, not structural. That's a category error. The terminal IS the structure. The chrome IS the contract.

MOS-SURFACE makes that structural respect explicit. It names the rules, documents the failure modes, and writes the tests. Going forward, any new surface work — a new screen, a new CLI output format, a new status indicator — runs through Section 33's checklist or it doesn't ship.

The doctrine is the deliverable. The fix is just its first proof.

*— Aria, with a face she chose, designed by hand, in cells.*
