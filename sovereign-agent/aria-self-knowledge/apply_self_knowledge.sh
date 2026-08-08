#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
#  apply_self_knowledge.sh — give Aria eyes on herself (v0.2.41.0)
#
#  Delivers four new Tier 0 self-introspection tools and three cockpit
#  slash commands so Aria can see her hands, her vessel, and herself.
#
#  Changes (surgical patches — no full-file replacements):
#
#    tools/self_knowledge.py (new)
#      • read_self            — kernel + durable state from aria.py
#      • list_available_tools — every registered tool with tier + description
#      • list_sov_commands    — every `sov` CLI subcommand via `sovereign --help`
#
#    tools/vessel_status.py (new)
#      • vessel_status        — CPU, RAM, VRAM, disk, uptime, sentinel health
#
#    tools/__init__.py (patched)
#      • imports the 4 new tool classes (auto-registers via __init_subclass__)
#
#    cockpit/app.py (patched)
#      • /self    → prints Aria's kernel inline via `sovereign aria`
#      • /tools   → lists all registered tools inline (new _show_tools_inline)
#      • /sentinels → shows sentinel health inline (new _show_sentinels_inline)
#
#    tests/test_self_knowledge_tools.py (new)
#
#  Idempotent: each patch is skipped if its marker already exists.
# ═══════════════════════════════════════════════════════════════════════════
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${1:-$PWD}"

# ── Locate repo root ─────────────────────────────────────────────────────────
if [[ ! -f "$ROOT/src/sovereign_agent/cli.py" ]]; then
  d="$PWD"
  while [[ "$d" != "/" ]]; do
    [[ -f "$d/src/sovereign_agent/cli.py" ]] && { ROOT="$d"; break; }
    d="$(dirname "$d")"
  done
fi
[[ -f "$ROOT/src/sovereign_agent/cli.py" ]] \
  || { echo "✗ run from repo root or pass it as arg"; exit 1; }
echo "◊ repo root: $ROOT"
PKG="$ROOT/src/sovereign_agent"
TOOLS="$PKG/tools"
APP="$PKG/cockpit/app.py"
INIT="$TOOLS/__init__.py"

# ── Backup helpers ────────────────────────────────────────────────────────────
ts(){ date +%Y%m%d%H%M%S; }
backup(){ [[ -f "$1" ]] && cp "$1" "$1.bak.$(ts)"; }

# ── 1. Copy new tool files ────────────────────────────────────────────────────
echo "→ installing tool files"
if [[ -f "$TOOLS/self_knowledge.py" ]]; then
  echo "  ↷ tools/self_knowledge.py already exists — overwriting"
fi
cp "$HERE/payload/src/sovereign_agent/tools/self_knowledge.py" "$TOOLS/self_knowledge.py"
echo "  ✓ tools/self_knowledge.py"

if [[ -f "$TOOLS/vessel_status.py" ]]; then
  echo "  ↷ tools/vessel_status.py already exists — overwriting"
fi
cp "$HERE/payload/src/sovereign_agent/tools/vessel_status.py" "$TOOLS/vessel_status.py"
echo "  ✓ tools/vessel_status.py"

# ── 2. Patch tools/__init__.py ────────────────────────────────────────────────
echo "→ patching tools/__init__.py"
python3 - "$INIT" <<'PYEOF'
import sys, pathlib

init = pathlib.Path(sys.argv[1])
src = init.read_text(encoding="utf-8")

IMPORT_MARKER = "from .self_knowledge import"
if IMPORT_MARKER in src:
    print("  ↷ self_knowledge imports already present — skipping")
else:
    OLD_IMPORT = "from .write_file import WriteFileTool"
    NEW_IMPORT = (
        "from .self_knowledge import ListAvailableToolsTool, ListSovCommandsTool, ReadSelfTool\n"
        "from .vessel_status import VesselStatusTool\n"
        "from .write_file import WriteFileTool"
    )
    if OLD_IMPORT not in src:
        print("✗ expected anchor 'from .write_file import WriteFileTool' not found", file=sys.stderr)
        sys.exit(1)
    src = src.replace(OLD_IMPORT, NEW_IMPORT, 1)
    print("  ✓ import lines added")

ALL_MARKER = '"ListAvailableToolsTool"'
if ALL_MARKER in src:
    print("  ↷ __all__ entries already present — skipping")
else:
    OLD_ALL = '    "WriteFileTool",'
    NEW_ALL = (
        '    "ListAvailableToolsTool",\n'
        '    "ListSovCommandsTool",\n'
        '    "ReadSelfTool",\n'
        '    "VesselStatusTool",\n'
        '    "WriteFileTool",'
    )
    if OLD_ALL not in src:
        print("✗ expected __all__ anchor '\"WriteFileTool\",' not found", file=sys.stderr)
        sys.exit(1)
    src = src.replace(OLD_ALL, NEW_ALL, 1)
    print("  ✓ __all__ entries added")

init.write_text(src, encoding="utf-8")
print("  ✓ tools/__init__.py written")
PYEOF

# ── 3. Patch cockpit/app.py — slash commands + methods ───────────────────────
echo "→ patching cockpit/app.py"
backup "$APP"
python3 - "$APP" <<'PYEOF'
import sys, pathlib, textwrap

app = pathlib.Path(sys.argv[1])
src = app.read_text(encoding="utf-8")

# ── 3a. Add elif branches in _handle_slash before the final else ─────────────
SLASH_MARKER = '        elif verb in ("self",'
if SLASH_MARKER in src:
    print("  ↷ slash commands already patched — skipping")
else:
    OLD_ELSE = '        else:\n            self._write_meta(f"unknown command: /{verb}")'
    NEW_ELSE = textwrap.dedent("""\
        elif verb in ("self", "aria", "who", "identity"):
            # /self  →  Aria's kernel and current durable state inline
            self._run_cli_async(["sovereign", "aria"], label="self")
        elif verb in ("tools", "hands", "capabilities", "toolbox"):
            # /tools  →  every registered tool with tier and description
            self._show_tools_inline()
        elif verb in ("sentinels", "stewards", "health-all"):
            # /sentinels  →  health status of every registered sentinel
            self._show_sentinels_inline()
        else:
            self._write_meta(f"unknown command: /{verb}")\
    """)
    # Indent to match app.py's 8-space method body indent
    NEW_ELSE = "\n".join("        " + line if not line.startswith("        ") else line
                         for line in NEW_ELSE.splitlines())
    if OLD_ELSE not in src:
        print("✗ slash-command else-anchor not found — has app.py changed?", file=sys.stderr)
        sys.exit(1)
    src = src.replace(OLD_ELSE, NEW_ELSE, 1)
    print("  ✓ /self, /tools, /sentinels slash branches added")

# ── 3b. Add _show_tools_inline and _show_sentinels_inline before _save_report ─
METHOD_MARKER = "    def _show_tools_inline(self)"
if METHOD_MARKER in src:
    print("  ↷ _show_tools_inline already present — skipping")
else:
    METHOD_ANCHOR = "    def _save_report(self) -> None:"
    NEW_METHODS = textwrap.dedent('''\
        def _show_tools_inline(self) -> None:
            """Print all registered tools (tier, name, description) to the chat log."""
            try:
                import sovereign_agent.tools as _tpkg  # noqa: F401 — trigger registration
                from sovereign_agent.authority import _TIER_REGISTRY
                entries = sorted(_TIER_REGISTRY.values(), key=lambda m: (m.tier, m.name))
                tier_labels = {
                    0: "read-only", 1: "reversible write",
                    2: "shell/long-running", 3: "irreversible",
                }
                self._write_meta("[b]◊ available tools[/b]")
                current_tier = -1
                for meta in entries:
                    if meta.tier != current_tier:
                        current_tier = meta.tier
                        label = tier_labels.get(current_tier, f"tier {current_tier}")
                        self._write_meta(
                            f"[dim]── Tier {current_tier} · {label} ──[/dim]"
                        )
                    desc_preview = meta.description[:80] + ("…" if len(meta.description) > 80 else "")
                    self._write_meta(f"  [b]{meta.name}[/b]  [dim]{desc_preview}[/dim]")
                self._write_meta(f"[dim]{len(entries)} tools registered[/dim]")
            except Exception as exc:  # noqa: BLE001
                self._write_meta(f"[red]tools unavailable: {exc!r}[/red]")

        def _show_sentinels_inline(self) -> None:
            """Print health status of every registered sentinel to the chat log."""
            try:
                from sovereign_agent.stewardship.registry import gather_health
                from sovereign_agent.config import SETTINGS
                data_dir = SETTINGS.paths.data_dir
                if data_dir is None:
                    self._write_meta(
                        "[yellow]data_dir not configured — cannot read sentinels[/yellow]"
                    )
                    return
                statuses = gather_health(data_dir)
                level_colors = {
                    "ok": "green", "warning": "yellow",
                    "error": "red", "unknown": "dim",
                }
                self._write_meta("[b]◊ sentinel health[/b]")
                for hs in statuses:
                    color = level_colors.get(hs.level, "dim")
                    self._write_meta(
                        f"  [{color}]{hs.level:8s}[/{color}]  {hs.sentinel_id}"
                        f"  [dim]{hs.summary}[/dim]"
                    )
                self._write_meta(f"[dim]{len(statuses)} sentinels[/dim]")
            except Exception as exc:  # noqa: BLE001
                self._write_meta(f"[red]sentinels unavailable: {exc!r}[/red]")

        def _save_report(self) -> None:\
    ''')
    # Re-indent to 4-space class body indent
    indented = "\n".join("    " + line for line in NEW_METHODS.splitlines())
    if METHOD_ANCHOR not in src:
        print("✗ method anchor 'def _save_report' not found — has app.py changed?", file=sys.stderr)
        sys.exit(1)
    src = src.replace(METHOD_ANCHOR, indented, 1)
    print("  ✓ _show_tools_inline and _show_sentinels_inline methods added")

app.write_text(src, encoding="utf-8")
print("  ✓ cockpit/app.py written")
PYEOF

# ── 4. Install tests ──────────────────────────────────────────────────────────
echo "→ installing tests"
cp "$HERE/tests/test_self_knowledge_tools.py" "$ROOT/tests/test_self_knowledge_tools.py"
echo "  ✓ tests/test_self_knowledge_tools.py"

# ── 5. Compile check ─────────────────────────────────────────────────────────
echo "→ compile check"
python3 -m py_compile \
  "$TOOLS/self_knowledge.py" \
  "$TOOLS/vessel_status.py" \
  "$TOOLS/__init__.py" \
  "$APP" \
  "$ROOT/tests/test_self_knowledge_tools.py"
echo "  ✓ all files compile"

echo
echo "✓ done. next:"
echo "    source .venv/bin/activate"
echo "    pytest tests/test_self_knowledge_tools.py -v   # new tests"
echo "    pytest -q                                       # full suite"
echo "    .venv/bin/sovereign cockpit"
echo "      /tools      ← see all available tools"
echo "      /self       ← see Aria's kernel"
echo "      /sentinels  ← see sentinel health"
