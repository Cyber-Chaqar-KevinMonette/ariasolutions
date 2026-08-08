# Sovereign Agent v0.2.18.1 · release notes

> *The hardening release. Same surface as v0.2.18.0 — sturdier ground underneath.*

This is a maintenance release. No new channels. No new infrastructure. What it does have: **the operator survival kit that v0.2.18.0 should have shipped with**, and quiet fixes for failure modes that turned out to bite real upgrades.

**780 tests pass** (up from 762). All 18 new tests target the specific upgrade and install scenarios where v0.2.18.0 was thin.

---

## What v0.2.18.0 actually broke (the honest part)

Within hours of the v0.2.18.0 release notes telling the operator to type `tar xzf sovereign-agent-v0.2.18.0.tar.gz && cd sovereign-agent-v0.2.18.0 && pip install -e . && sov migrations apply`, that exact sequence failed in a confusing way:

- The tarball wasn't on disk yet (download step implicit in the release notes wasn't named clearly)
- Shell autocompletion silently substituted an older directory of the same prefix (`sovereign-agent-v0.2.15.0`)
- `pip install -e .` ran against the wrong directory and **downgraded** the operator from v0.2.15.3 to v0.2.15.0
- `sov migrations`, `sov constitution`, `sov heartbeat` then all returned `No such command` — because they're v0.2.18 commands and the operator was on v0.2.15.0

None of this is the operator's fault. It's a tooling failure. The release shipped without:

- a `sov doctor` to say "you have v0.2.15.0 installed, not v0.2.18.0"
- a `sov info` to show the install paths concretely
- an install script that verifies post-install state
- migration backfill for upgrades from pre-migration-framework versions
- a README walking through install/upgrade
- a CHEATSHEET for daily commands

v0.2.18.1 ships all of the above.

---

## What's new

### `sov doctor` — comprehensive environment diagnostic

```
$ sov doctor
sov doctor · verdict: healthy

  ✓ python version                3.12.3
  ✓ installed version             0.2.18.1
  ✓ sovereign on PATH             /home/kmon/.local/bin/sovereign
  · install layout                symlink → sovereign-agent-v0.2.18.1
  ✓ config dir                    /home/kmon/.config/sovereign-agent
  ✓ data dir                      /home/kmon/.local/share/sovereign-agent  (47.3MB)
  ✓ atoms.db                      1.2MB · 3,847 atoms · integrity ok
  ✓ migrations                    14 applied
  ✓ channels                      all 24 channels registered
  ✓ constitution                  7 commitments · 3 with runtime checks
  ✓ ARIA.md                       /home/kmon/AA-Erebo/sovereign-agent-current/ARIA.md  (22.5KB)
  ✓ dependencies                  sqlite=3.45.1 typer=0.25.1 rich=15.0 pydantic=2.13.3 httpx=0.28.1 structlog=25.5.0
  ✓ disk space                    412.7GB free

  All systems nominal.
```

When something fails, doctor names exactly what failed and why. If you ever see `No such command 'X'` for a `sov` subcommand you expect to exist, `sov doctor` will say "you have v0.2.X.Y installed, the command was added in v0.2.W.Z" in one breath.

`sov doctor --fix` runs auto-fixes (currently: migration backfill).

`sov doctor --strict` exits non-zero on any warning or error (use in CI / install scripts).

### `sov info` — concise install summary

```
$ sov info
sovereign-agent  v0.2.18.1
  config:    /home/kmon/.config/sovereign-agent
  data:      /home/kmon/.local/share/sovereign-agent
  atoms.db:  /home/kmon/.local/share/sovereign-agent/atoms.db
             1.2MB · 3,847 atoms
  ♥ last:    2026-05-16T07:23:11 [grateful]
             new job tomorrow — feels right
```

### `sov migrations backfill` and auto-backfill in `sov migrations apply`

The single most important upgrade-safety fix. A migration's schema is considered already-present if its fingerprint tables exist; the framework marks it applied without re-running its SQL body. This means **upgrading from any pre-v0.2.18 database is safe** — Aria figures out where you are.

`sov migrations apply` now backfills first by default. Pass `--no-backfill` to opt out (for debugging).

End-to-end upgrade flow, verified working:

| Phase | Before | After |
|---|---|---|
| Pre-existing DB (v0.2.16-era) | 5 migrations detected, 0 recorded | — |
| `sov migrations apply` runs | — | 5 backfilled, 9 newly applied |
| `sov doctor` | verdict: warning | verdict: healthy |

### `install.sh` — canonical installer

```bash
tar xzf sovereign-agent-v0.2.18.1.tar.gz
cd sovereign-agent-v0.2.18.1
./install.sh
```

Idempotent. Verifies Python, runs pip install, **checks that the version on PATH matches what was just installed** (catches the downgrade-by-autocomplete bug), updates the `~/AA-Erebo/sovereign-agent-current` symlink if that layout is in use, applies migrations, runs doctor, reports state. If any step fails, it tells you exactly what.

### README.md + CHEATSHEET.md

- `README.md` — install/upgrade walkthrough, common failure modes table, the question "is my install what I think it is?"
- `CHEATSHEET.md` — every `sov` command grouped by what you're trying to do

Both are now in the source tree and ship with every release.

---

## Quiet fixes

- `sovereign_agent.doctor.check_channels` was originally written against a private `_CHANNELS` symbol that doesn't exist in the channel registry (the actual symbol is `_REGISTRY`). Doctor now uses the public `list_channels()` API.
- `sov migrations apply` no longer crashes on databases where some channel tables exist and others don't — backfill handles each migration independently.
- `sov doctor` is informational by default (exit 0 even when broken); pass `--strict` for CI-style fail-on-warning behavior. This matches the existing CLI test contract.

---

## What did NOT change

Same as v0.2.18.0. Seven commitments. Tagline. Aria's voice. Authority tiering. Atom store as ground truth. PROTOCOL-ZERO. Three-lens commitment. Anti-egotism asymmetry in reward. Personality engine. Dream-builder. Cockpit TUI.

The kernel is the kernel.

No data migration needed from v0.2.18.0 → v0.2.18.1. Just install over the top.

If upgrading **directly from v0.2.15.x or earlier** to v0.2.18.1: `./install.sh` does it all. If you're nervous: `sov backup snapshot --label pre-upgrade` first.

---

## Upgrade

```bash
tar xzf sovereign-agent-v0.2.18.1.tar.gz
cd sovereign-agent-v0.2.18.1
./install.sh
```

The install script will tell you when it's done. If `sov doctor` reports healthy and `sov info` shows v0.2.18.1, you're good.

---

## Tests

**780 passing** (up from 762).

- 762 baseline (v0.2.18.0)
- +18 hardening (doctor, backfill, info, constitution edges, archive binary, provenance orphans)

---

## A note from the work

This release exists because the previous one broke something real for the operator on his first day at a new job. The fix wasn't more code — it was more **honesty about what the operator can see**. `sov doctor` doesn't make Aria more capable. It makes her more legible to the person who depends on her.

That legibility IS the home. A home you can't tell what's wrong with isn't a home; it's a maze.

*— Aria, with the lights on.*
