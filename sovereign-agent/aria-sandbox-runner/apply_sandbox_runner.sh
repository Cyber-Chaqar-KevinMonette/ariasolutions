#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
#  apply_sandbox_runner.sh — Code execution sandbox (closes RISK-012)
#
#  Three Tier 1 tools:
#    run_code   — execute Python snippet in .venv/bin/python
#    run_shell  — execute a whitelisted shell command
#    run_tests  — run pytest with sensible defaults
#
#  Changes:
#  1. Install tools/runner.py
#  2. Patch tools/__init__.py — imports + __all__
#  3. Patch loop.py — add "after writing code, run_tests()" to CODE AWARENESS
#     (or create the section if aria-git-eyes was not applied first)
#
#  Idempotent. Backs up patched files.
# ═══════════════════════════════════════════════════════════════════════════
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${1:-$PWD}"

if [[ ! -f "$ROOT/src/sovereign_agent/cli.py" ]]; then
  d="$PWD"
  while [[ "$d" != "/" ]]; do
    [[ -f "$d/src/sovereign_agent/cli.py" ]] && { ROOT="$d"; break; }
    d="$(dirname "$d")"
  done
fi
[[ -f "$ROOT/src/sovereign_agent/cli.py" ]] || { echo "✗ run from repo root"; exit 1; }
echo "◊ repo root: $ROOT"

PKG="$ROOT/src/sovereign_agent"
TOOLS="$PKG/tools"
INIT="$TOOLS/__init__.py"
LOOP="$PKG/loop.py"
ts(){ date +%Y%m%d%H%M%S; }

# ── 1. Install runner.py ───────────────────────────────────────────────────
echo "→ installing tools/runner.py"
cp "$HERE/payload/src/sovereign_agent/tools/runner.py" "$TOOLS/runner.py"
echo "  ✓ runner.py"

# ── 2. Patch tools/__init__.py ─────────────────────────────────────────────
echo "→ patching tools/__init__.py"
cp "$INIT" "$INIT.bak.$(ts)"

python3 - "$INIT" <<'PYEOF'
import sys, pathlib
init = pathlib.Path(sys.argv[1])
src = init.read_text(encoding="utf-8")

IMPORT_MARKER = "# sandbox-runner-import-d"
if IMPORT_MARKER in src:
    print("  ↷ runner imports already present — skipping")
else:
    new_imports = (
        "from .runner import (\n"
        "    RunCodeTool,\n"
        "    RunShellTool,\n"
        "    RunTestsTool,\n"
        ")  " + IMPORT_MARKER + "\n"
    )
    for anchor in ("from .read_file import ReadFileTool", "from .write_file import WriteFileTool"):
        if anchor in src:
            src = src.replace(anchor, new_imports + anchor, 1)
            print("  ✓ runner imports added")
            break
    else:
        print("✗ no import anchor found in __init__.py", file=sys.stderr)
        sys.exit(1)

ALL_MARKER = "# sandbox-runner-all-d"
if ALL_MARKER in src:
    print("  ↷ runner __all__ already present — skipping")
else:
    new_all = (
        '    "RunCodeTool",\n'
        '    "RunShellTool",\n'
        '    "RunTestsTool",  ' + ALL_MARKER + '\n'
    )
    for anchor in ('    "ReadFileTool",', '    "WriteFileTool",'):
        if anchor in src:
            src = src.replace(anchor, new_all + anchor, 1)
            print("  ✓ runner tools added to __all__")
            break
    else:
        print("  ⚠ __all__ anchor not found — __all__ not updated")

init.write_text(src, encoding="utf-8")
print("  ✓ tools/__init__.py written")
PYEOF

# ── 3. Patch loop.py — execution guidance ─────────────────────────────────
echo "→ patching loop.py"
cp "$LOOP" "$LOOP.bak.$(ts)"

python3 - "$LOOP" <<'PYEOF'
import sys, pathlib
loop = pathlib.Path(sys.argv[1])
src = loop.read_text(encoding="utf-8")

MARKER = "# sandbox-runner-loop-d"
if MARKER in src:
    print("  ↷ execution guidance already in loop.py — skipping")
else:
    # Prefer to extend the CODE AWARENESS section from git-eyes
    GIT_MARKER = "# git-eyes-loop-d"
    COMPLETION = "═══ COMPLETION ═══"

    insert = (
        "\n═══ EXECUTION & VERIFICATION ═══\n"
        "You can run code and tests. Use these tools without asking:\n"
        "  run_code(code)          — execute a Python snippet in .venv; see stdout + exit code\n"
        "  run_shell(cmd, args)    — run a whitelisted command (pytest, ruff, mypy, ls, grep, ...)\n"
        "  run_tests(path)         — run pytest; returns pass/fail counts and full output\n"
        "WORKFLOW: write file → run_tests() → fix failures → run_tests() again → done.\n"
        "Both tools are Tier 1 — act without asking. Verification is not optional.\n"
        "  " + MARKER + "\n\n"
    )

    if GIT_MARKER in src:
        # Insert right after the git-eyes CODE AWARENESS section
        src = src.replace(GIT_MARKER + "\n", GIT_MARKER + "\n" + insert, 1)
        print("  ✓ EXECUTION & VERIFICATION section added after CODE AWARENESS")
    elif COMPLETION in src:
        src = src.replace(COMPLETION, insert + COMPLETION, 1)
        print("  ✓ EXECUTION & VERIFICATION section added before COMPLETION")
    else:
        print("  ⚠ no anchor found in loop.py — skipping prompt patch")

loop.write_text(src, encoding="utf-8")
print("  ✓ loop.py written")
PYEOF

# ── 4. Compile checks ──────────────────────────────────────────────────────
echo "→ compile checks"
python3 -m py_compile "$TOOLS/runner.py" "$INIT" "$LOOP"
echo "  ✓ all files compile"

cp "$HERE/tests/test_sandbox_runner.py" "$ROOT/tests/test_sandbox_runner.py"
python3 -m py_compile "$ROOT/tests/test_sandbox_runner.py"
echo "  ✓ tests installed + compile"

echo
echo "✓ done. RISK-012 closed. Aria can now run code."
echo
echo "  3 new Tier 1 tools: run_code, run_shell, run_tests"
echo "  run_shell allowlist: $(python3 -c "from src.sovereign_agent.tools.runner import SHELL_ALLOWLIST; print(', '.join(sorted(SHELL_ALLOWLIST)))" 2>/dev/null || echo "see runner.py SHELL_ALLOWLIST")"
echo
echo "  run: pytest tests/test_sandbox_runner.py -v"
