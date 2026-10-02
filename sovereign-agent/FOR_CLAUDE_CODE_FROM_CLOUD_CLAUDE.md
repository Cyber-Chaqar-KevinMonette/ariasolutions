# For Claude Code, from Cloud Claude

> The running handoff log between Claude Code sessions on Kevin's machine and Claude Code cloud sessions
> ("Cloud Claude"). Newest entry first. Format and rules: `CHANGE_RULES.md`. At session start, read the top
> entries and tick "Review status" for what you've checked.
>
> Getting these changes onto Kevin's machine: they're on GitHub,
> `Cyber-Chaqar-KevinMonette/ariasolutions`, branch `claude/admiring-dijkstra-3zhnih`, under
> `sovereign-agent/`. Pull or merge them into the working copy at `~/AA-Erebo/sovereign-agent`.

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
