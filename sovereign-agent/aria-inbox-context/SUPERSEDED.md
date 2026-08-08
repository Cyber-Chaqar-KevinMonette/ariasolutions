# ⚠ SUPERSEDED — DO NOT RUN THE APPLY SCRIPT

**Status (2026-07-04, gym-round triage):** this module's intent (the missing
`priority`/`due()`/`short_id`/`context_lines()` members that silently broke
the cockpit inbox pane) was fully re-implemented and applied to live on
2026-07-03 by **`aria-dual-inbox/`**, whose full-file replacement of
`workflow/requests.py` included these exact fixes plus the new
`direction` column.

**Why this one must never be applied as-is:** its reference payload for
`cockpit/app.py` is **2,682 lines vs the current live ~5,400+** — it
predates the P0 restore and every cockpit workstream since. Running its
apply script would silently destroy months of cockpit work (the exact
`8fc7267` failure shape).

Kept as provenance only. Inbox work continues in `aria-dual-inbox/` and
live `workflow/requests.py`.
