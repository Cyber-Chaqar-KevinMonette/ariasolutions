#!/usr/bin/env bash
# apply_command_master.sh — M31: enhanced command execution
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo "==> M31 command-master: $REPO"

cp "$REPO/aria-command-master/payload/src/sovereign_agent/tools/command_master.py" \
   "$REPO/src/sovereign_agent/tools/command_master.py"
echo "  OK   copied command_master.py"

python3 - "$REPO" <<'PYEOF'
import sys
from pathlib import Path

repo = Path(sys.argv[1])

def patch(path, old, new, marker):
    src = path.read_text()
    if marker in src:
        print(f"  SKIP {path.name} — already patched ({marker})")
        return False
    if old not in src:
        print(f"  ERROR {path.name} — anchor not found for {marker}", file=sys.stderr)
        sys.exit(1)
    path.write_text(src.replace(old, new, 1))
    print(f"  OK   {path.name} ({marker})")
    return True

loop = repo / "src/sovereign_agent/loop.py"
init = repo / "src/sovereign_agent/tools/__init__.py"
runner = repo / "src/sovereign_agent/tools/runner.py"

# ── runner.py: expand SHELL_ALLOWLIST ───────────────────────────────────────
patch(runner,
    old='''\
SHELL_ALLOWLIST: frozenset[str] = frozenset({
    "pytest",
    "ruff",
    "mypy",
    "python",
    "python3",
    "ls",
    "find",
    "grep",
    "wc",
    "head",
    "tail",
    "cat",
    "diff",
    "stat",
    "tree",
    "echo",
})''',
    new='''\
SHELL_ALLOWLIST: frozenset[str] = frozenset({  # command-master-runner-d
    # Core Python toolchain
    "pytest", "ruff", "mypy", "black", "isort",
    "python", "python3", "pip", "pip3", "uv",
    # File inspection
    "ls", "find", "tree", "cat", "head", "tail",
    "wc", "diff", "stat", "echo", "file",
    # Text processing
    "grep", "egrep", "fgrep", "rg", "awk", "sed",
    "sort", "uniq", "cut", "jq",
    # Git
    "git",
})''',
    marker="command-master-runner-d",
)

# ── tools/__init__.py: import command_master tools ───────────────────────────
patch(init,
    old='from .god_workflow_tools import (  # god-workflow-import-d',
    new='''\
from .command_master import (  # command-master-import-d
    RunCommandTool,
    EditInPlaceTool,
)
from .god_workflow_tools import (  # god-workflow-import-d''',
    marker="command-master-import-d",
)

# ── tools/__init__.py: add to __all__ ────────────────────────────────────────
patch(init,
    old='    "WorkflowMutateTool",       # god-workflow-all-d',
    new='''\
    "RunCommandTool",            # command-master-all-d
    "EditInPlaceTool",
    "WorkflowMutateTool",       # god-workflow-all-d''',
    marker="command-master-all-d",
)

# ── loop.py: TERMINAL DISCIPLINE section ─────────────────────────────────────
patch(loop,
    old='═══ ENGINEERING DOCTRINE ═══  # engineering-doctrine-d',
    new='''\
═══ TERMINAL DISCIPLINE ═══  # terminal-discipline-d
You have a full dev toolchain. Use it without asking:

  run_command(["pytest", "tests/"])          → run tests
  run_command(["ruff", "check", "src/"])     → lint
  run_command(["git", "diff", "--stat"])     → see what changed
  run_command(["rg", "pattern", "src/"])     → ripgrep search
  run_command(["jq", ".key", "file.json"])   → parse JSON
  edit_in_place(path, old_text, new_text)   → surgical file edit
  run_code("import json; ...")              → quick Python eval

Cycle: write → ruff → pytest → fix → pytest → done.
Always run tests after code changes. lint before pytest. Verify before proceeding.

═══ ENGINEERING DOCTRINE ═══  # engineering-doctrine-d''',
    marker="terminal-discipline-d",
)

print("M31 command-master: all patches applied.")
PYEOF

cp "$REPO/aria-command-master/tests/test_command_master.py" "$REPO/tests/test_command_master.py"
echo "==> M31 done. Run: .venv/bin/python -m pytest tests/test_command_master.py -q"
