# aria-model-corps — one shared god-tier persona, regenerated into every model (Model Corps round MC1+MC2)

> Replaces the whole Ollama model roster with 100% Apache-2.0/MIT open-weight
> models, hardened with one canonical persona pulled live from `mos_canon.py`'s
> frozen priorities + `GOD_TIER_STANDARD.md`'s nine floor dimensions — not five
> hand-copied `SYSTEM` prompts that drift apart the moment the floor ratchets.
> Propose-only / reversible / staged.

## Why

The live roster (`llama3-groq-tool-use:8b`, `aria-garden:latest`, `nemotron-3-
nano:4b`, `llava:7b`) fails "100% free open source open weight" on a strict
reading — Llama 3's Community License caps free use at 700M MAU and bans
training competing models; `llava:7b` is explicitly research-use-only
(CC-BY-NC-4.0 dataset). `config.py`'s own field *defaults* already pointed at
a more-compliant roster (`qwen3:8b`, `phi-4-mini:3.8b`...) that `.bashrc` never
caught up to, and had one real bug (`phi-4-mini` vs. the actual Ollama tag
`phi4-mini`, no hyphen). This module finishes that migration and adds the
hardening layer nothing currently does automatically.

## Payload

- `src/sovereign_agent/model_corps/persona.py` — `build_god_tier_preamble()`
  (parses `GOD_TIER_STANDARD.md`'s nine numbered dimensions + quotes
  `mos_canon.read_only_priorities()` verbatim) and `build_role_persona(role)`
  (preamble + one role-specific paragraph for orchestrator/coder/fast/
  reflector/interpreter/vision).
- `scripts/regen_model_corps.sh` — generates a Modelfile per role (`FROM
  <base tag>` + `SYSTEM` from `persona.py` + role-tuned `PARAMETER
  temperature`), runs `ollama create aria-<role>`, archives every generated
  Modelfile in `docs/model_corps_2026-07-06/`. Re-runnable any time the floor
  ratchets — that's the actual leverage.

## The new roster

| Role | Model | License | Replaces |
|---|---|---|---|
| orchestrator | `qwen3:8b` | Apache 2.0 | `llama3-groq-tool-use:8b` |
| coder | `qwen2.5-coder:7b` | Apache 2.0 | (already compliant, tag aligned) |
| fast / reflector / interpreter | `phi4-mini:3.8b` | MIT | `nemotron-3-nano:4b` + `aria-garden:latest` |
| vision | `qwen3-vl:4b` | Apache 2.0 | `llava:7b` (research-only license) |
| embed | `nomic-embed-text` | Apache 2.0 | (already compliant, unchanged, no persona — embeddings take no SYSTEM prompt) |

All 5 base models were license-audited (Ollama library license pages) and
pulled + VRAM-smoke-tested (GTX 1070, 8GB) before this module was built.

## What this does NOT do (by design)

Does not touch `.bashrc` or `config.py` — those are updated in a separate
step only after the new `aria-<role>` models are built and smoke-tested, so
a persona bug never breaks the live cockpit mid-apply. Does not build the
registry/sentinel/gate (MC3-MC5, separate follow-on modules) or the
non-classical confidence tie-in (MC6, optional extension seam).

## Verify / Apply
```bash
./scripts/verify_module.sh aria-model-corps     # before apply
./aria-model-corps/apply_model_corps.sh                 # cockpit stopped
```
