# aria-timeout-chunked-tests — the actual pytest-chunking fix (Timeout round · T5)

> Standalone — no dependency on T1-T4. Fixes the literal thing that
> happened twice this session: a pytest chunk of ~48-50 files exceeding
> the harness's own ~280s command timeout (several slow, real-Ollama-
> calling `_live` tests clustering together by bad luck, not a bug).
> Propose-only / reversible / staged.

## Payload

`scripts/run_tests_chunked.sh` — splits `tests/test_*.py` into N even
chunks (default 10, matching the size that worked by hand this session
after 6-chunk sizing started timing out), runs each with an explicit
foreground `timeout` command, and on a chunk **TIMEOUT** (never a real
test failure — those are surfaced directly, never needlessly bisected)
automatically bisects that one chunk in half and retries — mirroring
exactly the manual recovery done today — until the exact slow/hung file
is isolated.

Verified with a real subprocess trial against a fake `python -m pytest`
stand-in (one file that genuinely hangs, one that genuinely fails, four
that pass): the script correctly isolates the hang to the single
offending file and reports the failure directly, without conflating the
two or needlessly re-running clean files.

## Doc sync

`.claude/PLAYBOOK.md`'s Environment section names this script as the
standard full-suite verification command — nothing previously addressed
the harness-command-timeout problem at all.

## Verify / Apply
```bash
./scripts/verify_module.sh aria-timeout-chunked-tests
./aria-timeout-chunked-tests/apply_timeout_chunked_tests.sh
```
