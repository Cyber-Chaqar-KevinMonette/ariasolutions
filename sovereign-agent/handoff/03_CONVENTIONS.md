# 03 — Conventions (read BEFORE writing code)

## The staged-module pattern (how ALL features ship)
Build in `aria-<name>/`, never edit live `src/` in place (small bug
fixes excepted):
```
aria-<name>/
  payload/src/sovereign_agent/...   # whole NEW files, mirrored paths
  patcher.py                        # anchored transforms for EXISTING files
  apply_<name>.sh                   # guard → backup → patch → copy → test
  tests/test_<name>_live.py         # plain imports — the file that gets promoted
  tests/test_patcher.py             # pre-apply structural checks
  README.md
```
**Patcher law**: unique `MARK = "<name>-d"`; `if MARK in text: return
text, False`; `_replace_once` verifies EXACTLY one anchor occurrence and
raises PatchError (a moved anchor is loud, never silent corruption);
output py_compile-verified before writing.

**Test law**: shadow-copy / sys.modules-manipulating tests stay
staged-only (promoting one caused real cross-suite pollution); promoted
files use plain imports; the autouse `isolated_paths` fixture gives every
test tmp paths.

**Apply law**: cockpit stopped; timestamped backups of every touched
file; full pytest (`--ignore=tests/test_git_tools.py`) at 0 failures
after EVERY apply; commit only with permission.

## Style
MARK comments make provenance greppable. Kill switches on anything
autonomous. Stores: atomic write (tmp+os.replace) or append+fsync.
Cockpit refreshers: try/except → dim placeholder, never block boot;
expensive work is TIMER-ONLY (never eager on mount).
