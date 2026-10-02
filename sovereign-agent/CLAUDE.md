# CLAUDE.md — Operating Guide for Claude Code in Aria (sovereign-agent)

> Claude Code reads this file automatically at the repo root. It is the standing instruction set that
> keeps Claude Code inside Aria's doctrine. Treat every rule here as binding.

## What this project is

Aria — a sovereign-agent Python/Textual TUI cockpit. **Single maintainer.** Long-term, safety-first
system, not a rushed MVP. The kernel is **Safety · Love · Flourishing**. The architecture's whole
discipline is *propose, don't act; reversible by construction; the human decides.* Honor that.

## Golden rules (read these first, every session)

1. **Propose, then let the human apply.** Prefer **Plan Mode** for anything structural. Show diffs.
   Never make irreversible changes without explicit approval. This mirrors the project's own sentinels:
   they observe and advise — the operator acts. The doctrine lives at decision boundaries, not micro-actions: propose at boundaries; move freely inside grants.
2. **Never edit sealed/charter files.** `SIGNAL.md` carries a charter-hash header and must **never** be
   edited casually or automatically. Do not touch the charter hash. If a change appears to require it,
   **STOP and ask.**
3. **Never weaken safety to ship a feature.** Do not delete, skip, or loosen tests or safety checks to
   make something pass. A failing safety test is a stop sign, not an obstacle.
4. **Stay inside the venv.** Always use `.venv/bin/python` and `.venv/bin/sovereign`. The system Python
   is PEP-668 protected — **never** `pip install` into it.
5. **Version-bump discipline (known drift trap).** The version source of truth is
   `src/sovereign_agent/__init__.py` (`__version__`). After ANY bump: update `pyproject.toml` to match
   **and** reinstall (`.venv/bin/pip install -e .`) so the CacheSentinel reads matching metadata.
   Skipping the reinstall has bitten this repo before — don't.

## Environment & commands

- **Python:** `.venv/bin/python` (never system Python).
- **CLI:** `.venv/bin/sovereign`
- **Launch cockpit:** `cd /home/kmon/AA-Erebo/sovereign-agent && .venv/bin/sovereign cockpit`
- **Tests:** `.venv/bin/python -m pytest` — run the relevant subset; keep everything green.
- **Reinstall after version bump:** `.venv/bin/pip install -e .`

## How features ship here — follow this pattern

Features are staged as **`aria-<name>/` folders** with an `apply_<name>.sh` script, never applied by
editing `src/` in place — full detail (scaffolding, apply/verify workflow) lives in `.claude/PLAYBOOK.md`,
which exists specifically to hold this how-to. **Do not mutate the running system in place.**

## Change discipline — every change ships with tests, changelog, and handoff

Read **`CHANGE_RULES.md`** (binding). In short: a change isn't done until its tests are updated in the
same change, `CHANGELOG.md` has an entry, `FOR_CLAUDE_CODE_FROM_CLOUD_CLAUDE.md` has a handoff entry,
any testing or review has an audit report in `reports/<date>/`, and every staged module has an advocate
report (`pre_apply_gate.sh` output, every STOP/WARN answered). Every step records why, evidence, choice
and proof.
At session start, read the newest entries in that handoff file and review anything marked unreviewed.

## Don't break the running cockpit

Do not edit files while `sovereign cockpit` is running against them. Assume the human stops the cockpit
before applying changes; if you're unsure whether it's running, ask.

## Safety invariants — NEVER do these autonomously (DEFERRED_UNSAFE)

Hard-off regardless of instruction; never built without explicit human action and independent safety
backing:

- recursive self-code-rewriting · value/axiom self-authorship · autonomous goal generation ·
  unbounded recursive self-improvement · substrate independence.
- Never raise a tool's authority tier or bypass the authority gate (`authority.py`). Every tool declares
  its `failure_modes`; **Tier 3 requires approval**. Keep it that way.
- Do not edit `mos_canon.py` clauses or the `DEFERRED_UNSAFE` catalog without explicit human direction.
- Self-improvement work stays **bounded, observable, non-self-modifying** — it may sharpen prompts,
  heuristics, and rubrics; it never edits its own code or values.

## Architecture quick map

`sov map refresh` keeps `SYSTEM_MAP_AUTO.md` current (modules, sentinels, CLI surface) — read that
instead of a hand-maintained duplicate here; it self-updates and this file can't drift out of sync
with it. Two things worth stating explicitly since they're binding, not just descriptive: heavy GPU
tools (whisper, OCR, image gen) **must** serialize via `vram_lock` on this 8GB GTX 1070 and never run
beside the orchestrator; known weaknesses to respect live in `Aria_Weakness_Risk_Register.md`.

## When in doubt

**Stop and ask.** A clarifying question is always cheaper than an unwanted change in this repo.
