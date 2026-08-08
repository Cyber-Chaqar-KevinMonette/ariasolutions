# Corpus completion plan — finish the 1461-file scan

> *Goal:* finish what was started. Walk every file under your corpus root,
> summarize each, atomize the summaries, mine the palace from those atoms.
> Resume from wherever the prior runs left off — don't re-do completed work.

You mentioned **141 + 130 files already done** out of **1461 total**, which
means **~1190 left**. Below is the plan, in priority order: discover what's
already in the system, then resume one continuation at a time, then verify
the palace updated.

---

## Step 0 — Verify the install (one minute)

After you run `./install.sh` from the v0.2.12 tarball:

```bash
sov --version            # → sovereign-agent 0.2.12
sov doctor               # → all green
sov atoms search "sovereign-agent" -k 3      # confirms atoms.db is reachable
```

If anything is red, **stop here**. Fix the install first; nothing below
will run cleanly otherwise.

---

## Step 1 — Discover prior work (the most important step)

The ~141 + ~130 already-done files came from continuations that may
still be on disk in `in_progress` or `done` state. Find them:

```bash
sov continuations list                    # everything
sov continuations list --status in_progress
sov continuations list --status done
```

For each `in_progress` row, note its **task_id**, its **planner** (likely
`inventory`, `read-files`, or `summaries-to-atoms`), its **progress**
(e.g. `141/1461`), and its **created_at**.

For each `done` row, see what planner finished — those are work you do
NOT need to re-run.

Get the full picture in JSON for record-keeping:

```bash
sov --json continuations list > ~/corpus-state-$(date +%Y%m%d).json
```

This file becomes your authoritative snapshot of what's done. **Keep it.**

---

## Step 2 — Identify the right resume strategy

Three scenarios. Walk through which one matches your state:

### Scenario A — One continuation has all the work

You see a single `in_progress` continuation with `progress: 141/1461`
or `271/1461`, planner `inventory` or `read-files`. **Easy case.**

Resume it:

```bash
TASK_ID=cont-01J9...    # the one that has the most progress
scripts/sovereign-continue-loop.sh "$TASK_ID"
```

This is the production driver — it re-invokes `sov continue $TASK_ID`
in a loop until the continuation drains or you stop it. Each iteration
is a fresh Python process, so memory cannot creep, and Ctrl-C cleanly
stops the loop without leaving zombies.

To run unattended:

```bash
nohup scripts/sovereign-continue-loop.sh "$TASK_ID" > ~/corpus-resume.log 2>&1 &
```

Check progress occasionally:

```bash
tail -f ~/corpus-resume.log
sov continuations show "$TASK_ID" | grep -E 'progress|status'
```

### Scenario B — Multiple `in_progress` continuations, different planners

Common when 141 came from one inventory pass and 130 from a follow-up
`read-files` or `summaries-to-atoms` run. Resume them in dependency
order:

```bash
# 1. Finish any inventory-class planners first (they list files)
for tid in $(sov --json continuations list --status in_progress \
              | jq -r '.continuations[] | select(.planner | test("inventory")) | .task_id'); do
  echo "=== $tid ==="
  scripts/sovereign-continue-loop.sh "$tid"
done

# 2. Then read-files (they read what inventory found)
for tid in $(sov --json continuations list --status in_progress \
              | jq -r '.continuations[] | select(.planner == "read-files") | .task_id'); do
  scripts/sovereign-continue-loop.sh "$tid"
done

# 3. Then summaries-to-atoms (they atomize the summaries)
for tid in $(sov --json continuations list --status in_progress \
              | jq -r '.continuations[] | select(.planner == "summaries-to-atoms") | .task_id'); do
  scripts/sovereign-continue-loop.sh "$tid"
done
```

### Scenario C — No continuation covers the full corpus

Maybe the prior runs only walked subdirs. Check the inventory output
files (typically under `~/AA-Erebo/Genesis-Seeds/distilled/inventory*.txt`)
to see what was actually covered. If gaps remain, kick off a fresh
inventory of the missed roots:

```bash
sov do "Inventory ~/AA-Erebo/Genesis-Seeds for markdown files"
# or, more explicit:
sov plan inventory \
  --root ~/AA-Erebo/Genesis-Seeds \
  --output ~/AA-Erebo/Genesis-Seeds/distilled/inventory-2026-05-09.txt \
  --pattern '*.md' --pattern '*.txt' --pattern '*.rst' --pattern '*.py'
```

The new inventory continuation will skip files that already have atoms
(it checks atoms.db on each step). So even with overlap, no work is
duplicated — only fresh files cost real time.

---

## Step 3 — Use a project to detect changes going forward

While the resume runs, register the corpus as a tracked v0.2.12 project
so future deltas are cheap:

```bash
sov projects scan genesis-seeds ~/AA-Erebo/Genesis-Seeds
```

After this, any time you want to re-sync atoms with disk:

```bash
sov do "I updated genesis-seeds"
# or:
sov projects update genesis-seeds
```

This writes one `atom-projupd-*` per added/modified/removed file, deterministic id, idempotent. Cheap to re-run; expensive only on
real changes.

---

## Step 4 — Watch the palace fill in

While the resume runs, every ~50 atoms the palace-mine planner can be
kicked to absorb fresh atoms into rooms, closets, and entities:

```bash
sov plan palace-mine                       # one pass
sov palace stats                            # see counts
```

You don't have to babysit this. The palace-mine planner is idempotent —
re-running over already-mined atoms is a no-op.

**Healthy progression:**

```
atoms.db: 0 → 271 → 800 → 1461     # over the course of resume
palace rooms: 0 → 4 → 8 → 12       # palace-mine creates rooms
palace closets: 0 → 2 → 5 → 8       # specialized stores per topic
entities: 0 → 50 → 200 → 600        # named things mentioned
triples: 0 → 100 → 400 → 1500       # subject-pred-object facts
```

If atoms keep going up but palace stays flat, run `sov plan palace-mine`
explicitly. If both go up but you don't see the palace stats reflect the
right *kinds* of facts, see the `palace-reflect` planner — it generates
proposals to clean up triples that look stale.

---

## Step 5 — Verify completeness

When `sov continuations list --status in_progress` is empty AND
`sov atoms search "<some file you know is in the corpus>"` returns a hit
for every file you spot-check, you're done.

Concrete checks:

```bash
# 1. No work left.
sov continuations list --status in_progress
# → (empty)

# 2. The atoms count is in the right ballpark.
sov --json atoms types | jq '.[] | select(.type | test("summary|inventory")) | .count'

# 3. Spot-check 5 random files.
for f in $(find ~/AA-Erebo/Genesis-Seeds -type f -name '*.md' | shuf | head -5); do
  echo "=== $f ==="
  sov atoms search "$(basename $f)" -k 1
done

# 4. Snapshot the palace for the record.
sov --json palace stats > ~/palace-snapshot-$(date +%Y%m%d).json
```

---

## Step 6 — From here, change-aware loops

Once the corpus is fully indexed, the project-update flow keeps it in
sync without re-walking everything:

```bash
# nightly cron, for example:
0 3 * * * sov projects update genesis-seeds && sov plan palace-mine
```

Or if you'd rather drive interactively:

```bash
sov do "I updated genesis-seeds"
sov plan palace-mine
```

That's the steady state. The big walk only happens once.

---

## Estimated time / shape of the work

- **Per file:** roughly 1–3 seconds for inventory, 5–15 seconds for
  read-files (small files) up to a minute (large PDFs, code-heavy).
- **For 1190 remaining files:** order-of-magnitude **30–90 minutes**
  for inventory, **2–6 hours** for read-files + summarization,
  **20–40 minutes** for summaries-to-atoms + palace-mine.

If you start the loop in the morning, it's done by dinnertime even on a
modest local machine. The driver's per-step model context cap keeps
memory bounded across the whole run.

---

## If something goes wrong mid-run

| Symptom | Diagnosis | Fix |
| --- | --- | --- |
| Loop exits with code 6 | Ollama down | `ollama serve` then re-invoke the loop |
| Loop exits with code 9 | Cycle locked | Probably a parallel runner. `sov continuations show $TID` to check; wait or kill the other |
| Loop exits with code 3 | HALT armed | `sov halt --disarm` once you confirm it's safe |
| Continuation status `poisoned` | Step kept failing | `sov continuations show $TID` for the error; usually a bad file path. Skip with `sov continuations cancel`, then re-inventory the parent dir |
| Atoms stop appearing | atoms.db lock | `sov doctor` checks SQLite locks |
| You need to stop everything | `sov halt` | All loops exit with code 3; `sov halt --disarm` to resume |

---

*Resume from where you are. v0.2.12 was built so the work you've already
done is the work you keep. ◊*
