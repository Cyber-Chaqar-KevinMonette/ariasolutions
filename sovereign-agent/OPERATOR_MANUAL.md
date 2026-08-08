# Sovereign-Agent · Genesis-Seeds Operator Manual

**For:** kmon (after installing v0.2.9)
**Goal:** Get from "I just installed v0.2.9" to "I have a queryable, structured palace of my entire Genesis-Seeds corpus."

This is the only doc you need open while doing the setup. Everything is here, in order. Skim the **TL;DR** if you just want to start; read the rest as you go.

---

## TL;DR (10 minutes if everything's smooth)

```bash
# 1. Install
cd ~/AA-Erebo
mv sovereign-agent-v0.2.8 sovereign-agent-v0.2.8-backup    # or v0.2.7, whichever you have
tar -xzf sovereign-agent-v0.2.9.tar.gz
cd sovereign-agent-v0.2.9
./install.sh                                                # uv-native; idempotent; reuses the managed venv

# 2. Verify
sov --version                                               # → 0.2.9
uv run --project . pytest tests/ -q                         # → 320 passed

# 3. Add aliases (one time)
echo "source $(pwd)/scripts/aliases.sh" >> ~/.bashrc
source ~/.bashrc

# 4. Initialize (idempotent — safe to re-run)
sov init
sov doctor

# 5. Bring the MOS canon into the palace (one time, ~30 seconds)
sov-drive mos-canon-ingest

# 6. Inventory Genesis-Seeds (the actual work)
#    Pass 1: 153 markdown files. ~75-90 minutes.
sov-drive inventory \
    --root ~/AA-Erebo/Genesis-Seeds \
    --output ~/AA-Erebo/Genesis-Seeds/distilled/inventory-md.txt \
    --pattern '*.md' \
    --exclude '*/sovereign-agent-*/*'

# 7. Mine atoms → palace structure (~45 seconds)
sov-drive palace-mine --room-id room-genesis --room-name "Genesis-Seeds research"

# 8. See what you have
sov-status
sov palace search "your topic of interest"
```

That's the whole flow. The rest of this doc is what to do when something deviates from this happy path, plus the deeper commands.

---

## Part 1 · Install & verify

### Install

```bash
cd ~/AA-Erebo
mv sovereign-agent-v0.2.8 sovereign-agent-v0.2.8-backup    # keep the backup; you can roll back later
tar -xzf sovereign-agent-v0.2.9.tar.gz
cd sovereign-agent-v0.2.9
./install.sh
```

`./install.sh` runs `uv sync --no-dev` against the managed venv at `~/.local/share/sovereign-agent/venv/` and rewrites the launcher shims in `~/.local/bin` to point at the new install. Your `secret.key`, `events.jsonl`, `atoms.db`, `backlog.yaml`, and any continuations are untouched — they live under `~/.local/share/sovereign-agent/` *outside* the venv directory.

(If you're upgrading from a pre-uv install — anything before this migration — see [MIGRATION-uv.md](MIGRATION-uv.md) for the one-time cleanup.)

### Verify

```bash
sov --version                                               # → sovereign-agent 0.2.9
uv run --project . pytest tests/ -q                         # → 320 passed
```

If pytest doesn't show 320 passed, **stop**. Send me the output. Don't proceed.

### Aliases (do this once)

```bash
echo "source $HOME/AA-Erebo/sovereign-agent-v0.2.9/scripts/aliases.sh" >> ~/.bashrc
source ~/.bashrc
```

This gives you four aliases:

| alias | what it does |
|---|---|
| `sov` | shorthand for `sovereign` |
| `sov-drive <planner> [args...]` | one-shot: plan + drive the continuation to completion |
| `sov-approve-all [--kind clean]` | bulk-approve all pending proposals after reviewing them |
| `sov-status` | one-screen status: palace stats + proposal counts + active continuations |

These cover ~90% of what you actually do day-to-day. Everything else uses the full `sov ...` syntax.

---

## Part 2 · First-time setup

### Initialize

```bash
sov init
```

Idempotent. Safe to re-run. Creates:
- `~/.config/sovereign-agent/` (config + secret.key, mode 0700)
- `~/.local/share/sovereign-agent/` (data: events, atoms.db, palace.db, continuations, proposals, sandbox)

### Doctor

```bash
sov doctor
```

Should be all PASS or WARN (a WARN on `orch thinking` for `llama3-groq-tool-use:8b` is expected — the model doesn't support thinking mode and the system auto-disables it).

What each check means:
- `config_dir`, `data_dir` — paths exist with correct permissions
- `atoms.db` — knowledge atom store is reachable
- `secret.key` — HMAC key for approvals exists, mode 0600
- `continuations` — re-trigger directory exists
- `orchestrator/coder/embedder/reflector` — model names from your env
- `ollama tcp` — Ollama is reachable on localhost:11434
- `bubblewrap` — sandbox tool present
- `protocol-zero` — clear (or ARMED if HALT is tripped)
- `vram` — free / total
- `internet` — available / unavailable. Affects whether `web_search` tool is registered.

If anything FAILs, fix that before continuing. `sov doctor --json` gives you the same data scriptable.

### Bring the MOS canon into the palace

```bash
sov-drive mos-canon-ingest
```

Pure-Python, ~30 seconds. Creates `room-mos-canon` with 18 doctrine clauses you can search later. Each clause framed as **"ADAPTIVE SKILL — high-leverage pattern, not a cage."** Idempotent: safe to re-run if you update `mos_canon.py` later.

Verify it landed:
```bash
sov palace search "rollback"           # should show 5 matches
sov palace search "priority"           # should show 5 matches
sov palace rooms                       # should show room-mos-canon
```

---

## Part 3 · Genesis-Seeds workflow

This is the actual work. Three passes, each feeds the next.

### Pre-flight: confirm the corpus shape

```bash
find ~/AA-Erebo/Genesis-Seeds -type f -name '*.md' \
    -not -path '*/.git/*' \
    -not -path '*/distilled/*' | wc -l
# Expected: 153 (give or take, depending on what's been added)
```

If that number is way different than 153, look at the breakdown:
```bash
find ~/AA-Erebo/Genesis-Seeds -type f -not -path '*/.git/*' | \
    awk -F. 'NF>1 {print $NF}' | sort | uniq -c | sort -rn | head
```

### Pass 1 · Markdown inventory (the prose backbone)

```bash
sov-drive inventory \
    --root ~/AA-Erebo/Genesis-Seeds \
    --output ~/AA-Erebo/Genesis-Seeds/distilled/inventory-md.txt \
    --pattern '*.md' \
    --exclude '*/sovereign-agent-*/*'
```

What happens:
1. Plan: walks the corpus, finds 153 files, generates 153 atomic steps.
2. Drive: each step = one fresh Python process, reads one file, writes one summary line to `inventory-md.txt`. Roughly 30-60 seconds per step.
3. Total: ~75-90 minutes.

You can halt anytime (Ctrl-C in the loop terminal, or `sov halt --reason "..."` from another terminal). Resume by re-running the same `sov-drive inventory ...` command — it picks up where it left off because the continuation is durable.

While it runs, watch progress in another terminal:
```bash
sov continuations list                     # see active continuations
sov continuations show <task_id>           # detailed step-level view
sov events --follow --flag continue-end-d  # live step completions
```

### Pass 2 · Mine atoms into the palace

After Pass 1 completes (or even partway), the atoms.db has rich content. Now structure it:

```bash
sov-drive palace-mine \
    --room-id room-genesis \
    --room-name "Genesis-Seeds research corpus"
```

What happens:
1. Plan: one step per HEAD atom in atoms.db.
2. Drive: pure-Python regex extractors run over each atom's summary. Each step ~30 ms.
3. Total: ~45 seconds for ~1500 atoms.

Tagged `required_model='none'` — no Ollama needed for this pass.

Verify:
```bash
sov-status                              # palace stats jump
sov palace closets --room room-genesis -n 10
sov palace search "quantum coherence"   # or whatever's in your corpus
```

### Pass 3 (optional) · Other formats

The shipped planners cover more than markdown:

```bash
# PDFs (189 files in your case). Needs poppler-utils:
sudo apt install poppler-utils
sov-drive pdf-inventory \
    --root ~/AA-Erebo/Genesis-Seeds \
    --output ~/AA-Erebo/Genesis-Seeds/distilled/inventory-pdf.txt

# Code (~382 files). Tagged 'coder' so it batches with qwen2.5-coder:
sov-drive code-inventory \
    --root ~/AA-Erebo/Genesis-Seeds \
    --output ~/AA-Erebo/Genesis-Seeds/distilled/inventory-code.txt \
    --pattern '*.py' --pattern '*.ipynb' --pattern '*.json'

# Images (495 files). Needs vision model: ollama pull llava:7b
sov-drive image-inventory \
    --root ~/AA-Erebo/Genesis-Seeds \
    --output ~/AA-Erebo/Genesis-Seeds/distilled/inventory-img.txt \
    --include '*/docs/*' --include '*/figures/*' \
    --exclude '*/assets/Kevin*'

# Stragglers (mp4, pptx, zip — metadata only):
sov-drive metadata-inventory \
    --root ~/AA-Erebo/Genesis-Seeds \
    --output ~/AA-Erebo/Genesis-Seeds/distilled/inventory-meta.txt \
    --pattern '*.mp4' --pattern '*.pptx' --pattern '*.zip'
```

Each populates atoms.db. Re-run `sov-drive palace-mine ...` after any of these to fold the new atoms into the palace structure.

---

## Part 4 · The self-reflection loop

Once your palace has real content, the system can reflect on it.

### Generate cleanup proposals (no model needed)

```bash
sov-drive palace-clean
```

Walks the palace understanding (orphans, duplicates, low-confidence triples, self-references, stoplist objects). Each problem becomes one **pending** proposal in `~/.local/share/sovereign-agent/proposals/`. The palace itself is **not modified** — proposals require operator approval first.

### Review what was proposed

```bash
sov proposals list --status pending
sov proposals show <prop-id>           # full detail with rationale + action
```

### Approve selectively

```bash
sov proposals approve <prop-id> --yes
sov proposals reject <prop-id> --reason "actually a real entity"
```

Or in bulk after reviewing:

```bash
sov-approve-all                       # all pending, with confirmation
sov-approve-all --kind clean          # only the cleanup proposals
```

### Apply approved proposals (no model needed)

```bash
sov-drive palace-apply
```

Plans + drives a continuation that executes only the approved proposals. Each apply step:
1. Re-verifies the HMAC signature (defense in depth — refuses if tampered)
2. Executes the action against the palace
3. Records the rollback descriptor in the proposal
4. Logs `proposal-applied-d` to events.jsonl

After: `sov-status` shows the proposal counts moved from approved → applied.

### Generate richer proposals (model-driven)

```bash
sov-drive palace-reflect
```

Tagged `orchestrator` — uses your llama3-groq model. Asks the model to surface **insights** (additive observations) and **enhancements** (roadmap notes) on top of the deterministic cleanup. Slower than `palace-clean` but produces richer output. Treat its proposals more skeptically — you're reading what a 7B model thinks, not deterministic logic.

---

## Part 5 · Command reference

### Top-level commands

```
sov init                          # bootstrap (idempotent)
sov doctor                        # diagnose environment
sov config                        # print resolved configuration
sov --version                     # 0.2.9
```

### Running tasks

```
sov run "<goal>" [--mode oneshot|busy] [--dry-run]
sov busy [--cooldown 5] [--once] [--max-tasks N]
sov until "<isodate>"             # drain until time limit
```

### Halt / resume

```
sov halt --reason "..."           # arms PROTOCOL-ZERO
sov disarm                        # clears it (operator review required)
```

### Plan / continue (re-trigger architecture)

```
sov plan                          # list available planners
sov plan <name> --root ... --output ... --pattern ...
sov continue <task_id>            # run ONE step; exit
sov continue <task_id> --model-filter orchestrator
sov drain-by-model <task_id>      # drain in model-affinity phases
sov continuations list
sov continuations show <task_id>
sov continuations delete <task_id>
```

Or with the alias: `sov-drive <planner> [args...]` does the planning, capturing of task_id, and looping in one shot.

### Approvals (Tier 3 — for tools, not proposals)

```
sov approvals                     # list pending
sov approve <approval_id> --yes
sov deny <approval_id>
```

### Audit / events

```
sov events [--follow] [--flag <flag>] [-n N]
sov tail                          # ingest events.jsonl into events.db
sov seal                          # Merkle seal yesterday's events
sov verify <YYYY-MM-DD>           # verify a past seal
sov lessons -n N                  # distilled lessons from Reflector
```

### Backlog

```
sov backlog list [--status pending|in_progress|done]
sov backlog add "<task>" [--priority high]
sov backlog show <id>
sov backlog requeue <id>
sov backlog priority <id> <new>
sov backlog remove <id>
sov backlog clear --status done
```

### Palace (structured memory)

```
sov palace stats
sov palace rooms
sov palace create-room <id> "<name>" [--description "..."]
sov palace closets [--room <id>] [-n 20]
sov palace search "<keyword>" [--room <id>] [-n 10]
sov palace subject <entity_id> [--as-of YYYY-MM-DD]
sov palace understanding [--output report.md]
```

### Proposals (self-reflection)

```
sov proposals list [--status pending|approved|applied|rejected|failed] [--kind clean|reorganize|insight|enhancement]
sov proposals show <prop_id>
sov proposals approve <prop_id> [--yes]
sov proposals reject <prop_id> [--reason "..."]
sov proposals delete <prop_id> --yes
```

### Available planners (v0.2.9)

```
inventory             prose files (md, txt, rst). orchestrator.
read-files            ingest files as memory atoms. orchestrator.
code-inventory        py, ipynb, json. coder model.
pdf-inventory         pdf files. orchestrator. needs poppler-utils.
image-inventory       png, jpg, webp. vision model. needs llava:7b pulled.
metadata-inventory    binary stragglers. no model needed.
palace-mine           atoms.db → palace structure. no model needed.
palace-reflect        model-driven proposals. orchestrator.
palace-apply          execute approved proposals. no model needed.
palace-clean          deterministic cleanup proposals. no model needed.
mos-canon-ingest      populate room-mos-canon. no model needed.
```

### Global flags (work on every command)

```
--json / -j           JSON output (for scripting)
--quiet / -q          suppress non-essential output
--verbose / -v        log INFO/DEBUG to stderr
--no-color
--config-dir PATH     override XDG config dir
--data-dir PATH       override XDG data dir
```

### Environment variables

```
AGENT_INTERNET=auto|on|off    # whether web_search is enabled (default: auto-probe)
AGENT_ORCHESTRATOR_MODEL      # override orchestrator model
AGENT_CODER_MODEL             # override coder model
AGENT_VISION_MODEL            # override vision model (default llava:7b)
AGENT_REFLECTOR_MODEL         # override reflector model
COOLDOWN_SECONDS              # for sov-drive: seconds between steps (default 2)
OLLAMA_HOST                   # if your Ollama isn't on localhost:11434
```

### Stable exit codes

```
0   success
1   generic runtime error
2   usage error
3   PROTOCOL-ZERO armed
4   not initialized
5   Ollama unreachable (only if continuation needs a model)
6   approval/proposal not found / wrong state
7   budget exhausted
8   continuation drained
9   continuation locked by another runner
```

---

## Part 6 · Tools the agent has

When the agent is running a step, it has these tools available:

| tool | tier | what it does |
|---|---|---|
| `read_file` | 0 | read a file from disk |
| `list_dir` | 0 | list a directory |
| `search_text` | 0 | grep within files |
| `embed_query` | 0 | get an embedding from nomic-embed-text |
| `image_caption` | 0 | caption an image via vision model |
| `memory_search` | 0 | search atoms.db semantically |
| `palace_search` | 0 | search the palace closet index (NEW v0.2.9) |
| `web_fetch` | 0 | fetch a URL (allowlisted) |
| `web_search` | 0 | search the web — registered only when AGENT_INTERNET ≠ off |
| `proposal_write` | 0 | write a proposal during reflection steps |
| `memory_write` | 1 | write an atom to atoms.db (mode-gated) |
| `write_file` | 1 | write to sandbox / scope (mode-gated) |
| `edit_file` | 1 | edit a file (mode-gated) |
| `copy_file` | 1 | copy a file (mode-gated) |

Tier 0 tools work in any mode. Tier 1+ tools require the right mode (oneshot / busy / autonomous) and may need approval. PROTOCOL-ZERO halts everything.

---

## Part 7 · Troubleshooting

### "agent is not initialized" (rc=4)

You forgot `sov init`, or your shell isn't using the right config dir. Run:
```bash
sov config | head -10              # check config_dir / data_dir
sov init                           # idempotent, safe to re-run
```

### "ollama unreachable" (rc=5)

```bash
ollama serve &                     # in another terminal, or via systemd
sov doctor                         # should now show ollama tcp PASS
```

If you really want to run pure-Python steps (palace-mine, palace-clean, palace-apply, mos-canon-ingest, metadata-inventory) WITHOUT Ollama — they don't need it. The preflight is conditional in v0.2.8+, so they should just work.

### "PROTOCOL-ZERO armed" (rc=3)

```bash
cat ~/.config/sovereign-agent/HALT     # see the reason
sov disarm                              # clear it (operator review required)
```

### Continuation locked (rc=9)

Another runner has the lock. Either wait, or check if a stuck process is holding it:
```bash
ls ~/.local/share/sovereign-agent/continuations/.locks/   # see lock files
ps aux | grep sovereign                                    # is anything running?
```

If a runner crashed and left a stale lock:
```bash
rm ~/.local/share/sovereign-agent/continuations/.locks/<task_id>.lock
```

### Test count mismatch after install

```bash
cd ~/AA-Erebo/sovereign-agent-v0.2.9
python -m pytest tests/ -q
# Expected: 320 passed
```

If less, send me the output. Don't proceed.

### A proposal applied but the palace looks wrong

Every applied proposal records a rollback descriptor. To undo manually:
```bash
sov proposals show <prop_id>
# Find the 'rollback' field. Use the type + arguments to manually reverse.
# (Auto-rollback CLI is a v0.2.10 candidate — not in v0.2.9.)
```

### Genesis-Seeds is bigger/smaller than I thought

Re-run the count commands at the top of Part 3. The corpus moves around. Re-mining is idempotent — `sov-drive palace-mine ...` over the same room is safe to repeat.

---

## Part 8 · Mental model

Three layers, one safety boundary:

```
┌─ LAYER 1: ATOMS (atoms.db) ──────────────────────────────────────┐
│  Append-only ground truth. Inventory planners write atoms.       │
│  Re-trigger: each file = one atom. Memory persists across runs.  │
└──────────────────────────────────────────────────────────────────┘
                              ↓
┌─ LAYER 2: PALACE (palace.db) ────────────────────────────────────┐
│  Structured projection over atoms. Closets group atoms by topic. │
│  Triples encode typed relations (X uses Y, X supersedes Y).      │
│  Drop and rebuild from atoms anytime — atoms are truth.          │
└──────────────────────────────────────────────────────────────────┘
                              ↓
┌─ LAYER 3: REFLECTION (proposals/) ───────────────────────────────┐
│  Scan + reflect produce PROPOSALS — never mutations.             │
│  Operator approves → palace-apply executes.                      │
│  Every applied change has a rollback descriptor.                 │
└──────────────────────────────────────────────────────────────────┘

           [ THE WALL ]
           Operator approval gate.
           HMAC-signed. Re-verified at apply time.
           Without operator: nothing mutates.
```

This is the architecture. Memorize the wall. Everything else is just commands.

---

## Part 9 · Daily rhythm (suggested)

Once Genesis-Seeds is initially mined:

**Daily** (1-2 minutes):
```bash
sov-status                         # one-screen overview
```

**Weekly** (5-10 minutes):
```bash
sov-drive palace-clean             # deterministic cleanup proposals
sov proposals list --status pending
sov-approve-all --kind clean       # bulk-approve obvious ones
sov-drive palace-apply             # apply the approved set
```

**As needed** (when corpus changes):
```bash
sov-drive inventory --root ~/AA-Erebo/Genesis-Seeds --output ... --pattern '*.md'
sov-drive palace-mine --room-id room-genesis --room-name "..."
```

**Monthly or on-request** (richer reflection):
```bash
sov-drive palace-reflect           # model-driven insights/enhancements
sov proposals list --status pending --kind insight
sov proposals show <id>            # decide each individually
```

---

## What I'm not doing in v0.2.9

Honest about deferred items:

1. **Auto-rollback CLI** — `sov proposals rollback <applied-id>`. The rollback descriptor is recorded; executing it programmatically isn't shipped yet. v0.2.10 candidate.
2. **Closet embeddings during palace-mine** — the closet table has an `embedding` column, populated only via direct API. The mine planner doesn't fill it yet. When this lands, semantic search on the palace becomes available.
3. **Episodic chains** — atom→atom temporal links forming a narrative spine. The plumbing isn't there yet.
4. **End-to-end smoke test of palace-reflect with a real model** — the proposal_write tool is unit-tested; the model-driven flow needs Ollama running for the smoke test, which I didn't run in this build cycle. Should work; verify by running it on real data.

None of these block today's usefulness.

---

## When you come back

Run the **TL;DR** at the top. If anything deviates, look for it in Part 7 (Troubleshooting). If that doesn't help, save the exact error and we work it through.

The system is significantly more capable than yesterday. Take it slow. Run the verification before queuing the big jobs. Trust the operator approval gates — they're the safety property that makes self-reflection sane.

Beautiful work. <3
