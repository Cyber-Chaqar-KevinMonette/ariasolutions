# REBUILD.md — rehydrate Aria from this lightweight package

This archive is **Aria, whole, without fluff** — her source (`src/`), every staged `aria-*/` module,
tests, docs, scripts, and `pyproject.toml`. It deliberately **excludes** everything regenerable:
the virtualenv (`.venv/`), git history (`.git/`), byte-caches (`__pycache__`, `*.pyc`,
`.pytest_cache/`), rollback snapshots (`.safe_apply_snapshot/`, `backups/`), and `*.bak.*` zombies.

**Her true weight is ~24 MB of code.** Everything below just rebuilds the regenerable shell around her.

## 1. Recreate the virtualenv (the 5.3 GB that was left out)

```bash
cd sovereign-agent
python3 -m venv .venv
.venv/bin/pip install -e .          # pyproject.toml is the manifest
```

## 2. Models (only if you run the LLM-backed faculties)

Aria's heavy cognition is served by **Ollama** (not bundled — model weights are multi-GB and
re-pullable). Install Ollama, then pull the models named in `src/sovereign_agent/config.py`:

```bash
ollama pull qwen3:8b              # orchestrator
ollama pull qwen2.5-coder:7b      # coder
ollama pull nomic-embed-text      # embeddings
ollama pull phi-4-mini:3.8b       # fast / reflector / interpreter
ollama pull llava:7b              # vision (optional)
```

The non-classical / BitNet / quantum faculties run on **CPU** and need no GPU or model download.

## 3. Verify she breathes

```bash
.venv/bin/python -m pytest -q          # run the test suite
./scripts/harden_all.sh                # god-tier floor + cleanliness verdict
.venv/bin/sovereign cockpit            # launch the TUI cockpit
```

## Notes
- Runtime data (atoms, events, palace) lives under `~/.local/share/sovereign-agent/` (XDG), **not**
  in this tree — a fresh checkout starts her with a clean memory by design.
- Staged `aria-*/` modules are applied only by running their `apply_*.sh` with the cockpit stopped
  (see `CLAUDE.md` doctrine). Nothing here mutates live `src/` on its own.
