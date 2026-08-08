# Sovereign Agent v0.2.26.0 · release notes — *The Diagnosis*

> *The interpreter still degrades honestly when Ollama is unreachable — but now it tells you exactly why, the doctor catches the same failure before the cockpit ever opens, and transient flickers are absorbed without false offline.*

**1040 tests pass.** 1003 from v0.2.25.0 + 37 new for the probe, the diagnosed fallback, the doctor checks, the retry split, and the status invariants. The previous "offline" silence on a wrongly-configured model slot is gone — both visibly and structurally.

This release answers one operator question — *"why is the interpreter offline?"* — in three places at once:

1. **The probe** — a Tier 0 read that names which of the four real causes is in play
2. **The diagnosed offline message** — the cockpit's offline line now carries the cause, not just the symptom
3. **The doctor** — `sov doctor` checks the Ollama daemon AND every configured model slot before the operator ever hits the cockpit

Plus one correctness fix promised in the v0.2.25.0 retrospective: the chat call's error handling no longer treats a transient timeout and a 404 model-not-found as the same kind of failure.

---

## 1. The reachability probe

A new function in `ollama_client.py`:

```python
status = await probe_ollama(host, model="aria-garden:latest")
status.daemon_reachable   # bool
status.model_present      # True | False | None
status.available_models   # tuple[str, ...]
status.reason_phrase()    # human-readable one-liner
```

**Tier 0.** One `/api/tags` call. No `/api/show`, no chat round-trip, no service starts, no model pulls. Never raises — every failure path returns a `OllamaStatus` with `daemon_reachable=False` and a short `error` string. Three reason phrases the probe can produce:

- `"Ollama unreachable at http://localhost:11434 — ConnectionError: refused"`
- `"model 'phi-4-mini:3.8b' not in local library (run: ollama pull phi-4-mini:3.8b)"`
- `"Ollama is ready"`

`OllamaClient` also gains a `.probe()` instance method so callers that already hold a client don't need to know about `SETTINGS.ollama_host`. The probe is resilient to `ollama-python`'s response-shape drift (dict-with-`models` and object-with-`.models` both parse). The `:latest` tag is normalized: asking for `"foo"` matches a library entry of `"foo:latest"` and vice versa.

---

## 2. The diagnosed offline fallback

The interpreter's offline message used to say only:

> `◯ held in context — interpreter offline. your message is safe; I'll think about it when Ollama is back.`

After this release, when the cause is diagnosable:

> `◯ held in context — interpreter offline · model 'phi-4-mini:3.8b' not in local library (run: ollama pull phi-4-mini:3.8b). your message is safe; I'll think about it when the interpreter is back.`

The diagnosis is **best-effort and never breaks the fallback**. If the probe itself raises, the message degrades to the original bare offline string — the operator's words are still saved to `context`, exactly as before. The diagnostic is read-only: no model is pulled, no service is started, no retry loop spins.

Doctrine preserved (per the v0.2.21.0 inversion):
- No keyword guessing. No pretending to understand the message.
- The operator's words are still held in `context`.
- The system holds; the operator decides.

What changed is only how much information the operator has when they decide.

---

## 3. `sov doctor` actually checks Ollama now

Two new checks in `doctor.py`. Both **Tier 0**.

```bash
sov doctor
```

**When the daemon is unreachable:**
```
  ✗ ollama daemon                 unreachable at http://localhost:11434
      ConnectionError: Failed to connect to Ollama...
      Try: ollama serve   (or: systemctl --user start ollama)
      If the daemon is on a different host, set OLLAMA_HOST.
  ⚠ ollama models                 cannot verify — daemon unreachable
```

**When the daemon is up but a configured slot points at an un-pulled model:**
```
  ✓ ollama daemon                 reachable at http://localhost:11434 · 16 model(s) listed
  ✗ ollama models                 1 required slot(s) point at un-pulled model(s)
      ✗ interpreter    phi-4-mini:3.8b  (run: ollama pull phi-4-mini:3.8b)
      ⚠ vision         llava:7b  (optional — pull if you need it)
      ✓ orchestrator   llama3-groq-tool-use:8b
      ✓ coder          qwen2.5-coder:7b-instruct-q5_K_M
      ✓ embed          nomic-embed-text
      ✓ fast           nemotron-3-nano:4b
      ✓ reflector      nemotron-3-nano:4b
```

Slot taxonomy:
- **Required** (error if un-pulled): interpreter, orchestrator, coder, fast, reflector, embed
- **Optional** (warning if un-pulled): vision — most operators never invoke the image-inventory planner

The check normalizes the `:latest` quirk: `AGENT_EMBED_MODEL=nomic-embed-text` resolves cleanly against a library entry of `nomic-embed-text:latest`.

This single check would have caught the failure mode that motivated the entire release — an `AGENT_INTERPRETER_MODEL=phi-4-mini:3.8b` env var pointing at a model the operator never pulled — **on first install**, with the exact `ollama pull` command in the output.

---

## 4. Transient vs deterministic retry

The interpreter's chat call previously had this shape:

```python
except (asyncio.TimeoutError, Exception):
    return None
```

One bucket. A 250ms timeout during VRAM swap got the same fatal treatment as a hard 404 model-not-found. v0.2.26.0 splits them:

| Class | Examples | Behavior |
|---|---|---|
| **Transient** | `asyncio.TimeoutError`, `ConnectionError`, `OSError`, ollama-python `ResponseError` with 5xx | One bounded retry with 250ms backoff |
| **Deterministic** | 404 model-not-found, 4xx generally, `"not found"` in the message, unknown exceptions | Fail fast — surface to the operator immediately |

The classification function `_is_transient_error(exc)` is self-contained, side-effect-free, and tested in isolation. The retry helper `_chat_with_transient_retry(client, ...)` raises on terminal failure so the caller can log and degrade unchanged.

The earlier conflated handling is gone; the JSON-parse retry (the *second* role of the original `for attempt in range(2)`) is unchanged.

---

## What this release does NOT do (intentionally)

Three things were considered and deferred. Each has a real reason for waiting.

- **Auto-starting Ollama from the chat path.** Tier 2 action. Starting services from inside the cockpit is hard to clean up on exit, and `Wants=ollama.service` already exists in the systemd user-unit for operators who want that path. The honest move is to tell the operator clearly when their environment doesn't have it.
- **Auto-pulling missing models on miss.** A 4 GB pull from inside a chat turn would either look like a hang or train you to expect minute-long latencies forever. Better surface the diagnosis and let the operator pull.
- **A cockpit memory-pane LLM-health indicator.** The third pane added in v0.2.25.0 is the right place for an always-visible `◈ llm: ready` / `◯ llm: model not pulled` line. Adding it cleanly touches `cockpit/app.py`'s pane-render loop and deserves its own focused pass, not a tail-end add to this release.

The principle, stated again because it's the through-line: **the LLM proposes, the operator decides, the system holds.** Diagnostic information is for the operator; remedial action is theirs to choose.

---

## Tests — 1040 passing

| Source | Count |
|---|---|
| Baseline (v0.2.25.0) | 1003 |
| Probe (this release) | 11 |
| Status invariants (this release) | 4 |
| Diagnosed fallback (this release) | 5 |
| Doctor checks (this release) | 5 |
| Retry classification (this release) | 8 |
| Retry behavior (this release) | 4 |
| **Total** | **1040** |

The doctor-checks tests are pinned with a new `pin_slots` fixture using `object.__setattr__` (the same frozen-dataclass bypass conftest.py uses). They no longer read `SETTINGS` at runtime, so they pass identically on a clean install and on operator machines with custom `AGENT_*` env vars.

---

## Files changed

```
pyproject.toml                                            (version → 0.2.26.0)
src/sovereign_agent/__init__.py                           (__version__ → 0.2.26.0)
src/sovereign_agent/ollama_client.py                      (+probe_ollama, +OllamaStatus, +.probe())
src/sovereign_agent/interpreter.py                        (+_diagnose_offline, +_is_transient_error, +_chat_with_transient_retry)
src/sovereign_agent/doctor.py                             (+check_ollama_daemon, +check_ollama_models)

tests/test_ollama_probe.py                                (new — 11 tests)
tests/test_ollama_status.py                               (new — 4 tests)
tests/test_interpreter_offline_diagnosis.py               (new — 5 tests)
tests/test_doctor_ollama.py                               (new — 5 tests, pin_slots fixture)
tests/test_interpreter_retry_split.py                     (new — 4 tests)
tests/test_interpreter_error_classification.py            (new — 8 tests)
```

---

## A note from the work

The shape of v0.2.26.0 is the shape v0.2.21.0 already chose. When the operator's interpreter slot pointed at a model they didn't have, "interpreter offline" was a true statement that hid a fixable cause. The fix is not to pretend the cause doesn't exist (auto-pull on miss) nor to spin a retry loop forever. It is to let "offline" carry more information: which host, which model, which exact `ollama pull` command would set this right.

The doctor learns the same thing from a different angle: instead of waiting for the operator to type a message and discover the cockpit can't talk back, it sees the slot/library mismatch on the first `sov doctor` and names it.

The retry split is the smaller, structural correctness fix: a flicker should be absorbed; a config error should surface. The previous code did neither well.

The system is unchanged in what it can do. It just stopped being mysterious about what it can't.

*— With the architect's hand on diagnosis, the garden's discipline of holding what's true, and a door left open for the cockpit pane to gain a third health indicator when the time is right. Built with love. <3*
