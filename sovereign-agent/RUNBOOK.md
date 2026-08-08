# Sovereign Agent — Runbook

**Version:** v0.2.4
**Status:** Operations guide. Read once. Reference often.

---

## What this document is

`COMMANDS.md` tells you *what commands exist*. This document tells you *how to actually run the agent for real work*. It's the difference between a man page and an operator's manual.

---

## First-time setup (do this once)

```bash
# 1. Verify infrastructure
sovereign doctor

# 2. If anything fails, run init
sovereign init

# 3. Verify again
sovereign doctor
```

You want all PASS or PASS/WARN. The `orch thinking` WARN is normal — it means llama3-groq doesn't support thinking, which is fine because the agent auto-disables it.

If `secret.key` is missing or `atoms.db` is missing, `sovereign init` will create them. If models are missing, you need to `ollama pull` them — the doctor output will tell you which.

---

## Daily startup

If you run the agent regularly, do this each morning:

```bash
sovereign doctor                 # quick health check
sovereign events -n 5            # see what happened last
sovereign lessons -n 3           # see what was learned
```

Three commands. Tells you everything you need to know to start the day.

---

## How to write goals the agent can actually execute

The agent's biggest failure mode is loop-bouncing on vague goals. Here are the patterns that work and the patterns that don't.

### Patterns that work

**Direct tool invocations:**
> "Use list_dir on ~/AA-Erebo/Genesis-Seeds/Genesis-Seed/. For each file you find, append a line to ~/notes/inventory.md."

**Concrete state goals:**
> "Read /etc/hostname and write its contents to ~/hostname_backup.txt. Stop."

**Sequenced steps:**
> "Step 1: list_dir on ~/projects. Step 2: For each .py file, read its first 50 lines. Step 3: Write a one-sentence summary to ~/projects/INDEX.md. Stop after all .py files are processed."

**Stop conditions:**
> "...Stop after 30 files have been processed OR after 60 minutes elapsed, whichever comes first."

### Patterns that don't work

**Vague exploration:**
> ✗ "Look at my work and tell me what I should do next."

The agent doesn't know what "look at" means or what scope. It will ask for clarification.

**Multi-stage planning:**
> ✗ "Distill all 1557 files in Genesis-Seeds intelligently."

The agent at v0.2.4 cannot maintain a 1557-file project plan. Break it into phases (see `DISTILLATION_PLAN.md`).

**Open-ended questions:**
> ✗ "What is the best way to approach this?"

Conversational questions get conversational answers. They don't trigger tool use.

**Implicit context:**
> ✗ "Review the files."

Which files? Where? For what? Be explicit.

---

## Three usage patterns

### Pattern A — Quick task (2-5 minutes)

Use `--mode oneshot`. The agent does one thing, reflects, exits.

```bash
sovereign run --mode oneshot "Read /etc/hostname and tell me what it says. Stop."
```

Good for: checking files, simple writes, quick lookups.

### Pattern B — Bounded session (30-90 minutes)

Use `--mode timed`. The agent works on a goal until time runs out.

```bash
sovereign run --mode timed --minutes 60 "Inventory ~/AA-Erebo/Genesis-Seeds/Genesis-Seed/ConsiderableStartingpoint/. For each file, write a line to ~/inventory.md with: <path>, <size>, <one-line purpose>. Stop after 60 minutes."
```

Good for: medium-scope work, exploration with a time bound, anything you'd want to interrupt with a coffee break.

### Pattern C — Continuous mode (hours to days)

Use `--mode live`. The agent stays alive, drains backlog, reflects, continues.

```bash
sovereign run --mode live "Process tasks from ~/AA-Erebo/Genesis-Seeds/distilled/backlog.md one at a time. Mark each as done after completion. Stop only when backlog is empty or sovereign halt is called."
```

Good for: well-staged work where you trust the agent. Always have `sovereign halt` ready.

**Don't use Pattern C until:**
- You've successfully run Patterns A and B on similar work
- You have a clear backlog file the agent can drain
- You've watched `sovereign tail` long enough to trust how it's behaving

---

## Watching what the agent does

In another terminal:

```bash
sovereign tail
```

This streams events as they happen. You'll see:
- `trace-start-d` — agent received a goal
- `ingest-d` — goal parsed
- `model-d kind=plan` — agent reasoning about what to do
- `tool-d` — actual tool invoked, with payload
- `model-d kind=dispatch` — agent finalizing response
- `reflect-d` — lesson distilled
- `trace-end-d` — done

If you see lots of `model-d kind=plan` events with no `tool-d` events between them, the agent is loop-bouncing. Halt it and rephrase the goal more concretely.

---

## When something goes wrong

### "Tasks return immediately with vague responses"

The agent decided the task was conversational. Make the goal more concrete with explicit tool names or file paths. Add "Stop." at the end.

### "Tool calls fail with permission errors"

Either:
- You asked it to write outside the sandbox (default sandbox is `~/.local/share/sovereign-agent/sandbox/`)
- You asked it to do something Tier 2+ without approval

Check `sovereign approvals` for pending requests. Approve or deny.

### "Agent hangs for minutes"

Possible causes:
- Ollama is overloaded (check `nvidia-smi`)
- Model is slow on the current task
- Tool call is waiting on an external resource (web fetch timing out, etc.)

`sovereign tail` will usually show what's happening. If truly hung: `sovereign halt`. If halt doesn't work: `sovereign disarm`.

### "I see lessons being distilled but no real work happening"

The Reflector is firing on every iteration regardless of progress. If the agent loop-bounces 5 times, you'll see 5 lessons, none of them useful. Check tool-d events to see what tools actually got called. If none, the goal needs rewriting.

### "Memory db seems wrong / atoms not persisting"

```bash
ls -la ~/.local/share/sovereign-agent/atoms.db
sqlite3 ~/.local/share/sovereign-agent/atoms.db "SELECT COUNT(*) FROM atoms;"
```

Should grow as the agent works. If it's not growing, something's wrong with `memory_write`.

---

## Health metrics worth watching

After a real session of work:

```bash
sovereign events -n 100 | grep tool-d | wc -l       # how many tool calls
sovereign lessons -n 20                              # what was learned
ls -la ~/.local/share/sovereign-agent/sandbox/       # what was created
```

Healthy session: many `tool-d` events relative to `model-d kind=plan` events. Lessons that are specific (not generic). Sandbox files that match what you asked for.

Unhealthy session: many `model-d` events with few `tool-d` events. Lessons that are vague or repeated. Empty sandbox.

---

## Keeping the agent useful over time

**Run `sovereign seal` daily.** This produces a Merkle seal of the day's events. Audit checkpoint. There's a systemd timer that does this automatically if you've enabled it.

**Review lessons weekly.** Run `sovereign lessons -n 50` and skim. If lessons are vague or repetitive, the agent isn't learning useful things. The orchestrator model or the Reflector might need work.

**Don't accumulate too much in memory.** atoms.db can grow large. Periodically `sqlite3 ~/.local/share/sovereign-agent/atoms.db "SELECT COUNT(*) FROM atoms;"` — if it's > 10,000 atoms, consider archiving older ones.

**Keep events log under control.** events log grows fast in live mode. Rotate it monthly.

---

## Working with the distillation plan

If you're ready to begin Genesis-Seeds distillation:

```bash
# 1. Make the output directory
mkdir -p ~/AA-Erebo/Genesis-Seeds/distilled/repos
mkdir -p ~/AA-Erebo/Genesis-Seeds/distilled/documents
mkdir -p ~/AA-Erebo/Genesis-Seeds/distilled/godot

# 2. Read the plan
cat ~/AA-Erebo/Genesis-Seeds/sovereign-agent-v0.2.4/DISTILLATION_PLAN.md

# 3. Start Phase 1 (inventory)
sovereign run --mode timed --minutes 60 "<paste Phase 1 prompt from DISTILLATION_PLAN.md>"

# 4. After 60 min, check progress
ls -la ~/AA-Erebo/Genesis-Seeds/distilled/
wc -l ~/AA-Erebo/Genesis-Seeds/distilled/inventory.md

# 5. Repeat #3 (Phase 1 will take multiple sessions)
```

---

## When to escalate to a human (you, paying attention)

The agent should escalate when:
- It hits an approval-required action (Tier 2+) — this is automatic
- It encounters an unfamiliar tool error — happens in `events` log
- A reflection produces a lesson with low confidence — visible in `sovereign lessons`

You should escalate to yourself (i.e., stop and think) when:
- The same kind of failure happens twice
- A "successful" run produces no useful output
- You feel uneasy about what the agent just did but can't say why

The witnessing system principle applies: when something feels off, look more carefully before continuing.

---

## Closing

The agent is real. It runs. It's also v0.2.4 — capable but bounded. The runbook above is everything you need to actually use it for the next stretch of work.

When in doubt, the four moves are:

1. `sovereign doctor` (health check)
2. `sovereign tail` (see what's happening)
3. Rewrite the goal more concretely (most failures are goal-spec issues)
4. `sovereign halt` (stop cleanly)

That's the operational core. <3
