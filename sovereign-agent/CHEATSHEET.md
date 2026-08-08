# sov CHEATSHEET

> Every command Aria responds to, grouped by what you're trying to do.

---

## When something feels wrong

```bash
sov doctor                          # comprehensive diagnostic
sov doctor --fix                    # auto-fix what's auto-fixable (backfill migrations)
sov info                            # paths, version, atoms.db state
sov --version                       # what's on PATH right now
```

---

## Day one — first run

```bash
sov init                            # create config + data dirs, set keys
sov constitution list               # see Aria's seven commitments
sov people add Kevin --principal    # tell Aria who you are
sov heartbeat pulse "first pulse"   # her first liveness mark on this machine
```

---

## Daily — talking to her

```bash
# Natural language (v0.2.30.0+) — the easiest doorway
sov ask "my back hurts today"            # LLM-backed; she reads, decides, responds
sov ask "what do I have on rollbacks?"   # she'll search memory and tell you
sov ask --no-llm "hello"                 # offline-honest fallback (no Ollama needed)
sov ask --no-route "test"                # interpret only; no side effects

# Cockpit — the long-form home
sov-chat                            # full cockpit TUI (default)
sov chat                            # same; alias
sov chat status                     # is she paused waiting for conversation?
sov chat request --note "got a sec?"  # interrupt a long task to talk
sov chat resume                     # ok, back to work

# Deterministic keyword parsing — when you want exact dispatch
sov do "build trillion-dollar software"
sov do "pause my dream"
sov do "show status"
```

---

## People & relationships

```bash
sov people list                     # everyone Aria knows
sov people show <name>              # detail page for one person
sov people facts <name>             # what Aria knows about them
sov people as-of <name> 2026-01-01T00:00:00Z   # bitemporal: what she knew on that date

sov relationships connect Kevin colleague Mike
sov relationships path Kevin Feynman         # BFS through the graph
sov relationships neighbours Kevin           # all of Kevin's edges
```

---

## Memory & retrieval

```bash
sov recall search "X"               # FTS over recalls
sov recall record --title "X" --body "..."
sov recall verify <id>              # mark verified
sov recall list --stale             # what needs re-checking

sov episode open "Wed merge work" -s 2 --tags build,merge
sov episode add <id> task <task_id> --role primary
sov episode close <id> -s "figured out canonical-first rule"
sov episode search "merge"
```

---

## Work tracking

```bash
sov task add "Ship the report"      # opens a task
sov task list --status open
sov task done <id> --status success --lessons "..."
sov task lessons --from failed      # surfaces what didn't work and why
```

---

## Reasoning (chain-of-thought)

```bash
sov reasoning open "Should I X?" 
sov reasoning step <id> observation "I notice Y"
sov reasoning step <id> hypothesis "Maybe Z" -c 0.7
sov reasoning step <id> evidence "Found data point W" --sources "at-abc,rc-def"
sov reasoning step <id> counter_evidence "But also..." 
sov reasoning conclude <id> "Yes, X — because Z, despite W" -c 0.85
sov reasoning show <id>             # full trace, render in voice
sov reasoning search "sharding"
sov reasoning audit                 # finds high-confidence conclusions without evidence
```

---

## Gaps (known unknowns)

```bash
sov gaps open "What does Kevin's new job involve?" -p 2 --domain person
sov gaps investigate <id>           # mark in-progress
sov gaps close <id> -r "Asked Kevin directly; he's doing X"
sov gaps shelve <id>                # defer indefinitely
sov gaps list --priority 3          # only high-priority
sov gaps stats                      # close rate, breakdown
```

---

## Commitments (promises with due dates)

```bash
sov commitments make "Ship by Friday" --by aria --to operator \
    --due 2026-05-22T17:00:00Z -p 3
sov commitments start <id>          # mark in-progress
sov commitments keep <id> -r "Shipped on Thursday"
sov commitments break <id> -r "Underestimated scope"      # resolution required
sov commitments release <id> -r "Kevin said never mind"
sov commitments due-soon --within 7
sov commitments overdue
sov commitments stats               # keep rate
```

---

## Heartbeat (liveness pulse)

```bash
sov heartbeat pulse "building the merge logic, feels right" \
    --emotion absorbed --note "this is meaningful"
sov heartbeat recent -n 10          # last ten pulses, age relative to now
```

---

## Reward

```bash
sov reward add gap_found 2 --note "discovered cycle in episode chains"
sov reward list --kind gap_found
sov reward intensity-budget         # has she been over-rewarding herself?
```

---

## Provenance — show your work

```bash
sov provenance <node_id>            # walk backward through everything that informed it
sov provenance <node_id> --max-depth 10 --json
```

Works on any atom_id, fact_id, recall_id, task_id, episode_id.

---

## Constitution

```bash
sov constitution list               # the seven commitments + which have automated checks
sov constitution check --tier 3 --confidence 0.95 --source operator --idem foo
```

---

## Schema (migrations)

```bash
sov migrations status               # what's applied vs pending
sov migrations apply                # apply pending (auto-backfills first)
sov migrations apply --dry-run      # what WOULD be applied
sov migrations backfill             # explicit: detect existing schema, mark applied
```

---

## Storage scale-out

```bash
sov shards list                     # currently configured shards
sov shards add task                 # declare task channel → its own DB
sov shards migrate task --tables task_records,task_lessons --drop
```

---

## Archive (content-addressed blobs)

```bash
sov archive stats                   # total objects, bytes, sealed count
sov archive verify                  # re-hash every blob, confirm no tampering
sov archive verify <hash>           # one blob
sov archive gc --dry-run            # what would be reclaimed
sov archive gc                      # delete unreferenced unsealed blobs
```

---

## Backup & integrity

```bash
sov backup snapshot --label pre-upgrade
sov backup list
sov backup verify <id>              # re-hash, confirm intact
sov backup restore <id>             # staged audit, then swap

sov steward report                  # full audit pass across every channel
sov steward integrity               # SQLite PRAGMA integrity_check
sov steward compact --yes           # VACUUM + ANALYZE
```

---

## Reflection & introspection

```bash
sov dream status                    # last dream cycle, current scaffolds
sov insight list --recent           # what she's synthesized lately
sov insight reflect-on <topic>      # ask her to think harder about something
sov palace scan                     # corpus health snapshot
```

---

## Performance

```bash
sov profile enable                  # turn on disk samples (off by default)
sov profile disable
sov profile tail -n 20              # last 20 hot-path samples
sov profile summary                 # which paths cost the most time
```

---

## Telemetry (system load)

```bash
sov telemetry tail -n 20            # recent CPU/RAM/VRAM samples
sov telemetry summary               # today's min/avg/max
sov telemetry path                  # the JSONL file path
```

---

## QA & hardening

```bash
sov qa report                       # run the test suite, structured output
sov qa harden <module>              # static analysis against nine criteria
sov qa edge-cases                   # generated boundary/unicode/injection probes
```

---

## Halt

```bash
sov halt                            # PROTOCOL-ZERO; stops everything cleanly
sov halt clear                      # disarm
```
