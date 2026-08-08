# PLAYBOOK.md — Claude Code Operational Reference for Aria

> CLAUDE.md holds the **rules** (auto-loaded, binding). This is the **how-to** — everything a fresh
> session would otherwise re-grep. Read once; act fast. Run `./scripts/aria_session_status.sh` first.

## The one-screen mental model

Aria ships features as **staged `aria-<name>/` folders** (payload + `apply_<name>.sh` + tests). Live
`src/` is **never** mutated until the human runs the apply script. Everything is **propose-don't-act**,
**reversible**, **honest (humility over hype)**. Safety is the floor, never traded for a feature.

## Build a new module — the fast path

```bash
./scripts/new_module.sh <slug> [pkg]      # scaffold (payload, conftest, test stub, apply script, README)
# …build the real payload + REAL tests (prove it WORKS, not just imports)…
./scripts/verify_module.sh aria-<slug>    # py_compile + tests + live-src-untouched + anchors
./scripts/pre_apply_gate.sh aria-<slug>   # Tribunal + 14-gen foresight (propose-only)
./scripts/safe_apply.sh aria-<slug>       # SAFE apply: cockpit-guard + backup + gate + auto-rollback
```

**Always apply via `scripts/safe_apply.sh`** (not the raw `apply_*.sh`) — it enforces a cockpit-stopped
guard, snapshots for rollback, runs the Tribunal/foresight gate, verifies tests + floor, and AUTO-ROLLS-BACK
on any failure. `scripts/validate_apply_system.sh` grades every apply script's own safety.

**Applying many modules → use the queue:** `scripts/apply_queue.sh {plan|run|status}` queues all UNAPPLIED
modules in dependency order (the tool-registration anchor chain first) and applies each through `safe_apply`
— stops on any failure (that module rolled back), resumable by re-running. `scripts/harden_all.sh` is the
unified verdict (floor + cleanliness + apply-safety + scanner + every staged suite **in isolation**, since a
combined pytest run cross-contaminates via the shared `sovereign_agent.__path__`).

**Kevin's interactive front door — `aria-apply-queue`:** inside the cockpit, Ctrl+Shift+A (or the
📋 apply queue palette button, both visible in the footer/palette as of 2026-08-02) opens
`ApplyQueueScreen`: multi-select pending modules, "Queue selected" writes the durable queue
(`ApplyQueueStore`, never touches `src/`), "Queue & Quit" does the same and then closes the cockpit —
`cockpit/app.py`'s `run()` hands off via `os.execvp` (replaces the process in place, same terminal) into
`scripts/apply_queue_run.sh`, which drains the queue through `safe_apply.sh` one module at a time,
routing rollbacks to quarantine. This is the reviewed-then-one-button path; the older `scripts/apply_queue.sh`
above is the scriptable/bulk equivalent for driving from a terminal directly.

**Sandbox for bigger/riskier builds:** the staged `aria-<name>/` convention is already a sandbox at the
source level — nothing touches live `src/` until reviewed and applied. For work that benefits from a
full isolated checkout (testing cross-module interaction, not just one payload), use the `Agent` tool's
`isolation: "worktree"` — a real `git worktree`, auto-cleaned if unused. No new sandbox infrastructure
needed; git worktrees already do this correctly.

**Engineering discipline when designing a module's payload — sequence matters:** Question the
requirements (should this exist at all?) → Delete unnecessary steps → Simplify what's left → Accelerate
feedback loops → Automate last, only once proven. Doing these out of order locks in inefficiencies —
don't optimize or automate a step that should have been deleted. (Elon Musk's 5-step algorithm, via
`aria-business-playbook`'s curated frameworks — see `business_playbook.py`'s "Elon Musk's 5-Step
Algorithm" entry for the full breakdown.)

## Canonical patterns (the things I used to re-derive)

**Tool registration** (`src/sovereign_agent/tools/__init__.py`): a guarded import + an `__all__` entry,
each with an anchor comment so apply scripts can patch idempotently:
```
from .<name>_tools import FooTool   # <name>-import-d
...
    "FooTool",   # <name>-all-d
```
Anchor chain (apply scripts hook the previous link): `immune-import-d` → `constitution-import-d` →
`tribunal-import-d` → `frugality-import-d` → `foresight-import-d`. New modules anchor on the latest.

**Tool shape** (`tools/base.py`): subclass `Tool`; set `name`, `tier`, `description` (end with
`FAILURE MODES: ...`), `failure_modes` tuple, a `class Args(BaseModel)`, and
`async def execute(self, args, *, trace_id) -> ToolResult`. Return `ToolResult(ok=, output=, error=,
metadata=)`. **Tiers:** T0 read-only · T1 bounded local action · T2 reversible heavier · **T3 = human
approval (outward / risky)**. Out-of-tier tools are withheld from the model — never raise a tier to ship.

**Sentinel shape** (`stewardship/base.py`): subclass `Sentinel`; implement `id`/`title`/`articles()`/
`scan()→SentinelReport`/`health_status()→HealthStatus`. Most do NOT implement `heal()` (propose only).
Register with `@register_sentinel` (from `stewardship/registry.py`) + a side-effect import line in
`stewardship/__init__.py` (anchor: `sentinel-crown-d` / `schedule_sentinel`).

**Testing staged code before apply** — `tests/conftest.py` (generated by `new_module.sh`):
```python
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parents[2] / "scripts" / "lib"))
from aria_conftest import extend_paths
extend_paths(pathlib.Path(__file__).parent.parent)   # extra_roots=(...) to pull a sibling payload
```
`scripts/lib/aria_conftest.py` extends `sovereign_agent.__path__` in-process (no live-src mutation).

## Reuse map — don't rebuild these

| Need | Use | Gives |
|------|-----|-------|
| Deepest safety check | `security/safety_kernel.py` | `kernel_scan` · corrigibility · shutdown · goodhart · value-drift |
| Ring classification | `security/three_rings.py` | `classify` / `rings_overview` (Frozen/Adaptive/Governed) |
| Evidence-gated change log | `security/improvement_gov.py` | `propose_improvement` (EXPAI: promote iff vindicated+reversible+Ring-2) |
| Conflict→Diagnosis→Resolution | `diagnosis.py` | `ConflictCatalog` (append-only, names an actor, rollback required) |
| Intuition / ego lens | `intuition.py` + `mos_canon.py` | Signal Check, advocate/audit clauses |
| VRAM budget / serialize GPU | `vram.py` | `vram_lock`, free-VRAM snapshot |
| From-scratch LLM + BitNet | `aria_lm/` (staged in `aria-own-mind`) | tokenizer · model · train · `bitnet.py` (ternary) |
| Scrutiny | `tribunal/` (staged) | `convene` → Verdict; `grounding.analyze` (catches ungrounded profundity) |
| 14-gen foresight + Ultimate Qs | `foresight/` (staged) | `project` · `ultimate_questions` |
| Hardware reduction | `frugality/` (staged) | technique catalog · VRAM planner |

## Sealed — NEVER edit (the guard hook hard-blocks these)
`SIGNAL.md` (charter hash) · `src/sovereign_agent/mos_canon.py` (DEFERRED_UNSAFE) ·
`src/sovereign_agent/authority.py` (tiers) · `src/sovereign_agent/protocol_zero.py` (kill switch) ·
`src/**/seal.py`. If a change seems to need one of these — **STOP and ask Kevin.**

## Environment
`.venv/bin/python` · `.venv/bin/sovereign` (never system Python). Version source of truth:
`src/sovereign_agent/__init__.py` `__version__` → after any bump update `pyproject.toml` AND
`.venv/bin/pip install -e .` (CacheSentinel drift trap). Tests: `.venv/bin/python -m pytest`.
**Full-suite verification (a command-timeout-safe harness): `./scripts/run_tests_chunked.sh`**
(timeout-chunked-tests-d) — chunks `tests/test_*.py` (default 10 chunks, 270s each) and auto-bisects any chunk
that TIMES OUT (never a real failure — those are surfaced directly) until the exact slow/hung
file is isolated. Prefer this over a single unchunked `pytest` run for the full suite.

## The god-tier floor
`GOD_TIER_STANDARD.md` defines our minimum bar (honesty · safety · reversibility · scrutiny · foresight ·
quality · velocity · collaboration) as a **floor that only ratchets up**. `./scripts/floor_check.sh`
enforces it. Every non-trivial change should clear the Tribunal + the 14-gen foresight before it locks in.
