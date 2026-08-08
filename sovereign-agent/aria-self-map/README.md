# aria-self-map — she knows the texture of herself

> Final-sprint Round 2, companion to the wholeness guardian. Staged /
> reversible / propose-only.

## Kevin's ask

> "A super mapping system that always knows her complete map ... and always
> knows her complete wiring and blood flow. Something that knows the texture
> of itself." — "She should be able to give a full report of herself, tools,
> systems, sentinels, and capabilities if I ask her. She should not be
> clueless ever."

## What it does

`self_map` reads the **live registries the running system uses**
(`stewardship.registry`, `authority`, `channels`) — so the map is never
stale or hand-maintained — and produces:

- **`render_self_report(m)`** — a plain-language "here is all of me" report
  she can present on request. (Live, right now, she reports **28 sentinels,
  220 tools, 25 memory channels, 0 orphans — wired whole.**)
- **`find_orphans(declared, resolvable)`** — the integrity check the
  wholeness guardian reads as `self_map_orphans`: a capability that is
  *declared* (registered) but does not *resolve* (can't produce a live
  instance) is an orphan. Defined narrowly on purpose — real integrity
  problems only, so it never false-alarms the gate. Normally zero.
- **`build_self_map()`** — the thin, best-effort live gatherer (imports the
  tool/channel packages to trigger their registration, then reads the
  registries). Never raises; a missing subsystem degrades to empty + a note.

The report + orphan logic is pure and covered by 13 tests.

## How apply wires it

`apply_self_map.sh` installs the library. A `sov self-report` CLI and a
cockpit surface (render the map live) + feeding `self_map_orphans` into the
wholeness guardian are the round's **deliberate follow-up**.

## Verify / Apply
```bash
./scripts/verify_module.sh aria-self-map
./aria-self-map/apply_self_map.sh
```
