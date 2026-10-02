# CLAUDE.md — ariasolutions repo root

The main project is **`sovereign-agent/`** (Aria). Before changing anything, read:

1. `sovereign-agent/CLAUDE.md` — binding rules for working in Aria
2. `sovereign-agent/CHANGE_RULES.md` — every change ships with tests, changelog, handoff, audit and
   advocate reports
3. `sovereign-agent/FOR_CLAUDE_CODE_FROM_CLOUD_CLAUDE.md` — the handoff log between sessions; newest entry
   first

Run commands from `sovereign-agent/` with `.venv/bin/python` (create it with `uv sync --group dev`).

## Where things live (confirmed 2026-10-02)

- **Website source (ariasolutions.org — courses, store, terms, etc.):** `~/AA-Erebo/sovereign-agent/web/`
  on Kevin's machine (React/TSX, pages in `web/src/pages/public/`, e.g. `CoursesPage.tsx`,
  `StorePage.tsx`, `TermsPage.tsx`). **As of 2026-10-02 it is NOT in any GitHub repo.** Only its compiled
  output was copied to `sovereign-agent/site/`. Committing and pushing `web/` is priority #1, from a
  private repo, with no `.env` files, `node_modules/` or `dist/`.
- **Legal entity:** ARIA SOLUTIONS LLC (Kentucky, filed 2026-09-30), with an EIN. Brand "BigKev's Bot Shop"
  needs a filed assumed-name certificate.
- **Launch checklist:** the "Aria Solutions LLC — Launch Readiness Review" doc
  (https://claude.ai/code/artifact/cc09ba0e-f2d9-47ca-883d-f7639e730961).
