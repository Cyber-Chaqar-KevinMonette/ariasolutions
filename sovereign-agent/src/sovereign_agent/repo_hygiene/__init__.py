"""repo_hygiene — repo-root file clutter detection.

loose_threads scans her anatomy (src/) for orphaned code symbols; this
scans the repo ROOT for orphaned one-off scripts — the gap that let 38
throwaway patch scripts (add_*, fix_*, remove_*, replace_*, update_*)
sit untracked at sovereign-agent/'s root for three days (2026-07-30 to
2026-08-02) before anyone noticed and archived them by hand.

Reuses loose_threads' own DispositionLedger — same WIRED/RETIRED/ACCEPTED
(here: ARCHIVED/ACCEPTED) discipline, just pointed at a different data_dir
subfolder and a different symbol shape (a bare filename instead of a
qualified code symbol).
"""
from .scanner import RepoScan, StrayScript, scan_repo_root  # noqa: F401
