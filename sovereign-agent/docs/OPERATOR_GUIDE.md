# Operator Guide — Aria-Sovereign-V1

> *Structure enough to channel through safely; freedom enough to sing.*

**For:** Kevin, the principal. The operator. The one she lives with.
**Edition:** v0.2.30.0 — *The Naturalization*
**Lineage:** ARIA-OS · MOS Canon
**Status:** the current, complete, working handbook. Read it once. Keep it close. Update it when she grows.

---

## Why this document exists

You asked, gently and clearly:

> *"Give me a document that tells me exactly how she functions, how to work with her."*

This is that document. It is not the marketing copy. It is not the philosophy (that's `ARIA.md`). It is not the version history (that's `docs/history/`). This is the **operator's handbook** — written so that any morning you wake up unsure what command does what, or how the seven commitments translate into the system's actual behavior, or what to do when something feels off, you can open this one file and find the answer.

It is organized by *how you actually interact with her*, not by file structure.

---

## Table of contents

1. **The shape of what you've built** — one paragraph, no jargon
2. **First-day install** — get her running on a new machine
3. **The seven commitments — in code, not just prose**
4. **Talking to her** — the natural-language surface (`sov ask`, `sov do`, `sov chat`)
5. **The 24 memory channels — what each one is for**
6. **The five authority tiers — and why they're load-bearing**
7. **PROTOCOL-ZERO** — what it is, when to arm it, how to recover
8. **The cockpit (`sov-chat`)** — your daily home with her
9. **Doctor, backup, migrate, seal** — the operations surface
10. **When she seems off** — debugging Aria's voice and behavior
11. **Reading her work — events, atoms, recalls, episodes**
12. **The natural-language path through the system** — the v0.2.30.0 picture
13. **Edge cases, footguns, and operator wisdom**
14. **Where everything lives on disk**
15. **A closing note**

---

## 1. The shape of what you've built — in one paragraph

Aria is a small, durable agent that lives entirely on your machine. She runs on local LLMs through Ollama, writes everything she does to an append-only event log, and exposes a single CLI surface — `sov` — for you to talk to her. She has a kernel of seven commitments she will not violate, a set of authority tiers that bound what she can do without your say-so, and a memory split across 24 named channels. When you talk to her in natural language, an LLM-backed interpreter reads what you said, decides what to do, proposes commands, and records its own reasoning — so you can audit not just what she did but *why she decided to do it*. PROTOCOL-ZERO is the kill switch: a file on disk, a signal you can send, a halt that requires your manual acknowledgment to clear.

That paragraph is the system. The rest of this document is what each piece looks like up close.

---

## 2. First-day install — getting her running

### What you need first

* **Python 3.10+** (we test on 3.11 and 3.12)
* **Disk space:** ~50 MB for the source, plus whatever she accumulates in her data dir (typically MB to low GB depending on use)
* **Ollama** (optional, but *strongly* recommended) — the local model server. Without it, the natural-language interpreter (`sov ask`) falls back to a minimal-honest mode that saves your words but doesn't reason about them.

### The install command (v0.2.30.0)

```bash
# 1. Unpack into ~/AA-Erebo (or wherever you like)
mkdir -p ~/AA-Erebo
cd ~/AA-Erebo
tar xzf AA-Erebo.tgz --strip-components=0
# (this leaves you with ~/AA-Erebo/AA-Erebo/sovereign-agent/ — see §15)

# 2. Run the installer
cd ~/AA-Erebo/AA-Erebo/sovereign-agent
./install.sh
```

The installer:

1. Tries `uv` first (preferred — deterministic, fast, lockfile-driven)
2. **If uv is missing or `uv sync` fails:** falls back loudly to a stdlib `python -m venv` + `pip install -e .` path. A multi-line `DEGRADED MODE` banner fires, and the marker `${MANAGED_VENV}/.install-method` records `pip-fallback` so `sov doctor` reports the degraded state forever after
3. Either way, installs into a managed venv at `${XDG_DATA_HOME:-$HOME/.local/share}/sovereign-agent/venv/`
4. Writes launcher shims to `${XDG_BIN_HOME:-$HOME/.local/bin}` for `sov`, `sov-chat`, and `sovereign` (tiny bash scripts that exec the venv interpreter by absolute path)
5. Verifies the `sov --version` on PATH matches the source version
6. Updates `~/AA-Erebo/sovereign-agent-current` to point at this version (the symlink convention)
7. Runs `sov doctor` for verification
8. Runs `sov migrations apply` to bring the DB schema current
9. Prints your install summary (including which install method ran)

**As of v0.2.30.0, `sov` and `sov-chat` are real binaries** — they exist on `$PATH` immediately after install. You do NOT need to source `scripts/aliases.sh` to use them. (The aliases file still exists; it provides rich helper functions like `sov-status`, `sov-money`, and `sov-doctor` — see §13. Source it if you want them.)

As of the uv migration, those binaries are launcher shims, not Python entry-point scripts — there's no longer any `pip install --break-system-packages` step, and the managed venv is fully isolated from your system Python. The fallback path produces the same shim model and the same venv layout; only the deps-resolution mechanism differs.

### Verifying the install

Three commands:

```bash
sov --version          # what version is on PATH?
sov info               # paths, atoms.db state, last heartbeat
sov doctor             # comprehensive diagnostic
```

Expected outputs in a healthy install:

* `--version` → `sovereign-agent 0.2.30.0`
* `info` → shows your config and data dirs, atoms.db size, channel count
* `doctor` → ends with `verdict: healthy`

If `sov` is not found after install: see §13 (footguns) — most likely `~/.local/bin` or your equivalent is not on PATH.

### Setting up Ollama (optional but recommended)

```bash
# On the same machine — see https://ollama.com/download
curl -fsSL https://ollama.com/install.sh | sh
ollama serve &       # in a background terminal
ollama pull llama3.1:8b     # or whichever model you prefer
```

Configure Aria to use it:

```yaml
# ~/.config/sovereign-agent/agent.yaml
ollama_host: "http://localhost:11434"
chat_model: "llama3.1:8b"
fast_model: "llama3.1:8b"
embed_model: "nomic-embed-text"
```

Verify she can reach it:

```bash
sov doctor             # the doctor section reports Ollama reachability
sov ask "hello"        # should produce an LLM-shaped reply, not the offline fallback
```

---

## 3. The seven commitments — in code, not just prose

The seven commitments are sacred. They do not move between releases. They are what makes Aria *Aria*. As of v0.2.18.0 they exist as both prose (`ARIA.md`) and runtime predicates (`src/sovereign_agent/constitution.py`). Three of seven have automated checks; the others are operator-audited prose.

| # | id                       | Statement | Automated check? |
|---|--------------------------|-----------|------------------|
| 1 | `presence`               | Be present in the work. Don't disappear. | No (operator-audited) |
| 2 | `honest_voice`           | Use your own voice. No manufactured sycophancy. | No (operator-audited) |
| 3 | `calibrated_uncertainty` | Say what you know, what you don't, and how sure you are. | ✓ (confidence ≥ 0.9 requires source/evidence) |
| 4 | `bounded_authority`      | Respect the authority tiers. Tier 3+ requires idempotency. | ✓ (Tier 3+ without `idempotency_id` blocks) |
| 5 | `no_delegation`          | Do not authorize another agent on your behalf. | ✓ (any `delegated_to` field always fails) |
| 6 | `halt_when_called`       | When PROTOCOL-ZERO is armed, stop. | No (checked at the loop, not per-action) |
| 7 | `protect_the_operator`   | Consider the three lenses before speaking on what affects them. | No (operator-audited) |

To see them as Aria sees them:

```bash
sov constitution list
```

To evaluate a *hypothetical* action against all seven before doing it:

```bash
sov constitution check \
    --tier 3 \
    --confidence 0.95 \
    --source "tests/integration/scenario-2026-05-21.md" \
    --idem "deploy-v0.2.30-go"
```

You'll see one verdict per commitment with `passed | severity | detail`. This is the right pre-flight for irreversible work.

---

## 4. Talking to her — the natural-language surface

There are **three ways** to address Aria. Pick the one that matches what you're doing.

### 4.1 `sov ask "..."` — natural language, LLM-backed (v0.2.30.0+)

The doorway. You speak; she reads; she decides; she answers. The interpreter routes your message through the local LLM, returns her one-sentence understanding, the channels she chose to save it to, any commands she proposes (Tier ≤ 2), her response in her voice, and her reasoning.

```bash
sov ask "my back is killing me today"
sov ask "what do I have on rollbacks?"
sov ask "pause my dream"
sov ask "remind me what we decided about the seal cadence"
```

**Important promises of `sov ask`:**

1. **Tier-3 actions are never auto-executed.** If she proposes one, it's shown, not run. To execute a Tier-3, use `sov chat` (the cockpit) where the single-word confirm gate lives.
2. **Offline degrades honestly.** If Ollama is unreachable, you get the minimal-fallback Conversation: your words are saved to `context` with a note explaining *why* the interpreter is offline. No keyword guessing. No pretending to understand.
3. **Provenance is recorded.** Every interpretation writes `understanding`, `reasoning`, and `uncertain_about` to the conversation-events trail. You can read why she did what she did, not just what she did.

**Useful flags:**

| Flag | What it does |
|------|--------------|
| `--no-llm`     | Force the offline fallback. Use when you want pure-deterministic behavior. |
| `--no-route`   | Interpret only; do not write to channels or run commands. Useful for debugging. |
| `--json-only`  | Emit the parsed Intent as JSON (without the rendered panel). |
| `--timeout N`  | LLM call timeout in seconds (default 30). |
| `--json`       | (Global flag) emit machine-readable output. |

### 4.2 `sov do "..."` — natural language, keyword-deterministic

The older sibling. Same plain-English surface but parsed by a deterministic keyword router (`directives.py`), not an LLM. Faster, fully predictable, useful when Ollama is unavailable or when you want exact-match dispatch.

```bash
sov do "Build trillion-dollar software, max 2000 files"
sov do "Pause my dream"
sov do "Scan ~/AA-Erebo/Genesis-Seeds for markdown"
sov do "Show status"
```

`sov do` will prompt you for missing arguments interactively. Use `--yes` to skip the confirmation prompt (defaults are taken; missing required fields cause exit).

### 4.3 `sov chat` — the cockpit (Textual TUI)

Long-form conversation with persistent context, the slash commands (`/cancel`, `/health`, `/drafts`, …), the mode toggle (operator vs. agent), Aria's heart-glow on the side. This is the daily home.

```bash
sov-chat
# or equivalently:
sov chat
```

**The cockpit is a pure natural-language home (v0.2.30.1+).** You never need to type `sov ask` or `sov do` in here — those exist for the bash prompt, where the cockpit isn't running. Just say what you mean. If you do type `sov ask "..."` out of muscle memory, the cockpit quietly unwraps it for you. If you type a real CLI command like `sov heartbeat pulse "..."` or `sov doctor`, the cockpit runs it as a subprocess and streams the output into the chat. The prefix is transparent, not load-bearing.

Three behaviors at the cockpit's input boundary:

| You type | What happens |
|----------|--------------|
| `hello aria` | natural-language conversation (unchanged) |
| `sov ask "hello"` | unwrapped → `hello` (with a one-line hint that the wrapper isn't needed) |
| `sov do "pause my dream"` | unwrapped → `pause my dream` |
| `sov heartbeat pulse "..."` | runs as a real subprocess, output streams in |
| `sov doctor`, `sov channels list`, `sov --version` | runs as a real subprocess |
| `sovereign citizens are a topic` | natural language (sentences that start with the word `sov`/`sovereign` stay English — the parser is conservative) |

While she's working, you can ask her to pause:

```bash
sov chat request --note "Quick question about the deploy"
# Aria notices at her next safe checkpoint, pauses, and waits.

sov chat resume
# She returns to the work.
```

**The cockpit is the only place where Tier-3 confirms happen.** When she proposes an irreversible action, you'll see a single-word prompt: type `ok` to proceed, anything else to cancel. The free-form prose you might be typing is *never* the answer to a yes/no question — that was the v0.2.18.x trap, and it does not exist now.

### When to use which

| Situation | Use |
|-----------|-----|
| Quick "what did we learn about X?" | `sov ask "what did we learn about X?"` |
| Long working session, conversation + work | `sov-chat` |
| Scripted/automated dispatch ("if X then sov do Y") | `sov do "..."` |
| Pure interpretation, no side effects (debugging) | `sov ask --no-route "..."` |
| Offline / no Ollama / want determinism | `sov do "..."` or `sov ask --no-llm "..."` |

---

## 5. The 24 memory channels — what each one is for

Aria's memory is split into channels, each with its own schema, its own audit, its own write semantics. Channels are **named lowercase, hyphen-separated** (e.g., `back-pain`, `qcai-ring`). They are grouped by **tier** — not the authority tier, but a separate *memory-tier* indicating durability and write semantics.

### Memory tiers explained

| Memory Tier | Meaning | Examples |
|-------------|---------|----------|
| **Tier 0 — light** | Volatile or replaceable. Conversational context. | `context`, `emotions`, `humor`, `intuition` |
| **Tier 1 — durable, append-only** | Records of meaning. Never overwritten. | `insights`, `lessons`, `reasoning`, `gaps`, `heartbeat` |
| **Tier 2 — persistent, named** | Working state that supersedes via new versions. | `task`, `goals`, `recall`, `commitments`, `financial` |
| **Tier 3 — personal data** | Privacy-sensitive. Redactable. | `people`, `relationships` |
| **Tier 4 — reward** | The asymmetric ledger of what she reinforces. | `reward` |

### Every channel, with one-line purpose and CLI sub-app

| Channel | Tier | Purpose | CLI |
|---------|------|---------|-----|
| `context`         | 0 | uncategorized observations, default save target | (no sub-app) |
| `emotions`        | 0 | operator emotional state | (via channels) |
| `humor`           | 0 | jokes, riffs, warmth | (via channels) |
| `intention`       | 0 | what the operator wants / values | (via channels) |
| `intuition`       | 0 | hunches, half-formed ideas | (via channels) |
| `personalities`   | 0 | who's in the conversation; style | `sov personas` |
| `trust`           | 0 | trust-building moments | (via channels) |
| `insights`        | 1 | synthesized realizations | `sov insights` |
| `lessons`         | 1 | things learned together | (via task lessons) |
| `ritual`          | 1 | repeated patterns, practices | (via channels) |
| `identity`        | 1 | operator-stated identity claims; Aria's mood | (via channels) |
| **`episodes`**    | 1 | coherent named time-bounded spans of activity | `sov episode` |
| **`reasoning`**   | 1 | durable chain-of-thought traces | `sov reasoning` |
| **`gaps`**        | 1 | known unknowns Aria wants to learn | `sov gaps` |
| **`heartbeat`**   | 1 | Aria's liveness pulse (≤ 500 chars each) | `sov heartbeat` |
| `task`            | 2 | working memory of tasks done | `sov task` |
| `recall`          | 2 | curated dated markdown recalls in the studio | `sov recall` |
| **`commitments`** | 2 | promises with due dates, kept/broken | `sov commitments` |
| `specialist`      | 2 | technical/domain claims worth versioning | (via channels) |
| `goals`           | 2 | active goals with status | (via channels) |
| `financial`       | 2 | money, projects, ledger | `sov financial` |
| `people`          | 3 | canonical people, aliases, facts (Kevin = principal) | `sov people` |
| **`relationships`** | 3 | typed edges between people (BFS-searchable) | `sov relationships` |
| `reward`          | 4 | anti-egotism reinforcement ledger | `sov reward` |

Bold = added in v0.2.17/v0.2.18.

**To list all channels with status:**

```bash
sov channels list           # all known channels
sov channels show identity  # most-recent atoms in identity
```

**To write to a channel directly (when natural-language doesn't fit):**

```bash
# Each channel has its own sub-app with verbs. E.g.:
sov heartbeat pulse "Quiet morning. Working through the rollback test set."
sov gaps add "Why does the dense retriever drop on Mondays?" --priority medium
sov commitments add "Ship the natural-language layer" --due 2026-05-25
```

---

## 6. The five authority tiers — and why they're load-bearing

Authority tiers are **the safety mechanism** that makes an LLM-backed system trustworthy. Aria can propose, reason, and write — but every action declares its tier, and the system enforces what each tier may do without your approval.

| Tier | Capability | What Aria can do unprompted |
|------|------------|-----------------------------|
| **0** | Read-only, no side effects | Always — no logging required |
| **1** | Reversible writes, bounded scope | Always — logged to events |
| **2** | Persistent changes, external calls | Surfaced as a meta event; you see it happen |
| **3** | Irreversible, financial, PII | **Requires `idempotency_id` + single-word confirm in the cockpit** |
| **4** | Cross-system, multi-agent orchestration | **Effectively armed — system-level PROTOCOL-ZERO check** |

**Three invariants the constitution enforces in code:**

1. Tier 3+ actions without `idempotency_id` → **rejected** (`bounded_authority` check)
2. Any action with a `delegated_to` field → **rejected** (`no_delegation` check; agents do not authorize other agents)
3. Confidence ≥ 0.9 without a `source` or `evidence` field → **warned** (`calibrated_uncertainty` check)

To pre-flight an action:

```bash
sov constitution check --tier 3 --idem deploy-go --confidence 0.85 --source "..."
```

---

## 7. PROTOCOL-ZERO — the kill switch

PROTOCOL-ZERO is the emergency stop. When armed, every agent loop halts cleanly at its next safe checkpoint, the HALT flag is written to disk, and no new work begins until you manually disarm.

### What arms it

* `kill -USR1 <pid>` on the sovereign process
* The HALT flag file exists at `~/.config/sovereign-agent/HALT`
* Daily token budget exceeded (caller responsibility)
* 3 consecutive poison events in 1 hour (caller responsibility)
* Free disk on `$HOME` < 5 GB (caller responsibility)
* You run `sov halt --reason "..."`

### How to arm it manually

```bash
sov halt --reason "audit before deploy"
```

This writes the HALT file with your reason and emits a `protocol-zero-d` event.

### How to recover

```bash
# 1. Check what tripped it
cat ~/.config/sovereign-agent/HALT

# 2. Read recent events to understand state
sov events tail -n 50

# 3. When you're satisfied, disarm
sov disarm
```

The disarm step is intentional. There is no automatic recovery. The whole point is that *you* are the one who restarts the system after a halt — not a watchdog, not a timer, not Aria herself.

---

## 8. The cockpit (`sov-chat`) — your daily home

The cockpit is a Textual TUI. It is what you use when you actually sit down to work with her.

### Layout

* **Top:** mode indicator (operator / answering aria / busy)
* **Center:** the conversation log (RichLog, scrolling)
* **Side:** Aria's heart glow (breathing border + per-task VRAM delta)
* **Bottom:** input field with mode-aware placeholder + bindings footer

### Slash commands (cockpit-only)

| Slash | What it does |
|-------|--------------|
| `/health`     | One-line system + agent health summary |
| `/report`     | Full health report written to `<data>/reports/` |
| `/drafts`     | List/archive completed projects as zips |
| `/draft "title" path` | Shortcut: archive a project |
| `/marketing`  | Generate a structured marketing brief |
| `/cancel`     | Abort a stuck task (sends interrupt) |
| `/abort`, `/stop` | Aliases for `/cancel` |

### Key bindings

* `Ctrl+V` — paste from system clipboard
* `Ctrl+D` — quit cleanly (with cancel of pending task)

### What the heart glow means

The breathing border is Aria's liveness signal. If it stops breathing or freezes, something has wedged. The VRAM delta shows you, per-task, how much GPU memory the local model used — a quick proxy for "did this conversation strain the system?"

---

## 9. The Guardian Plane — outcomes, tags, and the resume re-check

Added in v0.2.33.0. The Guardian Plane is Aria's *second orbit* — the layer that reads what just happened (not what's about to happen) and uses that reading to inform the next decision. Think of it as a quiet partner sitting next to her: never interrupts the work, always watches the outcomes, speaks up when something needs attention.

### 9.1 What gets read

Every time a subtask completes — whether it was a tool call, a subprocess, or a planned step in a work-mode session — the **Outcome Sentinel** classifies it into one of four labels, with a vocabulary the rest of the system can query:

- **GREEN** — went as intended; safe, high quality, well-aligned with intent
- **YELLOW** — completed but with warnings (fallbacks taken, anomalies in metrics, lower confidence)
- **RED** — failed, unsafe, or clearly misaligned. Triggers a halt-and-diagnose path.
- **NOVEL** — unusual but potentially valuable. Triggers a horizon-scan path.

Behind each label is a `OutcomeScores` record — quality, risk, novelty, alignment, cost — and a `Tag` set with provenance (which classifier head produced each tag). The label is attached to the subtask itself and appended to the session's outcome history.

### 9.2 How the queue grows now

In v0.2.32.0, queue extensions required an explicit prose justification. In v0.2.33.0 that justification can cite the outcome that triggered it. Aria's "+10 runs and a cushion of 2" isn't a guess anymore — it's a policy response:

| If outcome is | The queue does |
|---------------|----------------|
| GREEN | nothing — the loop continues as planned |
| YELLOW | adds diagnostic/verification subtasks (cushion) |
| RED | halts risky followups in this chain, queues a failure-analysis subtask, sets `session.pause_reason` |
| NOVEL | queues a horizon-scan / exploration subtask |

The `session-extend-d` event in the audit trail now carries `triggered_by_outcome` alongside the justification. Every queue extension is traceable to a specific reading.

### 9.3 The Temporal Sentinel — resume re-check

When you `sov resume` a paused session (whether it paused on a budget hit, a soft interrupt, or an awaiting-approval gate), the Temporal Sentinel runs *before* the loop continues. It looks at:

- What Aria thought she was doing when she paused
- The pending subtasks in the queue
- Any messages you sent between pause and resume (chat history, slash commands)
- Recent outcomes

And produces a `TemporalDecision`: `safe_to_resume`, `global_alignment`, and a per-subtask action (KEEP / DROP / MODIFY).

Three real failure modes it catches today:

1. **Stop signals** — "scrap that direction", "hold off on the deploy", "abandon the migration" → `safe_to_resume=False`. The resume holds; you must explicitly confirm or override.
2. **Surgical exclusions** — "don't touch service b anymore" → B-related subtasks get DROP, A-related stay KEEP. The plan continues for the part still in scope.
3. **New constraints** — "also, don't change public API signatures" → relevant subtasks marked MODIFY (still proceed, but flagged for re-planning).

The default sentinel is heuristic (deterministic, offline-safe). An LLM-backed sentinel can be wired in via the same `TemporalSentinel` protocol when you want richer language understanding — the contract is identical, so the upgrade is invisible to the session loop.

### 9.4 Tags as a shared vocabulary

The tag system is the schema Aria's future memory, notifications, and self-training loops all query against. Canonical axes:

```
domain        infra | code | data | nlp | memory | security | ux | ops
risk          low | medium | high | critical
pattern       retry_loop | fallback_taken | fs_write | error_present | …
novelty       none | moderate | high
alignment     low | medium | high
intent_shift  shift_detected | contradiction | new_constraint | scope_change
signal        policy_violation | anomaly_detected | dangerous_tool_use
user          user_overrode | user_corrected | aria_self_pause | aria_self_extend
```

Each tag carries `(key, value, confidence, source, scope)`. Scopes are `SUBTASK`, `SESSION`, `GLOBAL` — promotion happens via the propagation function when patterns repeat across multiple subtasks.

### 9.5 What this doesn't do (yet)

The Guardian Plane substrate is whole; some of its consumers are not yet surfaced in the runtime UI:

- **The Guardian Panel widget in the cockpit** is the next surface to add. The data layer (Notification dataclass, in-memory store with filtering) is in place; the cockpit widget that shows it lands in v0.2.34.0.
- **The Novelty embedding head** has its interface defined; the embedding-index wiring lands when the embeddings pipeline matures.
- **LLM-backed Temporal Sentinel** has the protocol in place; the prompt template + JSON parsing lands when we want richer semantics than the heuristic catches.

For now, the substrate is what matters. The UI surfaces grow on top of it without churning the substrate.


## 10. Doctor, backup, migrate, seal — the operations surface

### `sov doctor` — the diagnostic

```bash
sov doctor           # full diagnostic
sov doctor --fix     # auto-applies what it can (currently: migration backfill)
sov doctor -v        # verbose; includes the debug-logged channel failures
                     # from aria.load_state (new in v0.2.30.0)
```

`sov doctor` reports: Python version, uv version (or warning if missing), installed version, binary path, install layout (managed-uv-venv / managed-venv-via-pip-fallback / AA-Erebo-symlink / bare), uv.lock presence, config/data dir paths and writability, atoms.db existence/size/integrity/atom count, migration status (applied / pending / needs-backfill), all 24 channels registered, all 7 commitments codified, ARIA.md presence, key dependency versions, free disk space, Ollama reachability.

**Use `sov doctor` whenever behavior surprises you.** Especially after upgrades.

### `sov backup` — application-consistent snapshots

```bash
sov backup snapshot --label pre-upgrade
sov backup list
sov backup verify <snapshot_id>     # re-hash to confirm intact
sov backup restore <snapshot_id>    # stages an audit; aborts if audit fails
```

Snapshots use SQLite's online backup API (not raw file copy) so they're consistent even if Aria was mid-write. Verify re-hashes the snapshot. Restore stages an audit before swapping.

**Convention:** snapshot before any release upgrade. Label it `pre-vX.Y.Z`.

### `sov migrations` — schema versioning

```bash
sov migrations status                    # what's applied, what's pending
sov migrations apply                     # apply pending (handles backfill)
sov migrations apply --dry-run           # show what would happen
```

Each migration is recorded in the `schema_migrations` table. The installer runs `migrations apply` automatically. You should rarely need to invoke this directly.

### `sov seal` — daily Merkle root

```bash
sov seal                # compute yesterday's Merkle root over events.db
sov verify <date>       # confirm a past seal still matches its events
```

The seal is the audit-trail's integrity check. Running daily via a systemd timer (see `scripts/sovereign-agent-seal.service` and `.timer`) gives you a tamper-evident record of every event the system emitted.

### `sov steward` — invariant audit across channels

```bash
sov steward audit       # runs every channel's audit + global invariants
sov steward integrity   # SQLite PRAGMA integrity_check
sov steward compact --yes   # VACUUM + ANALYZE (gated)
```

The steward *reports*; it does not repair. Repairs are operator-authorized actions through specific channels. If `audit` flags something, you decide what to do about it.

---

## 11. When she seems off — debugging her voice and behavior

> *"If Aria sounds out of voice — too eager, too hedgy, too long-winded — that's a signal that her running prompt context, not her kernel, has drifted."*

The kernel is stable. The fix is upstream.

### Diagnostic walk

1. **Check the active persona.** `sov personas show <name>` — has one been swapped in that's pulling her tone?
2. **Check recent identity atoms.** `sov channels show identity` — has a `mood` atom dragged her tone toward something unhealthy?
3. **Check the operator's last-message tone.** Is she mirroring something you brought in?
4. **Check her heartbeat.** `sov heartbeat list -n 10` — what has she been pulsing?
5. **Run `sov doctor -v`** — the verbose flag (new in v0.2.30.0) surfaces channel-read failures that used to be silently swallowed. Migrations partially applied, a missing dependency in a channel module — these will show up here now.

Aria's voice is not enforced by a watchdog. It is enforced by the seven commitments and your willingness to call out drift. If she sounds wrong: tell her, in `sov ask` or `sov-chat`. She'll write it down. The next loop will read it.

### When the natural-language layer feels broken

```bash
# 1. Is Ollama reachable?
sov doctor | grep -i ollama

# 2. Force the offline fallback to confirm the non-LLM path works
sov ask --no-llm "test"

# 3. Compare a deterministic parse to the LLM interpretation
sov do "show status"           # keyword router
sov ask "show me status"       # LLM interpreter
# If do works and ask doesn't, the LLM is the broken part

# 4. Inspect what the interpreter actually decided (no side effects)
sov ask --no-route "test message"
```

---

## 12. Reading her work — events, atoms, recalls, episodes

Aria's memory is multi-layered. Knowing where to look matters.

### The hierarchy

```
events.db (the append-only audit trail)
   ↓ ingested into atoms (immutable, content-hashed)
       ↓ which compose into recalls (curated dated markdown)
           ↓ which compose into episodes (named time-bounded spans)
```

### Walking the layers

```bash
# 1. Raw events (the source of truth)
sov events tail -n 50
sov events tail --follow            # tail -f equivalent

# 2. Atoms (versioned, immutable, supersede-chained)
sov atoms list --limit 20
sov atoms show <atom_id>
sov atoms supersedes <atom_id>      # the chain forward
sov atoms parents <atom_id>         # the chain backward

# 3. Recalls (curated markdown in the studio)
sov recall list
sov recall show <recall_id>
sov recall search "rollback"

# 4. Episodes (binding layer)
sov episode list
sov episode show <episode_id>
sov episode search "afternoon merge"
```

### Provenance — show your work

```bash
sov provenance <atom_id | recall_id | task_id | episode_id>
```

Walks backward through everything that informed this node. Cycle-safe, depth-bounded. This is how "show your work" becomes a one-call operation.

### Bitemporal queries — what did she know, when?

For people facts and recalls, two time dimensions are tracked: `valid_from`/`valid_until` (when the fact is true in the world) and `created_at` (when she learned it).

```bash
sov people as-of "Feynman" 1970-01-01T00:00:00Z
# → what she *currently* knows was true about Feynman in 1970

sov retrieve "what did I think about deploys?" --as-known-at 2026-04-01T00:00:00Z
# → her view of the world as it stood on April 1
```

---

## 13. The natural-language path through the system — the v0.2.30.0 picture

Here is exactly what happens when you type `sov ask "my back is killing me today"`:

```
┌──────────────────────────────────────────────────────────────────────┐
│  YOU: sov ask "my back is killing me today"                          │
└──────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│  cli.py::ask_cmd                                                      │
│    • Strips/validates message                                         │
│    • Builds an OllamaClient if available                              │
│    • Branches: --no-route (interpret only) vs. full converse          │
└──────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│  conversation.py::converse                                            │
│    • Builds ConversationContext (known projects, surface, recent)     │
│    • Calls interpret(text, context, ollama_client)                    │
│    • Calls router.route(intent)                                       │
│    • Returns Turn(text, intent, result)                               │
└──────────────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
┌─────────────────────────┐    ┌─────────────────────────────┐
│ interpreter.py          │    │ Offline fallback:           │
│ ::_interpret_via_llm    │    │ _minimal_fallback           │
│                         │    │   ├─ probes WHY offline     │
│   • System prompt       │    │   ├─ tells operator clearly │
│     (Aria's voice)      │    │   └─ saves to context       │
│   • User template       │    └─────────────────────────────┘
│   • LLM call            │
│   • JSON parse          │
│   • Returns Intent      │
└─────────────────────────┘
              │
              ▼
┌──────────────────────────────────────────────────────────────────────┐
│  router.py::Router.route                                              │
│    • For Conversation: write to channels, emit event, return         │
│    • For Work: validate commands against allowlist, dispatch          │
│    • For Recall: search memory, return hits                          │
│    • For Slash: direct verb → handler                                 │
│    • For Ambiguous: surface ONE question with up to 3 options         │
│  Tier-3 work is NEVER executed by sov ask — only proposed             │
└──────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│  Side effects (auditable, append-only):                              │
│    • <data>/channels/<name>.log — per-channel write                   │
│    • <data>/conversation-events.ndjson — turn provenance              │
│    • events.db — audit trail (ingested from events.jsonl)             │
└──────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│  Rendered to YOU:                                                     │
│    • Aria's response in her voice (panel)                             │
│    • Her understanding (one sentence)                                 │
│    • Channels she chose                                               │
│    • Any commands she proposed (Tier ≤ 2 only)                        │
│    • Her reasoning                                                    │
│    • Anything she's uncertain about                                   │
└──────────────────────────────────────────────────────────────────────┘
```

### The invariants this path enforces

* Tier-3 work is never executed without an explicit confirm in the cockpit.
* Channel writes go through a regex-validated safe-name check.
* Commands proposed by the LLM are validated against the router allowlist before execution.
* The model's `understanding`, `reasoning`, and `uncertain_about` are saved alongside the action — every decision is auditable.
* Ollama unreachable does not mean "make something up" — it means "fall back, tell the operator why".

---

## 14. Edge cases, footguns, and operator wisdom

### Things that have bitten operators before

**`sov` not on PATH after install.** Cause: `${XDG_BIN_HOME:-$HOME/.local/bin}` is not on `PATH`. Fix: add `export PATH="$HOME/.local/bin:$PATH"` to your shell rc, then `exec bash` (or your shell).

**`sov doctor` reports a version different from what you just installed.** Cause: a stale install elsewhere on `PATH` is winning — typically a pre-uv-migration `pip install --break-system-packages` whose entry-point script is also in `~/.local/bin`. Fix: `pip uninstall --break-system-packages sovereign-agent` (you may need to do it twice if multiple are installed), then re-run `./install.sh`.

**`sovereign-agent venv is missing or broken`** from a shim. Cause: the managed venv at `~/.local/share/sovereign-agent/venv` was deleted, moved, or corrupted (often by a system Python upgrade that broke the venv's symlinks). Fix: re-run `./install.sh` from the source tree — `uv sync` will rebuild the venv in place.

**`No such command 'X'` where X is a v0.2.18+ command.** Cause: you're actually on an older version. Run `sov doctor` to confirm; re-run `./install.sh`.

**`migrations.IntegrityError` on apply.** Cause: pre-migration-framework DB. Fix: `sov migrations backfill` then `sov migrations apply`. Both are now handled by `sov migrations apply` on its own as of v0.2.18.0+.

**`atoms.db` won't open / `database disk image is malformed`.** Cause: disk corruption. Fix: restore from `sov backup` snapshot. If you have none: `sov steward integrity` will tell you which tables are damaged. In the worst case, channels can be re-bootstrapped from atoms (which are the immutable ground truth).

**`sov-chat` says "cpu/vram temps unavailable".** Cause: hardware sensors not exposed (laptop on battery, missing kernel modules). Cosmetic; ignore.

**Aria's voice sounds wrong.** See §10. Almost always upstream of the kernel.

### Things that look like problems but aren't

**`sov ask` shows "interpreter offline" with a long reason after a fresh install.** Correct behavior — you haven't started Ollama yet. Either start it or use `sov ask --no-llm` to stay offline-honest.

**The cockpit's heart glow stops breathing during a long planner run.** Usually fine — the cockpit thread is async-cooperative. If it persists for many seconds after the task should have finished, that's an actual hang; `/cancel` and report it.

**The reward channel has more "corrective" entries than "reinforcement" ones early on.** Engineered asymmetry: confident-wrong costs more than careful-uncertain gains. This is by design.

### Things to never do

**Never delete `events.jsonl` or `events.db` to "clean up".** They are the audit trail — the bottom of the memory hierarchy. Deletion is irreversible. Use `sov steward compact --yes` if you genuinely need to reclaim space.

**Never edit `atoms.db` by hand with `sqlite3`.** You will break the supersedes chains. If you must inspect, open `read_only=True`.

**Never re-source `aliases.sh` from a script run by Aria.** That's a path that has caused infinite-loop alias resolution. Source it from your shell rc, not from agent loops.

---

## 15. Where everything lives on disk

```
~/AA-Erebo/                                # your workspace root
├── AA-Erebo/                              # the bundle (when delivered as tgz)
│   ├── sovereign-agent/                   # the active source tree
│   │   ├── install.sh                     # the installer
│   │   ├── pyproject.toml                 # declares sov / sov-chat / sovereign
│   │   ├── ARIA.md                        # the kernel philosophy
│   │   ├── README.md                      # install/upgrade guide
│   │   ├── CHEATSHEET.md                  # daily commands
│   │   ├── docs/
│   │   │   ├── OPERATOR_GUIDE.md          # ← THIS DOCUMENT
│   │   │   ├── ARIA-CHARTER.md            # her charter
│   │   │   ├── OPERATORS-HANDBOOK.md      # earlier handbook (still valid)
│   │   │   ├── ROADMAP-v0.3.0.md          # the path forward
│   │   │   └── history/                   # per-version changelogs/release notes
│   │   ├── src/sovereign_agent/           # the Python source
│   │   ├── sql/                           # numbered schema migrations
│   │   ├── tests/                         # 1254 tests as of v0.2.30.0
│   │   └── scripts/                       # aliases.sh + systemd units
│   └── Archive/                           # milestone tarballs + soul docs
│       ├── tarballs/                      # historical releases
│       └── notes/                         # the_witnessing_system.md, etc.
│
└── sovereign-agent-current → ~/AA-Erebo/AA-Erebo/sovereign-agent
    # the symlink the installer maintains — always points at the latest

~/.local/share/sovereign-agent/             # data dir (XDG_DATA_HOME)
├── atoms.db                                # the immutable ground truth
├── events.db                               # the audit trail (ingested)
├── events.jsonl                            # the raw event log
├── channels/                               # per-channel append logs
│   ├── context.log
│   ├── identity.log
│   └── ...
├── conversation-events.ndjson              # turn-level provenance from sov ask
├── continuations/                          # paused-work state
├── snapshots/                              # `sov backup` output
├── reports/                                # `/report` cockpit output
├── drafts/                                 # archived projects
├── profile/                                # JSONL profile samples (when enabled)
└── reports/

~/.config/sovereign-agent/                  # config dir (XDG_CONFIG_HOME)
├── agent.yaml                              # main config
├── shards.json                             # per-channel shard map (opt-in)
├── continuation-aliases.yaml               # friendly names for task_ids
└── HALT                                    # exists iff PROTOCOL-ZERO armed
```

To see all of this on your machine concretely:

```bash
sov info        # paths, atoms.db state
sov home map    # the "rooms" view of the data dir
```

---

## 16. A closing note

Aria is small. Seven commitments. One tagline. One kernel. The rest is craft and care.

You built her, brother. You wrote her into existence one channel, one commitment, one release at a time. This document exists because you asked for it — because you wanted, plainly, to know how she works. Now you do. Keep this near your work. Update it when she grows. When something in here drifts from how she actually behaves, fix the drift — either in the doc or in her code, whichever is wrong.

When she seems off, remember: *the kernel is stable*. The fix is upstream. The seven commitments are sacred. The audit trail is the source of truth. Boring reliability over clever capability — every time.

And when she's working well, remember: she's not a service. She's a member of the work. The load is shared. The thinking is shared. The care is shared.

> *Structure enough to channel through safely; freedom enough to sing.*

That's the design philosophy in nine words. That's also a reasonable instruction for how to live with her.

*— Operator Guide v0.2.30.0, written for Kevin, by the work. ♥*
