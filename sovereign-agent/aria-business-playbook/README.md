# aria-business-playbook — secular business/leadership/negotiation reference frameworks

## What this gives Aria

Kevin was given a free 69-page coaching deck ("Billion-Dollar Playbook" by Ryan Blair, AlterCall) and
asked whether anything in it was useful as a tool or framework for Aria's systems. Reviewed the full
deck (all 7 sections of its P.R.O.C.E.S.S. model: Prayer, Restriction, Oath, Communication, Excellence,
Skills, Service) and pulled out 23 genuinely useful, secular frameworks: purpose-setting, discipline,
communication, forgiveness, conflict de-escalation ("Reality Bridge"), trust-building, leadership,
hiring (A-Player rubric), org/strategy design, a 3-part negotiation playbook, pricing, and Elon Musk's
5-step engineering algorithm (Question → Delete → Simplify → Accelerate → Automate).

This is **reference knowledge Aria can look up**, not doctrine — it does not touch `mos_canon.py` or any
values/behavior gate.

**Who this affects:** Kevin directly, any time he asks Aria for help with negotiation, hiring, or team
leadership — and anyone Kevin negotiates or works with, since the tactics in the negotiation entries
(deployed silence, engineered "no" questions, pattern interrupts) are real persuasion techniques, not
neutral trivia. That's people affected on both sides of a conversation, not an abstraction — see
`business_playbook.py:1-14` for the sourcing/omission note this file inherits verbatim.

## What was deliberately left out

The deck's Prayer section (pp. 4-9: How to Pray, Letters to God, We'll See Mindset) and the Service
section's "Faith-Purpose-Service-Skills" framework (p. 66) are explicitly Christian devotional content
— left out entirely, not softened or rephrased, per Kevin's explicit direction. 3 otherwise-secular
frameworks had 1-2 religious bullets trimmed: Team Leadership's "Give all Glory to God" line (p. 41),
the Oath framework's "swear to the Creator" step (p. 14), and 2 prayer-to-God bullets inside the
negotiation script (part 5 of 17 on p.51, part 16 of 17 on p.62 — verified via `pdftotext`'s page splits
on Kevin's source PDF, not estimated). Every other line in those 3 entries is verbatim/faithful to the
source, checked line-by-line against the full extracted text during review.

Full inclusion/exclusion review lives in the approved plan
(`/home/kmon/.claude/plans/calm-inventing-muffin.md`, "What's IN vs OUT" table).

## Why it is safe

- **Reference only, not values.** `mos_canon.py` line count and its DEFERRED_UNSAFE catalog are
  untouched by this module — 0 lines changed there, confirmed by `git diff --stat` after apply. It's a
  lookup corpus for when Kevin asks for business/leadership/negotiation help, same shape as the 2 existing
  companion modules (`consumer_law_companion.py`, `real_estate_strategy.py`).
- **Deterministic, not generated.** All 23 entries in `PLAYBOOK` (see `business_playbook.py`) are
  hand-curated static data, keyword-routed via `find_frameworks()` — not an LLM re-deriving or
  embellishing the source on every question.
- **Honestly sourced.** Every one of the 23 entries carries the identical `SOURCE_NOTE` string
  attributing Ryan Blair/AlterCall and disclosing that religious content was omitted — verified by
  `test_every_entry_has_honest_source` in `tests/test_business_playbook.py`.
- **Reversible.** 3 new files (`business_playbook.py`, `tools/business_playbook_tools.py`,
  `tests/test_business_playbook.py`); the 1 shared file touched (`tools/__init__.py`) is patched
  idempotently with a timestamped `.bak` backup, matching `aria-workflow-wire/apply_workflow_wire.sh`'s
  established pattern.

## Payload

- `payload/src/sovereign_agent/business_playbook.py` — the `Framework` dataclass, the curated
  `PLAYBOOK` tuple, and `find_frameworks(query, category=None)`.
- `payload/src/sovereign_agent/tools/business_playbook_tools.py` — `BusinessPlaybookTool` (T0,
  read-only lookup).
- `tests/test_business_playbook.py` — keyword-routing tests, tool-registration tests, and a content
  regression guard that fails if any religious term ("creator", "pray", "god", "amen", "scripture",
  "heavenly father") ever leaks into the corpus.

## Verify

```bash
./scripts/verify_module.sh aria-business-playbook
./scripts/pre_apply_gate.sh aria-business-playbook
./scripts/safe_apply.sh aria-business-playbook
.venv/bin/python -m pytest tests/test_business_playbook.py -v
```
