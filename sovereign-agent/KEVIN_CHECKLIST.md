# Kevin's Checklist — Things Only the Human Can Do

*Updated: 2026-06-21 · Aria v0.4.0*

This file tracks actions that require Kevin specifically — auth, hardware, real-world interaction, operator decisions. Claude handles everything else. Check items off as you go.

---

## 🔴 CRITICAL — Platform Launch Gates

These are the gates that must be green before Aria is ready to serve others.

- [ ] **Record first external proof of value**
  Record the first time Aria genuinely helps someone who isn't Kevin.
  ```
  sov ask "run proof_of_value for [person], problem [X], value [Y], was_unprompted True"
  ```
  Or via Claude Desktop (after MCP config below) → use `record_proof_of_value` tool.
  *This is the single most important action. Until this is done, the institutional impulse says: "not yet."*

- [ ] **Verify proof gate green after recording**
  ```
  sov ask "run institutional_impulse_check"
  ```
  or via MCP: `institutional_impulse_check` tool.
  Look for `proof_gate.status == "green"`.

---

## 🟡 SOON — After This Session

### MCP / Claude Desktop (Plug & Play)
- [ ] **Add Aria to Claude Desktop on your main machine**
  Copy `docs/claude_desktop_config.json` into:
  - **Mac:** `~/.config/claude/claude_desktop_config.json`
  - **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
  Then restart Claude Desktop. Aria's 12 tools will appear.

- [ ] **Test `sov-mcp` is on PATH**
  ```bash
  sov-mcp --help
  ```
  If not found, re-run `./install.sh` (or `.\install.ps1` on Windows).

### Session Health
- [ ] **Record this session as a milestone heartbeat**
  ```bash
  sov heartbeat pulse "v0.4.0 platform layer live — MCP, Docker, Windows compat, 2836 tests"
  ```

- [ ] **Run `sov doctor`** to verify system health after today's changes
  ```bash
  sov doctor
  ```

- [ ] **Check the monthly-impulse-check cron was added**
  ```bash
  sov schedule list
  ```
  Look for `monthly-impulse-check` (fires 1st of each month at 10:00).

### Git
- [ ] **Review and commit today's work** when ready
  Changes: M62-M67 applied, MCP server, Docker, Windows compat, RISK-007 updated.
  I can draft the commit message — just ask.

- [ ] **Consider cutting a `v0.4.0` git tag** to mark this milestone.

---

## 🟢 WHEN CONVENIENT

### Optional Capabilities (heavy GPU — need your auth to install)
- [ ] **Install faster-whisper** (voice input transcription — GPU heavy)
  ```bash
  .venv/bin/pip install -e '.[media]'
  ```
  *Only if you want Whisper transcription. Uses ~2-3GB VRAM on top of the 5.75GB model.*

- [ ] **Install piper-tts** (local voice output)
  ```bash
  .venv/bin/pip install piper-tts
  ```

- [ ] **Install Playwright chromium** (browser tools — no GPU, but needs browser binary)
  ```bash
  .venv/bin/playwright install chromium
  ```

### Docker (if you have Docker installed)
- [ ] **Build and test the Docker image**
  ```bash
  docker compose up --build
  ```
  Check that MCP server starts and Ollama connection works.
  *Optional for local use — more useful when you want others to run Aria.*

### Windows / Mac Testing
- [ ] **If you have a Windows or Mac machine**, test the installer:
  - Windows: `.\install.ps1` in PowerShell
  - Mac: `./install.sh` (should work identically to Linux)
  Then verify `sov --help` and `sov-mcp --help` work.

### Platform / Multi-User Prep
- [ ] **Decide: public or private deployment?**
  Options (discuss with me when ready):
  1. Share Aria via `sov-mcp --transport sse` on a VPS — others connect via Claude Desktop
  2. Package for PyPI (`pip install sovereign-agent`) — full self-hosted
  3. Docker Hub public image — `docker pull aria/sovereign-agent`

- [ ] **RISK-003 (bus factor)**: Consider writing a "handoff doc" so someone else could maintain Aria if needed. Or identify a trusted second person who understands the architecture.

---

## 📋 RECURRING (Monthly)

- [ ] **Monthly: run `institutional_impulse_check`**
  (Cron does this automatically on the 1st — just review the output when notified.)

- [ ] **Monthly: run `weekly_reflection`** on Mondays
  (Cron fires automatically — review and adjust if scores are drifting.)

- [ ] **Periodic: run `sov sentinels check`** to see if any sentinels are in error/warning.

---

## ✅ ALREADY DONE (reference)

- [x] M62-M67 applied — 2877 tests passing
- [x] `sov-mcp` live — Aria is an MCP server
- [x] Docker setup — `Dockerfile` + `docker-compose.yml` at repo root
- [x] Windows compat — `install.ps1` + SIGUSR1 guard
- [x] `mos-institutional-impulse` clause added (clause 35)
- [x] Proof infrastructure live — `proof_of_value`, `proof_history`, `giving_ledger`
- [x] RISK-007 updated: OPEN → MITIGATING
- [x] Version: 0.4.0
- [x] `aegis/encrypted_at_rest.py` — 0% → 95% coverage (29 new tests)
- [x] `argon2-cffi>=23.1` added to `pyproject.toml` as declared dependency

---

*Claude maintains this list. When something changes, ask to update it.*
*"The only gate that matters right now: one external proof. Everything else is roots."*
