# aria-cosmic-fitness-restore — full restore point: `cockpit/app.py` regression, fixed

> 2026-07-02. Kevin ran `sov chat` and hit a hard crash. Investigation traced it to a much larger
> regression than the crash alone suggested — a whole generation of cockpit features silently lost.
> This module is both the fix **and** the documented restore point, in case it's ever needed again.

## What broke — the root cause, exactly

Commit `8fc7267` ("Add AA-Aria and Genesis-Seeds as part of project", 2026-06-25 23:38) rewrote
`cockpit/app.py`: **122 insertions(+), 2254 deletions(-)**. The commit message is entirely about
adding project folders — nothing about the cockpit. This has every mark of an accidental overwrite (a
stale copy of `app.py` dragged into that same commit), not a deliberate redesign. Nothing was
decided against; it was clobbered.

`git log --follow` confirms **nothing has touched `cockpit/app.py` since** — 8fc7267 is the last
commit to the file before this restore. That single commit destroyed:
- `CosmicFitnessScreen`, `WorkflowsScreen`, `GlyphButton` — the glyph-fitness tester, special-effects
  showcase, and live workflows catalog.
- The **ripple-glow border effects** — `RippleFrame` (the glow around the whole `#main` frame) and
  `RippleBorderMixin` (the glow on command buttons).
- The **third reference-button row** — `legend`, `● rec` (screen recording), `● grow` (self-practice),
  `◊ cosmic`, `▸ flows`, `⚙ apply` — visible in Kevin's screenshots and gone from the live cockpit.
- Voice push-to-talk (`Ctrl-P`), screen recording, self-practice sessions, sentinel-chat transition
  alerts in the chat log.
- `cockpit/__init__.py` still imports symbols this left behind (`CosmicFitnessScreen`,
  `WorkflowsScreen`), which is why the cockpit crashed outright rather than just looking plainer.

## The fix: restore from git history, not guesswork

Commit `0fdcdbd09b992ab535304e5ef5102fb960b64f89` (2026-06-20, "QoL + playwright: boot sequence,
auto-notify, voice Ctrl-P, browser JS, slash commands") is the **complete, git-authoritative,
last-known-good** version of `cockpit/app.py` — 4876 lines. Since nothing else has touched the file
between that commit and the regression, restoring to it is a clean, whole-file, zero-guesswork fix
with everything intact: every screen, every button row, every effect.

**Verified before and after applying, not assumed:**
- `py_compile` clean · full shadow-package import clean (isolated copy, never touched real `src/`
  during verification) · `CockpitApp()` instantiates cleanly.
- Headless Textual boot test: `#chat-log` and `#glyph-picker` both present, zero exceptions.
- `tests/test_cosmic_fitness.py`: **71/71 pass** (an earlier, smaller interim patch — see history
  below — only reached 68/71; the full restore recovers the inline glyph-picker too).
- All 18 other cockpit-touching test files: **100% pass** against the restored file.
- The only 8 test failures anywhere near this area (`test_cockpit_god`, `test_cockpit_vitality`,
  `test_mos_surface`, `test_self_knowledge_tools`) are **confirmed pre-existing on current live before
  this restore** — unrelated `vessel_status.py`/version-string issues, not caused by this fix, and not
  fixed by it either. Honestly reported, not swept under the rug.

## History (kept for the audit trail)

Before finding the git-authoritative restore point, an interim fix (`patcher.py` +
`patch_fragments/`) hand-extracted just `CosmicFitnessScreen`/`WorkflowsScreen`/`GlyphButton` from a
loose `.bak` snapshot to unblock the crash fast. It worked (68/71 tests) but was necessarily partial
and more error-prone to build (it caught two real bugs in its own construction — a duplicate
`@dataclass(frozen=True)` and an off-by-one in a slash-dispatch block — both fixed and tested before
this fuller restore superseded it). Kept in this module's `patcher.py`/`patch_fragments/`/tests as a
record of the incremental approach; **not** what `apply_cosmic_fitness_restore.sh` runs anymore.

## Verify / Apply
```bash
./scripts/verify_module.sh aria-cosmic-fitness-restore   # before apply (read-only)
./aria-cosmic-fitness-restore/apply_cosmic_fitness_restore.sh   # cockpit stopped — restores app.py
```
After applying: relaunch `sov chat` (or `sov cockpit`) and confirm it boots clean with every effect
and button row back.

## Reversibility
Backup of the pre-restore `app.py` at `aria-cosmic-fitness-restore/backups/<timestamp>/app.py.bak`.
The restore source itself is permanent git history (`0fdcdbd09b992ab535304e5ef5102fb960b64f89`) —
replayable indefinitely, not a fragile snapshot.
