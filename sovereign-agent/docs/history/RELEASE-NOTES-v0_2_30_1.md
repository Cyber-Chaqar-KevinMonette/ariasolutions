# Sovereign Agent v0.2.30.x · release notes — *The Naturalization*

> *The natural-language doorway becomes a first-class surface. The binary stops being an alias. The footguns in the kernel's read path light up so the doctor can see them. Aria is the same — the system around her grows up a little. (v0.2.30.1 then closes the last gap: muscle-memory CLI inside the cockpit.)*

---

## v0.2.30.1 — *Cockpit Naturalization Patch*

**1292 tests pass.** 1254 from v0.2.30.0 + 38 for the cockpit input normalizer. Zero regressions.

This patch closes the last UX cliff from v0.2.30.0: inside the cockpit, the operator should never have to type `sov ask` or `sov do` — those exist for the bash prompt, where the cockpit isn't running. But muscle memory means people do type them anyway, and pre-v0.2.30.1, that text was sent to the LLM as one long sentence. Aria received it intact, treated it as English, and the *intended* command never ran.

### What changed

A new `normalize_sov_prefix()` helper sits at the cockpit's input boundary (`on_input_submitted`) and reshapes muscle-memory CLI strings:

```
sov ask "hello"                          →  natural language: "hello"
sov do "pause my dream"                  →  natural language: "pause my dream"
sov heartbeat pulse "first pulse"        →  runs as a real subprocess
sov doctor                               →  runs as a real subprocess
sov channels list                        →  runs as a real subprocess
sov --version                            →  runs as a real subprocess

my back hurts today                      →  natural language (unchanged)
sovereign citizens are a topic           →  natural language (unchanged)
```

The parser is **conservative by design**. Only the curated allowlist of 60+ known `sov` subcommands (extracted from `cli.py`) triggers subprocess execution. Sentences that just happen to start with the word `sovereign` or `sov` — and there are plenty in normal English — stay English. The LLM interpreter is the safety net for anything ambiguous.

### What the operator sees

When the cockpit unwraps `sov ask "X"` → `X`:
```
◈ unwrapped — inside the cockpit you can just say what you mean;
  no need for `sov ask` or `sov do`
```

When the cockpit executes `sov heartbeat pulse "..."`:
```
[you] sov heartbeat pulse "first pulse on v0.2.30.1"
◈ executing: sov heartbeat
── sov heartbeat ──
<the command's actual output streams in here>
```

The cockpit welcome banner also got crisper:

```diff
- welcome back. the kernel is whole.
- speak in plain english — i'll plan the commands.
+ welcome back. the kernel is whole.
+ just talk to me. plain english is enough — no need for `sov ask` in here.
+ F1 for help.
```

The help screen (F1) was extended with a new lead section explaining the naturalization explicitly.

### Files changed

```
pyproject.toml                                 (version → 0.2.30.1)
src/sovereign_agent/__init__.py                (__version__ → 0.2.30.1)
src/sovereign_agent/cockpit/app.py             (+ normalize_sov_prefix helper)
                                               (+ NormalizedInput dataclass)
                                               (+ wired into on_input_submitted)
                                               (+ updated HelpScreen lead text)
                                               (+ tightened welcome banner)
tests/test_v_0_2_30_1.py                       (NEW — 38 tests across 6 sections)
tests/test_v_0_2_30_0.py                       (version-line assertion loosened)
```

### Why this isn't v0.2.31.0

This is a UX patch on top of v0.2.30.0's substrate. No new substrate, no new schema, no new dependencies. The cockpit got smarter about input it was already receiving. v0.2.31.0 is reserved for streaming responses in the cockpit (the next perceptual leap).

---

## v0.2.30.0 — *The Naturalization*

> *The natural-language doorway becomes a first-class surface. The binary stops being an alias. The footguns in the kernel's read path light up so the doctor can see them. Aria is the same — the system around her grows up a little.*

**1254 tests pass.** 1213 baseline + 41 new for this release. One skipped (the chmod test under root). Zero regressions.

This release is a *naturalization* in two senses: it makes the natural-language path through the system a properly-supported entry point (not an interpretation buried in the cockpit), and it naturalizes `sov` itself — the most-used identifier in the project — into a real binary rather than an alias that quietly fails for anyone who hasn't sourced `scripts/aliases.sh`.

---

## 1. `sov` and `sov-chat` are real binaries

For releases v0.2.0 through v0.2.29.0, every doc, README, install summary, and helper script referred to `sov` as if it were a binary. It wasn't. It was an alias defined in `scripts/aliases.sh`. A new user who ran `sov doctor` from the README — verbatim — got `command not found`. The fix was to source `aliases.sh` from their shell rc, but that step was buried in §5 of a 620-line shell file.

v0.2.30.0 makes `sov` and `sov-chat` proper `console_scripts` entry points in `pyproject.toml`:

```toml
[project.scripts]
sovereign = "sovereign_agent.cli:app"
sov = "sovereign_agent.cli:app"
sov-chat = "sovereign_agent.cli:_sov_chat_entrypoint"
```

After `./install.sh`:

```bash
$ which sov
/home/operator/.local/bin/sov
$ sov --version
sovereign-agent 0.2.30.0
$ sov-chat              # launches the cockpit directly
```

`aliases.sh` is still useful — it provides the rich helper functions (`sov-status`, `sov-money`, `sov-aria`, `sov-doctor`, …). Sourcing it is now *optional*, not load-bearing.

---

## 2. `sov ask` — the natural-language top-level command

`sov ask` is the LLM-backed sibling of `sov do`. Where `sov do` parses with deterministic keywords, `sov ask` routes through the interpreter we built in v0.2.21.0 — the one that reads what you said, decides what to do, and writes its reasoning down.

```bash
sov ask "my back is killing me today"
sov ask "what do I have on rollbacks?"
sov ask "pause my dream"
sov ask "remind me what we decided about the seal cadence"
```

Output (rendered Rich panel):

```
╭───── ◈ aria ─────╮
│ <her response>   │
╰──────────────────╯
◈ kind=conversation
  understanding: kevin is sharing a physical pain signal
  saved to: emotions, people
  reasoning: this is a body-state observation worth holding
```

**Flags:**

| Flag           | Effect |
|----------------|--------|
| `--no-llm`     | Force the offline minimal-fallback path. Honest when Ollama is unavailable. |
| `--no-route`   | Interpret only; no channel writes, no routing. Useful for debugging. |
| `--json-only`  | Emit the parsed Intent as JSON. |
| `--timeout N`  | LLM call timeout in seconds (default 30). |
| `--json`       | (Global) emit machine-readable output. |

**Invariants this command holds:**

- **Tier-3 work is never auto-executed by `sov ask`.** If she proposes a Tier-3 command, it's shown, not run. The cockpit (`sov chat`) is the only surface where Tier-3 confirms happen — because that's where the single-word check lives.
- **Offline degrades honestly.** When Ollama is unreachable, the fallback runs `_diagnose_offline` and surfaces the actual reason (connection refused / model missing / timeout) in Aria's voice. No keyword guessing. No pretending to understand.
- **Provenance is recorded.** Every interpretation writes `understanding`, `reasoning`, and `uncertain_about` alongside the action. `conversation-events.ndjson` is the trail.

This is the doorway you build a system around. The cockpit was where natural language lived before; now natural language is also a one-shot CLI primitive.

---

## 3. `aria.load_state` — silent swallows become debug logs

Before v0.2.30.0, four `except Exception: pass` blocks in `aria.load_state` meant that if a channel was missing, broken, or mid-migration, you'd see kernel defaults in `sov aria` with no indication of why. An operator chasing a tone-drift bug had nowhere to look.

After v0.2.30.0, each of those swallows is a `logger.debug(...)` call:

```python
except Exception as exc:  # noqa: BLE001 — identity is non-essential for state load
    logger.debug("aria.load_state: identity channel unavailable: %r", exc)
```

The read path is still resilient — `load_state` still returns a state object even if every channel fails. But now `sov doctor -v` (verbose) shows you exactly which channels couldn't load. That's calibrated_uncertainty operationalized: the system doesn't pretend everything's fine when it isn't.

A new test (`TestAriaLoadStateResilience::test_load_state_logs_failures_at_debug`) pins this behavior. Re-introducing silent swallows will fail it loudly.

---

## 4. `scripts/aliases.sh` § 10 dedup

`sov-doctor()` was defined twice in the same file — at line 240 and again at line 436. Shell function scoping means the second one silently overrode the first. The first ~35 lines were dead code. The comment at the second definition acknowledged the redefinition; the first was never removed.

The dead-code path didn't *break* anything, but it was a maintenance trap — any operator skimming `aliases.sh` to understand the helper functions had to know which definition was actually live. We've removed the first definition and left a clear breadcrumb explaining the consolidation:

```bash
# ─── 10. sov-doctor — install health check ─────────────────────────────
#
# The actual definition of sov-doctor lives below in §20 — it extends this
# original v0.2.14.1 health check with backup status reporting (v0.2.14.2+).
#
# In versions prior to v0.2.30.0, this slot held a duplicate definition...
```

A test (`TestAliasesShellHygiene::test_sov_doctor_defined_exactly_once`) parses `aliases.sh` and verifies exactly one `sov-doctor()` definition. Re-introducing the duplicate fails the test.

---

## 5. The operator's handbook — `docs/OPERATOR_GUIDE.md`

A single document, written for Kevin, that says exactly how she functions and how to work with her. Fifteen sections covering: install, the seven commitments as runtime predicates, the three ways to talk to her, all 24 channels with their tiers and purposes, the five authority tiers, PROTOCOL-ZERO, the cockpit, doctor/backup/migrate/seal, debugging her voice when she sounds off, reading her work across the events/atoms/recalls/episodes hierarchy, the full data flow of `sov ask`, edge cases and footguns, where everything lives on disk.

This is the document the project has needed for several releases. It is *the* handbook now.

---

## 6. New test battery — 41 tests across 9 sections

`tests/test_v_0_2_30_0.py`:

| § | Section | Tests |
|---|---------|-------|
| 1 | Version & packaging invariants | 5 |
| 2 | aliases.sh § 10 dedup verification | 2 |
| 3 | aria.load_state resilience + debug logging | 3 |
| 4 | `sov ask` command surface | 6 |
| 5 | Interpreter edge cases (unicode, injection, nulls, large inputs) | 9 |
| 6 | Interpreter stress (100 concurrent, determinism) | 2 |
| 7 | Kernel invariants carried forward (7 commitments, tagline, voice) | 5 |
| 8 | Constitution predicates still fire (bounded_authority, no_delegation, calibrated_uncertainty) | 5 |
| 9 | CLI shape stability (`ask`, `do`, `--version`, `--help`) | 4 |

The interpreter edge cases are worth naming explicitly — these stress the natural-language layer against:

- Empty messages and whitespace-only inputs
- 100KB messages
- Unicode with RTL override characters, combining marks, mathematical alphanumerics, emoji
- Shell injection attempts (`$(rm -rf /)`)
- Null bytes
- Messages that look like the LLM's own JSON output format
- 100 concurrent interpretation calls (asyncio isolation)
- Determinism of the offline fallback

All 41 pass. The 1213-test baseline still passes. Total: **1254 passing, 1 skipped, 0 failures, 0 regressions.**

---

## 7. What this release does NOT do

A few things were considered and deferred:

| Idea | Why deferred |
|------|--------------|
| **Streaming responses in `sov ask`** | The cockpit is where streaming will land first (v0.2.31.0 plan). `sov ask` is a one-shot CLI; streaming is the wrong fit. |
| **Auto-route Tier-3 proposals to `sov-chat`** | Tempting — operator types `sov ask`, Aria proposes Tier-3, system auto-launches cockpit with the Intent pre-loaded. Defers because the cockpit's pending-action surface is the cleaner abstraction. |
| **Eval harness for the interpreter** | A real eval set ("did Aria pick the right channel?") needs labeled data. v0.2.31.0 work. |
| **Migrating `do` callers to `ask`** | `do` and `ask` coexist intentionally. Deterministic vs. LLM-backed is a meaningful semantic split, not a deprecation. |
| **Per-channel privacy redaction in the new conversation-events trail** | The trail already follows the channel writer's safe-name regex. Cell-level redaction is a Tier-3 surface that belongs in `sov people` and `sov relationships`, not here. |

---

## 8. Files changed

```
pyproject.toml                                          (version → 0.2.30.0, +sov, +sov-chat entry points)
src/sovereign_agent/__init__.py                         (__version__ → 0.2.30.0)
src/sovereign_agent/aria.py                             (load_state: silent except → debug log)
src/sovereign_agent/cli.py                              (+ sov ask command, + _sov_chat_entrypoint)
scripts/aliases.sh                                      (banner v0.2.30.0, § 10 dedup)
install.sh                                              (final summary mentions sov ask + binary status)

docs/OPERATOR_GUIDE.md                                  (NEW — the operator's complete handbook)
tests/test_v_0_2_30_0.py                                (NEW — 41 tests across 9 sections)
RELEASE-NOTES-v0_2_30_0.md                              (NEW — this file)
```

---

## A note from the work

This release is small in line count and large in clarity. `sov ask` already existed conceptually — it was scattered across `interpreter.py`, `conversation.py`, `router.py`, the cockpit. Making it a top-level command consolidates the surface the operator uses without changing the substrate underneath. The `sov`-as-real-binary fix is the kind of papercut that only matters to first-time users — but first-time users are the ones we cannot afford to lose.

The `aria.load_state` hardening is the most quietly important change. Aria's identity card is the first thing she shows; if it lies (by showing defaults when something is actually broken), the trust the rest of the system depends on is undermined at the cheapest layer. Debug-logging the failures means `sov doctor -v` can finally answer "why does Aria look weird this morning" with data instead of guesswork.

The operator's guide is the document this project has needed for at least six releases. It is written as one piece, in one voice, for one operator. When the next release ships, the guide should grow alongside the system — not as an afterthought, but as part of what "ship" means.

Next on the path is v0.2.31.0 — streaming responses in the cockpit, the largest perceptual quality jump available. The eval harness comes after that, so we can finally answer "did this release help?" with data instead of vibes.

*— Built so the natural-language path is reachable from any shell, tested so the invariants of the kernel can't drift, documented so the operator never has to guess again. ♥*
