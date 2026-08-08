#!/usr/bin/env bash
# apply_live_work_chat.sh — durable live-chat messaging during work sessions.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAGE="$REPO/aria-live-work-chat"

if pgrep -f '(^|[[:space:]])(sov|sovereign)[[:space:]]+cockpit([[:space:]]|$)' >/dev/null; then
    echo "Refusing to apply while the Sovereign cockpit is running. Stop it, review this module, then retry." >&2
    exit 1
fi

cp "$STAGE/payload/src/sovereign_agent/tools/inbox_tools.py" \
   "$REPO/src/sovereign_agent/tools/inbox_tools.py"

REPO="$REPO" python3 - <<'PYEOF'
import os
import sys
from pathlib import Path

repo = Path(os.environ["REPO"])
app = repo / "src/sovereign_agent/cockpit/app.py"
loop = repo / "src/sovereign_agent/loop.py"

def replace_once(path: Path, old: str, new: str) -> None:
    src = path.read_text()
    if new in src:
        return
    if old not in src:
        print(f"Anchor missing in {path.name}: {old[:80]!r}", file=sys.stderr)
        raise SystemExit(1)
    path.write_text(src.replace(old, new, 1))

replace_once(app,
    "        self.set_interval(8.0, self._refresh_inbox_pane)\n",
    "        self.set_interval(1.0, self._refresh_inbox_pane)  # live-work-chat-d\n",
)
replace_once(app,
    """            if getattr(self, \"_session_running\", False):  # session-bridge-d
                # Kevin's no-interrupt rule: while a work session runs,
                # his words are QUEUED for the next safe boundary —
                # never dropped, never injected mid-iteration.
                self._queue_for_aria(text)
                return
""",
    """            if getattr(self, \"_session_running\", False):  # live-work-chat-d
                # Show Kevin's words immediately in the shared conversation,
                # then deliver them at the next safe execution boundary.
                self._write_you(text)
                self._queue_for_aria(text)
                return
""",
)
replace_once(app,
    """            if prev_status is None and r.direction != \"to_aria\":
                # A new outgoing request from Aria -- Kevin should see it
                # where he's already looking, not just in a pane he has
                # to remember exists.
                self._write_meta(
                    f\"[magenta]✉ she left you a note:[/magenta] \"
                    f\"{escape(r.title)} [dim][{r.short_id}][/dim]\"
                )
""",
    """            if prev_status is None and r.direction != \"to_aria\":
                # `send_to_human(..., live_chat=True)` is a real mid-task
                # conversational turn, still backed by the durable inbox.
                if \"live-chat\" in (r.tags or []):
                    body = (r.body or \"\").strip()
                    text = escape(r.title)
                    if body:
                        text += f\"\\n{escape(body)}\"
                    self._write_aria(text)
                else:
                    self._write_meta(
                        f\"[magenta]✉ she left you a note:[/magenta] \"
                        f\"{escape(r.title)} [dim][{r.short_id}][/dim]\"
                    )
""",
)
replace_once(loop,
    """  send_to_human(title, kind, body, ...)  T0 — a durable message to Kevin.
                                               Shows in his inbox AND the
                                               main chat pane. Not a live
                                               interrupt — he answers
                                               when he's next available.
""",
    """  send_to_human(title, kind, body, live_chat=True, ...)  T0 — send Kevin a live,
                                               durable mid-task message. It appears
                                               in the cockpit chat within a second
                                               and remains in the inbox. His reply
                                               reaches you at the next safe boundary.
""",
)
PYEOF

cp "$STAGE/tests/test_live_work_chat.py" "$REPO/tests/test_live_work_chat.py"
echo "Applied aria-live-work-chat. Verify with: .venv/bin/python -m pytest tests/test_live_work_chat.py tests/test_session_bridge_live.py -q"
