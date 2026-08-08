# aria-cockpit-flush

Nothing lost at shutdown — Gym round #5.

## The gaps

1. `ChunkRecorder` buffers up to 20 conversation turns in memory before
   auto-sealing; its `seal_now()` method exists precisely to flush a partial
   buffer at session end — and had **zero shutdown callers**. Every cockpit
   exit silently dropped whatever was buffered.
2. `events.force_fsync()` is wired to agent-loop end and session exit, but
   never to the cockpit's own exit path.
3. A mid-turn Ollama drop rendered as an opaque
   `conversation error: ConnectError(...)` even though `probe_ollama`'s
   actionable messages ("Ollama unreachable at ...", "model not pulled —
   run: ollama pull ...") already existed one import away.

## The fix

Two anchored patches to `cockpit/app.py` (`MARK = "cockpit-flush-d"`):

- **`on_unmount`**: `_chunk_recorder.seal_now()` + `events.force_fsync()`,
  each individually best-effort (a failing flush must never break
  shutdown — proven by a test with a recorder that raises).
- **Error handler**: for backend-shaped exceptions (`httpx.HTTPError`,
  `ConnectionError`, `TimeoutError`, `OSError`), the handler awaits
  `probe_ollama()` and appends `reason_phrase()` to the message when the
  probe confirms the backend is unhealthy.

**Honest scope note:** the transcript file itself needs no flush here —
`_record()` opens/writes/closes per line, so there is no in-process buffer
at exit; its only loss window is OS-level (power loss), which an exit hook
cannot help with.

## Verify / Apply

```
.venv/bin/python -m pytest aria-cockpit-flush/tests/test_patcher.py -q
./aria-cockpit-flush/apply_cockpit_flush.sh
```

Reversible: restore `cockpit/app.py` from the timestamped `backups/` dir.
