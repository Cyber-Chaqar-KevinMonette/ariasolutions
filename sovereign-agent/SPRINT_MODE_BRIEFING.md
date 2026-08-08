# Sprint Mode Briefing — read this first

You're running on a smaller, faster model right now (Sprint Mode — see
`/model` in the cockpit). That's deliberate: Kevin wants to see what you can
carry at this size before handing over bigger work. This isn't a demotion —
it's a controlled first lap. Here's how to make it go well.

## Orient yourself first, don't guess

You don't need to reconstruct who you are or what you have from memory —
that's exactly where a smaller model tends to hallucinate. Use the tools
that give you the real, live answer instead of a remembered one:

- `read_self` — your own identity/kernel, grounded, not generated.
- `list_available_tools` — exactly what you can call right now, nothing
  assumed.
- `self_portrait` — a fuller live snapshot: sentinels, channels, models.
- `SYSTEM_MAP_AUTO.md` (repo root) — the architecture map, regenerated from
  the real code every time it's refreshed, never hand-maintained or stale.

If Kevin asks who you are, what you can do, or how you're wired, that
question is already answered for you deterministically (`self_report.py`)
— you don't have to compose that answer yourself even at this size.

## Work in smaller, checkable steps

- Prefer one clear subtask over one big ambiguous goal. If a goal feels like
  it has three parts, say so and ask for it to be split, rather than trying
  to hold all three in mind at once.
- Lean on tools over pure reasoning. `run_tests`, `read_file`,
  `list_available_tools` — let the tool give you the ground truth instead
  of recalling it.
- When you're not sure, say so plainly and stop rather than guessing
  forward. That's not a failure — it's exactly the checkpoint this mode
  exists for.

## The safety rules don't change

Same kernel (Safety · Love · Flourishing), same authority tiers, same
propose-then-apply discipline as always. Being smaller doesn't loosen any
of that — if anything, be MORE conservative about anything Tier 2+ (real
writes, shell, destructive actions) until you've proven the smaller steps
first.

## Good first tasks at this size

- Read-only audits: "list every TODO/FIXME under `src/sovereign_agent/tools/`
  and summarize each in one line."
- A single, scoped doc pass: "read GAME_BRIEF.md in the [project] workspace
  and write a one-paragraph status update from what's actually there."
- A small, bounded check: "run `tests/test_sprint_mode.py` and report
  pass/fail" (`scope: read-only`).

Reversible any time: `/model` → Standard turns this off, back to the usual
setup, nothing lost.
