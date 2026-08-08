# Migration to `uv`

This document is for operators who installed any earlier version of
`sovereign-agent` via `pip install --break-system-packages -e .` (every
release up to and including v0.2.33.0).

Going forward, `./install.sh` uses [`uv`](https://docs.astral.sh/uv/)
exclusively. `pip` is no longer touched by the installer.

---

## What changed

| | Before | After |
|---|---|---|
| Installer | `pip install --break-system-packages -e .` | `uv sync --no-dev` into a managed venv (with a loud pip fallback) |
| Venv location | none (user-site) | `${XDG_DATA_HOME:-$HOME/.local/share}/sovereign-agent/venv/` |
| `sov` / `sov-chat` / `sovereign` on PATH | Python entry-point scripts in `~/.local/bin` | bash launcher shims in `~/.local/bin` that exec the venv interpreter |
| Reproducibility | none (fresh resolution every install) | `uv.lock` is committed, uv path is deterministic |
| System Python touched? | yes (`--break-system-packages`) | no, ever |
| Upgrade in place? | `pip install -e . --upgrade` against the managed venv | `./install.sh` — same as fresh install (idempotent) |
| Dev tooling | `pip install -e .[dev]` | `uv sync --group dev` (PEP 735) OR `uv sync --extra dev` OR `pip install -e .[dev]` — pyproject declares both blocks so all three work |

## uv-first, pip-fallback

`./install.sh` tries uv first. If uv is missing OR `uv sync` exits non-zero,
the script falls back to a stdlib `python -m venv` + `pip install -e .`
path. This guarantees the project installs in environments where uv isn't
available or has trouble starting (air-gapped boxes, restrictive CI, an
arch uv hasn't shipped a binary for yet, a transiently broken uv install).

**The fallback is loud, never silent.** When it fires:

1. A multi-line `DEGRADED MODE` banner prints to stderr with the reason.
2. The script writes the marker file `${MANAGED_VENV}/.install-method`
   containing `pip-fallback`. `sov doctor`'s `install layout` check reads
   this and reports the warning state forever after — there is no way to
   accidentally believe you have a deterministic install when you don't.
3. The final summary tells you which method ran.

The pip-fallback path produces a *working* install but **does not consult
`uv.lock`** — resolution happens fresh against PyPI. If determinism
matters to you, install uv and re-run.

## Architecture: the boot path

```bash
#!/usr/bin/env bash
set -e
VENV="$HOME/.local/share/sovereign-agent/venv"
if [[ ! -x "${VENV}/bin/sov" ]]; then
    echo "✗ sovereign-agent venv is missing or broken: ${VENV}" >&2
    echo "  Repair: re-run install.sh from the sovereign-agent source tree." >&2
    exit 127
fi
exec "${VENV}/bin/sov" "$@"
```

That's the whole boot path. No Python imports happen before the venv is
exec'd, so a broken system Python can never silently take over your
`sov` invocation.

---

## One-time cleanup for operators upgrading from a pre-uv install

If you ran any earlier version of `./install.sh`, you have a
`sovereign-agent` entry registered in your user-site `pip` database, and
its entry-point scripts (`sov`, `sov-chat`, `sovereign`) sit in
`~/.local/bin` alongside the new shims. Same names, different paths —
whichever was written second wins.

The new `./install.sh` already overwrites those names with shims, so in
most cases there's nothing more to do. But the user-site package is still
registered. To clean it up:

```bash
pip uninstall --break-system-packages sovereign-agent 2>/dev/null || true
```

You may need to run it twice if multiple installs accumulated.

Then re-run `./install.sh` from the source tree, and run `sov doctor` to
confirm the install layout reports as `managed venv (uv)`.

---

## Rollback

If for some reason you need to revert to the pre-uv install model:

```bash
# 1. Remove the managed venv and shims
rm -rf "$HOME/.local/share/sovereign-agent/venv"
rm -f "$HOME/.local/bin/sov" "$HOME/.local/bin/sov-chat" "$HOME/.local/bin/sovereign"

# 2. Check out the previous release's install.sh from git history
git show HEAD~1:install.sh > install.sh  # adjust SHA as needed
chmod +x install.sh

# 3. Run the old installer
./install.sh
```

Your data directory at `~/.local/share/sovereign-agent/` (everything
*outside* `venv/`) is untouched by either install model — `atoms.db`,
`secret.key`, `events.jsonl`, `backlog.yaml` all survive the swap.

---

## Why `uv`

Three reasons that compound:

1. **No more `--break-system-packages`.** That flag was always a
   workaround for PEP 668 ("we don't think you should pip-install into
   system Python"). The managed-venv layout sidesteps the entire problem
   class.

2. **Deterministic installs.** `uv.lock` is committed at release time,
   so the operator's resolution matches the maintainer's tested set.
   For a "sovereign" tool, this is the whole point.

3. **Faster.** `uv sync` on this codebase is ~3-10× faster than the
   equivalent `pip install -e .`. Re-running `./install.sh` after a tiny
   source change feels like a no-op, which encourages running it often
   instead of avoiding it.

The shim model — separating the *bootloader* (in `~/.local/bin`) from
the *runtime* (in the managed venv) — gives one more property worth
naming: the boot path is bash, not Python. A broken Python install
cannot take down `sov`'s ability to *report that it is broken*.
