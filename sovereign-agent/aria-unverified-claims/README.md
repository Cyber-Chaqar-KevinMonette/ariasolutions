# aria-unverified-claims — prove the say-so, don't just print it

> Staged / reversible / propose-only. Sourced from reading `long-running-agent-main`
> (MIT license) in the hardware-liberation zip corpus (`Plans/p-plans-hardware-liberation/zippedfolders/`).

## Where this came from

Kevin asked for a full pass over 225 archived repos: extract value, integrate what's real, then clean
up the zips. Most of the corpus turned out to be reference/tutorial material Aria's architecture already
independently matches — but `long-running-agent-main` names one real, concrete practice Aria's session
loop doesn't have: **"never trust the model's say-so, only real test/lint/build/typecheck results."**

`agent_session.py` marks a subtask `status = "done"` purely from `loop_result.ok` — the model's own
verdict on its own work (`agent_session.py:1252`). Nothing cross-checks that against what the subtask's
own action trace actually did.

## What this module does

It does **not** touch that completion gate — that's a load-bearing session path, deliberately left alone
here, the same way `aria-review-journal` shipped its library before touching the session close-out hook
as its own separate, reviewed patch.

Instead it adds one independent, additive honesty check to the review doc: does a subtask's own
`result_summary` claim verification ("tests pass", "all green", "confirmed working"...) that its own
trace never actually performed (no pytest/lint/build/verify-shaped tool call under that subtask's
`trace_id`)? If so, it's flagged plainly in `reviews/<session_id>/README.md`, right next to the sentinel
warnings — the same grounded-truth standard `scout_verify.py` already applies to retailer web pages
(✓ verified / ⚠ unconfirmed, never a faked green check), applied here to Aria's own claims about her
own work.

## Apply

```bash
./aria-unverified-claims/apply_unverified_claims.sh
```

Requires `aria-review-journal` already applied (patches its `render_readme()`). Reversible: restore the
backed-up `review_journal/__init__.py` and delete `src/sovereign_agent/unverified_claims.py` + its test.

## Verify before applying

```bash
./scripts/verify_module.sh aria-unverified-claims
```
