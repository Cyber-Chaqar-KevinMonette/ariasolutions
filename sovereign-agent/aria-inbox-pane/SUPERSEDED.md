# ⚠ SUPERSEDED — DO NOT RUN THE APPLY SCRIPT

**Status (2026-07-04, gym-round triage):** the inbox pane this module adds
is already live — the cockpit has carried a 4th inbox pane for weeks, and
its current form (split "→ You" / "→ Aria" directional view) shipped via
**`aria-dual-inbox/`** on 2026-07-03.

**Why this one must never be applied as-is:** its payload contains a stale
full copy of `cockpit/app.py` that predates the P0 restore and every
cockpit workstream since; running the apply script would silently destroy
months of cockpit work (the exact `8fc7267` failure shape).

Kept as provenance only.
