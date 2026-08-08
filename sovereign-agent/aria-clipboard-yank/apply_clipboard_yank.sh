#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
#  apply_clipboard_yank.sh — Ctrl+Y yank-last-response to clipboard (v0.2.40.0)
#
#  Changes (surgical patch to cockpit/app.py — no full-file replacement):
#    • Adds Binding("ctrl+y", "yank_last", "yank") after ctrl+v in BINDINGS
#    • Adds action_yank_last() method that copies Aria's last response
#      to the system clipboard via wl-copy (Wayland) / xclip / xsel / pbcopy
#    • Adds tests/test_yank_action.py
#
#  Idempotent: skips each insertion if the marker already exists.
#  Requires no new Python dependencies — uses _write_clipboard() already in app.py.
# ═══════════════════════════════════════════════════════════════════════════
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${1:-$PWD}"

# -- Locate repo root --------------------------------------------------------
if [[ ! -f "$ROOT/src/sovereign_agent/cli.py" ]]; then
  d="$PWD"
  while [[ "$d" != "/" ]]; do
    [[ -f "$d/src/sovereign_agent/cli.py" ]] && { ROOT="$d"; break; }
    d="$(dirname "$d")"
  done
fi
[[ -f "$ROOT/src/sovereign_agent/cli.py" ]] || { echo "✗ run from repo root or pass path as arg"; exit 1; }
echo "◊ repo root: $ROOT"
PKG="$ROOT/src/sovereign_agent"
APP="$PKG/cockpit/app.py"

# -- Preflight ---------------------------------------------------------------
python3 -c "import sys; assert sys.version_info >= (3,9), 'need Python 3.9+'"

# -- Backup ------------------------------------------------------------------
ts(){ date +%Y%m%d%H%M%S; }
cp "$APP" "$APP.bak.$(ts)"
echo "  ✓ backup written"

# -- Patch via Python (surgical; idempotent) ---------------------------------
python3 - "$APP" <<'PYEOF'
import sys, pathlib, textwrap

app = pathlib.Path(sys.argv[1])
src = app.read_text(encoding="utf-8")

# ── 1. Binding ──────────────────────────────────────────────────────────────
BIND_OLD = '        Binding("ctrl+v", "paste_clipboard", "paste",   show=True,  priority=True),\n        Binding("ctrl+r", "toggle_recording", "rec",    show=True,  priority=True),'
BIND_NEW = '        Binding("ctrl+v", "paste_clipboard", "paste",   show=True,  priority=True),\n        Binding("ctrl+y", "yank_last",       "yank",    show=True,  priority=True),\n        Binding("ctrl+r", "toggle_recording", "rec",    show=True,  priority=True),'

if 'action_yank_last' in src:
    print("  ↷ yank_last already present — skipping binding insertion")
elif BIND_OLD not in src:
    print("✗ expected BIND_OLD not found — has app.py changed? Aborting.", file=sys.stderr)
    sys.exit(1)
else:
    src = src.replace(BIND_OLD, BIND_NEW, 1)
    print("  ✓ Binding ctrl+y inserted")

# ── 2. action_yank_last method ───────────────────────────────────────────────
METHOD_ANCHOR = "        input_box.insert_text_at_cursor(single_line)\n\n    @staticmethod\n    def _read_clipboard() -> str:"
# No textwrap.dedent — write the replacement with correct absolute indentation
METHOD_REPLACEMENT = (
    "        input_box.insert_text_at_cursor(single_line)\n"
    "\n"
    "    def action_yank_last(self) -> None:\n"
    '        """Copy Aria\'s most recent response to the system clipboard (Ctrl+Y).\n'
    "\n"
    '        Scans _transcript backward from the end, collecting every "aria"\n'
    '        line since the last "you" entry (i.e. the last response block).\n'
    "        Writes to the clipboard via _write_clipboard() — wl-copy on\n"
    "        Wayland/COSMIC, xclip/xsel on X11, pbcopy on macOS. Surfaces a\n"
    "        visible meta line on both success and failure so the operator\n"
    "        always knows what happened.\n"
    '        """\n'
    "        last_you_idx = max(\n"
    "            (i for i, (sp, _) in enumerate(self._transcript) if sp == \"you\"),\n"
    "            default=-1,\n"
    "        )\n"
    "        block = [\n"
    "            text for sp, text in self._transcript[last_you_idx + 1 :]\n"
    "            if sp == \"aria\"\n"
    "        ]\n"
    "        if not block:\n"
    '            self._write_meta("[dim](nothing from aria to yank — send a message first)[/dim]")\n'
    "            return\n"
    '        payload = "\\n".join(block)\n'
    "        ok = self._write_clipboard(payload)\n"
    "        if ok:\n"
    '            preview = payload[:60].replace("\\n", " ")\n'
    '            self._write_meta(f"[dim]◊ yanked to clipboard: {preview}…[/dim]")\n'
    "        else:\n"
    "            self._write_meta(\n"
    '                "[yellow]clipboard write failed — is wl-copy / xclip installed?[/yellow]"\n'
    "            )\n"
    "\n"
    "    @staticmethod\n"
    "    def _read_clipboard() -> str:"
)

if 'action_yank_last' in src and METHOD_ANCHOR not in src:
    print("  ↷ method already patched — skipping method insertion")
elif METHOD_ANCHOR not in src:
    print("✗ expected METHOD_ANCHOR not found — has app.py changed? Aborting.", file=sys.stderr)
    sys.exit(1)
else:
    src = src.replace(METHOD_ANCHOR, METHOD_REPLACEMENT, 1)
    print("  ✓ action_yank_last() method inserted")

app.write_text(src, encoding="utf-8")
print("  ✓ app.py written")
PYEOF

# -- Copy tests --------------------------------------------------------------
cp "$HERE/tests/test_yank_action.py" "$ROOT/tests/test_yank_action.py"
echo "  ✓ tests/test_yank_action.py installed"

# -- Compile check -----------------------------------------------------------
echo "→ compile check"
python3 -m py_compile "$APP" "$ROOT/tests/test_yank_action.py"
echo "  ✓ compiles"

echo
echo "✓ done. next:"
echo "    source .venv/bin/activate"
echo "    pytest tests/test_yank_action.py -v    # new tests"
echo "    pytest -q                               # full suite — keep green"
echo "    .venv/bin/sovereign cockpit             # Ctrl+Y to test live"
