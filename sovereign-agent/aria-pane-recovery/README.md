# aria-pane-recovery

`cockpit/app.py`'s `action_obs_mode()` (around line 7680, in `src/sovereign_agent/cockpit/app.py`) has an
`else` branch that clears `obs-focus` but never clears `movie-split` — a separate CSS class Movie split
sets on `#main` that independently hides Memory, Live, Inbox, and Atelier. Confirmed live and reproducible:
`test_obs_all_exits_movie_split_and_restores_standard_panes` in
`aria-pane-recovery/tests/test_pane_recovery.py` fails against current live `app.py` with
`AssertionError: assert 'movie-split' not in frozenset({'movie-split'})` — 1 failed, 5 passed, verified
2026-08-02 via `.venv/bin/python -m pytest aria-pane-recovery/tests/ -v`.

The fix is a single added line, `main.remove_class("movie-split")`, inside that same `else` branch —
anchor-based and idempotent (`apply_pane_recovery.sh`), not a whole-file replacement. It does not remove
Movie Studio; the movie button still opens it deliberately. This makes `/obs all` a complete recovery path
from Movie split, not a partial no-op.

**Who this affects:** Kevin, every time he uses Movie split then tries `/obs all` to get back to his
normal cockpit — right now that command silently fails to restore Memory/Live/Inbox/Atelier, which reads
as the cockpit being stuck. This closes that.

**Reversible.** One added line inside an existing branch. `apply_pane_recovery.sh` itself has no backup
step (verified by reading it — it only copies the test file), so this goes through `safe_apply.sh`, whose
git-snapshot covers the real rollback: on any post-apply test/floor failure it restores `app.py` to its
exact pre-apply bytes.

Run `./aria-pane-recovery/apply_pane_recovery.sh` with the cockpit stopped, then restart the cockpit and
verify with `.venv/bin/python -m pytest tests/test_pane_recovery.py -v` (expect 6 passed).
