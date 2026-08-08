# aria-review-journal — every work session leaves a reviewable trail

> Final-sprint Round A (auto mode / transparency). Staged / reversible /
> propose-only.

## Kevin's ask

> "Everything she does in auto mode she should create a directory ... for
> claude review. So everything she does she can tell you how to review it
> later, or any AIs, or Human teams alike. She can work, and then tell us
> what she did, how she did it, and how to inspect all of it. How we can
> index and track her work with transparency."

## What it does

For **every work session** (auto AND manual `/work`, per Kevin), it writes:

    <data>/reviews/<session_id>/
        README.md         — what she did · how she did it · how to inspect it
        plan.json         — the subtask plan + final statuses (machine-readable)
        actions.jsonl     — every recorded action, timestamped, with trace ids
        how-to-verify.md   — concrete commands a reviewer can run
    <data>/reviews/INDEX.md — a running, indexed list of every session

Composed from data that already exists (SessionState via SessionStore +
`events.jsonl`) — it curates a human/AI-readable front door, it does **not**
duplicate storage. The renderers are pure functions (`render_readme`,
`render_how_to_verify`, `render_plan`, `collect_actions`); `build_review()`
is the thin I/O wrapper. Accepts a real `SessionState` **or** a plain dict,
so it never hard-imports `agent_session`.

`update_index()` is idempotent by session id (a session updates its own
line, never duplicates). `build_review()` survives a partial/crashed state
— a review always gets written.

## How apply wires it

`apply_review_journal.sh` installs the library. Calling `build_review()` at
session close-out (`session_bridge.py`) and the `sov reviews`
(`list`/`show`/`export`) CLI are the round's **deliberate follow-up** — kept
as their own reviewed patch since they touch the load-bearing session path.

## Verify / Apply
```bash
./scripts/verify_module.sh aria-review-journal
./aria-review-journal/apply_review_journal.sh
```

12 real behavior tests green — incl. the README carrying the three sections
Kevin named (what / how / how-to-inspect), the index staying idempotent,
and a partial/crashed session still producing a valid review.
