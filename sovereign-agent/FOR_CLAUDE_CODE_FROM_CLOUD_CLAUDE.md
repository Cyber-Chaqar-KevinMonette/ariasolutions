# For Claude Code, from Cloud Claude

> The running handoff log between Claude Code sessions on Kevin's machine and Claude Code cloud sessions
> ("Cloud Claude"). Newest entry first. Format and rules: `CHANGE_RULES.md`. At session start, read the top
> entries and tick "Review status" for what you've checked.
>
> Getting these changes onto Kevin's machine: they're on GitHub,
> `Cyber-Chaqar-KevinMonette/ariasolutions`, branch `claude/admiring-dijkstra-3zhnih`, under
> `sovereign-agent/`. Pull or merge them into the working copy at `~/AA-Erebo/sovereign-agent`.

---

## 2026-10-02 (c) — Cloud Claude — found the website source; launch readiness review

### Found
- **The website source is `~/AA-Erebo/sovereign-agent/web/`** (Kevin's grep found `CoursesPage.tsx`,
  `StorePage.tsx`, `TermsPage.tsx`, `OrderPage.tsx`, `LearnPage.tsx`, … in `web/src/pages/public/`).
  - It's **never been committed.** Neither `ariasolutions` nor `Erebo-Aria` on GitHub has `web/`, and
    `.gitignore` doesn't exclude it. It exists only on Kevin's laptop.
  - `sovereign-agent/site/` holds only a compiled build (Erebo-Aria commit "Deploy new React marketing
    frontend to site/", 2026-08-08), including `.js.map` source maps. That build has no `/courses` or
    `/store` routes, so the live site is a newer build.
- **The `ariasolutions` GitHub repo is public.** Kevin is making it private. No personal address or
  secrets were found in it.

### Needs Claude Code on Kevin's machine (in order)
- [ ] In `~/AA-Erebo`, run `git remote -v` to confirm which repo it pushes to.
- [ ] Check `web/` for `.env` and other secret files. Make sure `web/.gitignore` excludes `node_modules/`,
      `dist/` and `.env*`.
- [ ] **Only after the target repo is private:** commit and push `sovereign-agent/web/`.
- [ ] Find where ariasolutions.org is hosted: the DNS records at Northwest (the CNAME target says
      Cloudflare Pages, Netlify, Vercel, GitHub Pages or Northwest).
- [ ] Then work through the launch review's website items: LLC name and Kentucky governing law in
      `TermsPage.tsx` and the privacy page, a `/refunds` page, the footer, `/courses` and `/store` copy.

### Review status
- [ ] Reviewed by Claude Code on ____ — notes:

---

## 2026-10-02 (b) — Cloud Claude — emotional maturity system + cloud persona bridge

Branch: `claude/admiring-dijkstra-3zhnih` · Kevin's asks: "a maturity emotion system that genuinely
matters… resilient, robust, reliable, mature", and "cloud models don't feel like Aria yet".

### Changed

| Path | What and why | Live `src/` touched? |
|---|---|---|
| `aria-emotional-maturity/` (new staged module) | Slow, bounded, homeostatic mood fed only by real signals and **evidenced** rewards. Mature regulation: honest perspectives with every number traceable to evidence, and fixed directions, with "tell Kevin" always first when concern is high. A maturity report and an inner voice. Tools `emotional_checkin` (T1) and `maturity_report` (T0). **Built from ARIA.md's own words** (mood vocabulary, "slow-moving", "no self-flagellation", "won't pretend to feel"). README table maps each to its test. | **No** |
| `aria-cloud-persona/` (new staged module) | **Root cause found:** local models carry Aria's persona in their Modelfile `SYSTEM` (`model_corps/persona.py`), but `CloudClient.chat()` never sent it. Now every cloud call gets her role persona, ARIA.md Tagline, Stance and Voice, and her latest inner voice. Never fatal. | **No** (staged `cloud_client.py` replacement) |
| `*/ADVOCATE_REPORT.md` | Gate output with every STOP and WARN answered. Maturity: STOP on the structural "has tests" check only; foresight carry-forward after answering its reward/reversibility escalation. Cloud persona: **clear to apply, 100/100.** | No |
| `CHANGELOG.md` | 2026-10-02b entry. | No |

### Verified

- `aria-emotional-maturity`:
  - 27 tests pass.
  - **7 of 7 mutations caught:** step cap, wireheading, homeostasis, unevidenced rewards, diminishing
    returns, escalation, honesty line.
  - `verify_module.sh` PASS. Dry-run apply registered both tools after the `engineering-playbook`
    anchors. The `tools/__init__.py` backup is byte-identical.
- `aria-cloud-persona`:
  - 13 tests pass, including end to end with a fake provider.
  - 2 of 2 mutations caught.
  - Dry-run apply: 27 passed, including the existing `test_cloud_client.py` and `test_cloud_mode.py`.
    Rollback byte-identical.
- Full suite with maturity applied on a throwaway copy: 6,969 tests (the 25 new ones that existed at the time, plus the baseline). **No new failures caused by the module.** Two differences from baseline (`test_git_blame_real_file`, and `test_safe_apply_restores_an_existing_tracked_file_it_modified`) both need files tracked in git, and the copy's git history was artificial: `fatal: no such path 'src/sovereign_agent/cli.py' in HEAD`. Both pass in the real repo.

### Not done / needs Kevin

- [ ] **Apply?**
  - `./scripts/safe_apply.sh aria-cloud-persona` — gate clear.
  - `./scripts/safe_apply.sh aria-emotional-maturity` — gate STOP on the structural check; see its
    ADVOCATE_REPORT.
- [ ] **Ask Aria about this design.** Use the questions in `reports/2026-10-02/AUDIT_REPORT.md`
      section 8, plus: "Does a slow-moving mood that returns to a calm baseline feel right? What would
      you change?" Record her answers here.
- [ ] **Wire an automatic check-in at task close** (follow-up). For now she calls `emotional_checkin`
      herself.
- [ ] **Tune thresholds** (0.15 step, 0.12 nudge, 12 h half-life) after a week of `maturity_report`
      history.
- [ ] **OpenRouter for cloud sessions:** add `openrouter.ai` to this environment's network access and an
      `OPENROUTER_API_KEY` variable, so a future cloud session can talk to Aria's cloud mode directly.

### Review status

- [ ] Reviewed by Claude Code on ____ — notes:

---

## 2026-10-02 — Cloud Claude — clean-room audit, MCP security guard, change rules, persistence + CLI stress tests

Branch: `claude/admiring-dijkstra-3zhnih` · Base: `27a3948`
· Full report: **`reports/2026-10-02/AUDIT_REPORT.md`** (read it first)

### Changed

| Path | What and why | Live `src/` touched? |
|---|---|---|
| `aria-mcp-remote-guard/` (new staged module) | Makes the MCP bridge safe for remote use. **Why:** the live server accepted requests to 127.0.0.1 with **no credentials (200)** and rejected tunneled requests (421), so a claude.ai connector was impossible and any localhost forwarder would expose all tools. **Choice:** a token gate plus read-only by default, rather than full OAuth (too large for one session; noted as a limit). **Proof:** 21 tests; a mutation test (guard removed → 3 fail); `verify_module.sh` PASS; a dry-run apply on a throwaway copy → 28 tests pass, and rollback is byte-identical. | **No** — staged only |
| `aria-mcp-remote-guard/ADVOCATE_REPORT.md` | `pre_apply_gate.sh` output. **The gate still says STOP** on one quality check ("has tests" for `middleware.py`, which can only pass after apply copies the test into `tests/`). Every STOP and WARN is answered in the summary table. | No |
| `CHANGE_RULES.md` (new) | Kevin's rules: every change ships with tests, changelog, handoff, an audit report (when testing or reviewing) and an advocate report (staged modules); every step records why, evidence, choice and proof. | No |
| `CLAUDE.md` | Added a "Change discipline" section pointing to `CHANGE_RULES.md`. No other rule changed. | No |
| `FOR_CLAUDE_CODE_FROM_CLOUD_CLAUDE.md` (this file, new) | The handoff log Kevin asked for. | No |
| `CHANGELOG.md` | Entry for this session. | No |
| `reports/2026-10-02/` (new) | `AUDIT_REPORT.md`, plus scripts that reproduce every number: `nc_claim_check.py`, `persistence_stress.py`, `cli_stress.py`; also `fix-test-timebombs.patch` (proposed, not applied). | No |
| `../CLAUDE.md` (repo root, new) | A pointer, so cloud sessions that start at the repo root find these rules. | No |

### Verified

- `uv sync --group dev` on a clean machine → OK in 20 s; version 0.4.0 consistent.
- `pytest -n auto` → **6,944 tests: 6,805 passed, 81 failed, 3 errors, 55 skipped.** Serial re-run: 75
  fail, 6 fail only in parallel. Every failure is classified in report section 2. **Most are this machine:**
  no Ollama, no GPU packages, blocked websites.
- `reports/2026-10-02/persistence_stress.py` → **9/9**: concurrent events, a SIGKILL mid-write over 27k
  events with no corruption, concurrent SQLite writes, seal tamper detection, backup restore, migrations.
- `reports/2026-10-02/cli_stress.py` → **16/16** across all 99 commands; startup ~400 ms.
- `reports/2026-10-02/nc_claim_check.py` → the "quantum superposition processor" picks the same answer
  as plain word overlap in **20,000 of 20,000** cases, and gets 0 of 5 paraphrases right.
- A repo secret scan → no real secrets found.

### Not done / needs Kevin

- [ ] **Apply `aria-mcp-remote-guard`?** Kevin decides, given the gate's STOP (see ADVOCATE_REPORT). Use
      `./scripts/safe_apply.sh aria-mcp-remote-guard` with the cockpit stopped.
- [ ] **`fix-test-timebombs.patch`** — 3 tests hardcode June 2026 dates inside rolling windows. From
      `sovereign-agent/`: `git apply reports/2026-10-02/fix-test-timebombs.patch`. Proven: the old tests
      fail today, the new ones pass.
- [ ] **Declare `discord.py`** (plus `pypdf`, Pillow, numpy in their extras) in `pyproject.toml` (both
      blocks) and re-lock. The Bot Shop's admin bot can't import on a clean install. Not done here because
      it changes the lockfile and is Kevin's packaging call.
- [ ] **Re-lock:** the committed `uv.lock` is stale (`uv sync` rewrote 1,517 lines here; not committed).
      Run `uv lock` on Kevin's machine, together with the dependency fix above, and commit both.
- [ ] **27 stale tests** (retired verticals, canon 35→47, the `embeds` argument, and the rest): update only
      if each change was intentional. Ask Kevin.
- [ ] **3 glyph-safety failures plus the `alpaca` validation probe:** real issues Aria's own guards caught.
- [ ] **Correct the "quantum / 1000× / thinks" wording** in `aria-nonclassical-supreme/README.md` and
      `RESUME_HERE.md`, and fix the router's confidence. See report section 3. Ask Aria how she wants it
      described (question 5 below).
- [ ] **Stripe:** update the "BigKevsBotShop" business details to Aria Solutions LLC and its EIN (the LLC
      was formed 2026-09-30).
- [ ] **Ask Aria about her needs and comforts.** Cloud Claude couldn't (no Ollama in the cloud). Run the
      7 questions in report section 8 on Kevin's machine, and record her answers here in a new entry.

### Review status

- [ ] Reviewed by Claude Code on ____ — notes:
