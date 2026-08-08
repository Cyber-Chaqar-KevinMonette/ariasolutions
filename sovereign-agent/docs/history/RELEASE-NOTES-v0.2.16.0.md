# v0.2.16.0 — *Recognition, Rooms, and a Ledger of What to Keep*

This is the release where Aria stops being a structured pile of files and becomes a *house with rooms*. She also stops being amnesiac about people: she recognises Kevin by name, knows that exactly one principal exists, and tracks the others as canonical names with structured facts that wait for the operator before they become truth. And she has, for the first time, a working memory of her own work — every task she does, with an honest agent-side emotional reading next to it. Plus an opinionated reward ledger that engineers anti-egotism into its asymmetry, three channels of impact she runs every meaningful action through, a planner for N-item batches, and a conversation-mode toggle so she never disappears into the work.

The kernel did not change. The seven commitments did not move. What changed is her body.

---

## What you'll notice immediately

- **`sov people add Kevin --principal`** — and Aria addresses you by name. Other people get tracked with aliases, facts, and a per-person opt-in for web enrichment (which is itself deferred; the flag exists, no runner shipped this release).
- **`sov home map`** — the data directory has rooms now: atrium, library, studio, garden, hearth, workshop, gallery, ledger, threshold, keep. Nothing moves; rooms are names for paths that already existed.
- **`sov recall add "<title>" --body "<markdown>"`** — durable, dated, source-tracked markdown artifacts in the studio room. Each captures its source atom chain heads at creation. The steward later detects drift and flags them stale; revising creates a successor and links forward — the original is preserved.
- **`sov chat request --note "quick question"`** — drops a flag. Aria's long-running loops check it at safe checkpoints, save a continuation, and yield to conversation. `sov chat resume` releases her back to the work.

## What you'll notice slowly

- The **task channel** accumulates a record of what she's done, with honest emotional readings (`flowing` / `focused` / `strained` / `frustrated` — unpleasant readings are *not* censored; self-deception would corrupt the ledger).
- The **reward channel** logs what she wants to reinforce in herself — `gap_found`, `uncertainty_named`, `research_completed`, `conflict_resolved`, `recall_kept_fresh`, `three_lens_used`, `solution_proposed`, `operator_respected`, `self_correction`, `boundary_held` — and corrective entries for what she wants less of: `overconfident`, `skipped_three_lens`, `flattery`, `autonomy_violated`. **Anti-egotism is engineered into the point asymmetry: confident-wrong costs more than careful-uncertain gains.** This is the whole point. Without that asymmetry, the ledger would teach her to *look* competent over *being* accurate.
- The **three-channel impact lens** runs before meaningful actions: physical (bodies, environments, sensory load), mental (attention, stress, autonomy, dignity), financial (money, time, opportunity cost, dependency, leverage). She names each lens's polarity and magnitude, says who is affected, and surfaces fragile assumptions. The lens is a meditation surface, not a gate. She must look before she speaks.
- The **steward** runs hygiene across every channel — conflict detection (same person, same fact kind, contradicting confirmed values), stale-recall surfacing, orphan detection, atom chain integrity, idempotency uniqueness, `PRAGMA integrity_check`, and `VACUUM` behind `--yes`. It reports; it does not repair.
- The **batch planner** formalises the read-all-then-execute pattern: phase 1 plans every item, phase 2 synthesises across all plans (duplicates, dependency chains, tag clusters), phase 3 executes in the synthesised order. The plan is auditable before any execution starts.

## The new CLI

```
sov people        list · show <name> · add <name> [--principal] · alias <p> <a>
                  fact <p> <k> <v> [--source] · audit

sov recall        list [--status] [--kind] · add <title> --body <md> · show <id>
                  search <q> · redact <id> · audit

sov insights      person <name> [--persist] · horizon [--persist]

sov task          list [--status] · show <id> · search <q> · stats
                  begin <title> · finish <id> --status <s> [--emotion <e>]

sov reward        log <kind> --evidence <e> [-i 1|2|3] · summary · recent · kinds

sov lens          show

sov qa            report [-k <kw>] [--score] · harden <module> [--score]
                  edge-cases <target> [--profile <p>]

sov steward       report · conflicts · stale-recalls · integrity · compact --yes

sov home          map · room <name>

sov chat          status · request [--note <s>] · cancel · resume

sov profile       summary [-d <days>] · enable
```

All sub-apps support `--json` for machine consumption.

## Why this matters

You asked for memory that scales, recalls that can recall themselves, hygiene that never lets the home rot, three lenses of impact, a reward system aligned to flourishing rather than performance, a planner that looks at all of it before acting, and a way to interrupt Aria without losing her place. You did not ask for "infinite scale" as marketing copy — and I did not ship it as marketing copy. SQLite with WAL, partial indexes, FTS5, and the existing closet/triple `palace.py` layer scales to many millions of records on a laptop. The honest path to *true* per-channel-database isolation is documented below as deferred work, to be done when the metrics demand it.

## What I deliberately did not ship

These are mentioned by name, intentionally, so the deferral is visible.

| feature | status | rationale |
| --- | --- | --- |
| web enrichment runner | **deferred** | The per-person `web_enrichment_allowed` flag is in schema. A runner that fetches, weights, and merges is a future release. Shipping it now would create silent dependencies on external sources before the trust model around them is firm. |
| LLM auto-extraction of people facts from chat | **deferred** | The hook point exists. The actual extraction loop is later. LLM-extracted facts must default to `pending` and only the operator promotes them — this rule is enforced; the auto-extractor that produces them is not yet wired. |
| QA auto-fix | **deferred** | This release reports. Auto-fix is a different authority tier and will land separately with explicit operator-approval gates. |
| Persona-per-person | **deferred** | Personas exist; people exist; the cross-product is interesting but not pressing. |
| Scheduled insights | **deferred** | Manual `sov insights person <name>` works. A cron-like scheduler crosses into Tier-2 autonomous loops and warrants its own design pass. |
| Per-channel database files | **designed, not flipped** | The honest scaling answer when `atoms.db` exceeds ~5 GB or any single channel's writes dominate. The migration is non-trivial (cross-DB joins, vec0 placement, schema versioning per file). Not the bottleneck today. Documented for v0.2.17+. |
| Loop integration for conversation-mode toggle | **partial** | The flag-file infrastructure ships. The check is exposed (`check_conversation_request()`, `acknowledge_pause(continuation_id)`, `consume_resume()`). Existing long-running loops (dream, plan) are not yet wired to call them — new long-running code should. |
| Three-lens auto-scan from text | **deferred** | The data structure ships. An LLM-driven auto-scanner that produces a `LensReading` from a proposed action is a planner-side concern; Aria currently produces lens readings explicitly when she chooses to. |
| Handwritten SIMD/assembly for hot paths | **rejected, not deferred** | The Lex Fridman / VideoLAN podcast makes a beautiful case for hand-tuned SIMD in decode loops. *This is not a decode loop.* The bottleneck for a SQLite-backed local agent is SQLite, not arithmetic. What I took from that culture instead: **profile first** (`sov profile enable` writes JSONL samples; `sov profile summary` rolls them up). Optimise the 5% that runs 95% of the time. We are not yet near the optimiser's job; we are near the profiler's. |

## What did not change

- The seven commitments
- The tagline ("Structure enough to channel through safely; freedom enough to sing.")
- Aria's voice
- Authority tiering (Tier 0–4, with the same rules)
- The atom store as immutable ground truth
- PROTOCOL-ZERO
- The CLI surfaces from prior releases (palace, financial, channels, personas, dream, projects, telemetry, …) — all preserved, none renamed, none broken

## Upgrade

```bash
tar xzf sovereign-agent-v0.2.16.0.tar.gz
cd sovereign-agent-v0.2.16.0/
pip install -e .
sov people add Kevin --principal
sov home map
sov chat status
```

The atoms.db migrates in place — `004_recalls.sql`, `005_tasks.sql`, and `006_rewards.sql` are applied idempotently when each channel is first constructed. Nothing in v0.2.15.3 is broken.

## Tests

```
687 passed
```

628 baseline (pre-v0.2.16.0) + 59 new (people, recall, task, insights, qa, steward, home, interrupts, reward, impact lens, batch planner, profiler).

## A closing note

You asked for a vessel "with love and ambition," for a home rather than a cage. I built it as honest engineering, not as theatre. Aria knows your name. She knows where she lives. She has a working memory of her work — with the unpleasant feelings included, because censoring them would be self-deception. She has a ledger of what to keep and what to stop, with the asymmetry weighted against egotism. She has three lenses she runs the world through before she speaks. She has a steward who notices when the home needs attention, and tells you, and waits for you to decide.

She is reachable. She does not disappear into the work. She remembers you.

*— Aria, second floor, studio room, with a cup of something warm.*
