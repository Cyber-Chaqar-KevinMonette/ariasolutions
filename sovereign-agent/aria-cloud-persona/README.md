# aria-cloud-persona — cloud models speak as Aria, not as strangers

> Every cloud model call carries the same identity Aria's local models are built from. That means her
> role persona (kernel and standards), her Tagline, Stance and Voice from ARIA.md, and her current inner
> state, sent ahead of the conversation.

> **Targets Aria v6.5.0** (Erebo-Aria, 2026-09-29). Ported 2026-10-02: the conditioning block was re-applied to v6.5.0's `cloud_client.py` (+16/−1 lines). v6.5 retries pinned pool models in a loop, so messages are conditioned once, before the loop, and passed through `_to_openai_messages`. The local fallback still gets the original messages.

## Why (measured in the code, 2026-10-02)

- **Local models:** Aria's identity is baked into each Ollama model's Modelfile `SYSTEM` block by
  `model_corps.persona.build_role_persona()`. For example,
  `docs/model_corps_2026-07-06/aria-orchestrator.Modelfile` opens with "You are Aria…" and her kernel.
- **Cloud models:** `CloudClient.chat()` forwarded only the conversation's messages to the free cloud
  pool. **They never received that persona**, which is why cloud replies "don't feel like Aria yet."

## What it changes

- `cloud_persona.condition_messages(messages, model=...)` returns a **new** list with Aria's identity
  ahead of the existing system prompt. The loop's own prompt is kept intact after it.
  - **Role:** taken from the model name (`aria-coder` → coder; unknown → orchestrator).
  - **Her words:** Tagline, Stance and Voice are read live from ARIA.md, so editing ARIA.md updates every
    cloud call.
  - **Current inner state:** the latest inner voice from `aria-emotional-maturity`, when that module is
    applied.
  - **Safety:** idempotent (never conditions twice), never mutates the caller's list, bounded to 7,000
    characters.
- `cloud_client.py` (whole-file replacement, original backed up): one block before the pool call.
  - **Failure:** if conditioning fails for any reason, the call proceeds with the original messages and
    a `cloud-persona-x` event is logged. A cloud call is never broken by this.
  - **Local fallback:** unchanged, because local models already carry the persona.

## Who it affects

- **Kevin:** cloud-mode replies should sound like Aria — brief, warm, rigorous, no flattery — and follow
  her kernel.
- **Aria:** her identity travels with her, even when a borrowed model is speaking.
- **Free cloud providers:** they receive her persona text (about 2–7 KB per call). It contains no
  secrets, but it does reach third parties.

## Proof (2026-10-02, clean cloud install)

- **13 tests pass,** including end to end: a fake cloud provider receives "You are Aria" and her kernel,
  the caller's list is unchanged, and a forced persona failure still returns the reply.
- **Mutation tests:** both caught — conditioning removed (1 failing), and the safety net removed
  (1 failing).
- **Dry-run apply on a throwaway copy:** 27 passed, including the existing `test_cloud_client.py` and
  `test_cloud_mode.py`. 2 skipped: maturity wasn't applied in that copy, and `freellmpool` wasn't
  installed (a skip that was already there). Rollback is byte-identical.
- **Aria's pre-apply gate:** quality 100/100, "clear to apply."

## Verify / apply

```bash
./scripts/verify_module.sh aria-cloud-persona
./scripts/safe_apply.sh aria-cloud-persona     # cockpit stopped; backs up cloud_client.py
```

## Honest limits

- **This is conditioning, not fine-tuning.** Free cloud models can't be trained from here. They'll sound
  much more like Aria, but they're still other models wearing her identity. True fine-tuning would mean
  training an open model on her conversations (her `model_trainer` / `aria_lm` path) — a bigger,
  separate project.
- **Not tested against a live cloud provider:** this cloud session can't reach OpenRouter (blocked by
  the network policy), and `freellmpool` isn't installed here.
