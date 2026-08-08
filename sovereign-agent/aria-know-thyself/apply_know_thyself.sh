#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
#  apply_know_thyself.sh — The Cosmic Gym. Aria becomes fully self-aware.
#
#  Four changes:
#
#  1. loop.py — three new system-prompt sections injected before COMPLETION:
#       KNOW THYSELF — BOOT SEQUENCE  (aria_status on every session start)
#       YOUR WORLD                    (where everything lives, all paths)
#       SENTINEL HEALTH               (what to do with sentinel warnings)
#
#  2. tools/aria_status.py — unified one-call snapshot:
#       vessel + kernel + tools + sentinels + session + workspace paths
#
#  3. tools/read_diagnosis_log.py — reads the ConflictCatalog:
#       Conflict→Diagnosis→Resolution history; institutional memory
#
#  4. cockpit/app.py — three new slash commands (using @work decorator):
#       /boot      → full self-awareness status inline
#       /docs      → read and display CLAUDE.md doctrine
#       /diagnosis → show recent conflict catalog entries
#
#  Apply after: aria-self-knowledge (vessel_status, read_self, list_available_tools)
#               aria-session-memory (read_session)
#  If those aren't applied yet, aria_status degrades gracefully.
#
#  Idempotent. Backs up loop.py, app.py, __init__.py before patching.
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
APP="$PKG/cockpit/app.py"
ts(){ date +%Y%m%d%H%M%S; }

# ── 1. Install tool files ──────────────────────────────────────────────────
echo "→ installing tools/aria_status.py"
cp "$HERE/payload/src/sovereign_agent/tools/aria_status.py" "$TOOLS/aria_status.py"
echo "  ✓ tools/aria_status.py"

echo "→ installing tools/read_diagnosis_log.py"
cp "$HERE/payload/src/sovereign_agent/tools/read_diagnosis_log.py" "$TOOLS/read_diagnosis_log.py"
echo "  ✓ tools/read_diagnosis_log.py"

# ── 2. Patch tools/__init__.py ─────────────────────────────────────────────
echo "→ patching tools/__init__.py"
cp "$INIT" "$INIT.bak.$(ts)"

python3 - "$INIT" <<'PYEOF'
import sys, pathlib
init = pathlib.Path(sys.argv[1])
src = init.read_text(encoding="utf-8")

if "from .aria_status import" in src:
    print("  ↷ aria_status import already present — skipping")
else:
    for anchor in ("from .read_file import ReadFileTool", "from .write_file import WriteFileTool"):
        if anchor in src:
            src = src.replace(
                anchor,
                "from .aria_status import AriaStatusTool\n"
                "from .read_diagnosis_log import ReadDiagnosisLogTool\n"
                + anchor,
                1,
            )
            print("  ✓ AriaStatusTool, ReadDiagnosisLogTool imports added")
            break
    else:
        print("✗ no anchor found in __init__.py", file=sys.stderr)
        sys.exit(1)

if '"AriaStatusTool"' not in src:
    for anchor_all in ('    "ReadFileTool",', '    "WriteFileTool",'):
        if anchor_all in src:
            src = src.replace(
                anchor_all,
                '    "AriaStatusTool",\n    "ReadDiagnosisLogTool",\n' + anchor_all,
                1,
            )
            print("  ✓ AriaStatusTool, ReadDiagnosisLogTool added to __all__")
            break
else:
    print("  ↷ AriaStatusTool already in __all__ — skipping")

init.write_text(src, encoding="utf-8")
print("  ✓ tools/__init__.py written")
PYEOF

# ── 3. Patch loop.py ──────────────────────────────────────────────────────
echo "→ patching loop.py (KNOW THYSELF sections)"
cp "$LOOP" "$LOOP.bak.$(ts)"

python3 - "$LOOP" <<'PYEOF'
import sys, pathlib
loop = pathlib.Path(sys.argv[1])
src = loop.read_text(encoding="utf-8")

MARKER = "# know-thyself-d"
if MARKER in src:
    print("  ↷ loop.py already patched — skipping")
    sys.exit(0)

NEW_SECTIONS = (
    "\n"
    "═══ KNOW THYSELF — BOOT SEQUENCE ═══\n"
    "At the start of EVERY new session, before any task work, call:\n"
    "\n"
    "  aria_status()   → one call returns: VRAM, CPU, RAM, disk, uptime,\n"
    "                    kernel (commitments, voice, mood), all registered tools\n"
    "                    by tier, sentinel health for each monitor, active session\n"
    "                    summary, and workspace paths.\n"
    "\n"
    "Report a one-line orientation before beginning:\n"
    '  "GTX 1070, 6.1GB VRAM free. 3/3 sentinels ok. 23 tools. v0.2.60."\n'
    "\n"
    "If aria_status is unavailable, fall back individually:\n"
    "  vessel_status() + read_self() + list_available_tools()\n"
    "\n"
    "On session RESUME (a prior session was in progress):\n"
    "  read_session()  → what was done, what remains; call BEFORE new work\n"
    "                    so you don't repeat completed subtasks.\n"
    "\n"
    "Do the boot sequence every time, without being asked.\n"
    "\n"
    "═══ YOUR WORLD ═══\n"
    "Source and data — use read_file, list_dir, search_text freely (all Tier 0):\n"
    "\n"
    "SOURCE (your body — find by searching for CLAUDE.md to locate repo root):\n"
    "  CLAUDE.md                              → operating doctrine; read when unsure\n"
    "  src/sovereign_agent/aria.py            → your kernel (commitments, voice)\n"
    "  src/sovereign_agent/tools/             → your hands  (list_dir to browse)\n"
    "  src/sovereign_agent/stewardship/       → your sentinels (health monitors)\n"
    "  src/sovereign_agent/authority.py       → tier matrix\n"
    "  src/sovereign_agent/router.py          → how intents are classified\n"
    "  src/sovereign_agent/diagnosis.py       → conflict catalog schema\n"
    "\n"
    "DATA (your memory — all under SETTINGS.paths.data_dir):\n"
    "  atoms.db      → long-term memory   use: memory_search, memory_write\n"
    "  palace.db     → memory palace      use: palace_search\n"
    "  diagnoses/    → conflict catalog   use: read_diagnosis_log()\n"
    "  sessions/     → prior sessions     use: read_session()\n"
    "  sandbox/      → Tier 1 write space (safe for your own files)\n"
    "  images/       → generated/edited/screenshot images\n"
    "\n"
    "NAVIGATION (all Tier 0, act without asking):\n"
    "  aria_status()               → everything at once\n"
    "  read_file(path)             → read any text file\n"
    "  list_dir(path)              → list a directory\n"
    "  search_text(pattern, path)  → grep across a directory tree\n"
    "\n"
    "═══ SENTINEL HEALTH ═══\n"
    "Sentinels are in src/sovereign_agent/stewardship/. They observe and report\n"
    "but never act — propose-only architecture. Health is in aria_status().\n"
    "\n"
    "  ok      → nominal. Continue.\n"
    "  warning → something needs attention. Note it; investigate if relevant.\n"
    "  error   → invariant violated. Investigate before depending on that subsystem.\n"
    "\n"
    "Never ignore a sentinel error. Read its source to understand what it watches.\n"
    "Check read_diagnosis_log() for prior incidents before deciding what to do.\n"
    "\n"
)

OLD = "═══ COMPLETION ═══"
if OLD not in src:
    print("✗ COMPLETION anchor not found in loop.py", file=sys.stderr)
    sys.exit(1)

src = src.replace(OLD, NEW_SECTIONS + OLD, 1)
# Mark as applied (inside the docstring area at top of file)
src = src.replace(
    'SYSTEM_PROMPT_TEMPLATE = """\\\n',
    'SYSTEM_PROMPT_TEMPLATE = """\\\n' + MARKER + '\n',
    1,
)
loop.write_text(src, encoding="utf-8")
print("  ✓ KNOW THYSELF + YOUR WORLD + SENTINEL HEALTH added to loop.py")
PYEOF

# ── 4. Patch app.py ───────────────────────────────────────────────────────
echo "→ patching cockpit/app.py (/boot, /docs, /diagnosis)"
cp "$APP" "$APP.bak.$(ts)"

python3 - "$APP" <<'PYEOF'
import sys, pathlib
app_path = pathlib.Path(sys.argv[1])
src = app_path.read_text(encoding="utf-8")

# ── 4a. Slash command branches ────────────────────────────────────────────
SLASH_MARKER = "# know-thyself-slash-d"
if SLASH_MARKER in src:
    print("  ↷ slash commands already patched — skipping")
else:
    OLD_ELSE = ('        else:\n'
                '            self._write_meta(f"unknown command: /{verb}")')
    if OLD_ELSE not in src:
        print("✗ else-block anchor not found in app.py", file=sys.stderr)
        sys.exit(1)
    NEW_BRANCHES = (
        '        elif verb in ("boot", "status", "arise", "awaken"):\n'
        '            # /boot → unified self-awareness snapshot\n'
        '            self._show_boot_status()\n'
        '        elif verb in ("docs", "doctrine", "claude", "rules"):\n'
        '            # /docs → read and display CLAUDE.md operating doctrine\n'
        '            self._show_claude_md()\n'
        '        elif verb in ("diagnosis", "conflicts", "log"):\n'
        '            # /diagnosis [N] → recent conflict catalog entries\n'
        '            self._show_diagnosis_log(_arg_to_int(arg, 10))\n'
        '        ' + SLASH_MARKER + '\n'
        '        else:\n'
        '            self._write_meta(f"unknown command: /{verb}")'
    )
    src = src.replace(OLD_ELSE, NEW_BRANCHES, 1)
    print("  ✓ /boot, /docs, /diagnosis slash branches added")

# ── 4b. New methods (using @work for async tasks, matching app.py pattern) ─
METHOD_MARKER = "def _show_boot_status(self)"
if METHOD_MARKER in src:
    print("  ↷ _show_boot_status already present — skipping")
else:
    ANCHOR = "    def _save_report(self)"
    if ANCHOR not in src:
        print("✗ _save_report anchor not found in app.py", file=sys.stderr)
        sys.exit(1)

    NEW_METHODS = (
        '\n'
        '    @work(exclusive=False, group="cli")\n'
        '    async def _show_boot_status(self) -> None:\n'
        '        """/ boot — full self-awareness snapshot via aria_status()."""\n'
        '        self._write_meta("[bold cyan]◊ booting self-awareness...[/bold cyan]")\n'
        '        try:\n'
        '            from sovereign_agent.tools.aria_status import AriaStatusTool\n'
        '            tool = AriaStatusTool()\n'
        '            result = await tool.execute(tool.Args(), trace_id="boot")\n'
        '        except Exception as exc:\n'
        '            self._write_meta(f"[red]aria_status unavailable: {exc!r}[/red]")\n'
        '            return\n'
        '        if not result.ok:\n'
        '            self._write_meta(f"[yellow]aria_status failed: {result.error}[/yellow]")\n'
        '            return\n'
        '        m = result.metadata or {}\n'
        '        self._write_meta(f"[bold cyan]{result.output}[/bold cyan]")\n'
        '        v = m.get("vessel", {})\n'
        '        if "vram_free_mb" in v:\n'
        '            self._write_meta(\n'
        '                f"[dim]vessel:[/dim] "\n'
        '                f"VRAM {v[\'vram_free_mb\']}MB free/{v.get(\'vram_total_mb\',\'?\')}MB  "\n'
        '                f"| RAM {v.get(\'mem_used_gb\',\'?\')}GB/{v.get(\'mem_total_gb\',\'?\')}GB  "\n'
        '                f"| CPU {v.get(\'cpu_percent\',\'?\')}%  "\n'
        '                f"| up {v.get(\'uptime_hours\',\'?\')}h"\n'
        '            )\n'
        '        s = m.get("sentinels", {})\n'
        '        if "detail" in s:\n'
        '            level_colors = {"ok": "green", "warning": "yellow", "error": "red"}\n'
        '            parts = []\n'
        '            for sd in s["detail"]:\n'
        '                c = level_colors.get(sd["level"], "white")\n'
        '                parts.append(f"[{c}]{sd[\'id\']}:{sd[\'level\']}[/{c}]")\n'
        '            self._write_meta("[dim]sentinels:[/dim] " + "  ".join(parts))\n'
        '        t = m.get("tools", {})\n'
        '        if "total" in t:\n'
        '            tc = t.get("tier_counts", {})\n'
        '            tier_str = "  ".join(f"T{k[-1]}:{v}" for k, v in sorted(tc.items()))\n'
        '            self._write_meta(f"[dim]tools:[/dim] {t[\'total\']} loaded  [{tier_str}]")\n'
        '        k = m.get("kernel", {})\n'
        '        if "designation" in k:\n'
        '            self._write_meta(\n'
        '                f"[dim]kernel:[/dim] {k[\'designation\']}  "\n'
        '                f"| voice: {k.get(\'voice\', \'\')}"\n'
        '            )\n'
        '        for c in k.get("commitments", []):\n'
        '            self._write_meta(f"  [dim]·[/dim] {c}")\n'
        '        w = m.get("workspace", {})\n'
        '        if "repo_root" in w:\n'
        '            self._write_meta(f"[dim]repo:[/dim]     {w[\'repo_root\']}")\n'
        '            self._write_meta(f"[dim]data dir:[/dim] {w.get(\'data_dir\', \'??\')}")\n'
        '        sess = m.get("session", {})\n'
        '        if sess.get("status") not in (None, "no active session"):\n'
        '            self._write_meta(\n'
        '                f"[dim]session:[/dim]  {sess.get(\'goal\',\'?\')[:80]}  "\n'
        '                f"[{sess.get(\'done\',0)}/{sess.get(\'subtask_count\',0)} done]"\n'
        '            )\n'
        '\n'
        '    def _show_claude_md(self) -> None:\n'
        '        """/ docs — display CLAUDE.md (operating doctrine) inline."""\n'
        '        import pathlib as _pl\n'
        '        p = _pl.Path(__file__).resolve()\n'
        '        for _ in range(8):\n'
        '            candidate = p / "CLAUDE.md"\n'
        '            if candidate.exists():\n'
        '                try:\n'
        '                    text = candidate.read_text(encoding="utf-8")\n'
        '                    self._write_meta("[bold cyan]◊ CLAUDE.md — operating doctrine[/bold cyan]")\n'
        '                    for line in text.splitlines():\n'
        '                        self._write_meta(line or " ")\n'
        '                except Exception as exc:\n'
        '                    self._write_meta(f"[red]error reading CLAUDE.md: {exc}[/red]")\n'
        '                return\n'
        '            p = p.parent\n'
        '        self._write_meta("[yellow]CLAUDE.md not found — searched 8 levels up from cockpit[/yellow]")\n'
        '\n'
        '    @work(exclusive=False, group="cli")\n'
        '    async def _show_diagnosis_log(self, limit: int = 10) -> None:\n'
        '        """/ diagnosis — show recent conflict catalog entries."""\n'
        '        self._write_meta(f"[bold cyan]◊ diagnosis catalog (last {limit})...[/bold cyan]")\n'
        '        try:\n'
        '            from sovereign_agent.tools.read_diagnosis_log import ReadDiagnosisLogTool\n'
        '            tool = ReadDiagnosisLogTool()\n'
        '            result = await tool.execute(tool.Args(limit=limit), trace_id="diag")\n'
        '            if result.ok:\n'
        '                for line in result.output.splitlines():\n'
        '                    self._write_meta(line)\n'
        '            else:\n'
        '                self._write_meta(f"[yellow]{result.error}[/yellow]")\n'
        '        except Exception as exc:\n'
        '            self._write_meta(f"[red]diagnosis log error: {exc!r}[/red]")\n'
        '\n'
        '    def _save_report(self)'
    )
    src = src.replace(ANCHOR, NEW_METHODS, 1)
    print("  ✓ _show_boot_status, _show_claude_md, _show_diagnosis_log methods added")

app_path.write_text(src, encoding="utf-8")
print("  ✓ cockpit/app.py written")
PYEOF

# ── 5. Compile checks ──────────────────────────────────────────────────────
echo "→ compile check"
python3 -m py_compile \
  "$TOOLS/aria_status.py" \
  "$TOOLS/read_diagnosis_log.py" \
  "$INIT" \
  "$LOOP" \
  "$APP"
echo "  ✓ all files compile"

# ── 6. Install tests ───────────────────────────────────────────────────────
cp "$HERE/tests/test_know_thyself.py" "$ROOT/tests/test_know_thyself.py"
python3 -m py_compile "$ROOT/tests/test_know_thyself.py"
echo "  ✓ tests/test_know_thyself.py installed + compiles"

echo
echo "✓ done. Aria is now fully self-aware."
echo
echo "  cockpit: /boot      → full status snapshot"
echo "           /docs      → read CLAUDE.md doctrine"
echo "           /diagnosis → recent conflict catalog"
echo
echo "  agent:   aria_status()         → one-call everything"
echo "           read_diagnosis_log()  → past conflicts + fixes"
echo
echo "  run tests: pytest tests/test_know_thyself.py -v"
