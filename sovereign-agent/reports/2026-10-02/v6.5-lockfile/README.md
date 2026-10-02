# v6.5 lockfile fix — `pyproject.toml` + `uv.lock` for Erebo-Aria

**For:** `~/AA-Erebo/sovereign-agent/` (Aria v6.5.0, Erebo-Aria commit `5766122`). **Not** for this old
snapshot.

## Why

- **The committed `uv.lock` is stale.** It lists 114 packages and doesn't include `mcp` at all, so
  installs re-resolve on the fly.
- **`pyproject.toml` says `mcp>=1.0` with no upper bound.** A fresh install on 2026-10-02 pulled
  **mcp 2.2.0**, which renamed `FastMCP`, and **`sov-mcp` crashed on import**. Kevin's machine works only
  because it already had mcp 1.x.
- **An import scan found packages the code uses but never declares.** `numpy` is imported at top level
  by 36 modules and was only arriving by accident through scipy. Most notably, `discord.py` is undeclared,
  and it's needed by the Bot Shop admin bot.

## What changed (`pyproject.diff`: 21 lines added, 1 changed)

| Change | Where | Evidence |
|---|---|---|
| `mcp>=1.0,<2` | core | mcp 2.2.0 broke `sov-mcp`. The only cap added, because it's the only proven breakage. |
| `numpy>=1.26`, `psutil>=5.9` | core | numpy is imported at top level by 36 modules; psutil is the cockpit monitor |
| `discord.py>=2.3` | new `discord` extra | `discord_admin/bot.py` |
| `trimesh`, `fast-simplification` | new `three-d` extra | shape engine, game-ready meshes |
| `nvidia-ml-py` | new `gpu` extra | cockpit GPU monitor (`pynvml`) |
| `Pillow`, `open-clip-torch`, `piper-tts` | `media` extra | sprite and clip QA, voice |
| `torch`, `safetensors`, `huggingface-hub` | `training` extra | `aria_lm`, `weight_store`, video |
| `pypdf` | `distill` extra | PDF planner fallback |
| `markdownify` | `browser` extra | `tools/web_better.py` |
| `anthropic` | `cloud` extra | `tools/image_analyze.py` |

Not added: `bpy`, `mathutils` and `bmesh` are Blender's built-in modules. They only run inside Blender and
can't be installed with pip.

## Proof (2026-10-02)

- `uv lock` → 199 packages (was 114). **mcp is locked at 1.30.0.**
- Clean install from pristine v6.5 source with this lock, using `uv sync --locked --group dev`:
  - `sov-mcp` imports with all 16 tools
  - `sovereign --version` → 6.5.0
- Full v6.5 suite: see `../AUDIT_REPORT.md` section 11.

## How to apply (on Kevin's machine)

```bash
cd ~/AA-Erebo/sovereign-agent
cp pyproject.toml pyproject.toml.bak && cp uv.lock uv.lock.bak
cp <this folder>/pyproject.toml <this folder>/uv.lock .
uv sync --locked --group dev          # add  --extra discord  etc. for the features you use
.venv/bin/python -c "from sovereign_agent.mcp_server import mcp; print(len(mcp._tool_manager._tools), 'tools')"
./scripts/run_tests_chunked.sh
git add pyproject.toml uv.lock && git commit -m "Pin mcp<2, declare missing deps, regenerate uv.lock"
```

To undo: restore the two `.bak` files.
