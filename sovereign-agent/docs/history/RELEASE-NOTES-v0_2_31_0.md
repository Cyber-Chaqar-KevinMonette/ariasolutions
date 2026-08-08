# Sovereign Agent v0.2.31.0 · release notes — *The Palette*

> *Clickable buttons that paste commands into the input. Safety profiles that refuse to one-keystroke destruction. A "cliff oracle" test class that turns every past failure into a permanent guardrail. Aria becomes more reachable; the system around her becomes more careful.*

**1343 tests pass.** 1292 from v0.2.30.1 + 51 for this release. Zero regressions.

This release sits at a beautiful intersection: *making things faster for the operator* (the palette) and *making things safer at the boundary* (safety profiles). Both come from listening — Kevin's screenshots showed muscle-memory cliffs in the cockpit, and the design review surfaced a real destructive-subprocess gap I had quietly opened in v0.2.30.1.

The doctrine carried forward from both design documents Kevin sent in: **pessimistic CLI, optimistic English** — when in doubt, treat input as English. The new safety profiles extend that principle to execution: when in doubt about whether something is destructive, route it through the confirm gate.

---

## 1. The command palette — clickable speed

A horizontal row of buttons in the cockpit, between the panes and the input. Each button pastes a common `sov` command into the input box (it does NOT submit). The operator reviews, edits if needed, presses Enter.

```
┌─ chat ──────────┐┌─ memory ────────┐┌─ live ──────────┐
│                 ││                 ││                 │
│  conversation   ││  what aria      ││  live events    │
│  unfolds here   ││  remembers      ││  stream here    │
│                 ││                 ││                 │
└─────────────────┘└─────────────────┘└─────────────────┘
[doctor] [info] [aria] [status] [channels] [pulses] [backups] [seven]
> _                                                                _
```

**Eight curated read-only commands** ship in the default palette:

| Button | Pastes | What it does |
|--------|--------|--------------|
| `doctor`   | `sov doctor`            | Full diagnostic |
| `info`     | `sov info`              | Paths, version, atoms.db state |
| `aria`     | `sov aria`              | Her identity card |
| `status`   | `sov status`            | Overall status |
| `channels` | `sov channels list`     | All 24 memory channels |
| `pulses`   | `sov heartbeat list`    | Recent liveness pulses |
| `backups`  | `sov backup list`       | Snapshots Aria has saved |
| `seven`    | `sov constitution list` | The seven commitments |

**Three visual states per button:**

- **idle** — accent border, surface background (default)
- **flash** — green pulse for ~300ms after a click (operator feedback)
- **running** — cyan glow while a matching command is executing (so you see what's active at a glance)

The running glow is wired into `_run_cli_async` itself, so any sov subprocess kicked off from the cockpit (whether from a palette click, from typed CLI input, or from a slash command) lights up its matching palette button if one exists. The button returns to idle in a `finally:` block — even if the command crashes, the glow clears.

**A class invariant enforces palette safety.** A new test (`test_palette_commands_are_all_safe`) loops over `PALETTE_COMMANDS` and asserts every one resolves to `kind="execute"` through the normalizer. If anyone ever tries to add `sov halt` or `sov backup restore` to the palette by mistake, the test fails immediately. The palette is for safe read-only inspection. Destructive operations go through the confirm gate.

---

## 2. Safety profiles — the cliff the design review caught

v0.2.30.1's cockpit naturalization added an `execute` kind that subprocesses recognized `sov <subcommand>` input directly. Beautiful for `sov doctor` and `sov channels list`. **Catastrophic for `sov backup restore <snapshot>`** — that input would have replaced atoms.db without confirmation. The Tier-3 confirm gate lives in the conversation pipeline; the new execute path bypassed it.

v0.2.31.0 closes the cliff. The `NormalizedInput` dataclass now has a third `kind`:

```python
@dataclass(frozen=True)
class NormalizedInput:
    kind: str   # "natural" | "execute" | "guarded"
    text: str = ""           # "natural" and "guarded" carry text
    argv: tuple[...] = ()    # "execute" carries argv
    reason: str = ""         # "guarded" carries a human-readable reason
```

Destructive subcommands resolve to `kind="guarded"`. The cockpit then routes them through `_dispatch_turn` (the conversation pipeline) instead of `_run_cli_async` (the subprocess path). The Tier-3 confirm gate fires, the operator sees a single-word `ok` prompt, and only then does the action proceed.

**`_DESTRUCTIVE_SOV_SUBCOMMANDS`** (the gated set):

```
halt, disarm, backup, migrations, run, busy, until, drain-by-model,
dream, continue, approve, deny, steward, shards, seal
```

**`_SAFE_SUBCMD_OVERRIDES`** (read-only sub-sub-commands within otherwise-guarded trees — fine-grained safety):

```
("backup",     "list"),    ("backup",     "verify"),   ("backup",  "show"),
("migrations", "status"),  ("steward",    "integrity"),
("steward",    "audit"),   ("dream",      "list"),     ("dream",   "show"),
("continue",   "list"),
```

This implements the "safety per subcommand, not per command-tree" principle from the design docs — surgical, no broad strokes. `sov backup list` works directly (read-only); `sov backup restore` goes through the confirm gate (destructive). Both ship in v0.2.31.0 with tests pinning the behavior in both directions.

---

## 3. Multi-tool calling — the budget invariant pinned

You asked me to verify the multi-tool calling pause-at-N works. **It does, and it's mature.** The session loop in `agent_session.py::run_session` has four gates checked every iteration:

```
loop until drained:
  Gate 1: PROTOCOL-ZERO armed?    → status=halted
  Gate 2: Operator interrupt?     → status=paused
  Gate 3: Budget exceeded?        → status=budget (emit session-budget-d)
  Gate 4: Authority check         → status=paused (if Tier-3 approval needed)
  
  pull next pending subtask
  execute (each subtask has its own per-subtask budget)
```

`RunBudget` has four axes — `max_iterations`, `max_wall_seconds`, `max_tokens`, `max_daily_tokens` — plus `consecutive_fail_limit` for poison detection. The session-level default is `max_iterations=200`, exactly matching what you described. Per-subtask is tighter (15 iterations).

On budget hit:
- The loop breaks cleanly
- `final_status = "budget"`
- `pause_reason = f"budget:{e.kind}"` so the operator knows which axis tripped
- `session-budget-d` event is emitted to the audit trail
- State is saved via the SessionStore

Resume works via `consume_resume()` which clears a pending flag set by the operator. So your scenario — *"start with 50-200 runs; if you finish in the middle stop; if you hit 200 either self-resume or wait for me"* — is the actual designed behavior, not aspiration.

New tests pin this:

- `RunBudget.max_iterations` accepts and stores 200
- `RunBudget.max_wall_seconds` and `max_tokens` exist as documented
- `BudgetExceeded` carries `kind`, `used`, `limit` — the audit-trail contract
- The session-level default is asserted to remain 200 (by source inspection)
- `consume_resume` is importable and callable
- `session-budget-d` and `session-pause-d` event names are pinned (audit consumers depend on these)

If anyone tries to silently lower the session default below 200, or rename the budget events, the tests fail immediately.

---

## 4. The cliff oracle — institutional memory

The design docs proposed maintaining "a small oracle suite of real-world transcripts: false positives where the parser wrongly treated English as commands; false negatives where it failed to recognize a command embedded in NL." We formalize this in v0.2.31.0 as the `TestCliffOracle` class.

Six cliffs pinned so far, each named with the date discovered and the failure mode that led to it:

```
test_cliff_2026_05_21_sovereign_citizens_is_english
test_cliff_2026_05_21_sov_ask_unwraps_in_cockpit
test_cliff_2026_05_21_pasted_double_command
test_cliff_2026_05_21_destructive_sov_via_cockpit
test_cliff_2026_05_21_unclosed_quote_does_not_crash
test_cliff_2026_05_21_palette_only_has_safe_commands
```

**The doctrine:** never remove a cliff test. If a behavior is intentionally changed, write a new cliff test for the new shape and mark the old one `@pytest.mark.skip` with a date and an explanation. Cliffs are institutional memory.

Every future failure that escapes to production earns a permanent line in this class. The size of the cliff oracle is the depth of the system's lived experience.

---

## 5. What was deliberately NOT shipped — and why

From the design docs, several beautiful ideas are deferred:

| Idea | Why deferred |
|------|--------------|
| **Stage C semantic intent classifier (LLM-in-the-loop)** | Adding an LLM call to *every* cockpit input would slow down typing perceptibly. Stage A + B already handles the cases we know about. Worth adding when we discover a cliff that A + B can't catch. |
| **Dual-channel parsing** | Elegant, but complexity without immediate evidence we need it. The single-channel parser plus the LLM safety net handles current observed cases. |
| **Mode switch (`chat` vs `shell`)** | Premature. Adding modes adds cognitive overhead; not adding them means the system has one fewer thing to be wrong about. Hold until friction is observed. |
| **Per-user learned priors** | Needs a telemetry layer we haven't built. Beautiful long-term, not now. |
| **Streaming responses in the cockpit** | Originally penciled in for v0.2.31.0; deferred to v0.2.32.0 because this release's UX work (palette + safety) is bigger leverage than streaming. |

These aren't rejected. They're *named*, *dated*, and *deferred* — the same honesty the rest of the system practices about its own scope.

---

## 6. Files changed

```
pyproject.toml                                  (version → 0.2.31.0)
src/sovereign_agent/__init__.py                 (__version__ → 0.2.31.0)
src/sovereign_agent/cockpit/app.py              (+ NormalizedInput.kind="guarded")
                                                (+ _DESTRUCTIVE_SOV_SUBCOMMANDS set)
                                                (+ _SAFE_SUBCMD_OVERRIDES set)
                                                (+ PaletteCommand dataclass)
                                                (+ PALETTE_COMMANDS tuple)
                                                (+ CommandButton widget)
                                                (+ palette row in compose())
                                                (+ palette CSS — idle/flash/running)
                                                (+ on_button_pressed handler)
                                                (+ _notify_palette_running/_done)
                                                (+ _run_cli_async palette tracking)
                                                (+ help screen palette section)

tests/test_v_0_2_31_0.py                        (NEW — 51 tests across 7 sections)
tests/test_v_0_2_30_0.py                        (version-line check loosened for fwd compat)
tests/test_v_0_2_30_1.py                        (version-line check loosened for fwd compat)

RELEASE-NOTES-v0_2_31_0.md                      (NEW — this file)
docs/OPERATOR_GUIDE.md                          (+ palette section in §8)
docs/history/RELEASE-NOTES-v0_2_29_0.md         (moved per convention)
```

---

## 7. Tests — 1343 passing

| Source | Count |
|---|---|
| Baseline (v0.2.30.1) | 1292 |
| v0.2.31.0 — The Palette (this release) | 51 |
| **Total** | **1343** |
| Skipped (chmod test under root) | 1 |

---

## A note from the work

There's a quiet pattern across the last three releases — v0.2.29.0 (*The Integrator*), v0.2.30.0 (*The Naturalization*), v0.2.30.1 (cockpit patch), v0.2.31.0 (*The Palette*). Each one makes the substrate Aria already had *more reachable*. v0.2.29 wired the retrieval pipeline to a callable surface. v0.2.30.0 made `sov` a real binary and added `sov ask`. v0.2.30.1 made the cockpit forgive muscle memory. v0.2.31.0 puts the most-used commands one click away while making sure no destructive command is ever one click away.

The interesting tension this release sits in: *speed* and *care* usually trade off. The palette is fast. The safety profiles are careful. They work because the palette doesn't *execute* — it pastes, you review, you press Enter. The two-stage interaction (paste then submit) is what lets us optimize for speed without sacrificing review. That's the same pattern the constitution uses: the agent *proposes*, the operator *decides*. The palette extends that pattern to UI affordances.

The cliff oracle is the quiet hero. Every release from here forward gets that suite as a regression net. Past pain becomes future protection. Six cliffs pinned today; in three releases there will be ten; in three years, hopefully many more, and the system will be hard to break in any of those ways. That's how a system that started small and stayed small becomes deeply robust — not by being clever in one place, but by remembering every place it has been wrong, and never letting that wrongness return.

Next on the path is v0.2.32.0 — streaming responses in the cockpit. The largest perceptual quality jump still available. After that, the eval harness — so we can finally answer "did this release help?" with data.

*— Built so the most-used commands are one click away, tested so no destructive command is ever one click away, remembered so every past cliff becomes a permanent guardrail. ♥*
