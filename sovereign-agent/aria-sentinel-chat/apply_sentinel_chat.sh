#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
#  apply_sentinel_chat.sh — Sentinel health alerts appear in the chat pane
#
#  After aria-cockpit-vitality, sentinel health shows in the status bar.
#  This module goes further: when a sentinel degrades mid-session (ok→warning,
#  ok→error, warning→error), a banner appears in the CHAT PANE immediately.
#  Recovery (warning→ok) emits a calm "cleared" message.
#
#  Implementation:
#  1. Adds `_prev_sentinel_states: dict` field to CockpitApp.__init__
#  2. Patches `_refresh_status_worker` to compare sentinel states each cycle
#     and call `_write_meta` on regression / recovery
#
#  Idempotent. Backs up app.py.
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

APP="$ROOT/src/sovereign_agent/cockpit/app.py"
ts(){ date +%Y%m%d%H%M%S; }

echo "→ patching cockpit/app.py"
cp "$APP" "$APP.bak.$(ts)"

python3 - "$APP" <<'PYEOF'
import sys, pathlib, re
app = pathlib.Path(sys.argv[1])
src = app.read_text(encoding="utf-8")

# ── Step 1: add _prev_sentinel_states field to __init__ ───────────────────
INIT_MARKER = "# sentinel-chat-init-d"
if INIT_MARKER not in src:
    # Find a field initialization in __init__ — look for self._chat_log or similar
    for anchor in (
        "        self._chat_log: RichLog | None = None\n",
        "        self._status_label",
        "        self.status = reactive(",
    ):
        if anchor in src:
            inject = (
                "        self._prev_sentinel_states: dict[str, str] = {}  "
                + INIT_MARKER + "\n"
            )
            src = src.replace(anchor, inject + anchor, 1)
            print("  ✓ _prev_sentinel_states field added to __init__")
            break
    else:
        print("  ⚠ no __init__ anchor found — _prev_sentinel_states not added")

# ── Step 2: patch _refresh_status_worker to compare and alert ─────────────
REFRESH_MARKER = "# sentinel-chat-refresh-d"
if REFRESH_MARKER not in src:
    # Find the body of _refresh_status_worker — it calls self._render_status_bar()
    OLD = (
        "                self.status = await asyncio.to_thread(self._read_status)\n"
        "                self._render_status_bar()\n"
    )
    NEW = (
        "                self.status = await asyncio.to_thread(self._read_status)\n"
        "                self._render_status_bar()\n"
        "                # sentinel-chat: compare and alert on regressions\n"
        "                self._check_sentinel_transitions()  " + REFRESH_MARKER + "\n"
    )
    if OLD in src:
        src = src.replace(OLD, NEW, 1)
        print("  ✓ _check_sentinel_transitions() call added to _refresh_status_worker")
    else:
        print("  ⚠ _refresh_status_worker body not found — sentinel alerts not wired")

# ── Step 3: inject _check_sentinel_transitions method ─────────────────────
METHOD_MARKER = "# sentinel-chat-method-d"
if METHOD_MARKER not in src:
    method_code = '''
    def _check_sentinel_transitions(self) -> None:  # sentinel-chat-method-d
        """Compare current sentinel states to previous; emit chat alerts on change."""
        try:
            from sovereign_agent.config import SETTINGS
            from sovereign_agent.stewardship.registry import gather_health
            statuses = gather_health(SETTINGS.paths.data_dir)
        except Exception:
            return

        WORSE = {"ok": 0, "warning": 1, "error": 2, "unknown": 1}
        new_states: dict[str, str] = {h.sentinel_id: str(h.level) for h in statuses}

        for sid, level in new_states.items():
            prev = self._prev_sentinel_states.get(sid, "ok")
            if WORSE.get(level, 0) > WORSE.get(prev, 0):
                # Regression
                summary = next(
                    (h.summary for h in statuses if h.sentinel_id == sid), ""
                )
                color = "[red]" if level == "error" else "[yellow]"
                self._write_meta(
                    f"{color}◊ SENTINEL ALERT: {sid} — {level}[/{color.strip('[').strip(']')}]"
                )
                if summary:
                    self._write_meta(f"[dim]  {summary[:200]}[/dim]")
            elif WORSE.get(level, 0) < WORSE.get(prev, 0) and prev != "ok":
                # Recovery
                self._write_meta(f"[green]◊ sentinel cleared: {sid}[/green]")

        self._prev_sentinel_states = new_states

'''
    # Insert the method before _write_meta or before _refresh_inbox_pane
    for anchor in ("    def _write_meta(self, text: str)", "    def _refresh_inbox_pane"):
        if anchor in src:
            src = src.replace(anchor, method_code + anchor, 1)
            print("  ✓ _check_sentinel_transitions method injected")
            break
    else:
        print("  ⚠ method injection anchor not found")

app.write_text(src, encoding="utf-8")
print("  ✓ app.py written")
PYEOF

# ── Compile check ──────────────────────────────────────────────────────────
echo "→ compile check"
python3 -m py_compile "$APP"
echo "  ✓ app.py compiles"

cp "$HERE/tests/test_sentinel_chat.py" "$ROOT/tests/test_sentinel_chat.py"
python3 -m py_compile "$ROOT/tests/test_sentinel_chat.py"
echo "  ✓ tests installed + compile"

echo
echo "✓ done. Sentinel health alerts now appear in the chat pane."
echo
echo "  When any sentinel degrades mid-session:"
echo "    ◊ SENTINEL ALERT: <id> — warning/error"
echo "  When it clears:"
echo "    ◊ sentinel cleared: <id>"
echo
echo "  run: pytest tests/test_sentinel_chat.py -v"
