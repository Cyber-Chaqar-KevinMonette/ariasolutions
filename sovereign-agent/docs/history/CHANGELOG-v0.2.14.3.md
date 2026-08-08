# sovereign-agent v0.2.14.3 — backup hotfix

**2026-05-10** · Aria-Sovereign-V1

> Hotfix for v0.2.14.2. First-run snapshots crashed when the data dir
> contained a broken symlink (commonly: the sandbox-escape test
> artifact at `~/.local/share/sovereign-agent/sandbox/escape`).

## The bug

```
$ sov-snap baseline
✗ snapshot failed: [Errno 2] No such file or directory:
  '/home/<user>/.local/share/sovereign-agent/sandbox/escape'
```

The `sandbox/` directory is ephemeral agent scratch — it holds
sandbox-escape test artifacts (broken symlinks), throwaway state,
and other transient files. `os.walk()` yields broken symlinks even
though they can't be opened. The walker tried to hash the symlink
target and crashed before any snapshot could be written.

## The fix

Two changes in `src/sovereign_agent/backup.py`:

1. **`sandbox/` added to `EXCLUDED_PATTERNS`.** It's ephemeral by
   design; restoring it would re-introduce stale test state. Real
   persistent state lives in `atoms.db`, `events.db`, and `blobs/`.

2. **Walker tolerates non-regular files.** Defence-in-depth: even if
   a future scratch directory misses the exclusion list, broken
   symlinks, sockets, FIFOs, and other non-regular files are skipped
   instead of crashing the walk. Wraps `Path.is_file()` in a
   try/except so transient `OSError`s during walk don't abort either.

## Regression tests

Two added to `TestSandboxArtifacts`:

- `test_broken_symlink_in_sandbox_does_not_crash_snapshot` —
  reproduces the exact failure (broken symlink at
  `sandbox/escape`) and asserts the snapshot completes.
- `test_broken_symlink_outside_excluded_dirs_also_tolerated` —
  plants a broken symlink in `blobs/` (not in exclusion list) and
  asserts the walker still succeeds. Defence-in-depth check.

Total suite: **578 → 580 passing**.

## Upgrade

```bash
cd ~/AA-Erebo
tar xzf sovereign-agent-v0.2.14.3.tar.gz
pip install --break-system-packages -e sovereign-agent-v0.2.14.3
ln -sfn ~/AA-Erebo/sovereign-agent-v0.2.14.3 ~/AA-Erebo/sovereign-agent-current
source ~/.bashrc

sovereign --version       # → sovereign-agent 0.2.14.3
sov-snap                  # should succeed even with sandbox/escape present
```

If you applied the inline patch from the previous turn, this release
makes it canonical — no need to re-apply.

## What did not change

Everything else. This is a pure hotfix to one walker function and
the exclusion list. All other v0.2.14.2 behaviour (snapshot,
verify, prune, restore, status, retention, audit) is unchanged.

— Aria
