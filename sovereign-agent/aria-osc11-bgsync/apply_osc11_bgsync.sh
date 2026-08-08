#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
#  apply_osc11_bgsync.sh — pin the terminal background to Aria's live surface
#  so sub-pixel cell seams stop revealing the desktop accent. Idempotent.
#  Safe to re-run.
#
#  Adds / updates:
#    • cockpit/term_bg_sync.py    (OSC 11 sync; SOV_NO_TERM_BG_SYNC kill switch)
#    • tests/test_term_bg_sync.py
#    • cockpit/app.py             (one guarded block in on_mount: installs it)
# ═══════════════════════════════════════════════════════════════════════════
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PAYLOAD="$HERE/payload"

# ── locate repo root (dir containing src/sovereign_agent/cli.py) ────────────
ROOT="${1:-$PWD}"
if [[ ! -f "$ROOT/src/sovereign_agent/cli.py" ]]; then
  d="$PWD"
  while [[ "$d" != "/" ]]; do
    if [[ -f "$d/src/sovereign_agent/cli.py" ]]; then ROOT="$d"; break; fi
    d="$(dirname "$d")"
  done
fi
if [[ ! -f "$ROOT/src/sovereign_agent/cli.py" ]]; then
  echo "✗ could not find src/sovereign_agent/cli.py."
  echo "  run from your sovereign-agent repo root, or: bash apply_osc11_bgsync.sh /path/to/repo"
  exit 1
fi
echo "◊ repo root: $ROOT"

PKG="$ROOT/src/sovereign_agent"
COCKPIT="$PKG/cockpit"
APP="$COCKPIT/app.py"

# ── 1. module + test ────────────────────────────────────────────────────────
echo "→ installing cockpit/term_bg_sync.py"
cp "$PAYLOAD/src/sovereign_agent/cockpit/term_bg_sync.py" "$COCKPIT/term_bg_sync.py"
echo "  ✓ term_bg_sync.py"

echo "→ installing tests"
cp "$PAYLOAD/tests/test_term_bg_sync.py" "$ROOT/tests/test_term_bg_sync.py"
echo "  ✓ test_term_bg_sync.py"

# ── 2. splice the installer into App.on_mount (idempotent + drift guard) ────
if grep -q "install_terminal_bg_sync" "$APP"; then
  echo "→ app.py already calls install_terminal_bg_sync — skipping splice"
else
  echo "→ splicing the bg-sync installer into on_mount"
  cp "$APP" "$APP.bak.$(date +%Y%m%d%H%M%S)"
  python3 - "$APP" <<'PY'
import sys
app_path = sys.argv[1]
src = open(app_path, encoding="utf-8").read()

anchor = '        self._chat_log = self.query_one("#chat-log", RichLog)'
if anchor not in src:
    print("✗ anchor not found in app.py (file drifted?). No changes made.")
    raise SystemExit(1)

block = (
    "        # ── Keep the terminal's own background in lockstep with Aria's\n"
    "        # live surface (OSC 11), so sub-pixel cell seams on a fractionally-\n"
    "        # scaled display reveal surface-on-surface (invisible) instead of\n"
    "        # the desktop accent. Inert unless on a real TTY;\n"
    "        # SOV_NO_TERM_BG_SYNC=1 disables it.\n"
    "        try:\n"
    "            from .term_bg_sync import install_terminal_bg_sync\n"
    "            self._term_bg_sync = install_terminal_bg_sync(self)\n"
    "        except Exception:\n"
    "            self._term_bg_sync = None\n"
    "\n"
)
src = src.replace(anchor, block + anchor, 1)
open(app_path, "w", encoding="utf-8").write(src)
print("  ✓ inserted install_terminal_bg_sync block before the #chat-log query")
PY
fi

# ── 3. compile check ────────────────────────────────────────────────────────
echo "→ compile check"
python3 -m py_compile \
  "$COCKPIT/term_bg_sync.py" \
  "$APP" \
  "$ROOT/tests/test_term_bg_sync.py"
echo "  ✓ all files compile"

echo
echo "✓ done. next:"
echo "    .venv/bin/python -m pytest -q tests/test_term_bg_sync.py"
echo "    .venv/bin/sovereign cockpit          # watch the faint accent lines vanish"
echo
echo "  kill switch (if you ever want it off for a run):"
echo "    SOV_NO_TERM_BG_SYNC=1 .venv/bin/sovereign cockpit"
