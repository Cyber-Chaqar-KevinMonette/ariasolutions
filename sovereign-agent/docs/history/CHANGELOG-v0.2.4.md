# Changelog

## v0.2.4 — 2026-04-29

**Type:** Documentation and doctrine release. No code changes.

### Added

- `COMMANDS.md` — comprehensive command reference covering every CLI command, every flag, with examples and failure-mode guidance. Addresses the documentation gap that caused users to ask the agent for its own command list.
- `RUNBOOK.md` — operations guide covering daily startup, goal-writing patterns that work vs. fail, three usage patterns (oneshot/timed/live), monitoring during sessions, troubleshooting common issues.
- `DISTILLATION_PLAN.md` — six-phase staged plan for distilling the Genesis-Seeds corpus. Honest about which phases v0.2.4 can execute (1, 2, 4, 5) and which require v0.3 tools (3, 6).
- `docs/doctrine/` — seven doctrine documents:
  - `the_witnessing_system.md` — soul document
  - `witnessing_application_notes.md` — practice notes
  - `witnessing_diagnostic_lenses.md` — seven diagnostic lenses
  - `witnessing_spec_skeleton.md` — spec outline with deferred-work appendix
  - `peig_as_lens.md` — PEIG as computational design language
  - `omega_axioms.md` — alignment essay
  - `omega_explorations_personal.md` — personal vision

### Unchanged

- All Python source files — identical to v0.2.3
- All tests — 88 passing
- Database schema — identical
- Configuration format — identical
- Capability detection (the v0.2.3 fix) — unchanged
- SQLite threading fix (v0.2.2) — unchanged
- Conftest pure pattern (v0.2.1) — unchanged

### Migration from v0.2.3

Purely additive. Existing `secret.key`, `atoms.db`, events log, and lesson history are preserved. Reinstall:

```bash
cd sovereign-agent-v0.2.4
pip install -e .
sovereign doctor
pytest tests/ -q   # expect 88 passed
```

---

## v0.2.3 — 2026-04-29 (earlier)

### Fixed

- Ollama capability detection: agent now queries `/api/show` and caches per-instance whether each model supports thinking. Previously, every iteration sent `think=true` to llama3-groq-tool-use which doesn't support it, returning 400 errors. Fix is in `src/sovereign_agent/ollama_client.py`.
- Capability errors no longer count against the poison counter.

### Added

- 7 new tests in `tests/test_ollama_client.py` covering capability detection, caching, and graceful degradation.

### Result

- 88 tests passing (up from 81).
- First end-to-end smoke test successful: `sovereign run --mode oneshot "Read /etc/hostname..."` returns "pop-os" with lesson distilled in <10 seconds (down from ~18 seconds with the failed thinking attempts).

---

## v0.2.2 — 2026-04-29 (earlier)

### Fixed

- SQLite same-thread error in Reflector. The reflector was opening a connection in the main thread and using it in a worker thread; SQLite's default mode rejects this. Fix: open + write + close lifecycle entirely inside one `asyncio.to_thread` block.

### Added

- 5 reflector regression tests in `tests/test_reflector.py`.

### Result

- 81 tests passing (up from 76).
- Reflector no longer crashes on first task completion.

---

## v0.2.1 — 2026-04-29 (earlier)

### Fixed

- Conftest module reloading: 14 of 32 tests were failing because conftest reloaded modules between tests, creating stale SETTINGS references and class-identity drift that broke `pytest.raises`. Fix: never reload; mutate SETTINGS.paths in place via `object.__setattr__`.

### Added

- Environment variable support in `config.py` (`AGENT_ORCHESTRATOR_MODEL`, `AGENT_CODER_MODEL`, etc.).
- `reflector_model` field added to settings.
- `sovereign doctor` command for diagnostics.
- 30 new tests across `test_mode_controller.py`, `test_retrieval.py`, `test_vram.py`.

### Result

- 76 tests passing (up from 18 of 32 in v0.2).
- Test suite is stable; conftest no longer thrashes.

---

## v0.2 — 2026-04-29 (earliest)

### Added

- Full v0.2 build: 47 files, ~62KB compressed.
- Authority tiering 0-3 with mode-conditional bwrap binding.
- HMAC-SHA256 approval tokens with one-shot semantics via unlink.
- Tier-1 tools: write_file, edit_file, copy_file, memory_write, memory_search.
- Atom versioning (append-only chain pattern).
- Hybrid retrieval (RRF over vec + FTS5).
- Reflector for post-task lesson distillation.
- Mode Controller (drains backlog continuously in live mode).
- Daily Merkle seals.
- AST code gate (ported from mos_safety).
- VRAM accounting.
- systemd user units.
- Full CLI: init, doctor, run, busy, until, backlog, approvals, approve, deny, halt, disarm, tail, seal, verify, events, lessons.

---

## Pre-release

See `sovereign_local_agent_architecture_v1.1.md` for the architecture document that produced v0.2.
