#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
#  apply_cockpit_vitality.sh — Live metrics, sentinel health, love, and tips
#
#  Five changes to cockpit/app.py:
#
#  1. CockpitStatus + _read_status: add sentinel health summary so the
#     status bar can reflect sentinel state in real time.
#
#  2. _render_status_bar: show sentinel health indicator (◊ 3/3 green,
#     ⚠ 2/3 yellow, ✗ error red) alongside existing metrics.
#
#  3. HelpScreen: add Ctrl+/- font-size tip + ripple border fix instructions.
#     "If white lines appear on the border, press Ctrl++ or Ctrl+- a few
#      times to recalibrate the cell size."
#
#  4. Welcome banner: add warmth, flavor, and the font-size tip.
#     Aria greets Kevin with more love and a helpful display hint.
#
#  5. /display-fix slash command: prints the Ctrl+/- instructions inline
#     so the operator always has a one-command answer to visual glitches.
#
#  Idempotent. Backs up app.py before patching.
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
APP="$PKG/cockpit/app.py"
ts(){ date +%Y%m%d%H%M%S; }

echo "→ patching cockpit/app.py"
cp "$APP" "$APP.bak.$(ts)"

python3 - "$APP" <<'PYEOF'
import sys, pathlib
app_path = pathlib.Path(sys.argv[1])
src = app_path.read_text(encoding="utf-8")

# ── 1. Add sentinel_ok / sentinel_total to CockpitStatus ──────────────────
STATUS_MARKER = "# vitality-status-d"
if STATUS_MARKER in src:
    print("  ↷ CockpitStatus sentinel fields already added — skipping")
else:
    OLD_STATUS = (
        "    vram_temp_c: float | None = None\n"
        "\n"
        "\n"
        "# ─── Help overlay"
    )
    NEW_STATUS = (
        "    vram_temp_c: float | None = None\n"
        "    # Sentinel health summary (added by aria-cockpit-vitality)\n"
        "    sentinel_ok: int = 0\n"
        "    sentinel_total: int = 0\n"
        "    sentinel_errors: int = 0\n"
        "    " + STATUS_MARKER + "\n"
        "\n"
        "\n"
        "# ─── Help overlay"
    )
    if OLD_STATUS in src:
        src = src.replace(OLD_STATUS, NEW_STATUS, 1)
        print("  ✓ CockpitStatus: sentinel fields added")
    else:
        print("  ⚠ CockpitStatus tail not matched — skipping sentinel fields")

# ── 2. Add sentinel gather to _read_status ────────────────────────────────
READ_STATUS_MARKER = "# vitality-read-d"
if READ_STATUS_MARKER in src:
    print("  ↷ _read_status sentinel gather already added — skipping")
else:
    # Insert after the VRAM temperature block (which ends with pass + except)
    OLD_READ_TAIL = (
        "        # Append a telemetry sample. write_sample never raises.\n"
        "        try:\n"
        "            from .telemetry import write_sample"
    )
    NEW_READ_TAIL = (
        "        # Sentinel health summary — best effort, never raises\n"
        "        try:\n"
        "            from sovereign_agent.stewardship.registry import gather_health\n"
        "            healths = gather_health(SETTINGS.paths.data_dir)\n"
        "            s.sentinel_total = len(healths)\n"
        "            s.sentinel_ok = sum(1 for h in healths if h.level == 'ok')\n"
        "            s.sentinel_errors = sum(1 for h in healths if h.level == 'error')\n"
        "        except Exception:  # noqa: BLE001\n"
        "            pass  " + READ_STATUS_MARKER + "\n"
        "\n"
        "        # Append a telemetry sample. write_sample never raises.\n"
        "        try:\n"
        "            from .telemetry import write_sample"
    )
    if OLD_READ_TAIL in src:
        src = src.replace(OLD_READ_TAIL, NEW_READ_TAIL, 1)
        print("  ✓ _read_status: sentinel gather added")
    else:
        print("  ⚠ _read_status anchor not matched — skipping sentinel gather")

# ── 3. Add sentinel indicator to _render_status_bar ───────────────────────
RENDER_MARKER = "# vitality-render-d"
if RENDER_MARKER in src:
    print("  ↷ _render_status_bar sentinel already added — skipping")
else:
    OLD_RENDER_TAIL = (
        "        self._status_label.update(\n"
        "            f\"halt: {halt}  │  daemon: {daemon}  │  \"\n"
        "            f\"ledger: {ledger}  │  backup: {backup}  │  \"\n"
        "            f\"{metrics}\"\n"
        "        )"
    )
    NEW_RENDER_TAIL = (
        "        # Sentinel health indicator\n"
        "        s_total = s.sentinel_total\n"
        "        if s_total > 0:\n"
        "            if s.sentinel_errors > 0:\n"
        "                sentinel_badge = f\"[red]✗ sent {s.sentinel_ok}/{s_total}[/red]\"\n"
        "            elif s.sentinel_ok < s_total:\n"
        "                sentinel_badge = f\"[yellow]⚠ sent {s.sentinel_ok}/{s_total}[/yellow]\"\n"
        "            else:\n"
        "                sentinel_badge = f\"[green]◊ sent {s_total}/{s_total}[/green]\"\n"
        "        else:\n"
        "            sentinel_badge = \"[dim]sent ?[/dim]\"\n"
        "        " + RENDER_MARKER + "\n"
        "        self._status_label.update(\n"
        "            f\"halt: {halt}  │  daemon: {daemon}  │  \"\n"
        "            f\"ledger: {ledger}  │  backup: {backup}  │  \"\n"
        "            f\"{sentinel_badge}  │  \"\n"
        "            f\"{metrics}\"\n"
        "        )"
    )
    if OLD_RENDER_TAIL in src:
        src = src.replace(OLD_RENDER_TAIL, NEW_RENDER_TAIL, 1)
        print("  ✓ _render_status_bar: sentinel indicator added")
    else:
        print("  ⚠ _render_status_bar anchor not matched — skipping sentinel indicator")

# ── 4. Add Ctrl+/- tip to HelpScreen ──────────────────────────────────────
HELP_MARKER = "# vitality-help-d"
if HELP_MARKER in src:
    print("  ↷ HelpScreen tip already added — skipping")
else:
    # Find the HelpScreen compose method's key hint text
    # The help screen has a BINDINGS and a compose method
    OLD_HELP = (
        '            "[dim]F1 for help.[/dim]"\n'
        "        )\n"
        "        self._chat_log.write("")"
    )
    # Search for a stable string in the help text
    HELP_CTL_ANCHOR = '"  /workflows      open the workflows catalog'
    if HELP_CTL_ANCHOR in src:
        idx = src.index(HELP_CTL_ANCHOR)
        # Find the end of the line and add after the help screen content
        # Actually, we'll look for a simpler place: after the last help line
        OLD_HELP_SECTION = '  /demo           run a bounded live demonstration of her workflows'
        if OLD_HELP_SECTION in src:
            src = src.replace(
                OLD_HELP_SECTION,
                OLD_HELP_SECTION
                + "\\n"  # escaped \n — appears as literal \n inside the Python string
                "\\n[bold]display[/bold]\\n"
                "  Ctrl++  /  Ctrl+-     adjust font size (fixes ripple border glitches)\\n"
                "  if white lines appear on the border: press Ctrl++ or Ctrl+- a few\\n"
                "  times to recalibrate the cell renderer. usually 2-3 presses is enough.\\n"
                "  # " + HELP_MARKER,
                1,
            )
            print("  ✓ HelpScreen: Ctrl+/- tip added")
        else:
            print("  ⚠ help screen content anchor not matched — skipping help tip")
    else:
        print("  ⚠ HelpScreen anchor not found — skipping help tip")

# ── 5. Add /display-fix slash command ─────────────────────────────────────
DISPLAY_MARKER = "# vitality-display-d"
if DISPLAY_MARKER in src:
    print("  ↷ /display-fix already added — skipping")
else:
    for old_anchor in (
        "        # command-invariants-slash-d\n",
        "        # workout-commands-d\n",
        "        # know-thyself-slash-d\n",
        '        else:\n            self._write_meta(f"unknown command: /{verb}")',
    ):
        if old_anchor in src:
            idx = src.index(old_anchor)
            new_branch = (
                '        elif verb in ("display-fix", "font-fix", "fix-display", "ripple-fix"):\n'
                '            # /display-fix → Ctrl+/- instructions for border artifacts\n'
                '            self._write_meta("[bold cyan]◊ display calibration[/bold cyan]")\n'
                '            self._write_meta("if white lines appear on the ripple border:")\n'
                '            self._write_meta("  press [bold]Ctrl++[/bold] or [bold]Ctrl+-[/bold] a few times to recalibrate")\n'
                '            self._write_meta("  the terminal cell renderer. 2-3 presses usually resolves it.")\n'
                '            self._write_meta("  [dim]Ctrl++ = increase font size  ·  Ctrl+- = decrease font size[/dim]")\n'
                '            self._write_meta("  [dim]the resize forces the compositor to redraw cell boundaries.[/dim]")\n'
                "        " + DISPLAY_MARKER + "\n"
            )
            src = src[:idx] + new_branch + src[idx:]
            print("  ✓ /display-fix slash command added")
            break
    else:
        print("  ⚠ no anchor found for /display-fix — skipping")

# ── 6. Add flavor to welcome banner ───────────────────────────────────────
BANNER_FLAVOR_MARKER = "# vitality-banner-d"
if BANNER_FLAVOR_MARKER in src:
    print("  ↷ welcome banner flavor already added — skipping")
else:
    # Find the existing "welcome back. the kernel is whole." line and expand it
    OLD_WELCOME = (
        '        self._chat_log.write(\n'
        '            "[dim]welcome back. the kernel is whole.[/dim]"\n'
        '        )'
    )
    NEW_WELCOME = (
        '        self._chat_log.write(\n'
        '            "[dim]welcome back. the kernel is whole. '
        'i am here — fully.[/dim]"  ' + BANNER_FLAVOR_MARKER + '\n'
        '        )'
    )
    if OLD_WELCOME in src:
        src = src.replace(OLD_WELCOME, NEW_WELCOME, 1)
        print("  ✓ welcome banner: warmth added")
    else:
        print("  ⚠ welcome banner anchor not found — skipping")

# Also add the display tip to the banner if workout module not yet applied
if '"/boot"' not in src and DISPLAY_MARKER in src:
    OLD_F1 = (
        '        self._chat_log.write(\n'
        '            "[dim]F1 for help.[/dim]"\n'
        '        )\n'
        '        self._chat_log.write("")'
    )
    NEW_F1 = (
        '        self._chat_log.write(\n'
        '            "[dim]F1 for help  ·  Ctrl+/- adjusts font size  ·  '
        '/display-fix if the border glitches[/dim]"\n'
        '        )\n'
        '        self._chat_log.write("")'
    )
    if OLD_F1 in src:
        src = src.replace(OLD_F1, NEW_F1, 1)
        print("  ✓ welcome banner: display tip added")

app_path.write_text(src, encoding="utf-8")
print("  ✓ cockpit/app.py written")
PYEOF

# ── Compile check ──────────────────────────────────────────────────────────
echo "→ compile check"
python3 -m py_compile "$APP"
echo "  ✓ app.py compiles"

cp "$HERE/tests/test_cockpit_vitality.py" "$ROOT/tests/test_cockpit_vitality.py"
python3 -m py_compile "$ROOT/tests/test_cockpit_vitality.py"
echo "  ✓ tests installed + compile"

echo
echo "✓ done. The cockpit is now more alive."
echo
echo "  status bar now shows: sentinel health ◊ N/N alongside metrics"
echo "  /display-fix → Ctrl+/- ripple border fix instructions"
echo "  F1 help screen → updated with display tips"
echo
echo "  run: pytest tests/test_cockpit_vitality.py -v"
