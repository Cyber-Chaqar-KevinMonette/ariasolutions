"""patcher.py — FABLE II M8: safe, efficient git work.

Kevin: *"work safely and efficiently with her git tools — robust and
resilient."* Payload replaces git_write.py wholesale (never-main
discipline, garden-aware, RESULT-style checkpoint, forbidden-verb
backstop) — the "whole NEW files, mirrored paths" convention, since the
diff touches nearly every function. Patches:
  1. tools/__init__.py — register GitCheckpointTool (chained on M6's
     modes-crown anchors — "new modules anchor on the latest").
  2. tools/git_tools.py — the same forbidden-verb backstop the write
     tools carry, for defense-in-depth consistency (the read-only tools
     never call these verbs, but the shared helper refuses them anyway).

Anchored transforms only; MARK-idempotent; a moved anchor raises loudly."""
from __future__ import annotations

MARK = "git-flow-d"


class PatchError(Exception):
    pass


def _replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if text.count(old) != 1:
        raise PatchError(f"{label}: expected 1 anchor, found {text.count(old)}")
    return text.replace(old, new, 1)


# ── 1. tools/__init__.py — register GitCheckpointTool ───────────────────
#
# Follows the repo's own anchor-chain convention exactly (PLAYBOOK.md:
# "<name>-import-d" / "<name>-all-d") — not just the module-wide MARK —
# so path_scan's ships-tools/no-registration check (and any human reading
# the chain: modes-crown-import-d → git-flow-import-d) recognizes it.
TOOLS_IMPORT_MARK = "git-flow-import-d"

INIT_IMPORT_ANCHOR = ("from .stance_tools import ObservatoryTool, SetStanceTool  "
                      "# modes-crown-import-d\n")
INIT_IMPORT_NEW = (
    INIT_IMPORT_ANCHOR
    + f"from .git_write import GitCheckpointTool  # {TOOLS_IMPORT_MARK}\n"
)

INIT_ALL_ANCHOR = '    "ObservatoryTool",  # modes-crown-all-d\n'
INIT_ALL_NEW = (
    INIT_ALL_ANCHOR
    + '    "GitCheckpointTool",  # git-flow-all-d\n'
)


def patch_tools_init(text: str) -> tuple[str, bool]:
    if TOOLS_IMPORT_MARK in text:
        return text, False
    text = _replace_once(text, INIT_IMPORT_ANCHOR, INIT_IMPORT_NEW,
                         label="tools import")
    text = _replace_once(text, INIT_ALL_ANCHOR, INIT_ALL_NEW,
                         label="tools __all__")
    return text, True


# ── 2. tools/git_tools.py — the same forbidden-verb backstop ────────────

GIT_TOOLS_ANCHOR = '''def _git(args: list[str], cwd: Path | None = None) -> tuple[bool, str]:
    """Run a git command. Returns (ok, output_or_error)."""
    try:
'''

GIT_TOOLS_NEW = f'''def _git(args: list[str], cwd: Path | None = None) -> tuple[bool, str]:
    """Run a git command. Returns (ok, output_or_error)."""
    # {MARK} — the same defense-in-depth backstop the write tools carry.
    # This module is read-only and never calls these verbs; the check
    # costs nothing and means a future bug here can't slip one through
    # either — absence, not discouragement, all the way down.
    if args and args[0] in ("reset", "clean", "filter-branch", "filter-repo"):
        return False, f"refused: {{args[0]!r}} is not a permitted git verb"
    if any(a in ("--force", "-f", "--force-with-lease") for a in args):
        return False, "refused: force flags are not permitted"
    try:
'''


def patch_git_tools(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    return _replace_once(text, GIT_TOOLS_ANCHOR, GIT_TOOLS_NEW,
                         label="git_tools _git backstop"), True


ALL_PATCHES = {
    "tools/__init__.py": patch_tools_init,
    "tools/git_tools.py": patch_git_tools,
}
