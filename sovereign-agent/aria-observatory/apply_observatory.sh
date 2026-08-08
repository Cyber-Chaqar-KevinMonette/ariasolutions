#!/usr/bin/env bash
# apply_observatory.sh — M29: full observability (tool-start events, token counter, /activity)
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo "==> M29 observatory: $REPO"

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
app  = repo / "src/sovereign_agent/cockpit/app.py"

# ── loop.py patch 1: emit token-usage-d after tokens_used ───────────────────
patch(loop,
    old='''\
            tokens_used += int(response.get("prompt_eval_count", 0)) + int(
                response.get("eval_count", 0)
            )

            msg = response.get("message", {})''',
    new='''\
            tokens_used += int(response.get("prompt_eval_count", 0)) + int(
                response.get("eval_count", 0)
            )
            _record("token-usage-d", {  # observatory-token-d
                "prompt_tokens": int(response.get("prompt_eval_count", 0)),
                "completion_tokens": int(response.get("eval_count", 0)),
                "running_total": tokens_used,
                "model": model,
            })

            msg = response.get("message", {})''',
    marker="observatory-token-d",
)

# ── loop.py patch 2: emit tool-start-d before tool.execute() ────────────────
patch(loop,
    old='''\
                result: ToolResult = await tool.execute(parsed, trace_id=trace_id)''',
    new='''\
                _record("tool-start-d", {  # observatory-tool-start-d
                    "tool": tool_name,
                    "tier": meta.tier,
                    "args_summary": str(args)[:200],
                })
                result: ToolResult = await tool.execute(parsed, trace_id=trace_id)''',
    marker="observatory-tool-start-d",
)

# ── app.py patch 1: add _last_tool and _session_tokens instance vars ────────
patch(app,
    old='''\
        self._pending_callback: Any | None = None''',
    new='''\
        self._pending_callback: Any | None = None
        self._last_tool: str = ""        # observatory-status-d
        self._session_tokens: int = 0   # observatory-status-d''',
    marker="observatory-status-d",
)

# ── app.py patch 2: extend _render_event to track tool/token events ─────────
patch(app,
    old='''\
        self._events_log.write(f"[dim]{ts}[/dim] [{color}]{flag}[/{color}]")

    # ''',
    new='''\
        # observatory-render-d
        if flag == "tool-start-d":
            payload = ev.get("payload", {})
            self._last_tool = payload.get("tool", "")
            tier = payload.get("tier", "?")
            self._events_log.write(
                f"[dim]{ts}[/dim] [cyan dim]→ {self._last_tool} T{tier}[/cyan dim]"
            )
            self._render_status_bar()
            return
        if flag == "token-usage-d":
            self._session_tokens = ev.get("payload", {}).get(
                "running_total", self._session_tokens
            )
            self._render_status_bar()
        self._events_log.write(f"[dim]{ts}[/dim] [{color}]{flag}[/{color}]")

    # ''',
    marker="observatory-render-d",
)

# ── app.py patch 3: show tokens + last tool in status bar ───────────────────
patch(app,
    old='''\
        # vitality-render-d
        self._status_label.update(
            f"halt: {halt}  │  daemon: {daemon}  │  "
            f"ledger: {ledger}  │  backup: {backup}  │  "
            f"{sentinel_badge}  │  "
            f"{metrics}"
        )''',
    new='''\
        # vitality-render-d  # observatory-status-d
        obs_parts: list[str] = []
        if self._session_tokens > 0:
            obs_parts.append(f"⊕ {self._session_tokens}t")
        if self._last_tool:
            obs_parts.append(f"[dim][{self._last_tool}][/dim]")
        obs_suffix = "  │  " + "  ".join(obs_parts) if obs_parts else ""
        self._status_label.update(
            f"halt: {halt}  │  daemon: {daemon}  │  "
            f"ledger: {ledger}  │  backup: {backup}  │  "
            f"{sentinel_badge}  │  "
            f"{metrics}{obs_suffix}"
        )''',
    marker="observatory-status-d",
)

# ── app.py patch 4: /activity slash command ──────────────────────────────────
patch(app,
    old='''\
        # vitality-display-d
        # command-invariants-slash-d
        # workout-commands-d
        # know-thyself-slash-d
        else:
            self._write_meta(f"unknown command: /{verb}")''',
    new='''\
        elif verb in ("activity", "toollog"):
            self._show_activity_log()  # observatory-activity-d
        # vitality-display-d
        # command-invariants-slash-d
        # workout-commands-d
        # know-thyself-slash-d
        else:
            self._write_meta(f"unknown command: /{verb}")''',
    marker="observatory-activity-d",
)

# ── app.py patch 5: _show_activity_log method ───────────────────────────────
patch(app,
    old='''\
    def _handle_mode_slash(self, arg: str) -> None:''',
    new='''\
    def _show_activity_log(self, n: int = 30) -> None:
        """Print last N audit events with tool/token focus. /observatory-activity-d"""
        import json as _json
        if not self._events_path.exists():
            self._write_meta("[dim]no events log yet[/dim]")
            return
        lines = self._events_path.read_text().splitlines()[-n:]
        if not lines:
            self._write_meta("[dim]activity log is empty[/dim]")
            return
        self._write_meta("[bold cyan]◊ recent activity[/bold cyan]")
        for raw in lines:
            try:
                ev = _json.loads(raw)
                ts = ev.get("ts", "")[11:19]
                flag = ev.get("flag", "?")
                payload = ev.get("payload", {})
                if flag == "tool-start-d":
                    tool = payload.get("tool", "?")
                    tier = payload.get("tier", "?")
                    self._write_meta(
                        f"  [dim]{ts}[/dim] [cyan]→ {tool}[/cyan] [dim]T{tier}[/dim]"
                    )
                elif flag == "token-usage-d":
                    total = payload.get("running_total", 0)
                    self._write_meta(f"  [dim]{ts}[/dim] [dim]⊕ {total}t running[/dim]")
                elif flag.endswith("-x"):
                    err = payload.get("error", "")[:60]
                    self._write_meta(
                        f"  [dim]{ts}[/dim] [red]{flag}[/red] [dim]{err}[/dim]"
                    )
                elif flag.endswith("-d") and flag not in ("token-usage-d",):
                    self._write_meta(
                        f"  [dim]{ts}[/dim] [green dim]{flag}[/green dim]"
                    )
            except Exception:  # noqa: BLE001
                pass

    def _handle_mode_slash(self, arg: str) -> None:''',
    marker="_show_activity_log",
)

print("M29 observatory: all patches applied.")
PYEOF

# Copy tests
cp "$REPO/aria-observatory/tests/test_observatory.py" "$REPO/tests/test_observatory.py"
echo "==> M29 done. Run: .venv/bin/python -m pytest tests/test_observatory.py -q"
