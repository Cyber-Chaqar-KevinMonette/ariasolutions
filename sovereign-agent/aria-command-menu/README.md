# aria-command-menu — Workstream M: popup command palette + missing-button audit

**Kevin's ask:** *"move the buttons into a drop down menu or a pop up menu that is perhaps
scrollable so we can store more 'buttons' or features while conserving space for observability and
for work"* + *"make sure we add more buttons to the new menus if we genuinely are missing some."*

## What this ships

- Collapses the 3 permanent `Horizontal` palette rows (`#palette-row`/`-2`/`-3`, 21 buttons total —
  more than the "14" this workstream was originally speced against; the palette grew since) into
  **one row**: a `☰ commands` button + 3 live strips (observability / security / emotions).
- `CommandPaletteScreen` (new file, mirrors `ApplyQueueScreen`'s proven `ModalScreen` shape almost
  line for line) — a scrollable popup listing every command + reference button. Bound to `Ctrl+M`
  (previously unused) alongside the button.
- Clicking a command in the popup pastes it into `#input-box` **exactly as today** — the existing
  `on_button_pressed` paste logic is untouched; the only addition is auto-closing the popup first
  when the click originates there.
- **3 live strips**, each reusing existing, already-live data sources (no new plumbing):
  - **Observability** — `stewardship.registry.gather_health()` (ok/warn/err counts).
  - **Security** — `authority.tools_available_in_mode(Mode.ONESHOT)` (Tier-3 tool count) +
    whether `workflow/safe_eval` (this session's own L-fix) is present.
  - **Emotions** — `emotion.derive_emotions()` / `emotion_to_mood()` — a genuinely live engine that
    had zero cockpit surface before this.
- **Missing-button audit** (the second half of Kevin's ask) — a grep of `cli.py`'s registered typer
  apps against the palette found 3 real, already-safe, zero-presence commands, now added:
  `sov sentinels scan`, `sov dream list` (already pre-approved in `_SAFE_SUBCMD_OVERRIDES`, just never
  had a button), `sov requests list --all`. **`sentinels` was also missing from
  `_KNOWN_SOV_SUBCOMMANDS` entirely** — a typed `sov sentinels scan` didn't even auto-execute before
  this fix. A 4th candidate (quarantine review) was found but deliberately deferred: it's currently
  only a `python -m sovereign_agent.apply_queue quarantine list` entry point with no `sov`-prefixed
  form, and `normalize_sov_prefix` only recognizes `sov`/`sovereign`-prefixed input — a palette button
  for it would silently misroute to the chat pipeline. Needs a `sov apply-queue` CLI wrapper first;
  named here, not silently dropped.

## Why anchored span patches, not a full-file replace

`app.py` is 4,894 lines and evolves fast (it was fully restored from a much older commit earlier this
session after a prior full-file mistake broke `sov chat`). `patcher.py` makes 10 small, independently
verified, uniquely-anchored edits rather than touching anything else in the file.

## Tests (10/10 passing pre-apply)

`tests/test_patcher.py` — all 10 edits apply cleanly against the CURRENT live file, are idempotent,
old `palette-row-2`/`-3` IDs are gone, `PALETTE_COMMANDS`/`REFERENCE_BUTTONS` themselves are
untouched (only `compose()`'s rendering changed), and the patched file compiles.
`tests/test_command_menu.py` — a full headless boot (Textual's `run_test()`/`Pilot`, same pattern as
the pre-existing `tests/test_cockpit.py`) against a **shadow copy** of the whole package (never
touches real `src/`): the popup opens/closes via `Ctrl+M`, lists every command
(`len(PALETTE_COMMANDS) + len(REFERENCE_BUTTONS)` buttons, dynamically — not a hardcoded count),
clicking a command pastes it and auto-closes the popup, the 3 new gap-audit buttons are reachable
and paste the right command, `sov sentinels scan` is now recognized by `normalize_sov_prefix`, and
all 3 strips render without throwing when their backing data is absent/empty.

Reversible: restore `app.py` from the backup, `rm cockpit/command_palette_screen.py`.
