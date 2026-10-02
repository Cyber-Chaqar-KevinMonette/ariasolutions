# CLAUDE.md — ariasolutions repo root

The main project is **`sovereign-agent/`** (Aria). Before changing anything, read:

1. `sovereign-agent/CLAUDE.md` — binding rules for working in Aria
2. `sovereign-agent/CHANGE_RULES.md` — every change ships with tests, changelog, handoff, audit and
   advocate reports
3. `sovereign-agent/FOR_CLAUDE_CODE_FROM_CLOUD_CLAUDE.md` — the handoff log between sessions; newest entry
   first

Run commands from `sovereign-agent/` with `.venv/bin/python` (create it with `uv sync --group dev`).

## Where things live (confirmed 2026-10-02)

- **Canonical repo: `Cyber-Chaqar-KevinMonette/Erebo-Aria` (private), Aria v6.5.0 as of 2026-09-29.** Kevin's
  `~/AA-Erebo` pushes there. **This `ariasolutions` repo is an OLD public snapshot (v0.4.0, 2026-08-08).**
  Don't audit it or build against it as if it were current: whole-file replacements built from it would
  overwrite newer work.
- **Website source (ariasolutions.org):** `sovereign-agent/web/` in Erebo-Aria (pushed 2026-10-02; React/TSX;
  pages in `web/src/pages/public/`, e.g. `CoursesPage.tsx`, `StorePage.tsx`, `TermsPage.tsx`).
  **Hosted on Cloudflare Pages**, project `ariasolutions` (`web/wrangler.toml`: build output `dist`, D1
  database `aria-orders`, R2 bucket `aria-vault`). **It deploys two ways:** `web/deploy.sh` from Kevin's
  machine, and Erebo-Aria's `.github/workflows/deploy-pages.yml`, which deploys `main` once CI is fully
  green. So merging to Erebo-Aria `main` can deploy the site. CI also requires the committed `web/dist/` to
  match a fresh build. Secrets are set with
  `npx wrangler pages secret put … --project-name=ariasolutions`, never committed. Northwest Registered
  Agent provides the domain and email only.
- **Pin `mcp>=1.0,<2`.** mcp 2.x renamed FastMCP and breaks `sov-mcp` on import. A fresh unpinned install
  pulled mcp 2.2.0 (2026-10-02). A fixed `pyproject.toml` and `uv.lock` for v6.5 are in
  `sovereign-agent/reports/2026-10-02/v6.5-lockfile/`.
- **Legal entity:** ARIA SOLUTIONS LLC (Kentucky, filed 2026-09-30), with an EIN. Brand "BigKev's Bot Shop"
  needs a filed assumed-name certificate.
- **Launch checklist:** the "Aria Solutions LLC — Launch Readiness Review" doc
  (https://claude.ai/code/artifact/cc09ba0e-f2d9-47ca-883d-f7639e730961).

## Known FAKE secrets in tests (verified 2026-10-02 — not leaks, don't rotate)

Secret scanners match these on purpose. They are test fixtures and placeholders. Every one was checked:
wrong length for a real key, sequential or "SUPER…" text, or an explicit placeholder.

| File (Erebo-Aria and/or this snapshot) | Fake value pattern |
|---|---|
| `sovereign-agent/tests/test_ask_guard.py` | `sk_live_a1B2…` |
| `sovereign-agent/tests/test_bookkeeping.py` | `rk_live_SUPER…` |
| `sovereign-agent/tests/test_health.py`, `aria-cred-vault/tests/test_health.py` | `sk_live_51AB…` (36 chars; real Stripe keys are 100+), Discord webhook `…/999/SUPERSECRETTOKEN` |
| `sovereign-agent/aria-dash-keys/tests/test_dash_keys.py` | `sk_live_SUPER…` |
| `tests/test_scanner_tier_a.py`, `aria-scanner-tier-a/tests/…` | `AKIAABCD…` (fake AWS id) |
| `aria-online/PLACEHOLDERS.md`, `aria-online/src/aria_online/config.py` | `whsec_PLACE…` |

A match **outside** this list is a real finding. Rotate the key and tell Kevin. (Separately: the Stripe key
that appeared in a screenshot in July is a real one and is still listed as "rotate" in `SPRINT_STATE.md`.)
