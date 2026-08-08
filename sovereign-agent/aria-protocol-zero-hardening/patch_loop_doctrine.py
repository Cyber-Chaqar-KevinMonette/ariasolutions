"""Patch loop.py — M64: add git-reflect-d doctrine comment in KNOW THYSELF section.

After every git_commit() call in the loop, Aria should call git_commit_reflect().
This is a doctrinal wire-up comment, not logic change.
"""
import sys
from pathlib import Path

path = Path(sys.argv[1])
src = path.read_text()

MARKER = "git-reflect-d"
if MARKER in src:
    print("  git-reflect-d already present — skipping")
    sys.exit(0)

# Find the KNOW THYSELF section or tool_call section to add the comment
# Try multiple anchor points
ANCHORS = [
    ("git_commit", "# git-reflect-d: call git_commit_reflect() immediately after every git_commit() call\n"),
]

patched = False
for anchor_text, comment in ANCHORS:
    if anchor_text in src:
        # Find first occurrence of git_commit in the source and add comment near it
        # We add the comment as a block near the top of the file after imports
        pass

# Simpler approach: add a module-level docstring comment near the top
# Find the first blank line after imports
KNOW_THYSELF_MARKER = "# KNOW THYSELF"
if KNOW_THYSELF_MARKER in src:
    OLD = KNOW_THYSELF_MARKER
    NEW = KNOW_THYSELF_MARKER + "\n# git-reflect-d: call git_commit_reflect() immediately after every git_commit() call"
    patched_src = src.replace(OLD, NEW, 1)
    path.write_text(patched_src)
    print(f"  patched {path} (KNOW THYSELF section)")
else:
    # Fallback: add comment after the module docstring / before first import
    lines = src.splitlines(keepends=True)
    insert_at = 0
    for i, line in enumerate(lines):
        if line.startswith("from ") or line.startswith("import "):
            # Find end of import block
            insert_at = i
            break
    # Add comment before imports
    comment_line = "# git-reflect-d: call git_commit_reflect() immediately after every git_commit() call\n"
    lines.insert(insert_at, comment_line)
    path.write_text("".join(lines))
    print(f"  patched {path} (prepended git-reflect-d comment)")

sys.exit(0)
