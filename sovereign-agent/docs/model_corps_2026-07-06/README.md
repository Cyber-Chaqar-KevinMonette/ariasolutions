# Model Corps — the god-tier open-weight roster (2026-07-06)

The whole Ollama model stack was replaced with 100% Apache-2.0/MIT
open-weight models, each hardened with a **shared** persona pulled live from
`mos_canon.py`'s frozen Safety/Love/Flourishing priorities +
`GOD_TIER_STANDARD.md`'s nine floor dimensions — one canonical source
(`src/sovereign_agent/model_corps/persona.py`), regenerated into every
model by `scripts/regen_model_corps.sh`, not five hand-copied `SYSTEM`
blocks that drift apart the moment the floor ratchets upward.

## What replaced what

| Role | Model | License | Replaces | Why |
|---|---|---|---|---|
| orchestrator | `qwen3:8b` | Apache 2.0 | `llama3-groq-tool-use:8b` | Llama 3 Community License caps free use at 700M MAU, bans training competing models |
| coder | `qwen2.5-coder:7b` | Apache 2.0 | (already compliant) | tag aligned to `config.py`'s own default |
| fast / reflector / interpreter | `phi4-mini:3.8b` | MIT | `nemotron-3-nano:4b` + `aria-garden:latest` | unified 3 roles onto 1 base model; `aria-garden` was itself Llama-3-based |
| vision | `qwen3-vl:4b` | Apache 2.0 | `llava:7b` | LLaVA's own license is **research-use-only** (CC-BY-NC-4.0 dataset) — not commercially licensed at all |
| embed | `nomic-embed-text` | Apache 2.0 | (unchanged, already compliant) | embeddings take no `SYSTEM` prompt |

Each of the 5 base models was license-audited directly against its Ollama
library page and VRAM-smoke-tested (GTX 1070, 8GB) before any Modelfile was
built. The previous roster's exact Modelfiles remain preserved at
`docs/archived_ollama_models_2026-07-06/` for restoration if ever needed.

## The Modelfiles in this folder

`aria-<role>.Modelfile` — the exact, generated `FROM <base>` +
`SYSTEM "<persona>"` + `PARAMETER` output for each of the 6 hardened
models, archived by `scripts/regen_model_corps.sh` every time it runs.
Re-running that script (e.g. after `GOD_TIER_STANDARD.md` gains a 10th
dimension, or a role paragraph is edited) regenerates every one of these
from the same shared source and overwrites this archive with the new
version — that's the actual ratchet mechanism in practice.

## The governance layer (`aria-model-corps-governance`)

Beyond the swap itself, a standing layer now watches the roster:

- **Registry** (`model_corps_governance/registry.py`) — a persisted NDJSON
  ledger of the declared roster (role/base/license/VRAM/persona hash).
- **`ModelCorpsSentinel`** (`stewardship/model_corps_sentinel.py`) — checks
  every role's license against an explicit allow-list
  (Apache-2.0/MIT/BSD-3-Clause), checks the registered tag is actually
  installed (drift), checks the largest model against `vram.py`'s own
  budget constants.
- **Gate + eval** (`model_corps_governance/gate.py`) — a small (12-case),
  mechanically-scored, no-LLM-judge eval per role, persisted as a trend.
  Closes `GOD_TIER_CRITERIA.md`'s own named gap #2 ("standing scored model
  benchmark"). First live pass (2026-07-06): **11/12 (0.92)** — gate
  verdict **PASS**. The one honest miss was the vision role's exact-phrasing
  check on "no image provided," not gamed to a perfect score.
- **Non-classical confidence tie-in** (`model_corps_governance/
  nonclassical_confidence.py`) — an optional composition of the existing,
  already-real `nonclassical_supreme.superpose` quantum-faithful simulation
  as an extra confidence signal over multiple candidate strings. Not a
  claim that any model's weights are literally non-classical — that isn't
  physically possible at this scale; this composes what already exists
  honestly rather than inventing a new claim.

## Restoring the previous roster

See `docs/archived_ollama_models_2026-07-06/README.md` — the pre-round
custom `aria-*` models' exact Modelfiles are preserved there. The base
tags this round replaced (`llama3-groq-tool-use:8b`, `nemotron-3-nano:4b`,
`llava:7b`) were left installed, not deleted, so a rollback needs only an
`.bashrc` env-var revert, no re-pull.
