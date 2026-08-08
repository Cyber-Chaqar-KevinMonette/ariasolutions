# aria-engineering-playbook — index over wondelai/skills software-engineering frameworks

## What this gives Aria

Kevin pointed at `github.com/wondelai/skills` (MIT license, 1.8k stars) and asked where its content
could enhance Aria's own frameworks, workflows, and tools. It's 62 Claude Code skills distilled from
named books (Clean Code, DDIA, System Design, Domain-Driven Design, Release It!, Team Topologies, etc.)
plus 12 "metaskills" — resumable guided journeys. Two moves came out of that review: the marketplace
itself was installed in `~/.claude/settings.json` (3 plugin bundles: `code-craftsmanship`,
`systems-architecture`, `metaskills`) for direct slash-command use, and this module is the companion —
an Aria-internal **index** over the 12 engineering skills, so Aria herself can recall and cite the right
framework by name when helping design or build sovereign-agent, not only when a human happens to invoke
the skill first.

## Why it is an index, not a reproduction

Each of the 12 entries in `engineering_playbook.py` carries exactly two things taken from the real
skill: its "Core Principle" sentence and its numbered discipline list (e.g. Clean Code →
Meaningful Names / Functions / Comments and Formatting / Error Handling / Unit Testing / Code Smells).
It does not reproduce the worked examples, code tables, or scoring rubrics that make up the rest of
each `SKILL.md` — that full depth lives in the actual skill, one `Skill wondelai-skills:<slug>`
invocation away now that the marketplace is installed. This keeps the two moves complementary instead
of duplicative: the marketplace install is the depth layer, this module is the recall layer.

## Why it is safe

- **Reference only, not values.** `mos_canon.py` line count is untouched by this module — 0 lines
  changed there, the same guarantee `aria-business-playbook` already established for this pattern. This
  is an index over engineering craft (naming, refactoring, architecture, resilience), not a change to
  Aria's own doctrine.
- **Deterministic, not generated.** All 12 entries in `PRINCIPLES` are static data, keyword-routed via
  `find_principles()` — same discipline as `business_playbook.py` and `consumer_law_companion.py`, 0
  LLM calls involved in a lookup.
- **Honestly sourced.** Every one of the 12 entries' `.source` property names the real `skill_slug` and
  states explicitly that it's an index, not the full framework — verified by
  `test_every_entry_names_its_real_skill_and_source` in `tests/test_engineering_playbook.py` (13 tests
  total).
- **MIT licensed source, properly attributed.** `SOURCE_REPO` names `wondelai/skills` directly; the
  repo has 1.8k stars and was last updated 2026-08-02, per `gh api repos/wondelai/skills`.
- **Reversible.** 3 new files; the 1 shared file touched (`tools/__init__.py`) is patched idempotently
  with a timestamped `.bak` backup, matching `aria-business-playbook`'s and
  `aria-workflow-wire/apply_workflow_wire.sh`'s established pattern.

**Who this affects:** Kevin, whenever he or Aria are designing or reviewing sovereign-agent code —
the disciplines this index recalls (naming, module boundaries, resilience patterns, team ownership)
directly shape how future contributors experience the codebase.

## Payload

- `payload/src/sovereign_agent/engineering_playbook.py` — the `Principle` dataclass, the curated
  `PRINCIPLES` tuple (12 entries across 2 categories: `code-craftsmanship`, `systems-architecture`),
  and `find_principles(query, category=None)`.
- `payload/src/sovereign_agent/tools/engineering_playbook_tools.py` — `EngineeringPlaybookTool` (T0,
  read-only lookup).
- `tests/test_engineering_playbook.py` — keyword-routing tests, tool-registration tests, and a
  source-honesty test.

## Verify

```bash
./scripts/verify_module.sh aria-engineering-playbook
./scripts/pre_apply_gate.sh aria-engineering-playbook
./scripts/safe_apply.sh aria-engineering-playbook
.venv/bin/python -m pytest tests/test_engineering_playbook.py -v
```
