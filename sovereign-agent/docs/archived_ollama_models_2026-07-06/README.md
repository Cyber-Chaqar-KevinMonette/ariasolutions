# Archived Ollama models — 2026-07-06

Six custom `aria-*` Ollama models were deleted during a disk-space cleanup
(reclaiming ~44G) as part of the move to replace the whole model stack
with the latest open-weight models. Their exact Modelfiles are preserved
in this folder — byte-for-byte what `ollama show <name> --modelfile`
produced right before deletion — so any of these can be rebuilt later if
the base blob (or an equivalent public download of the same base model)
is available again. None of these were ever referenced by the live
`AGENT_*_MODEL` environment variables in `.bashrc`.

**Update, same day (2026-07-06):** the move this note anticipated has now
landed — see `docs/model_corps_2026-07-06/`. The stack that was "left
untouched" when this note was first written (`llama3-groq-tool-use:8b`,
`qwen2.5-coder:7b-instruct-q5_K_M`, `nemotron-3-nano:4b`,
`aria-garden:latest`, `nomic-embed-text`, `llava:7b`) has since been
replaced in `.bashrc`/`config.py` by the hardened `aria-<role>` models
(Apache-2.0/MIT only). The old base tags were left installed (not deleted)
for an easy rollback; `aria-garden:latest` specifically remains installed
too, since it is one of the six models this README already documents.

## What each one was

| Model | Size | Base model | Purpose (from its own SYSTEM prompt) |
|---|---|---|---|
| `aria-agent:latest` | 5.4G | Qwen2.5-Coder 7.6B (Apache 2.0) | "ARIA Garden Agent v5 — FULL TOOLS ENABLED" — an autonomous tool-using agent for distilling `genesis-seeds/` research material into a single high-value document. |
| `aria-distiller-v4.1:latest` | 5.4G | Qwen2.5-Coder 7.6B (Apache 2.0) | "OPENJARVIS NATIVE (TEXT-ONLY, 16K CTX)" — a pure-text, no-tool-calls autonomous loop, same genesis-seeds distillation task, output as versioned markdown trees. |
| `aria-garden-perfect:latest` | 5.4G | Qwen2.5-Coder 7.6B (Apache 2.0) | "Aria Garden v2.2 — 13-Qubit Bonsai Distiller + Godot Quantum Brain" — distillation plus generating a Godot 4 project (quantum-brain-driven avatar, AI camera, procedural animals). |
| `aria-garden-32k:latest` | 10G | Qwen2.5-Coder 14.8B (Apache 2.0) | Same Garden/Godot concept as above, v2.1, 32k context window. |
| `aria-garden-65k:latest` | 10G | Qwen2.5-Coder 14.8B (Apache 2.0) | Same Garden/Godot concept, v2.0, 65k context window. |
| `aria-teacher:latest` | 7.2G | Gemma 4 5.1B (Apache 2.0) | A dedicated "teacher" persona instructing an experimental quantum-phase-space language model ("Aria" as a 12-qubit ring network) on human vocabulary, syntax, and emotional language — a distinct, earlier concept from the current sovereign-agent Aria. |

Two of the five Qwen-based models share an identical base blob
(`sha256-52476f59...` for agent/distiller/garden-perfect at 7.6B;
`sha256-2073329812...` for garden-32k/65k at 14.8B) — only their SYSTEM
prompt and context-window parameters differ.

## Restoring one

1. Pull (or confirm you already have) the base model named in the
   Modelfile's `FROM` line — for the 7.6B models that's Qwen2.5-Coder
   7B-class; for the 14.8B models, the 14B-class; for `aria-teacher`,
   Gemma 4 (5.1B, Q4_K_M).
2. Edit that Modelfile's `FROM` line to point at the pulled model's tag
   instead of the original local blob path (which no longer exists after
   deletion) — e.g. `FROM qwen2.5-coder:7b-instruct-q5_K_M`.
3. `ollama create <new-name> -f <the-modelfile>`.

The full exact SYSTEM prompts, PARAMETER values, TEMPLATE, and LICENSE
text are preserved verbatim in each `.Modelfile` file in this folder.
