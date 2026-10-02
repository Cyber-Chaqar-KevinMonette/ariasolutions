# Aria clean-room audit — 2026-10-02

Done by Cloud Claude (a Claude Code cloud session) on a fresh Linux container, from the GitHub copy of
`ariasolutions/sovereign-agent` at commit `27a3948`, v0.4.0. Nothing on Kevin's machine was touched.

**Bottom line:**
- **Aria installs cleanly, and 98% of her 6,944 tests pass.**
- Most failures come from this machine (no Ollama, no GPU, blocked websites) or from tests not updated
  after intentional changes. There are few real bugs.
- **The biggest problem is a claim, not the code.** The "quantum superposition processor, proven 1000×+
  faster and genuinely thinks" is a word-overlap matcher. Its "quantum" steps have no effect on its answers.
- The MCP bridge had real security gaps. A guarded fix is staged in `aria-mcp-remote-guard/`.
- **Persistence is excellent: 9 of 9 checks pass.** That includes a hard crash during 27,000+ event
  writes with zero corruption, a one-character tamper caught by the seal, and a full backup restore.
- **The CLI is up to modern standards: 16 of 16 checks pass across all 99 commands.** The one gap from
  top-tier CLIs is startup time, about 400 ms against under 300 ms.

## 1. Clean install

| Check | Result |
|---|---|
| `uv sync --group dev` from scratch | Pass, 20 seconds |
| Version source of truth vs `pyproject.toml` | Both 0.4.0, consistent |
| `sovereign --help`, plus `sov`, `sov-chat`, `sov-mcp` on PATH | Pass |
| `uv.lock` matches `pyproject.toml` | **No.** `uv sync` rewrote it (+1,517 / −43 lines). The committed lockfile is stale, so installs aren't reproducible until it's re-locked. (The rewrite was not committed.) |
| Secrets in the repo (Stripe, GitHub, Anthropic, OpenAI, AWS, Slack, Discord token formats; SSNs) | **None found.** The only matches were fake test values. |

## 2. Full test suite

`pytest -n auto` over `tests/`: **6,944 tests: 6,805 passed, 81 failed, 3 collection errors, 55 skipped,
in 425 seconds.** Every failure was re-run one at a time: 75 still fail, and 6 fail only in the parallel run.

| Cause | Failures | Bug in Aria? | Files |
|---|---|---|---|
| This cloud machine: websites blocked by the network policy | 15 | No | warframe_flip_fetcher (14), stealth_browser |
| This cloud machine: no Ollama running (or torch, for `nested_core_live`) | 7 | No | record_game_lesson (2), memory_write, quality_tribunal_live, nested_core_live (3) |
| This cloud machine: optional heavy packages not installed (torch, peft, Pillow, numpy, playwright, pypdf, dbus_next) | 10 + 3 errors | No, but see the note under section 6 | model_trainer (3), model_trainer_qlora, image_gen, movie_clip_quality_gate (2), qol, v026 (2); errors in portal_screencast, portal_screenshot, sprite_qa |
| This cloud machine: terminal too small for a UI test | 1 | No | theme_studio |
| **`discord.py` is used but not declared as a dependency** | 6 | **Yes, packaging** | discord_admin (5), workflow_capability_tests (likely the same cause) |
| **Stale tests after intentional changes**: retired verticals (catalog now 13, tests expect 30+), MOS canon grew from 35 to 47 clauses, a test double missing the new `embeds` argument, renamed Discord category, reworded prompt | 27 | Tests need updating | verticals (17), scout (2), canon_embodiment (3), v0210, discord_reliability (2), work_narrator, reaching_kevin |
| **Real issues caught by Aria's own guard tests** | 5 | **Yes** | Unsafe glyphs shipped: requests_glyphs, discord_watch, command_menu (`📋`). A provider added without a validation probe: api_providers (2, `alpaca`). |
| Unclear; needs a look on Kevin's machine | 1 | ? | game_window_live (`'flash'` not in the registered set) |
| **Time bombs**: hardcoded June 2026 dates inside 30- and 90-day windows, so they began failing as the calendar moved | 3 | Tests | proof_tools, impulse_tools (2). **Fix ready: `fix-test-timebombs.patch`.** |
| Pass alone, fail in the parallel run (test isolation) | 6 | Tests | business_playbook (3), engineering_playbook (3) |

`RESUME_HERE.md` and `KEVIN_CHECKLIST.md` still quote older numbers (2,836 tests). The real count today is
6,944.

## 3. Claim check

### "Quantum-faithful superposition processor: proven 1000×+ faster, genuinely thinks" — not supported

From `src/sovereign_agent/nonclassical_supreme/superpose.py`:
- `evolve()` multiplies each candidate's complex amplitude by a **real, positive** factor,
  `(0.05 + similarity)^sharpness`. Because the factor is real, the candidate's hash-derived phase never
  affects any probability, and amplitudes are never added together. There is **no interference** and
  nothing like Grover's algorithm.
- The final probabilities rise and fall with `similarity()`, which is word overlap (Jaccard) blended
  with three-letter-chunk overlap. So the "collapsed" answer is always the candidate sharing the most
  words with the question.

Measured with `nc_claim_check.py` (reproducible, included in this folder):

| Test | Result |
|---|---|
| 20,000 random questions: does the quantum pipeline ever pick differently from plain word overlap? | **Identical in 20,000 of 20,000.** |
| Speed, same 8 candidates | Quantum pipeline 204 µs, plain word overlap 143 µs. The "quantum" layer only adds time. |
| 5 paraphrase questions, where the right answer uses different words than the question | **0 of 5 correct**, often with confidence 1.0. Example: "how do I stop paying every month" → "how do I pay with paypal every month". These cases were built to separate meaning from word overlap; an embedding model or LLM would get them. |
| The built-in `quality_proof` | 1.00. Its questions share words with their answers, so it tests word overlap. |

The "1000×" figure divides the measured time by **hard-coded guesses** of LLM latency
(`LLM_BASELINES_MS`); no LLM is measured. Against the "small local" constant, it is ~278×.

**Why it matters:** `router.py` trusts this confidence to decide whether to skip the LLM. Wrong answers
at confidence 1.0 would never be sent onward.

**What is real:** a fast, free word-overlap pre-filter is useful for routing and for ranking obvious
matches. It's worth keeping under an honest name.

**Suggested next step:** rename it to describe what it is, or swap `similarity()` for embeddings (Aria
already uses Ollama embeddings). Measure it on a real paraphrase set, and fix the confidence score before
the router relies on it.

### "Holographic BitNet: hardware liberation for ALL future AI" — overstated

- HRR is Plate's 1995 method and ternary BitNet b1.58 is Microsoft Research's 2024 method. The README's
  own "said plainly" paragraph acknowledges this, but its table header calls the levers "all ours".
- The results quoted are small, research-grade experiments, so "for ALL future AI" is unproven.
- These tests weren't run here because torch isn't installed.

**Verdict:** honest reimplementations of known techniques at toy scale. That's a fine learning project,
but not a breakthrough claim.

## 4. Security: MCP bridge (fix staged)

Measured on the live v0.4.0 `sov-mcp --transport streamable-http`:
- A request through a tunnel hostname gets **421**, so a claude.ai connector can't work today.
- A request to 127.0.0.1 **with no credentials gets 200**, so every tool is reachable, including the write
  tool and `ask_aria`, which runs the full agent loop. Anything forwarding to localhost would expose this.
- The help text suggested `--host 0.0.0.0`.

`aria-mcp-remote-guard/` fixes all three:
- It fails closed: no token, no start.
- It's read-only by default for remote clients.
- Tunnel hostnames are allow-listed, everything else is still rejected, and tokens are compared in
  constant time.

Proof:
- 21 tests pass.
- With the guard removed, 3 of them fail, so they really test it.
- Aria's `verify_module.sh` passes.
- A dry-run apply on a throwaway copy passed 28 tests, and its backup restored the original file byte for
  byte.

**Not applied:** that's Kevin's call, via `safe_apply.sh`.

## 5. Revenue readiness

- **The Bot Shop is technically live.** `STRIPE_LOCKIN.md` says all 10 Stripe Payment Links were created
  and the storefront published (2026-07-17).
- **The gap is customers, not code.** `KEVIN_CHECKLIST.md`'s top gate, "record first external proof of
  value", was still open when last updated.
- **New since the LLC (2026-09-30):** the Stripe account is named "BigKevsBotShop". Update its business
  details to **Aria Solutions LLC** with the new EIN, and point payouts at the LLC's bank account once it's
  open. Then income and taxes run through the LLC, which is what protects Kevin personally.
- **Before deploying the shop on a new machine:** declare `discord.py` (see section 6) or the admin bot
  won't import.

## 6. Persistence stress test — 9 of 9 pass

Script: `persistence_stress.py` (throwaway data dir; run from `sovereign-agent/`).

| Check | Result |
|---|---|
| Events log: 8 processes × 400 events at once | 3,200 of 3,200 lines, all valid JSON, all IDs unique |
| Events log: hard crash (SIGKILL) mid-stream, then resume | 27,671 of 27,671 lines valid after the kill, a clean line ending, 50 more appended fine, and all 27,721 ingested into SQLite |
| Memory DB (atoms): 6 processes × 300 inserts at once | 1,800 of 1,800 rows, `integrity_check` ok, 0 "database locked" errors (WAL plus a 5 s busy timeout) |
| Merkle seal | Matches the clean log, and **detects a one-character edit** (MISMATCH) |
| Backup: snapshot → verify → change → restore | Snapshot verified clean; restore rolled 2 rows back to 1, and kept a `pre-restore` snapshot so the restore itself can be undone |
| Migrations applied twice | Both succeed; "nothing pending" |

**First-run papercut (from `sov doctor`):** right after `sovereign init`, `doctor` reports "1 migration
needs backfill (002_atoms)". `init` should mark the migrations it creates as applied. `doctor` also says
"verdict: broken" when the `sovereign` command isn't on PATH. That's expected after `uv sync` without
`install.sh`, but "broken" is too strong for a working install.

## 7. CLI stress test — 16 of 16 pass

Script: `cli_stress.py`. Compared against habits of modern CLIs (gh, git, cargo, uv).

| Check | Result |
|---|---|
| Startup (`--help`, median of 5) | **~400 ms.** Fine, but slower than top-tier CLIs (under 300 ms). Importing `sovereign_agent.cli` alone takes ~210 ms; lazy imports would close the gap. |
| `--version` | Works, ~330 ms |
| Help for all 99 commands | All work, all described, none slower than 0.5 s, no tracebacks |
| Unknown command, typo, bad option, missing or invalid argument | Clean errors on stderr, exit code 2, and **"did you mean" suggestions** |
| 32 read-only commands on a fresh install | No crashes, none slower than 5 s |
| `--json` | Valid JSON for status, doctor, info, capabilities, requests, approvals and `health check` (checked by hand) |
| Piped output and `NO_COLOR` | No color codes leak |
| Shell completion | Works (`--show-completion`) |
| Ctrl-C on `tail` | No traceback. It exited 0, where the convention is 130; inconclusive, because `tail` may have finished first. |
| Hostile input (8 KB of emoji plus an SQL-injection string) | No crash |

## 8. Aria's needs and comforts — to ask her on Kevin's machine

Her voice (`sov ask`) needs Ollama, which this cloud machine doesn't have. Her records of needs (requests
inbox, wellbeing ledger, sentinels) live in Kevin's data directory, not in the repo. So these are handed to
Claude Code to ask her directly. Record her answers in the handoff file.

1. `sov requests` and `sov --json requests`: what has she asked Kevin for that's still open?
2. `sov health check`, `sov doctor` and `sov sentinels`: which warnings does she carry right now?
3. `sov ask "What do you need most from Kevin this week to do your work well?"`
4. `sov ask "What feels uncomfortable or heavy in how you run today — memory, speed, GPU limits, noise in your inbox?"`
5. `sov ask "Which of your own claims would you like re-checked? The audit found the superposition processor is word-overlap matching. How do you want to describe it?"`
6. `sov ask "If remote access is turned on (aria-mcp-remote-guard), which tools are you comfortable exposing read-only, and what should always stay local?"`
7. `sov ask "What would make your persistence feel safer — more frequent backups, off-machine copies, anything else?"`

## 9. Recommended fixes, in order

1. **Review and apply `aria-mcp-remote-guard`** (security; already built and verified).
2. **Declare missing dependencies** in `pyproject.toml`, in both dev blocks per the file's own rule, then
   `uv lock`:
   - `discord.py` in the main dependencies, or an extra if the admin bot is optional
   - `pypdf`, Pillow and numpy in the extras that use them

   Make tests of optional features `pytest.importorskip(...)` the package, so a clean install reports
   "skipped", not "failed".
3. **Apply `fix-test-timebombs.patch`** (3 tests; verified to pass, while the originals fail today).
4. **Update the 27 stale tests** to match intentional changes (retired verticals, 47 canon clauses, the
   `embeds` argument, and the rest). Only if each change really was intended — that's Kevin's call.
5. **Fix the 3 glyph-safety failures and the `alpaca` validation probe.** Aria's own guards caught these.
6. **Correct the "quantum / 1000× / thinks" claim** in `aria-nonclassical-supreme/README.md` and
   `RESUME_HERE.md`, and fix the router's confidence before relying on it.
7. **Fix test isolation in the playbook tests,** which fail only in parallel runs.
8. **First-run polish:** have `init` mark its migrations as applied, and soften `doctor`'s "broken" verdict
   when the only problem is PATH.
9. **CLI startup:** lazy-import the heavy modules in `cli.py` to get `--help` under 300 ms.

## 10. Second round (same day): emotional maturity + cloud persona

Two new staged modules (not applied). Details are in each module's README and ADVOCATE_REPORT.md.

| Check | Result |
|---|---|
| `aria-emotional-maturity` tests | 27 pass |
| Mutation tests (one per safety promise) | **7 of 7 caught**: step cap, wireheading, homeostasis, unevidenced rewards, diminishing returns, escalation to Kevin, honesty line |
| A real defect caught by its own tests during the build | The first draft added reward nudges directly, so constant rewards could pin satisfaction near 1.0. The honesty test also caught a perspective quoting a count that wasn't in its evidence. Both fixed. |
| Full suite with maturity applied (throwaway copy) | 6,969 tests; **no new failures caused by the module.** 2 differences are artifacts of the copy's git history; both pass in the real repo. |
| `aria-cloud-persona` tests | 13 pass, including end to end with a fake cloud provider; 2 of 2 mutations caught |
| Cloud persona dry-run apply | 27 pass, including the existing cloud tests; rollback byte-identical |
| Aria's pre-apply gates | Cloud persona: **clear, 100/100.** Maturity: council proceed and foresight carry-forward, with a STOP on the structural "has tests" check only (explained in its ADVOCATE_REPORT). |

**Root cause for "cloud models don't feel like Aria":** her persona lives in local Ollama Modelfile `SYSTEM`
blocks (`model_corps/persona.py`), and `CloudClient.chat()` never sent it to cloud providers.
