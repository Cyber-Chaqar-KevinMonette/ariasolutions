"""command_bridge.py — 🌉 the cockpit speaks, the server updates.

Kevin's ask (2026-07-18): "execute slash commands in Discord via our
cockpit… have her update the server that way." Honest mechanism: Discord
doesn't let a bot invoke its own slash commands (interactions are
user-initiated by design) — but every admin outcome is OURS, exposed as
helpers in bot.py. So the bridge is a local, audited command queue:

  cockpit `/server <cmd>` → enqueue() appends to
  `<data>/discord_admin/command_queue.ndjson` → the gateway bot's watcher
  task picks it up, runs the SAME idempotent, lock-serialized, rate-paced
  operation the slash command runs, and appends the receipt to
  `command_results.ndjson` → the cockpit echoes it.

Safety: a strict WHITELIST (never eval, never arbitrary), destructive
cleanup still demands the typed phrase as its argument, both files live
on local disk only, malformed entries are skipped with honest results.
This module is the pure half — queue/result stores + rendering; the
executor lives in bot.py's watcher.
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

__all__ = ["WHITELIST", "enqueue", "pending", "record_result",
           "result_for", "render_help"]

# cmd → (needs the gateway?, one-line help)
WHITELIST: dict[str, str] = {
    "setup-all": "the whole setup: structure → webhooks → guides",
    "setup": "build/repair server structure from the blueprint",
    "webhooks": "mint/rehome webhooks + vault the URLs",
    "seed": "post every channel's guide (idempotent)",
    "audit": "the consolidation worksheet (orphans vs blueprint)",
    "scan": "plan coverage — what's missing",
    "cleanup": "delete listed orphan channels (needs: DELETE ORPHANS)",
    # grant-bridge-d (Kevin, 2026-07-27): "give Theodore full access... so
    # we can run tests" — the SAME entitlement grant /grant runs, reachable
    # from the cockpit/CLI without Kevin needing to type it in Discord.
    "grant": "grant a member a plan + timer (args: <user_id> <plan> <days>)",
}

_STALE_S = 3600.0        # a queued command older than this is never executed


def _qpath(data_dir: Path) -> Path:
    return Path(data_dir) / "discord_admin" / "command_queue.ndjson"


def _rpath(data_dir: Path) -> Path:
    return Path(data_dir) / "discord_admin" / "command_results.ndjson"


def _read(path: Path) -> list[dict]:
    try:
        out = []
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
                if isinstance(r, dict):
                    out.append(r)
            except Exception:  # noqa: BLE001
                continue
        return out
    except Exception:  # noqa: BLE001
        return []


def _append(path: Path, rec: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def enqueue(data_dir: Path, cmd: str, args: str = "") -> str:
    """Queue a whitelisted server command; returns its id.
    Unknown command → ValueError (the cockpit shows help instead)."""
    cmd = (cmd or "").strip().lower()
    if cmd not in WHITELIST:
        raise ValueError(f"unknown server command: {cmd!r}")
    rid = uuid.uuid4().hex[:12]
    _append(_qpath(data_dir), {"id": rid, "ts": time.time(),
                               "cmd": cmd, "args": (args or "").strip()})
    return rid


def pending(data_dir: Path, *, now: float | None = None) -> list[dict]:
    """Queued commands with no result yet, oldest first; stale ones
    (>1h — e.g. queued while the bot was down for ages) are auto-answered
    as expired rather than surprising the server later."""
    now = time.time() if now is None else now
    done = {r.get("id") for r in _read(_rpath(data_dir))}
    out = []
    for rec in _read(_qpath(data_dir)):
        if rec.get("id") in done or rec.get("cmd") not in WHITELIST:
            continue
        if now - float(rec.get("ts", 0)) > _STALE_S:
            record_result(data_dir, rec["id"],
                          "⌛ expired unrun (queued over an hour ago) — "
                          "re-issue it if you still want it")
            continue
        out.append(rec)
    out.sort(key=lambda r: r.get("ts", 0))
    return out


def record_result(data_dir: Path, rid: str, result: str) -> None:
    _append(_rpath(data_dir), {"id": rid, "ts": time.time(),
                               "result": str(result)[:4000]})


def result_for(data_dir: Path, rid: str) -> str | None:
    for rec in _read(_rpath(data_dir)):
        if rec.get("id") == rid:
            return str(rec.get("result", ""))
    return None


def render_help() -> str:
    lines = ["🌉 /server <cmd> — she updates the Discord server from here:"]
    for cmd, blurb in WHITELIST.items():
        lines.append(f"  /server {cmd:<10} {blurb}")
    lines.append("The gateway bot executes each one (same idempotent, "
                 "audited ops as the slash commands) and reports back here.")
    return "\n".join(lines)
