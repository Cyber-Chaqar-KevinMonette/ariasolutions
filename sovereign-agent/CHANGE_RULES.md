# CHANGE_RULES.md — how every change ships (Claude Code, Cloud Claude, and Kevin)

> Binding for every session that changes this repo: Claude Code on Kevin's machine, Claude Code cloud
> sessions ("Cloud Claude"), and Kevin. CLAUDE.md points here. These rules add to CLAUDE.md and
> `.claude/PLAYBOOK.md` and never override them (staging, sealed files and safety invariants still win).

## Principle: intelligence behind every step

No step is taken without a stated reason and a check that it worked. For every change, the changelog or
handoff records:
- **why** — the problem, in a sentence
- **evidence** — what was measured or read that shows the problem is real
- **choice** — the option picked, and the main alternative rejected, with the reason
- **proof** — the command run and its exact result

"It seemed right" is not a reason. "Not verified" is an acceptable, honest result. A silent guess is not.

## The rule: a change is six things, or it isn't done

Every code change ships together with the first four. Five and six are added when they apply.

1. **The code** — staged as an `aria-<name>/` module per PLAYBOOK.md, unless Kevin says otherwise.
2. **Its tests**, updated in the same change:
   - New behavior → a new test that proves it works, not just that it imports.
   - Changed behavior → the existing tests updated to the new behavior, and the change log says why.
   - A bug fix → a regression test that **fails before the fix and passes after it**. Check this; don't
     assume it.
   - Removed behavior → its tests removed in the same change, with the reason in the changelog.
3. **A `CHANGELOG.md` entry** at the top, under `## Unreleased — <YYYY-MM-DD> (<short title>)`: what
   changed, why, and how it was verified (tests run, pass/fail counts).
4. **A handoff entry** in `FOR_CLAUDE_CODE_FROM_CLOUD_CLAUDE.md` (format below), so the next session,
   on any machine, knows exactly what changed and what's waiting.
5. **An audit report**, required when a session tests, measures, or reviews the system (test runs,
   stress tests, claim checks, security reviews), or changes anything security-relevant. It's saved as
   `reports/<YYYY-MM-DD>/AUDIT_REPORT.md`, together with the scripts that reproduce every number in it.
   It leads with the bottom line, then gives a table of results, and splits "bug in Aria" from "limit of
   the machine the test ran on".
6. **An advocate report**, required for every staged `aria-<name>/` module before it's proposed for
   apply. Run `./scripts/pre_apply_gate.sh aria-<name>` (Tribunal, Advocate Spectrum council of ten,
   14-gen foresight, quality, grounding, integrity and timeout gates). Save the output as
   `aria-<name>/ADVOCATE_REPORT.md`, with a short summary on top that answers **every** STOP and WARN:
   fixed (how), or not fixed (why). Never apply over a STOP without Kevin's explicit OK.

## Tests: hard rules

- **Never delete, skip, or loosen a test to make it pass.** A failing safety test is a stop sign.
- **Updating a test is allowed only when the behavior change was intended.** If unsure whether a
  failure is a bug or an intended change, stop and ask Kevin.
- **No time bombs.** Never hardcode a date that must fall inside a rolling window ("last 30 days"). Build
  dates relative to now, or inject a fixed `now`. (Three tests broke this way in 2026-09; see the
  2026-10-02 audit.)
- **Declared dependencies only.** If code imports a third-party package, it's in `pyproject.toml` (both
  dev blocks, per that file's rule) and `uv.lock`. Tests for optional extras start with
  `pytest.importorskip("<package>")`, so a clean install reports *skipped*, not *failed*.
- **Tests must not depend on order.** Each test passes alone and in the full parallel run
  (`./scripts/run_tests_chunked.sh`).
- **Report results honestly**: exact counts, including failures and anything not run, with the reason.
  Say "not verified" when a check couldn't be run.

## Claims: hard rules

- Every claim in a README, changelog or handoff ("faster", "proven", "thinks", "secure") names the
  measurement behind it and how to reproduce it.
- Speed comparisons measure both sides. A hard-coded guess is not a baseline.
- If a claim turns out to be wrong, correct it in the same change that finds it.

## Handoff file format (`FOR_CLAUDE_CODE_FROM_CLOUD_CLAUDE.md`)

Newest entry at the top. One entry per session that changed anything:

```
## <YYYY-MM-DD> — <who: Cloud Claude | Claude Code> — <one-line summary>
Branch: <branch> · Commits: <short hashes>
### Changed
- <file or module> — <what and why>
### Verified
- <command> → <exact result>
### Not done / needs Kevin
- <item> — <why it's waiting>
### Review status
- [ ] Reviewed by <the other side> on <date> — <notes>
```

- **Cloud sessions:** commit and push to the session's branch before ending. Anything not pushed is
  lost when the container is reclaimed.
- **Claude Code on Kevin's machine:** at session start, pull, read the newest handoff entries, check
  the "Review status" boxes for what you verified, and note anything you disagree with.
- Never put secrets, tokens, SSNs or personal financial details in a handoff, changelog or commit.

## Done checklist (copy into a session's final message)

- [ ] Code staged (or applied with Kevin's OK)
- [ ] Tests added or updated; regression test fails-before and passes-after
- [ ] Relevant tests run; exact counts reported
- [ ] `CHANGELOG.md` entry added
- [ ] `FOR_CLAUDE_CODE_FROM_CLOUD_CLAUDE.md` entry added
- [ ] Audit report in `reports/<date>/` (if anything was tested, measured or reviewed)
- [ ] Advocate report in each staged module, every STOP/WARN answered
- [ ] Every step has its why, evidence, choice and proof written down
- [ ] Docs whose claims changed are corrected
- [ ] Committed and pushed (cloud), or left for Kevin to review (local)
