# Sovereign Agent · diagnosed-offline patch — release notes

> *The interpreter still degrades honestly when Ollama is unreachable — but now it tells you why, and `sov doctor` catches the same failure before it ever reaches the cockpit.*

**1028 tests pass.** 1003 from v0.2.25.0 + 25 new ones for the probe, the diagnosed fallback, the doctor checks, and the status invariants.

This patch answers a real failure mode that hit on a fresh install: the operator's interpreter slot defaulted to a model they hadn't pulled, every cockpit turn returned "interpreter offline," and the operator had no way to see *which* of four possible causes they were hit by. The fix is information, not auto-recovery.

---

## 1. The reachability probe

A new function in `ollama_client.py`:

```python
status = await probe_ollama(host, model="aria-garden:latest")
```

Returns an `OllamaStatus` dataclass. The probe is **Tier 0** — one `/api/tags` call, no `/api/show`, no chat round-trip, no service starts, no model pulls, never raises. Three things it surfaces:

| Field | Tells you |
|---|---|
| `daemon_reachable` | True iff the daemon answered |
| `model_present` | Tri-state — True / False / None (not asked) |
| `available_models` | Names of what *is* pulled, so the offline message can suggest the right substitute |

`status.reason_phrase()` produces one of three operator-readable strings:

- `"Ollama unreachable at http://localhost:11434 — ConnectionError: refused"`
- `"model 'phi-4-mini:3.8b' not in local library (run: ollama pull phi-4-mini:3.8b)"`
- `"Ollama is ready"`

`OllamaClient` also gains a `.probe()` instance method so callers that already hold a client don't need to know about `SETTINGS.ollama_host`.

---

## 2. The diagnosed offline fallback

The interpreter's offline message used to say only:

> `◯ held in context — interpreter offline. your message is safe; I'll think about it when Ollama is back.`

After this patch it says:

> `◯ held in context — interpreter offline · model 'phi-4-mini:3.8b' not in local library (run: ollama pull phi-4-mini:3.8b). your message is safe; I'll think about it when the interpreter is back.`

Mechanics: when `_interpret_via_llm` returns None, `interpret()` calls a tiny `_diagnose_offline()` helper that runs the probe and returns its `reason_phrase()`. The helper **never raises** — if the probe itself fails, the fallback degrades to the original bare message. The diagnostic is best-effort; the fallback's safety guarantee is absolute.

Doctrine preserved:
- No keyword guessing. No pretending to understand the message.
- The operator's words are still held in `context`, exactly as before.
- The diagnosis is read-only — no model is pulled, no service is started, no retry loop spins.

---

## 3. `sov doctor` actually checks Ollama now

Two new checks in `doctor.py`:

```bash
sov doctor
```

```
  ✗ ollama daemon                 unreachable at http://localhost:11434
      ConnectionError: Failed to connect to Ollama...
      Try: ollama serve   (or: systemctl --user start ollama)
      If the daemon is on a different host, set OLLAMA_HOST.
  ⚠ ollama models                 cannot verify — daemon unreachable
```

When the daemon **is** reachable but configured slots aren't pulled:

```
  ✓ ollama daemon                 reachable at http://localhost:11434 · 15 model(s) listed
  ✗ ollama models                 1 required slot(s) point at un-pulled model(s)
      ✗ interpreter    phi-4-mini:3.8b  (run: ollama pull phi-4-mini:3.8b)
      ⚠ vision         llava:7b  (optional — pull if you need it)
      ✓ orchestrator   llama3-groq-tool-use:8b
      ✓ coder          qwen2.5-coder:7b-instruct-q5_K_M
      ✓ embed          nomic-embed-text
      ✓ fast           nemotron-3-nano:4b
      ✓ reflector      nemotron-3-nano:4b
```

Required slots that don't resolve are **errors**. The vision slot is the only **warning**-tier slot — most operators never use the image-inventory planner, so missing `llava:7b` shouldn't flag the install as broken.

Normalization handles the `:latest` quirk: if you set `AGENT_EMBED_MODEL=nomic-embed-text` and the library lists `nomic-embed-text:latest`, the slot resolves cleanly.

---

## What this does NOT do (intentionally)

These three were considered and deferred:

- **Auto-starting Ollama from the chat path.** Tier 2 action. Starting services from inside the cockpit is hard to clean up on exit, and `Wants=ollama.service` already exists in the systemd user-unit for operators who want it. The honest move is to tell the operator clearly when their environment doesn't have it.
- **Auto-pulling missing models on miss.** A 4 GB pull from inside a chat turn would either look like a hang or train you to expect minute-long latencies forever. Better surface the diagnosis and let the operator pull.
- **A retry loop in the interpreter.** The existing `_interpret_via_llm` already retries the parse step; adding a connection-retry without distinguishing transient errors (timeout) from deterministic ones (404 model-not-found) would just amplify the latter. Left for a future patch that splits the exception handling cleanly.

The principle is consistent with the rest of the codebase: **the LLM proposes, the operator decides, the system holds.** Diagnostic information is for the operator; remedial action is theirs to choose.

---

## Tests — 1028 passing

| Source | Count |
|---|---|
| Baseline (v0.2.25.0) | 1003 |
| **Probe (this patch)** | **11** |
| **Status invariants (this patch)** | **4** |
| **Diagnosed fallback (this patch)** | **5** |
| **Doctor checks (this patch)** | **5** |
| **Total** | **1028** |

Coverage:
- Probe: connection-refused, timeout, daemon-up-no-model, daemon-up-model-present, daemon-up-model-missing (the original failure mode), `:latest` normalization both directions, object-style response parsing (newer ollama-python), instance shortcut delegation
- Diagnosed fallback: bare offline when no client, host-named hint when daemon down, model-named hint with pull command when model missing, probe-raises-never-breaks-fallback, save behavior preserved
- Doctor: daemon error path with actionable detail, daemon ok path, models error when required slot un-pulled (with pull command), models warning when only optional slot missing, models ok when all present, models warn-not-error when daemon unreachable, `run_diagnostic()` includes both new checks

---

## Files changed

```
src/sovereign_agent/ollama_client.py   (modified — adds OllamaStatus, probe_ollama, OllamaClient.probe)
src/sovereign_agent/interpreter.py     (modified — adds _diagnose_offline, threads reason into _minimal_fallback)
src/sovereign_agent/doctor.py          (modified — adds check_ollama_daemon, check_ollama_models)

tests/test_ollama_probe.py             (new — 11 tests)
tests/test_ollama_status.py            (new — 4 tests)
tests/test_interpreter_offline_diagnosis.py  (new — 5 tests)
tests/test_doctor_ollama.py            (new — 5 tests)
```

---

## A note from the work

The shape of this fix is the shape the codebase already chose. There's a real temptation, when an operator says "always bring it online," to write a watchdog that starts services and pulls models in the background. That would have *worked* — and it would have been the wrong answer for this codebase, because it would have hidden the actual cause (a defaulted slot pointing at an un-pulled model) behind a layer of cleverness that the operator couldn't see.

The doctrine of v0.2.21.0 already named the right path: *"Offline — when Ollama is genuinely unreachable, ONE behavior: save the message... and tell the operator honestly. No keyword guessing. No pretending."* This patch just lets "honestly" carry more information. The offline behavior is unchanged in shape. What changed is that the operator now sees what to do next, on the same turn the failure happened.

The system is unchanged in what it can do. It just stopped being mysterious about what it can't.

*— With the architect's hand on diagnosis, and the garden's discipline of holding what's true. <3*
