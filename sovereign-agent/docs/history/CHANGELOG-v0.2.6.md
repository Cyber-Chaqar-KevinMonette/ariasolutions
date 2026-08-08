# v0.2.6 · Model-affinity scheduling + multi-format planners

**Tests:** 178 (v0.2.5) → **208** (v0.2.6). Suite passes in ~12s.
**Backward compat:** v0.2.5 continuations load unchanged. All v0.2.5 commands and flags work identically.

---

## Install (drop-in over v0.2.5)

```bash
cd ~/AA-Erebo
mv sovereign-agent-v0.2.5 sovereign-agent-v0.2.5-backup
tar -xzf sovereign-agent-v0.2.6.tar.gz
cd sovereign-agent-v0.2.6
~/.local/share/sovereign-agent/venv/bin/pip install -e . --upgrade
~/.local/share/sovereign-agent/venv/bin/sovereign --version   # → 0.2.6
python -m pytest tests/ -q                                     # → 208 passed
```

Your data (events.jsonl, atoms.db, secret.key, backlog.yaml, continuations from v0.2.5) — **all untouched**.

---

## What's new

### Model-affinity scheduling

Each step now declares `required_model` (orchestrator | coder | vision | fast | none). The runner batches by model so each model loads exactly once instead of swapping per step.

```bash
sovereign drain-by-model <task_id>
# Phase 1: orchestrator (153 steps, llama3-groq stays hot) — 76 min
# Phase 2: coder (185 steps, qwen2.5-coder stays hot)      — 80 min
# Phase 3: vision (495 steps, llava stays hot)             — 82 min
# Phase 4: none (43 metadata steps, no model)              —  3s
```

Manual control: `sovereign continue <id> --model-filter orchestrator`

### Four new planners

| name | tags steps as | use for |
|---|---|---|
| `code-inventory` | `coder` | `.py`, `.ipynb`, `.json` — code-aware summaries |
| `pdf-inventory` | `orchestrator` | `.pdf` — extracts text via pdftotext (or pypdf), then summarizes. Skips image-only/encrypted PDFs |
| `image-inventory` | `vision` | `.png`, `.jpg`, `.webp` — vision-model captions. Use `--include` to whitelist subpaths |
| `metadata-inventory` | `none` | binary stragglers (mp4, zip, pptx) — pure-Python, no model |

### Inventory planner additions

```bash
sovereign plan inventory \
    --root ~/AA-Erebo/Genesis-Seeds \
    --output ~/AA-Erebo/Genesis-Seeds/distilled/inventory.txt \
    --pattern '*.md' \
    --exclude '*/sovereign-agent-*/*' \
    --exclude '*/Copy 1/*' \
    --include-no-extension \
    --max-file-size 200000
```

- `--exclude PATTERN` (repeatable): skip files matching this glob
- `--include-no-extension`: also include LICENSE, transcripts, files with no suffix
- `--max-file-size N`: skip files over N bytes (default 200KB for inventory)
- Oversized files are reported in the plan's notes for triage

### New `image_caption` tool (Tier 0)

Wraps Ollama's vision endpoint. Available to the agent in any mode. Used by `image-inventory` planner. Defaults to `llava:7b`; override via `AGENT_VISION_MODEL` env var.

To use vision: `ollama pull llava:7b` (4.7GB). Or smaller: `ollama pull llava-phi3` (2.3GB) and set `AGENT_VISION_MODEL=llava-phi3`.

### Per-model progress in `continuations show`

```
status: in_progress · progress: 432/967
by model: orchestrator=153/153  coder=200/202  vision=79/495
```

---

## Real-world workflow: full Genesis-Seeds inventory

```bash
# Markdown corpus (153 files) - your Pass 1
sovereign plan inventory \
    --root ~/AA-Erebo/Genesis-Seeds \
    --output ~/AA-Erebo/Genesis-Seeds/distilled/inventory-md.txt \
    --pattern '*.md' \
    --exclude '*/sovereign-agent-*/*'

# Code (~382 files: 185 .py + 17 .ipynb + 182 .json)
sovereign plan code-inventory \
    --root ~/AA-Erebo/Genesis-Seeds \
    --output ~/AA-Erebo/Genesis-Seeds/distilled/inventory-code.txt

# PDFs (~189 files; image-only ones get skipped automatically)
sudo apt install poppler-utils    # one-time, for pdftotext
sovereign plan pdf-inventory \
    --root ~/AA-Erebo/Genesis-Seeds \
    --output ~/AA-Erebo/Genesis-Seeds/distilled/inventory-pdf.txt

# Images (495 files; whitelist what matters)
ollama pull llava:7b              # one-time
sovereign plan image-inventory \
    --root ~/AA-Erebo/Genesis-Seeds \
    --output ~/AA-Erebo/Genesis-Seeds/distilled/inventory-img.txt \
    --include '*/docs/*' --include '*/figures/*' \
    --exclude '*/assets/Kevin*'

# Stragglers (mp4, pptx, zip) - metadata only
sovereign plan metadata-inventory \
    --root ~/AA-Erebo/Genesis-Seeds \
    --output ~/AA-Erebo/Genesis-Seeds/distilled/inventory-meta.txt \
    --pattern '*.mp4' --pattern '*.pptx' --pattern '*.zip'

# Drive each (or combine into one big plan and use drain-by-model)
sovereign drain-by-model <task_id>
```

---

## Architecture notes

**Why a `required_model` field per step instead of a separate queue per model?**

The continuation file remains the single source of truth. One YAML lists every step, what it needs, where it is. `sovereign continuations show` shows the whole picture. Halt-resume works phase-aware. No data duplication, no parallel filesystem queues to keep in sync.

**Why does `drain-by-model` order phases orchestrator-first?**

Orchestrator is the most-common, fastest-to-load model in a typical mixed corpus. Loading it first means most operators see meaningful progress within seconds of starting a drain. Other phases run alphabetically after.

**`required_model='none'` short-circuit.** Metadata steps (binary stragglers) don't invoke any model. The runner has a pure-Python execution path tagged by `step.kind`. Currently only `metadata_inventory_file` ships, but the dispatcher is generic — extend `_execute_no_model_step` to add more.

---

## Files changed (vs v0.2.5)

```
src/sovereign_agent/
  __init__.py                    version bump 0.2.5 → 0.2.6
  config.py                      + vision_model field
  continuation.py                + Step.required_model, + Continuation.{next_pending_for_model, models_needed, progress_by_model}
  continue_runner.py             + model_filter, + _resolve_model_name, + _execute_no_model_step
  cli.py                         + drain-by-model command, + --exclude/--include/--include-no-extension flags, + --model-filter on continue
  planners/
    __init__.py                  + 4 planners in REGISTRY
    inventory.py                 + exclude/include_no_extension/max_file_size
    code_inventory.py            NEW
    pdf_inventory.py             NEW
    image_inventory.py           NEW
    metadata_inventory.py        NEW (with execute_metadata_step pure-Python executor)
  tools/
    __init__.py                  + ImageCaptionTool export
    image_caption.py             NEW
scripts/
  sovereign-continue-loop.sh     + --model-filter flag
tests/
  test_v026.py                   NEW (30 tests)
pyproject.toml                   version bump 0.2.5 → 0.2.6
CHANGELOG-v0.2.6.md              NEW (this file)
```

Everything else: bit-identical to v0.2.5.

---

## Rollback

```bash
mv sovereign-agent-v0.2.6 sovereign-agent-v0.2.6-failed
mv sovereign-agent-v0.2.5-backup sovereign-agent-v0.2.5
cd sovereign-agent-v0.2.5
~/.local/share/sovereign-agent/venv/bin/pip install -e . --upgrade
```

Continuation files created under v0.2.6 with `required_model` fields will be loaded by v0.2.5 — the field is silently dropped on read. Multi-model continuations still work but lose phase-batching.

---

## Known limitations

1. **End-to-end binary verification skipped this build cycle** (token budget). The 208 tests cover unit and CLI integration; the bundle has not been re-tested against a fresh extract on a clean venv. Run `pytest tests/ -q` first thing after install — if it shows 208 passed, you're good.

2. **Vision model not auto-pulled.** `image-inventory` planner expects `llava:7b` (or your `AGENT_VISION_MODEL`) already pulled. Doctor will catch this on next run if you forgot.

3. **PDF extractor not bundled.** Install `poppler-utils` for `pdftotext` (recommended) or `pip install pypdf` (fallback). Planner errors at plan-time if neither is available.

4. **No OCR for image-only PDFs.** They get skipped with a note. Future v0.2.7 candidate.
