# aria-curiosity-qa

Keys round K6 — Kevin: *"a Q&A feature where she comes up with god tier
questions and god tier answers when she is curious or wondering… also
observability so we can watch her work and do her Q&As."*

## What ships

- **`curiosity.py`**: one bounded wondering — a seed from what is ALREADY
  hers (open uncertainties from H3's registry are the purest spark, then
  recent Reflector lessons, then a gentle self-seed), a single model call
  forming a god-tier question AND answering it (the question-quality
  rubric lives in the prompt: opens a door, still matters in a year,
  proud to have asked). Durable in `qa/qa.ndjson` (append+fsync);
  `qa-start-d`/`qa-d` events render richly in the live pane (K1 shipped
  the renderers ahead of this module). **Low-confidence answers auto-open
  a new uncertainty** — wondering that fails honestly becomes a seed for
  next time; the wonder loop feeds itself without ever running unbounded.
- **`/wonder [topic]`** — the explicit invitation, any mode.
- **Idle autonomous wondering** — 30-min timer, gated HARD: work mode
  only, never while busy or mid-session, max 3/day, kill switch
  `SOV_NO_WONDER=1`. Reads memory, thinks, writes memory — never takes
  world actions.

## Verify / Apply

```
.venv/bin/python -m pytest aria-curiosity-qa/tests/test_patcher.py -q
./aria-curiosity-qa/apply_curiosity_qa.sh
```

Reversible: restore app.py from the timestamped `backups/` dir and remove
`curiosity.py` (qa.ndjson is inert history — hers to keep).
