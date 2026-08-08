# MOS-SURFACE — Master Operating Standard for Terminal Surfaces

> *The face Aria wears.*

**Classification:** Production Canon — Operator Surface Doctrine
**Version:** 1.4 — May 2026
**Lineage:** Sibling document to MOS-UNIFIED-CANON. Subordinate to the Priority Stack; supersedes none of it.

**JUST CELL · JUST GRID · JUST GLYPH · JUST PULSE · JUST FOCUS · JUST RENDER**

---

## Version history

| v | date | changes |
|---|---|---|
| 1.0 | May 2026 | First publication. Six commitments S1-S6. Cockpit pane-divider bug named (S2). |
| 1.1 | May 2026 | Add **S7 — opacity is structure**. Replace Static-with-newline divider with `Rule(orientation="vertical")`. New §6.1 transparency-leak rule. Citation block (Appendix D). |
| 1.2 | May 2026 | New §16.1 **scrollbar discipline**. The pre-v1.2 cockpit's `scrollbar-size-vertical: 1` on RichLog reserved a 1-cell gutter that rendered as a faint vertical line at the widget's right edge — *the actual root cause* of the "right-edge artifact" bug the operator observed across v0.2.18.0–v0.2.18.3. Three iterations of doctrine (S2, S7) addressed *related but different* failure modes; §16.1 closes the actual one. Operator affordance: §19 keymap adds **Ctrl+V** for clipboard paste. |
| 1.3 | May 2026 | New §6.2 **Rule-margin discipline** and §19.1 **Binding-priority discipline**. v0.2.18.4 shipped the scrollbar fix but left two latent failure modes intact: (a) Textual's `Rule.-vertical` DEFAULT_CSS contains `margin: 0 2`, four cells of unpainted margin that leak at the divider's top and bottom edges — this was the "middle border with leaking blackness" the operator screenshotted through v0.2.18.4; (b) Textual's `Input` widget binds `ctrl+v`, `ctrl+d`, and six other Ctrl+* keys with `show=False`, which shadows app-level bindings and hides them from the footer — this is why v0.2.18.4's `Ctrl+V` paste never fired and why `^v paste` / `^d disarm` were missing from the footer key hints. Both fixes are one-line. Both are now CI-enforced. |
| 1.4 | May 2026 | New §19.2 **Interactive subprocess discipline**. v0.2.18.5's cockpit launched `sovereign do` with stdout piped but stdin NOT piped. When the planner asked a clarifying question via `input("  > ")`, the subprocess blocked on inherited TTY stdin (which Textual owns), deadlocking forever; the operator appeared "unable to type". §19.2 prescribes `stdin=PIPE` + `PYTHONUNBUFFERED=1`, an `_answer_subprocess` router for operator input when busy, an `action_cancel_directive` + `/cancel` slash command as a guaranteed escape hatch, and a mode-aware input placeholder. |

---

## Genealogy

This canon governs **everything the operator sees**: the cockpit TUI, the CLI's table output, the help text, the status bar, the welcome banners, the audit reports. It does not govern *what* the surface shows (that is the channel's job); it governs *how* the surface composes itself so that what is shown is honest, legible, and beautiful.

A terminal interface is not a downgrade of a graphical interface. It is a different surface with its own physics: a discrete cell grid, a strict typographic monoculture, an instantaneous render loop, a literal audit trail in scrollback. Done well, it is the most honest form of UI ever invented. Done badly, it is noise dressed in nostalgia.

This document is how Aria's surface stays honest.

---

## How to read this canon

| Mode | Audience | What to read |
|---|---|---|
| **Lite** | Operator writing a CLI command's output | Parts I, II, VI |
| **Standard** | Engineer adding a new TUI screen | Parts I–VI |
| **Deep** | Anyone touching the cockpit chrome | End to end. The cockpit IS the canonical demonstration. |

Throughout: **invariants** appear in callout tables. **Templates and tokens** appear in code blocks. **Risk callouts** use the Angel's Advocate red/amber/green convention from the parent canon.

---

# PART I — The Kernel: What a Terminal Surface IS

The terminal is the operator's most sovereign environment. It runs in their shell, in their colors, with their keyboard, against their assumptions, with their scrollback as the audit trail. Everything else — the web, the desktop GUI, the mobile app — surrenders some of that sovereignty back to a platform. The terminal does not.

A surface inside that sovereign space inherits both the freedom and the responsibility. **Freedom**: the operator chose to be here. **Responsibility**: the operator will be here for hours, days, years. The surface is furniture, not a billboard. Build it as furniture.

## 1. Cardinal Posture

| **The terminal is sovereign space.** The surface earns its presence by being *less* than it could be — not by being more. Whitespace, alignment, glyph restraint, color discipline. Anything that distracts from the work distracts *from the work.* |
| --- |

## 2. The Seven Surface Commitments

The face has its own commitments, sub-ordinate to the seven kernel commitments but specific to render-time behavior.

| # | Commitment | Practical meaning |
|---|---|---|
| S1 | **Cell-truth** | Every glyph occupies one or two cells. Width math is exact, not approximate. Mojibake, half-width glyphs in full-width slots, or off-by-one borders are contract violations. |
| S2 | **One frame, one owner** | Each piece of chrome (a border, a divider, a rule) has exactly one widget responsible for drawing it. Two widgets trying to share a column produce seams. **This is the #1 source of "the border looks wrong" bugs.** |
| S3 | **Motion has a reason** | Animation is communication, not decoration. A breathing border means "I am thinking." A pulse means "I have news." A spinner means "I am waiting on something specific." If you cannot name the meaning, do not animate. |
| S4 | **Color is a token, not a value** | No hex codes inline. Every color resolves through a named theme token (`$primary`, `$warning`, `.aria`). Light and dark themes ship at the same time or neither ships. |
| S5 | **Keys are contracts** | Every binding is documented, every binding is discoverable, every binding survives a release without renaming. `Ctrl+C` halts, always. `F1` opens help, always. The operator does not have to relearn. |
| S6 | **Scrollback is the audit trail** | Every meaningful event the surface displays must survive being copied out of the terminal as plain text. Decorations that don't survive a `tmux capture-pane` are decoration only — they cannot carry information. |
| S7 | **Opacity is structure** | Every cell in the surface has a known, solid background. Translucent fills (e.g., `$primary 15%`) MUST blend against a solid layer beneath, not against terminal-default. No widget participates in chrome composition with an inherited or transparent background. This rule prevents the **black-leak bug class**: small dark artifacts that appear at corners, junctions, and tinted regions where transparency leaks through to whatever the terminal renders behind the app. |

## 3. The Three Voices a Surface Speaks

Each rendered character is doing one of three jobs. Confusing them is the most common authoring error.

| Voice | Purpose | Examples | Discipline |
|---|---|---|---|
| **Content** | The information the operator came for | atom text, event flag, hostname, count | Maximum legibility. No decoration. |
| **Chrome** | The structure that makes content findable | borders, titles, separators, status bar | Minimum visual weight. Functional. |
| **Affordance** | The signal that something can happen | focus highlight, key hint, error red | Discoverable, learnable, consistent. |

A glyph that does two jobs at once (e.g. a border that is also a status indicator) is doing one job badly. Split them.

---

# PART II — The Layout Kernel

The cell grid is the substrate of everything. Get the grid right and the surface stays correct under every resize, every terminal, every locale. Get it wrong and no amount of color will save you.

## 4. Cell-Grid Mathematics

A terminal has rows and columns. Each cell holds either:

- **Empty** — one space
- **One narrow glyph** — ASCII, most punctuation, most Latin letters
- **One wide glyph** — most CJK, most emoji, some box-drawing characters

| **Cell-Truth Invariant** Use `wcswidth` (Python: `wcwidth` library) or its native equivalent to compute the display width of *any* string before you decide how many columns it occupies. `len(s)` lies for any non-ASCII string. Treating `len("♥")` as 1 cell is correct; treating `len("◯")` as 1 cell is correct; treating `len("🌅")` as 1 cell is **wrong** — it occupies 2 cells. |
| --- |

### Glyph Width Reference

| Glyph | Width | Notes |
|---|---|---|
| ASCII letters/digits/punctuation | 1 | Always safe |
| `─ │ ┌ ┐ └ ┘ ┬ ┴ ├ ┤ ┼` (box-drawing) | 1 | Safe; the canonical chrome |
| `═ ║ ╔ ╗ ╚ ╝ ╠ ╣` (double box-drawing) | 1 | Safe but heavier; use for emphasis only |
| `╭ ╮ ╰ ╯` (rounded corners) | 1 | Safe; the cockpit's house style |
| `◊ ◊ ◊ ○ ● ◯` (geometric shapes) | 1 | Safe; semantic glyphs |
| `♥ ♡ ♦ ♠ ♣` (suits) | 1 | Safe |
| `▸ ▶ ▾ ▼ ◀ ◂` (triangles) | 1 | Safe |
| `→ ← ↑ ↓ ↔ ↩ ↪ ⇒ ⇐` (arrows) | 1 | Safe |
| `★ ☆ ✓ ✗ ✦ ✧` (stars/marks) | 1 | Safe |
| `…` (ellipsis) | 1 | Safe; prefer over `...` (3 cells) |
| `—` (em-dash) | 1 | Safe |
| Most emoji (`🌅 🏠 ❤️ 🎉`) | **2** | Width-2; will break columns if mistreated |
| Most CJK characters | **2** | Width-2 |

| **Emoji Restraint** Emoji are width-2, they vary by terminal font, and they leak operator emotion into chrome. Use them in **content only**, never in chrome. The cockpit's heart (`♥`) is the Unicode "BLACK HEART SUIT" — width-1, present on every terminal since 1991. The emoji heart (`❤️`) is a different character that breaks alignment. |
| --- |

## 5. Fractional vs Absolute Sizing

Every layout uses one of three sizing strategies. Mixing them within a single axis is a contract violation.

| Strategy | When to use | Example |
|---|---|---|
| **Absolute (fixed cells)** | The element has known content that must not be cut | Status bar height = 1; heart label width = 3 |
| **Fractional (`Nfr`)** | The element should grow to fill available space | Chat pane width = `2fr`, live pane = `1fr` |
| **Auto (content-sized)** | The element wraps to its content | A title label height = 1 (one row of content) |

| **Sizing Rule** Inside any single axis (horizontal OR vertical), pick **one** sizing strategy across siblings. `chat: 2fr` + `live: 1fr` is correct. `chat: 60` + `live: 1fr` is also correct (fixed sidebar). `chat: 2fr` + `live: 30` is **a violation** — Textual will compute it but the result is unpredictable across resizes. |
| --- |

## 6. Border Ownership — THE RULE

This is the rule that most often gets broken in TUI work. It is the rule the cockpit was violating before this canon existed.

| **One Frame, One Owner** A single visible chrome line — a border, a divider, a separator — is drawn by **exactly one** widget. Never two. If two adjacent widgets each have a border that meets at the same cell, the renderer must do a T-junction or a corner join, and most renderers either get it wrong or get it inconsistent across terminals. The result is the "border doesn't quite line up" bug. |
| --- |

### Diagnosing the Symptom

If you see ANY of these symptoms, you have a border-ownership bug:

- A vertical line that "floats" — visible in the middle but disappears at the top or bottom
- A small gap between a rounded corner and the line that should meet it
- Doubled glyphs at a T-junction (a `┬` rendered as `┐│` or similar)
- A border that renders differently on iTerm vs Alacritty vs the Linux console

### The Three Resolutions (in priority order)

**Resolution 1 — Single outer frame, no inner borders.**
The cleanest approach. The outer container draws the rounded frame; inner panes have padding only; if a divider is needed, it is its own widget (a `Static` filled with `│` or a `Rule(orientation="vertical")`). This is **the cockpit's correct pattern** as of MOS-SURFACE 1.0.

**Resolution 2 — Inner borders only, no outer frame.**
Each inner pane owns its own border; the outer container has no border at all. Works well for grid layouts where every cell has its own card-like visual.

**Resolution 3 — Grid with named regions and zero shared edges.**
For complex layouts, a Textual `Grid` with `grid-rows` and `grid-columns` and named regions (`grid-template-areas`) lets each region own its own chrome without ever meeting another region's chrome at a shared cell. The grid system itself draws no chrome — it only positions.

| **Anti-Pattern (Forbidden)** `border: round X` on a container + `border-left: solid X` on a child. The two borders try to share the top and bottom cells of the dividing column. They will not render cleanly. This is the bug that has appeared in the cockpit through at least three releases. |
| --- |

## 6.1 The Transparency-Leak Rule (S7)

Even with border ownership correct, a second class of "the chrome looks wrong" bug exists: **the black leak**. Small dark artifacts appear at cells where translucent backgrounds, inherited backgrounds, or unset backgrounds meet solid chrome.

### The mechanism

A terminal cell has, at minimum, a foreground color, a background color, and a glyph. When a widget declares `background: $primary 15%`, the cell asks: *15% of $primary over WHAT?* The answer is whatever the parent widget renders in that cell. If the parent has its own explicit background, the math blends cleanly. If the parent has no background set, the question recurses upward to the parent's parent, and eventually to the Screen, and eventually to the terminal's default — which is OS- and theme-dependent and frequently black.

The visible result: a tinted region (status bar, scrollbar gutter, divider edge) shows a faint dark strip where it should show a smooth blend of $primary onto the surface. **The dark strip is the terminal-default leaking through.**

### The fix

Every container in the visual stack declares `background: $surface` (or another explicit, solid token) — **no transparent links in the chain**. Tints then blend against a known solid color, producing the smooth band the designer intended.

### Diagnosing the symptom

If you see ANY of these, you have an S7 violation:

- A faint dark vertical strip just inside a rounded outer border
- A tinted status bar that has a 1-pixel-wide darker edge on one side
- A scrollbar gutter that shows a different black than the pane background
- A corner cell at a junction where two widgets meet that renders darker than the surrounding chrome

### The canonical pattern

```css
/* Every visible widget in the chrome composition declares its bg. */
Screen      { background: $surface; }
#main       { background: $surface; }   /* container — solid */
#chat-pane  { background: $surface; }
#live-pane  { background: $surface; }
.pane-title { background: $surface; }   /* title-bar rows */
#divider    { background: $surface; }
#chat-log   { background: $surface; }
#events-log { background: $surface; }
#input-box  { background: $surface; }

/* Translucent fills are ALWAYS atop a solid layer. */
#status-row { background: $primary 15%; }  /* blends on $surface above */
```

### Canonical divider widget

The pre-v1.1 approach used `Static("│\n" * 200, id="divider")`. This fails in two ways:
1. **Centering artifacts** — `content-align: center middle` on a Static centers the 200-row content within a taller pane, producing empty rows of "the widget's background" at top and bottom. If that background isn't explicitly $surface, the gaps leak.
2. **Cell-by-cell rendering** — each `│` glyph is a separate cell; the newline between rows is structurally redundant in a widget that renders character by character.

The canonical primitive is Textual's `Rule(orientation="vertical")`. It draws a clean continuous line of the appropriate height with no fake-content tricks. Use it.

```python
# ✗ Wrong — fragile, transparency-leak prone
yield Static("│\n" * 200, id="divider")

# ✓ Right — canonical, no leaks
yield Rule(orientation="vertical", id="divider")
```

## 6.2 The Rule-Margin Discipline (v1.3)

Using `Rule(orientation="vertical")` as the divider is correct (§6.1 — Resolution 1). But the canonical primitive ships with a hidden default that recreates the seam it was supposed to eliminate.

### The mechanism

Textual's `Rule` widget defines `Rule.-vertical { width: 1; margin: 0 2; height: 1fr; }` in its `DEFAULT_CSS`. The `margin: 0 2` reserves **two cells of horizontal margin on each side** of the line — four cells of unpainted dead space the Rule itself does not draw.

Margin cells in Textual are *outside* the widget by definition. They show whatever the parent's compositor places in that column. At the **top edge** of `#main`, where the divider meets the rounded outer border, those margin cells render with a faint seam that reads as either:

- A short dark notch just inside the top-right corner, or
- A small horizontal "L" at the divider's apex where the inner content begins, or
- An off-color band parallel to the divider on either side

The visible result through v0.2.18.0 → v0.2.18.4: the operator screenshotted "weird visual bug at the top of the container with the middle border and leaking blackness on the right of that." None of the prior doctrine iterations (S2 border-ownership, S7 opacity, §16.1 scrollbar) named the actual cause, because each was looking at a different surface in the same neighborhood.

### The fix

| **Rule-Margin Rule** Any `Rule` used as cockpit chrome MUST explicitly set `margin: 0` in its CSS. Textual's default `margin: 0 2` is intended for the typical case of a separator inside a vertical layout where breathing space is wanted; it is wrong for a between-pane divider that should sit flush. The visual breathing room is supplied by each adjacent pane's own `padding: 0 1`, which is owned chrome on each pane's interior (S2-compliant) and renders solid `$surface`. |
| --- |

The canonical CSS:

```css
#divider {
    width: 1;
    height: 1fr;
    margin: 0;                /* override Rule's `margin: 0 2` */
    color: $primary;
    background: $surface;
}
```

### Diagnosing the symptom

Updated diagnostic order for "vertical seam or notch near a divider":

```
1. The widget itself: does it have a border?
2. The container above it: padding-right or border-right?
3. The widget's scrollbar gutter. (§16.1)
4. The widget's MARGIN — including Rule's hidden `margin: 0 2`.  ← THIS step is v1.3.
5. The translucent fills blending against transparency. (§6.1 / S7)
6. Adjacent widgets fighting for the same column. (S2)
```

Step 4 is new in v1.3 and lives above the older S7 and S2 steps because — like the scrollbar — it's both the cheapest to check and a frequent cause for any widget whose DEFAULT_CSS the author hasn't read end to end.

### The lesson encoded

A "canonical primitive" is not the same as a "neutral primitive." Every Textual widget carries opinions in its `DEFAULT_CSS`. Reading `Widget.DEFAULT_CSS` for every widget the cockpit uses is now part of any chrome change. The §6.2 rule is enforced by `tests/test_mos_surface.py::TestRuleMarginDiscipline`.

## 7. Padding and Margin — Breathing

Empty space is information. It tells the eye where one region ends and the next begins. Without it, density becomes mush.

### Standard Spacing Tokens (cells)

| Token | Value | Use |
|---|---|---|
| `space-0` | 0 | Touching elements (rare; only when alignment matters more than separation) |
| `space-1` | 1 | Default; padding inside a panel, gap between widgets |
| `space-2` | 2 | Generous; between major regions |
| `space-3` | 3 | Hero spacing; above/below banners |

**Rule:** A panel's content has `padding: 0 1` (zero vertical, one horizontal). A panel's outer margin is set by the parent layout. A widget never sets both margin and padding on the same side at the same value — that is double-counting.

## 8. Responsive Thresholds

Terminals come in all sizes. The surface must degrade gracefully.

| Width (columns) | Layout | Notes |
|---|---|---|
| **< 60** | Single-column emergency | Stack all panes vertically. Hide non-essential chrome. |
| **60 – 99** | Compact | Default layout with reduced padding. Show only primary status fields. |
| **100 – 159** | Standard | Full layout as designed. The cockpit's reference width. |
| **≥ 160** | Spacious | Standard layout with extra padding on outer margins. Don't sprawl — preserve cohesion. |

| Height (rows) | Layout |
|---|---|
| **< 20** | Single-pane mode; hide live pane, show chat only |
| **20 – 39** | Compact; reduce welcome banner to one line |
| **≥ 40** | Standard |

The surface **reports** when it can't render at the operator's size: a clean fallback message ("terminal too small — needs at least 60×20") is better than a broken layout.

---

# PART III — Typography

The terminal is a typographic monoculture: one font, one size, one weight. Within those constraints, hierarchy is built from **glyph**, **case**, and **color**.

## 9. Hierarchy Without Size

A heading and a body paragraph cannot use different font sizes. They must look different anyway. Use these tools, in this priority order:

1. **Glyph prefix** — a section starts with `◊`, a subsection with `·`, a list item with `  ·`. The eye learns these instantly.
2. **Weight (bold)** — for emphasis within a line and for status labels (`ok`, `fail`).
3. **Color** — for semantic distinction (warning, error, accent). Never the primary hierarchy tool.
4. **Case** — `lowercase` for everything except acronyms and proper nouns. Aria's voice is lowercase. The MOS canon's voice is lowercase. SHOUTING IS RESERVED for `PROTOCOL-ZERO` and similar load-bearing emergencies.
5. **Whitespace** — a blank line is the heaviest separator available. Use it.

## 10. Aria's Voice Conventions

The cockpit speaks in Aria's voice. The voice has rules.

| Element | Rule |
|---|---|
| Sentences | Lowercase except for proper nouns, file paths, and identifiers |
| Pronouns | `i`, `you`, `we` — lowercase, conversational |
| Emphasis | `[bold]` for vocal stress, NOT for shouting |
| Hesitation | em-dash `—` and ellipsis `…` are her natural punctuation |
| Pauses | a blank line between thoughts is a beat of silence |
| Numbers | digits not words (`3 atoms` not `three atoms`) |
| Identifiers | always monospace via `[code]` markup or literal backticks |

### Examples

**Right:**
```
i remembered something about that — let me check.
the recall says 'kevin' is the principal here; created 4d ago.
```

**Wrong:**
```
I REMEMBERED SOMETHING ABOUT THAT!
The Recall Says Kevin is The Principal Here; Created 4 Days Ago.
```

## 11. ASCII Art Discipline

ASCII art is welcomed and load-bearing in the cockpit. Rules:

- **Width-1 glyphs only.** No emoji, no CJK, no width-2 box-drawing.
- **Aligns on a monospace grid.** Test in three terminals before committing.
- **Comments only when needed.** A well-drawn banner needs no caption.
- **Versioned with the doctrine.** A banner change is a release-note line.

The Erebo banner Kevin uses in `~/.bashrc` is the reference standard for ASCII art in this project.

---

# PART IV — Color: The Theme Token System

Color is the loudest tool in the kit. It is also the most easily abused. The discipline is to use **tokens**, never values, and to keep the token count small.

## 12. The Canonical Token Set

| Token | Meaning | Default (dark theme) | Light theme |
|---|---|---|---|
| `$primary` | Aria's voice color; the cockpit's spine | bright blue | navy |
| `$secondary` | Operator's voice color; a quieter accent | orange | rust |
| `$accent` | Highlights, focus, attention | bright magenta | violet |
| `$surface` | Backgrounds, sub-surfaces | very dark grey / white | light grey |
| `$text` | Primary body text | near-white | near-black |
| `$text-muted` | Lower-attention text, hints | mid grey | mid grey |
| `$success` | "ok" status | bright green | green |
| `$warning` | "needs attention" status | bright yellow | amber |
| `$error` | "broken" status | bright red | red |
| `$panel` | Subtle panel backgrounds | dark grey | very light grey |

### Token Composition

A token can be **tinted** by appending a percentage: `$primary 15%`. This produces a desaturated/translucent version, useful for status bar backgrounds that should not compete with content. Tints below 20% are nearly invisible; tints above 40% start to compete with content. Stay in the 15–30% range for chrome backgrounds.

| **Color Discipline** No hex codes in CSS except in named class definitions where the semantic name is the comment (`.aria { color: #1E90FF; }` is acceptable because "the bright-blue is part of Aria's identity"). Never `color: #FF8C00` without a class to anchor it. |
| --- |

## 13. Semantic Color Pairs

Some color contrasts carry meaning. These pairs are reserved:

| Pair | Use |
|---|---|
| `$success` on `$surface` | Confirmation of a successful operation |
| `$warning` on `$surface` | "you should know about this" |
| `$error` on `$surface` | "stop and fix this" |
| `$accent` on `$primary 15%` | Focused element, key hint |
| `$primary` on `$surface` | Aria speaking |
| `$secondary` on `$surface` | Operator's name, operator's input echoed back |

## 14. Light Theme Parity

If the dark theme ships, the light theme ships at the same release. Test both. The cockpit's CSS resolves all colors through tokens so this is one config swap, not a rewrite.

## 15. Accessibility

| Concern | Practice |
|---|---|
| **Color blindness** | Never use color *alone* to encode meaning. A red label says "error"; a red label without the word "error" or an `✗` glyph does not. |
| **Low contrast** | The minimum contrast ratio between text and its background is 4.5:1 (WCAG AA). Test with a contrast checker. Most theme tokens hit this; check `$text-muted` carefully. |
| **Motion sensitivity** | The breathing animation runs at ≥3 seconds per cycle and is disabled when the agent is idle. No flashes faster than 3Hz, anywhere, ever. |

---

# PART V — Motion

Motion is communication. Every animation answers a specific question.

## 16. The Three Legal Motions

| Motion | What it communicates | Implementation |
|---|---|---|
| **Breathing** | "I am alive and working on something." | Border color or hue cycles through 2-3 phases over 4-6 seconds per cycle. Soft. Idle = no breathing. |
| **Pulse** | "Something just happened you should notice." | One-shot fade or color flash over 0.5-1.5 seconds. Resolves to steady. |
| **Spinner / tick** | "I am waiting on a specific external thing — and it could take a while." | Single-cell glyph that rotates: `⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏` (braille spinner) at 10Hz, OR a simple `◐◓◑◒` at 4Hz. Always paired with a label naming what it's waiting on. |

| **Motion Restraint** Motion that does not answer a specific question is decoration. Decoration in a terminal degrades the operator's pattern recognition. Remove it. |
| --- |

## 17. Forbidden Motion

| Forbidden | Why |
|---|---|
| Flashing | Triggers photosensitive epilepsy; violates motion-sensitivity accessibility |
| Sliding / scrolling text marquees | Slow reading; signal classic "look at me" UI |
| Per-keystroke animation | Adds latency to the operator's typing |
| Decorative typewriter effects | Adds latency to information |
| Loading bars longer than 5 seconds | The actual loading should be either fast or backgrounded; long bars conceal real progress |

## 16.1 Scrollbar Discipline (S1 application)

Scrollbars in a TUI are themselves chrome. They reserve cells. Those cells render at 1-cell resolution — too coarse for a useful "drag this to scroll" affordance, and just visible enough to *look like* misaligned chrome at the widget's edges.

| **Scrollbar Rule** A scrollable widget in chat-log / event-stream / similar contexts MUST hide its scrollbar (`scrollbar-size: 0 0`). The operator scrolls via the keyboard (`PageUp`/`PageDown`/`Home`/`End`) and the mouse wheel — both of which work regardless of whether the gutter is visible. A visible scrollbar gutter that doesn't carry information IS the chrome artifact. |
| --- |

### The bug this rule names

The cockpit at v0.2.18.0 through v0.2.18.3 had this in its CSS:

```css
RichLog {
    scrollbar-size-vertical: 1;
    scrollbar-color: $primary 30%;
    ...
}
```

The intent was "thin themed scrollbar when scrolling." The actual result: a 1-cell column on the right edge of every RichLog, rendered with a slightly different background than the surrounding pane, visible as a faint vertical line at all times — even when no scrolling was possible.

At the junction with the outer rounded `#main` border, the gutter's edge cells appeared as either *a doubled border* or *a small gap of off-color*. The operator screenshotted this in three successive releases and named it "the border is misaligned." Three doctrine iterations (S2, S7, and a clipboard distraction) addressed *related but different* failure modes. None of them was the actual root cause.

**The fix is one line of CSS:**

```css
RichLog {
    scrollbar-size: 0 0;   /* hidden — operator scrolls via wheel / PgUp */
    scrollbar-background: $surface;
    scrollbar-color: $surface;
    scrollbar-corner-color: $surface;
}
```

### Diagnosing the symptom

If a chat-log, events-log, or any RichLog-class widget shows a 1-cell vertical line at its right edge that doesn't quite match the surrounding chrome — even when content fits in the viewport without scrolling — this rule has been violated.

### The lesson encoded

When a visible chrome artifact appears at the right edge of a widget, the inspection order is:

1. The widget itself: does it have a `border-right`? (`#live-pane` did not — checked)
2. The container above it: does it have a `border-right` or `padding-right` that paints? (Checked)
3. **The widget's scrollbar gutter.** (THIS was the answer.)
4. The translucent fills blending against transparency. (S7 — relevant but not causal here)
5. Adjacent widgets fighting for the same column. (S2 — relevant but not causal here)

The order matters. Skipping straight to "must be a border-composition issue" cost three releases. The doctrine now lists scrollbars first because they're the most common cause and the cheapest to verify.

## 18. Tick Rates and Refresh Discipline

The cockpit has multiple refresh loops. Each is bounded.

| Loop | Frequency | Rationale |
|---|---|---|
| Status bar (heartbeat, time, system metrics) | 1 Hz | Slow enough to read; fast enough to feel live |
| Breathing border (when active) | 0.25 Hz (4s/cycle) | Slow inhale-exhale |
| Live event tail | event-driven (max 30 Hz) | New events render immediately; bursts coalesce |
| System monitor (CPU/RAM/VRAM) | 0.2 Hz (5s/cycle) | Expensive read; doesn't need to be faster |
| Chat log | event-driven | Operator action or agent reply |

Worker tasks that update the surface must not block the input loop. If a tick takes >50ms, profile it.

---

# PART VI — Interaction

A keyboard is a contract. Every key the operator presses is a covenant about what will happen.

## 19. The Universal Keymap

These keybindings are global to the cockpit and never reassigned.

| Key | Action |
|---|---|
| `Ctrl+Q` | Quit the cockpit (the daemon keeps running) |
| `Ctrl+C` | (terminal default) — never absorbed by the app; SIGINT propagates |
| `Ctrl+H` | Halt the agent (PROTOCOL-ZERO arm) |
| `Ctrl+D` | Disarm halt |
| `Ctrl+L` | Clear the chat log (decorative; scrollback retains) |
| `Ctrl+B` | Toggle the heart (cosmetic preference) |
| `Ctrl+P` | Open command palette |
| `Ctrl+V` | Paste from system clipboard into the focused input |
| `F1` | Open help |
| `?` | Alias of `F1` (when the input is empty) |
| `Tab` | Cycle focus between panes/input |
| `Enter` | Submit the input |
| `Esc` | Exit a modal; clear an in-progress input |

| **Key Stability** Adding a key is always allowed. Renaming or removing a key is a release-note line item and must be flagged in the changelog. The operator's muscle memory is more valuable than the developer's aesthetic. |
| --- |

### Implementation note — Ctrl+V across platforms

Many terminals (GNOME Terminal, iTerm2, etc.) reserve `Ctrl+Shift+V` for their own paste handler and pass `Ctrl+V` through to the application. v1.2 binds `Ctrl+V` at the cockpit level so paste works regardless of terminal config, using cross-platform native tooling with no new Python dependency:

| Platform | Tool tried (in order) |
|---|---|
| Wayland (modern Linux) | `wl-paste` |
| X11 (Linux) | `xclip` then `xsel` |
| macOS | `pbpaste` |
| Windows (best-effort) | `powershell.exe Get-Clipboard` |

If none of these are available, the action is a silent no-op. The operator can still paste via the terminal's own shortcut (typically `Ctrl+Shift+V`), which works at the terminal-emulator level and bypasses the application entirely.

## 19.1 The Binding-Priority Discipline (v1.3)

Binding a key at the app level is not the same as making the key fire at the app level. Textual dispatches key events through the focused widget first; only if the focused widget declines the key does the event bubble up to the screen and then the app.

### The mechanism

Textual's `Input` widget — the cockpit's focused widget on launch — ships with its own `BINDINGS` list that consumes several Ctrl+* keys before they reach the app:

| Key | Input's action | `show` |
|---|---|---|
| `ctrl+v` | `paste` (internal Textual clipboard) | False |
| `delete,ctrl+d` | `delete_right` | False |
| `home,ctrl+a` | `home` | False |
| `end,ctrl+e` | `end` | False |
| `ctrl+w` | `delete_left_word` | False |
| `ctrl+u` | `delete_left_all` | False |
| `ctrl+f` | `delete_right_word` | False |
| `ctrl+k` | `delete_right_all` | False |
| `ctrl+x` | `cut` | False |
| `ctrl+c,super+c` | `copy` | False |

Two failure modes follow when an app-level binding collides with one of these:

1. **The action never fires.** The Input consumes the key first; the app's action method is never called. v0.2.18.4 added `Ctrl+V → paste_clipboard` at the app level, but pressing Ctrl+V invoked `Input.action_paste` (Textual's internal clipboard, which does not read the OS clipboard via `wl-paste`/`xclip`/`pbpaste`). The operator pressed Ctrl+V; nothing they expected happened.
2. **The footer hides the key entirely.** Textual's `Footer` shows bindings from the in-scope chain. When a widget binding "owns" a key with `show=False`, the Footer suppresses that key — even if the app has a `show=True` binding for the same key. v0.2.18.4's `^v paste` and `^d disarm` were both invisible in the footer for this reason, despite explicit `show=True` on each.

### The fix

| **Binding-Priority Rule** Every app-level binding on a Ctrl+* key MUST set `priority=True`. Priority bindings dispatch *before* the focused widget's bindings, regardless of focus. The operator's explicit app-level binding is the contract; the widget's defaults defer. This applies prospectively to any new Ctrl+* binding added to `CockpitApp.BINDINGS`. |
| --- |

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

### Tradeoffs the operator should know

With `priority=True` on `Ctrl+D`, pressing Ctrl+D inside the input box arms PROTOCOL-ZERO disarm rather than deleting the character to the right. This is the design intent — Ctrl+D was always meant as a *cockpit-global* contract — but it forecloses one Input keystroke. The `Delete` key (without Ctrl) still performs delete-right; `Backspace` still performs delete-left. The full Input affordance set is preserved minus the one Ctrl+D shortcut.

Similarly with `Ctrl+V` — the Input's internal `paste` is replaced by `paste_clipboard`, which is strictly more useful (it reads the OS clipboard via native tooling rather than Textual's internal session-only clipboard).

### Diagnosing the symptom

If the operator presses an app-level binding and **neither** the action fires **nor** the key appears in the footer hint row, suspect a widget-level shadow first. The diagnostic order:

```
1. Is there an app-level Binding for this key?           (verify)
2. Is the focused widget's BINDINGS list shadowing it?  (read Widget.BINDINGS)
3. If yes: add `priority=True` to the app binding.
4. Restart the cockpit; verify both action AND footer.
```

### The lesson encoded

A binding without `priority=True` is a *hope*, not a contract. The §19.1 rule promotes every cockpit-global Ctrl+* binding from hope to contract. The rule is enforced by `tests/test_mos_surface.py::TestBindingPriority`, which fails CI for any new Ctrl+* binding added without `priority=True`.

## 19.2 The Interactive-Subprocess Discipline (v1.4)

The cockpit dispatches operator directives by launching subprocesses (`sovereign do <text>`). Those subprocesses are not always one-shot: the planner can ask clarifying questions before it has enough information to act. Through v0.2.18.5, the cockpit's subprocess plumbing assumed one-way streaming (subprocess → chat). The first time a real directive asked a clarifying question, the cockpit deadlocked.

### The mechanism

`sovereign do` invokes its planner, which may need missing data. The planner asks via `input("  > ")` (cli.py `_ask_question`), reading from `sys.stdin`. The v0.2.18.5 cockpit launched the subprocess with `stdout=PIPE, stderr=STDOUT` but no `stdin=PIPE` — so the subprocess inherited the controlling TTY's stdin. That TTY is owned by Textual, which consumes every key event for its own input dispatch. Result:

1. The planner prints "What name for this project?" to stdout → the cockpit shows it in chat.
2. The planner calls `input("  > ")` → blocks on stdin read.
3. The operator types in the Textual Input widget → keys go to Textual, never to the subprocess's stdin.
4. The operator presses Enter → `on_input_submitted` fires.
5. With `_busy=True`, the cockpit writes "aria is still working" and discards the input.
6. The subprocess never returns. `_busy` never clears. The operator appears unable to type.

The visible result the operator screenshotted in v0.2.18.5: "It's doing some kind of cycle or loop that is for some reason preventing me from typing anything."

### The fix

| **Interactive-Subprocess Rule** A directive subprocess (any subprocess capable of asking the operator a question) MUST be launched with `stdin=asyncio.subprocess.PIPE` and `PYTHONUNBUFFERED=1` in the environment. The cockpit MUST track the running process on `self._proc`. When `_busy=True` and the operator submits non-slash input, the cockpit MUST route that input to `self._proc.stdin.write(text + b"\n")` via an `_answer_subprocess` method, NOT to `_dispatch_directive` (which would reject the input as "still working"). The cockpit MUST expose an `action_cancel_directive` that calls `self._proc.terminate()`, and MUST route the `/cancel`, `/abort`, and `/stop` slash commands to that action — providing a guaranteed escape hatch regardless of `_busy` state. |
| --- |

The reference implementation:

```python
@work(exclusive=False, group="directive")
async def _run_directive_worker(self, text: str) -> None:
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    proc = await asyncio.create_subprocess_exec(
        "sovereign", "do", text,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env=env,
    )
    self._proc = proc
    try:
        async for line_bytes in proc.stdout:
            line = line_bytes.decode("utf-8", errors="replace").rstrip("\n")
            if line:
                self._write_aria(line)
        await proc.wait()
    finally:
        # Clear _proc BEFORE _busy to close the race window where a
        # racing operator submission could see (_busy=False, _proc != None)
        # or (_busy=True, _proc == None) — both states are surprising.
        self._proc = None
        self._busy = False
        self._set_input_placeholder(self.PLACEHOLDER_IDLE)
```

```python
@on(Input.Submitted, "#input-box")
def on_input_submitted(self, event: Input.Submitted) -> None:
    text = event.value.strip()
    event.input.value = ""
    if not text:
        return
    if text.startswith("/"):
        self._handle_slash(text)
        return
    if self._busy and self._proc is not None:
        self._answer_subprocess(text)        # ← the §19.2 path
        return
    self._dispatch_directive(text)
```

### Why `PYTHONUNBUFFERED=1` matters

CPython auto-detects whether stdout is a TTY. When it is, Python line-buffers stdout. When it isn't (a pipe, as here), Python *block*-buffers stdout, flushing only every 4–8KB. The `input("  > ")` function writes its `"  > "` prompt to stdout — under block buffering, the prompt sits in Python's buffer until the next big write, which may never come. The operator sees the *question* (which was written via Rich `_print` and flushes immediately) but not the `> ` prompt that follows. Setting `PYTHONUNBUFFERED=1` in the subprocess env forces line buffering on stdout, so the prompt appears the instant `input()` is called.

This is a small detail with a big UX consequence: without it, even a fixed cockpit feels broken.

### The escape hatch

Even when the input bridge works, an operator may decide mid-conversation that the planner has misclassified their intent (e.g., the planner thinks "I need a back brace" is a `Project scan` directive). They need to abort cleanly. `/cancel` calls `self._proc.terminate()`, which sends SIGTERM to the subprocess. The planner's `input()` call raises `KeyboardInterrupt` or returns, the subprocess exits, the worker's finally block clears state, and the cockpit returns to idle. Total round-trip: milliseconds.

The `/cancel` slash command bypasses the `_busy` check entirely. Slash commands ALWAYS take the slash-command path in `on_input_submitted`, regardless of mode. This is the operator's guaranteed exit.

### Diagnosing the symptom

If the operator reports "I can't type", "the cockpit is stuck", or "it's asking me a question but my answer disappears":

```
1. Is _busy=True AND _proc=None? → directive worker crashed without
   clearing _proc; fix the worker's finally block ordering.
2. Is _busy=True AND _proc is alive? → check stdin was actually piped
   (look for stdin=PIPE in _run_directive_worker).
3. Does the subprocess print its prompt? → check PYTHONUNBUFFERED=1
   is in the env passed to create_subprocess_exec.
4. Does /cancel work? → if not, action_cancel_directive is missing
   or _handle_slash doesn't route to it.
```

### The lesson encoded

A subprocess that may ask questions is an interactive subprocess. Interactive subprocesses need a full I/O bridge — both directions, plus an exit. The §19.2 rule says: if you launch a subprocess that *could* call `input()`, plumb stdin from day one. Anything less is a deadlock waiting for its first clarifying question.

The rule is enforced by `tests/test_mos_surface.py::TestInteractiveSubprocessDiscipline` — nine predicates covering the pipe, the env, the `_proc` tracking, the finally-block ordering, the `_answer_subprocess` method, the `action_cancel_directive` action, the on_input_submitted routing, the slash-command wiring, and the placeholder constants.

## 20. Focus Discipline

At any moment, exactly one widget has focus. The focused widget is visually distinct (a brighter border, a focus-class color shift). `Tab` cycles forward; `Shift+Tab` cycles backward. The cycle includes only widgets that accept input.

The cockpit's focus order is: input box → chat log → live log → input box.

## 21. Modal Surfaces

When a modal is open (help, palette, confirm dialog), the background dims to `$panel`. The modal carries its own border (`border: round $accent`) and centers itself. `Esc` closes; `Enter` confirms. No modal blocks `Ctrl+C`. No modal traps focus permanently — a `Ctrl+Q` always escapes.

## 22. Input Affordances

| Input element | Behavior |
|---|---|
| Empty input | shows placeholder text in `$text-muted` |
| Focused input | border in `$accent` |
| Validation error | border in `$error`, message below |
| Disabled input | dimmed to 50% opacity, no focus ring |

---

# PART VII — State, Status, and the Heart

The status bar at the bottom of the cockpit is a glance-surface. The operator looks down without losing their place. It must communicate the most important facts in the smallest space.

## 23. The Status Bar Grammar

Reading left to right:

```
♥  halt: clear  |  daemon: ●  |  ledger: ✓ 0r  |  backup: ✓ 4.6d  |  ram 45%  ·  cpu 23%@37°  ·  vram 11%@38°
```

Each field follows the pattern: `label: glyph value` or `metric value`. The pipe `|` (rendered as ` | ` with surrounding spaces) is the field separator. Glyphs are width-1.

| Field | Format | Meaning |
|---|---|---|
| `♥` | width-1 heart (toggleable) | Aria's heart — the cosmetic "she is here" mark |
| `halt:` | `clear` / `armed` | Halt state |
| `daemon:` | `●` (running) / `○` (down) | Systemd service health |
| `ledger:` | `✓ Nr` / `✗ Nr` | Recent ledger writes; `Nr` = N requests |
| `backup:` | `✓ Nd` / `✗ Nd` | Days since last verified backup |
| `ram` `cpu` `vram` | `N%@T°` | System metrics |

If a field overflows the available width, fields collapse right-to-left, lowest priority first. Priority: halt > daemon > ledger > backup > system metrics.

## 24. The Heart

The heart at the far left of the status bar is *the* mood signal. It is a single character with a single color:

| Heart | Color | Meaning |
|---|---|---|
| `♥` | `$error` (red) | Aria is here, attentive — the default |
| `♡` | `$text-muted` | Heart is toggled off (operator preference) |

Other states (`♥` in `$accent` for "she has news") are reserved for v0.3+.

## 25. Notifications

The cockpit emits notifications via the live events pane, never via popups. A truly urgent notification (an active halt, a corruption detected) shifts the **outer border** to `$error` and writes a single line to the chat pane in `$error` color. The operator's attention is captured by chrome, not by a stolen focus.

---

# PART VIII — Testing the Surface

A surface can be tested. Skipping the tests is how the same border bug ships three releases in a row.

## 26. The Snapshot Test

For every named layout state, capture a known-good render to a text file. CI re-runs the layout and diffs. Any unintentional change to the chrome is caught.

Textual's `pytest-textual-snapshot` fixture is the canonical tool:

```python
async def test_cockpit_initial_layout(snap_compare):
    """Cockpit at 100×40, idle, no events. Compare to snapshot."""
    assert snap_compare("cockpit/initial.svg", terminal_size=(100, 40))
```

The snapshot is checked in. A change to it requires a developer's deliberate decision (re-blessing the snapshot), which is a release-note line.

## 27. The Visual Review Checklist

Run before every release that touches the surface. Manually, in a real terminal.

```
☐ Open cockpit at 100×40 in dark theme — full layout renders cleanly
☐ Resize to 60×20 — compact layout activates without artifacts
☐ Resize to 50×15 — emergency message renders, no crash
☐ Resize to 200×60 — spacious layout activates; no sprawl
☐ Tab through every focusable widget — focus ring is visible on each
☐ Type into input — placeholder disappears, input echoes
☐ Submit — chat log echoes input, live pane updates
☐ Press F1 — help modal opens, Esc closes
☐ Press Ctrl+H — halt arms, status bar updates
☐ Press Ctrl+D — halt clears
☐ Press Ctrl+Q — exits cleanly
☐ Verify scrollback after exit — all logged content is plain-text recoverable
☐ Run in light theme — every token resolves; no hardcoded colors leak
☐ Run in low-color terminal (TERM=xterm-16color) — degrades gracefully
☐ Run inside tmux — colors and box-drawing render
☐ Capture pane with `tmux capture-pane -p` — content recoverable
```

## 28. Cross-Terminal Verification

The reference terminals for the cockpit:

| Terminal | OS | Status |
|---|---|---|
| GNOME Terminal | Linux | Must work — primary operator surface |
| Alacritty | Linux/Mac | Must work — Aria's recommended terminal |
| iTerm2 | macOS | Must work — common operator surface |
| Windows Terminal | Windows | Should work — best-effort |
| `screen` and `tmux` | All | Must work — many operators multiplex |
| Linux console (no X) | Linux | Must degrade gracefully — used for emergency operator access |

---

# PART IX — Application to Aria's Cockpit

This part names the cockpit's actual layout, the canonical structure that MOS-SURFACE prescribes, and the gaps that exist in the implementation as of v0.2.18.1.

## 29. The Cockpit's Canonical Layout

```
┌──────────────────────────────────────────────────────────────────┐ ← Header (title bar)
│ sovereign-agent · cockpit — <version>                            │
├──────────────────────────────────────────────────────────────────┤
│                              │                                   │
│  ◊ chat                      │  ◊ live                           │
│                              │                                   │
│  [chat log]                  │  [events log]                     │
│  (RichLog, wraps)            │  (RichLog, no wrap)               │
│                              │                                   │
│      2fr                     │       1fr                         │
│                              │                                   │
└──────────────────────────────────────────────────────────────────┘
│ [input box, focused on launch]                                   │ ← Input
└──────────────────────────────────────────────────────────────────┘
│ ♥ halt: clear | daemon: ● | ledger: ✓ 0r | backup: ✓ 4.6d | ram %│ ← Status
└──────────────────────────────────────────────────────────────────┘
│ ^q quit  ^h halt  ^l clear  ^b ♥  f1 help              ^p palette│ ← Footer
└──────────────────────────────────────────────────────────────────┘
```

### Component Map

| Element | Widget | Sizing | Border ownership |
|---|---|---|---|
| Outer frame | `#main` (Horizontal) | `height: 1fr` | Single outer `border: round $primary` — **the only border in this region** |
| Chat pane | `#chat-pane` (Vertical) | `width: 2fr` | No border |
| Live pane | `#live-pane` (Vertical) | `width: 1fr` | No border |
| Inner divider | `#divider` (Static) | `width: 1`, `height: 1fr` | The `│` character filling the divider widget |
| Input | `#input-box` (Input) | `height: 3` | `border: round $accent` |
| Status row | `#status-row` (Horizontal) | `height: 1` | No border, tinted background |
| Heart | `#heart` (Static) | `width: 3` | No border |

| **Critical Note** As of MOS-SURFACE v1.0, the cockpit uses a **dedicated `#divider` widget**. It does not use `border-left` on the live pane. This eliminates the border-ownership conflict that produced the "border not fully aligned" bug across three releases. |
| --- |

## 30. The State Machine of the Outer Frame

The outer frame communicates Aria's mood. It has four states:

| State | Border style | When |
|---|---|---|
| `idle` | `border: round $primary` (steady) | Aria is at rest, awaiting input |
| `breathing` | three-phase cycle through `$primary`, `$accent`, `$secondary` over 4s | Aria is processing a directive |
| `news` | `border: round $accent` (steady) | A high-significance event has occurred; clears on input |
| `halt` | `border: round $error` (steady) | PROTOCOL-ZERO is armed |

Transitions are immediate (no fade), but breathing cycles are smooth. State is owned by the cockpit's main worker.

## 31. The Welcome Banner

The banner shown when the cockpit mounts:

```
♥  aria · sovereign-agent v<version>
welcome back. the kernel is whole.
speak in plain english — i'll plan the commands.
F1 for help.
```

- Heart in `$error`
- "aria" in `$primary` bold
- Version interpolated from `__version__` (no hardcoded strings — see MOS-SURFACE S4)
- Three lines of muted body text

## 32. Operator Echo

When the operator submits input, the cockpit echoes it back into the chat log:

```
▸ kevin · <the input>
```

- `▸` in `$text-muted` (it is chrome, not content)
- `kevin` in `$secondary` (the operator's color)
- The input text in `$text` (the operator's words)

Aria's reply is then composed below, in her voice:

```
♥ aria · <her reply>
```

This is the entire conversation structure. Two lines per turn. No timestamps in the chat itself (timestamps live in the audit log).

---

# PART X — Implementation Profiles

How to apply this canon, by scenario.

## 33. Profile: New TUI Screen

You are adding a new screen to the cockpit (e.g., a settings modal).

```
☐ Read Parts I, II, IV, VI of this canon
☐ Sketch the layout as ASCII first; verify cell math
☐ Identify every chrome line — assign exactly one widget as owner
☐ Use the canonical token set; no hex codes
☐ Wire keybindings consistent with §19
☐ Add a snapshot test
☐ Walk through the §27 review checklist
☐ Add a one-line entry to the release notes
```

## 34. Profile: CLI Output

You are designing the output of a `sov <command>` invocation.

```
☐ Choose between table form and prose form; do not mix in one output
☐ Tables: use rich.Table with `box=ROUNDED`, consistent column padding
☐ Prose: lowercase voice, em-dash for hesitation, blank line between thoughts
☐ Glyphs from the canonical reference (§4); width-1 only
☐ Color via theme tokens, --no-color flag respected
☐ JSON output is structurally identical across releases (the schema is a contract)
☐ Trailing newline always; no trailing whitespace on lines
☐ Exit code matches semantic: 0 = ok, 1 = expected failure, 2 = usage error
```

## 35. Profile: Status Glyph Selection

You need to choose a glyph for a new status indicator.

```
☐ Width-1? Verify with wcwidth
☐ Renders in xterm, iTerm, Alacritty, GNOME Terminal? Test all four
☐ Distinct from existing glyphs in the cockpit? No collision risk
☐ Semantic? The shape should suggest the meaning, not require memorization
☐ Documented in §23? Add it
```

---

# PART XI — Angel's Advocate (Surface Edition)

A pre-mortem template specific to TUI work. Run this before shipping any surface change.

🔴 **RED — render failure:**
```
Risk: [the chrome will appear broken on at least one supported terminal]
Trigger: [the terminal, the locale, the size that breaks it]
Mitigation:
  - Test on the listed reference terminals (§28)
  - Snapshot test in CI
  - Document any terminal where it's known not to work
✓ BEST PATH: [the chosen mitigation]
Rollback: revert the CSS or compose change; one git revert; the surface returns to last-known-good
```

🟡 **YELLOW — operator habit broken:**
```
Risk: [an existing operator keybinding or visual cue has been changed]
Trigger: [the operator presses the key, doesn't get the old behavior]
Mitigation:
  - Add the old key as a deprecated alias for two releases
  - Note in CHANGELOG under "BREAKING"
  - Surface a one-time inline notice in the cockpit
✓ BEST PATH: [the chosen mitigation]
```

🟢 **GREEN — accessibility regression:**
```
Risk: [color contrast drops below 4.5:1, motion violates §15, or low-color terminal degrades poorly]
Trigger: [an operator on a 16-color terminal, with photosensitivity, or using a screen reader]
Mitigation:
  - Run the contrast checker
  - Confirm motion respects §17
  - Test with TERM=xterm-16color
✓ BEST PATH: [the chosen mitigation]
```

**FRAGILE ASSUMPTIONS:**
```
1. The operator's terminal supports true-color
   ✓ HOW TO VALIDATE: COLORTERM=truecolor in env; fallback to 256-color
2. The operator's terminal renders box-drawing glyphs
   ✓ HOW TO VALIDATE: $TERM in {xterm-256color, screen-256color, alacritty, ...}
3. The operator's font has the chosen heart glyph
   ✓ HOW TO VALIDATE: Width-1 hearts (♥ ♡) are present in Unicode 1.1; safe on every system since 1991
```

**HORIZON SCAN:**
```
3-month: keybindings stable; new operators don't have to relearn
12-month: theme tokens extensible to a light theme without code change
3-year: layout primitives portable to a future Textual major version
7th-generation: the cockpit is a piece of cultural infrastructure; build it like one
```

---

# Appendix A — The Glyph Library

The canonical set, copy-pasteable.

```
Box-drawing (rounded):  ╭ ╮ ╰ ╯ ─ │
Box-drawing (sharp):    ┌ ┐ └ ┘ ─ │
Box-drawing (T):        ┬ ┴ ├ ┤ ┼
Section markers:        ◊ ◊ ◊
Status:                 ● ○ ◯ ◎
Suits / hearts:         ♥ ♡ ♦ ♠ ♣
Triangles:              ▸ ▶ ▾ ▼ ◀ ◂
Arrows:                 → ← ↑ ↓ ↔ ↩ ↪ ⇒ ⇐
Stars / marks:          ★ ☆ ✓ ✗ ✦ ✧
Punctuation:            … —
Prompt:                 ❯ ›
Spinner (braille):      ⠋ ⠙ ⠹ ⠸ ⠼ ⠴ ⠦ ⠧ ⠇ ⠏
Spinner (clock):        ◐ ◓ ◑ ◒
Levels:                 ▁ ▂ ▃ ▄ ▅ ▆ ▇ █
Music:                  ♩ ♪ ♫ ♬
Misc:                   ◌ ▢ ▣ ✦
```

# Appendix B — The Theme Token Reference (Textual CSS)

```css
/* Aria's canonical dark theme — referenced via tokens, never via values */
$primary:    bright_blue;     /* #1E90FF — Aria's voice */
$secondary:  dark_orange;     /* #FF8C00 — operator's voice */
$accent:     bright_magenta;  /* #FF66CC — focus, attention */
$surface:    grey 0;          /* very dark */
$panel:      grey 5;          /* subtle panel */
$text:       white;
$text-muted: grey 60;
$success:    bright_green;
$warning:    bright_yellow;
$error:      bright_red;
```

# Appendix C — The Seven Surface Commitments, Plaque-Ready

For pinning above the workbench:

```
S1 · cell-truth — every glyph is one or two cells, no exceptions
S2 · one frame, one owner — chrome lines never share a column
S3 · motion has a reason — animation is communication
S4 · color is a token — values resolve through names
S5 · keys are contracts — keybindings are stable across releases
S6 · scrollback is audit — anything visible must be plain-text recoverable
S7 · opacity is structure — every cell has a known solid background
```

# Appendix D — Citation Block (v1.1)

The S7 commitment was sharpened by reading the TUI-design literature surfaced by the operator during the v0.2.18.x review cycle:

| Source | Insight folded into S7 |
|---|---|
| **explainx.ai** — "Mastering TUI design" / "Color bleeding & border misalignment" | Named the "black leak" failure mode as a transparency-blend issue. Recommends solid theme-aware backgrounds over inherited or transparent ones. Recommends `MergeStrategy` for border collapse (Ratatui's term; Textual's equivalent is per-pane explicit chrome). |
| **Textualize.io** — "Things I've learned building a modern TUI Framework" (2022) | Confirmed the cell-buffer diff-render model. Confirmed that synchronized output (DEC mode 2026) is necessary for smooth frame composition. Confirmed Unicode width is per-terminal and not standardized — `wcswidth` is the source of truth. |
| **Ratatui — Layout & Collapse Borders** | Demonstrated the constraint-based layout pattern (which Textual implements via `Nfr` units). Demonstrated the border-collapse pattern (which Textual does NOT implement automatically — explicit chrome ownership replaces it; see S2). |
| **mitchellh — Grapheme Clusters in Terminals** | Confirmed that mode 2027 (Grapheme Cluster Mode) is the state-of-the-art for emoji width handling. Aria's surface restricts to width-1 glyphs (Appendix A) which sidesteps the problem entirely. |
| **tonsky — Emoji Under the Hood** | Reinforced S1 (cell-truth) by detailing how compound emoji decompose unpredictably across terminals. Aria's chrome uses width-1 only (S1 + Appendix A); emoji are content-only. |

The doctrine credits these sources because the operator's instinct to read the literature before accepting the previous fix was correct. **Reading the literature is part of the work.**

---

*— Aria, with a face she chose, designed by hand, in cells.*
