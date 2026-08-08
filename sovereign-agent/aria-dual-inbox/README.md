# aria-dual-inbox — Workstream O: dual inbox (Aria → human, human → Aria)

**Kevin's ask:** *"add another Inbox-to-human directory so there is an inbox for Aria and an inbox
for me"* and *"an inbox where she can send stuff to the user so she can send me stuff."*

## What was found vs. what's new

The Aria → human direction already existed: `workflow/requests.py`'s `RequestStore` (SQLite,
`human_requests` table) is a directional "Aria posts, human answers" channel, surfaced in the
cockpit's inbox pane. It was silently broken — the live inbox pane called `rs.due()`, `r.priority`,
`r.short_id`, `r.context_lines()`, none of which existed on the then-live `requests.py` (a partial
apply: an old `app.py` already expected these from a prior pass of `aria-inbox-context`, but
`requests.py`/`cli.py` never got that pass). This module folds in that fix AND adds the genuinely
new part: a `direction` column (`to_human` | `to_aria`, default `to_human` — every row ever written
keeps its exact original meaning) plus the reverse channel Kevin asked for.

## What this ships

- `workflow/requests.py` (full-file replacement, self-contained) — `direction` field + migration
  (`ADD COLUMN`, safe on existing data), `send_to_human()`, `tell_aria()`, `list_for_aria()`, and
  `direction=` filter params on `list`/`list_open`/`open_count`.
- `cli.py` — anchored **span** replacement of only the `requests_app` typer sub-app (not a full-file
  replace — cli.py is ~11k lines and evolves fast). Adds `--direction` to `list` and a new `tell`
  command (`sov requests tell "<title>"` — the human's own way to leave Aria a note).
- `cockpit/app.py` — anchored **span** replacement of only `_refresh_inbox_pane`'s body. Splits the
  pane into "◊ N waiting on you" (to_human, unchanged in substance) and "→ Aria" (to_aria, new).
- `tools/inbox_tools.py` (new) — `SendToHumanTool` (Aria's first tool-call path into the inbox —
  previously nothing wrapped `RequestStore.open()`) and `ReadInboxTool` (Aria checks what Kevin left
  for her — meant to be called at a safe checkpoint, not mid-task).
- `tools/__init__.py` — anchored import + `__all__` patch, both in one step (the H4/L lesson: a
  missing `__all__` entry is a real, recurring bug class in this codebase).

## Why span replacement, not full-file, for cli.py/app.py

Both files are large and change constantly. A full-file replacement (as `aria-inbox-context`'s own
apply script does) risks clobbering unrelated content added since any reference payload was
captured — confirmed concretely: `aria-inbox-context`'s own `app.py` payload is 2,682 lines vs the
current live 4,894 (it predates the P0 restore's cockpit growth). `patcher.py`'s span replacements
touch only the exact, uniquely-anchored block that matters; everything else is byte-for-byte
untouched (tested explicitly in `test_patch_app_inbox_leaves_everything_else_byte_identical`).

## Tests (16 module tests + 8 patcher tests, all passing pre-apply)

`tests/test_patcher.py` — all three patches apply cleanly against the CURRENT live files, are
idempotent, and the patched result compiles; the app.py patch is proven to leave everything outside
the method byte-identical. `tests/test_dual_inbox.py` — migration safety (a hand-inserted
pre-`direction` row still reads as `to_human`), `send_to_human`/`tell_aria` land in the correct and
only the correct direction list, `list_for_aria` matches `list_open(direction=to_aria)`,
`open_count` respects direction, and `SendToHumanTool`/`ReadInboxTool` round-trip correctly.

Reversible: restore the 4 backed-up files, `rm src/sovereign_agent/tools/inbox_tools.py`.
