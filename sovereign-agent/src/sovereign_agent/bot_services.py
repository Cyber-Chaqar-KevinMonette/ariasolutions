"""bot_services.py — 🎛 the Discord bots, run/stopped from the cockpit.

Kevin's ask (2026-07-18): "make it runnable via the cockpit. I enter the
cockpit via sov chat and then I can run the discord bots with a simple
toggle command." The bots live as systemd user units (aria-bot = the
gateway bot, aria-duty = the 24/7 duty loop) — systemd is the ONLY
process manager (single-instance discipline: never a zombie, never the
same bot running ten times). So the toggle is a thin, audited seam over
`systemctl --user`, and the state readers ask systemd — the one source
of process truth.

Pure + injectable: every function takes a `runner` (argv -> (rc, out))
so tests never touch the real OS. All failures degrade to honest
"unknown", never a crash.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

__all__ = ["UNITS", "service_states", "toggle", "restart", "restart_duty",
           "render_states", "states_line", "PRODUCTION_UNIT",
           "pause_for_production", "resume_after_production",
           "write_production_flag", "clear_production_flag", "read_production_flag"]

UNITS: tuple[str, ...] = ("aria-bot.service", "aria-duty.service")


def _default_runner(args: list[str]) -> tuple[int, str]:
    """Run systemctl; bounded, captured, never raises past the boundary."""
    import subprocess
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=20)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except Exception as exc:  # noqa: BLE001
        return 1, type(exc).__name__


def service_states(runner=None) -> dict[str, dict]:
    """unit -> {"active": bool|None, "state": str, "pid": int}.
    active=None means "could not ask systemd" — shown as unknown,
    never guessed."""
    runner = runner or _default_runner
    out: dict[str, dict] = {}
    for unit in UNITS:
        rc, text = runner(["systemctl", "--user", "show", unit,
                           "-p", "ActiveState", "-p", "MainPID"])
        state, pid = "unknown", 0
        if rc == 0:
            for line in text.splitlines():
                if line.startswith("ActiveState="):
                    state = line.split("=", 1)[1].strip() or "unknown"
                elif line.startswith("MainPID="):
                    try:
                        pid = int(line.split("=", 1)[1].strip() or 0)
                    except ValueError:
                        pid = 0
        active = None if state == "unknown" else (state == "active")
        out[unit] = {"active": active, "state": state, "pid": pid}
    return out


def _ledger(data_dir: Path | None, entry: dict) -> None:
    if data_dir is None:
        try:
            from sovereign_agent.config import SETTINGS
            data_dir = SETTINGS.paths.data_dir
        except Exception:  # noqa: BLE001
            return
    try:
        p = Path(data_dir) / "discord_duty" / "service_toggle.ndjson"
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
    except Exception:  # noqa: BLE001
        pass


def toggle(on: bool, *, runner=None, data_dir: Path | None = None,
          units: tuple[str, ...] | None = None) -> str:
    """Start or stop the given units (both, by default) through systemd
    (the no-zombie path), write an audited ledger line, and return the
    honest receipt. units=None keeps the original both-units behavior;
    movie-focus-d (Kevin, 2026-07-29) added the scope so aria-duty alone
    can be paused for movie production without dropping aria-bot's live
    Discord connection — see pause_for_production() below."""
    runner = runner or _default_runner
    scope = units or UNITS
    verb = "start" if on else "stop"
    results = []
    for unit in scope:
        rc, _ = runner(["systemctl", "--user", verb, unit])
        results.append((unit, rc == 0))
    _ledger(data_dir, {"ts": time.time(), "action": verb, "units": list(scope),
                       "results": {u: ok for u, ok in results}})
    states = service_states(runner)
    ok_all = all(ok for _, ok in results)
    label = "Discord bots" if scope == UNITS else " + ".join(u.replace(".service", "") for u in scope)
    head = (f"◉ {label} STARTED" if on and ok_all else
            f"▪ {label} STOPPED" if not on and ok_all else
            "⚠ toggle finished with issues")
    return head + " — " + states_line(states)


def restart(*, runner=None, data_dir: Path | None = None,
            units: tuple[str, ...] | None = None) -> str:
    """discord-control-d (Kevin, 2026-07-25): "add a way for me to control
    the bot... restart the discord bot." A fresh process picking up
    today's code, through the SAME no-zombie systemd path as toggle() —
    `systemctl --user restart` on the given units (both, by default), not
    a separate stop+start pair (systemd's own restart is atomic; two
    separate calls would risk a half-stopped gap if the second one
    failed).

    units=None restarts everything in UNITS (the original, still-default
    behavior). movie-focus-d (Kevin, 2026-07-28) added the units= scope so
    aria-duty alone can be restarted — see restart_duty() below — without
    also bouncing the Discord gateway bot's connection."""
    runner = runner or _default_runner
    scope = units or UNITS
    results = []
    for unit in scope:
        rc, _ = runner(["systemctl", "--user", "restart", unit])
        results.append((unit, rc == 0))
    _ledger(data_dir, {"ts": time.time(), "action": "restart",
                       "units": list(scope), "results": {u: ok for u, ok in results}})
    states = service_states(runner)
    ok_all = all(ok for _, ok in results)
    label = "Discord bots" if scope == UNITS else " + ".join(u.replace(".service", "") for u in scope)
    head = f"↻ {label} RESTARTED" if ok_all else "⚠ restart finished with issues"
    return head + " — " + states_line(states)


def restart_duty(*, runner=None, data_dir: Path | None = None) -> str:
    """Kevin, 2026-07-28: 'add a button and command for me to restart it'
    — aria-duty.service specifically. Its Playwright scraper has a known,
    unfixed memory leak (confirmed live: grew from ~5GB to ~10GB RSS over
    a few hours), and restarting just this ONE unit reclaims that RAM
    without dropping aria-bot's live Discord gateway connection — the two
    concerns (scraping vs. Discord presence) are independent, so a
    targeted restart is strictly better than bouncing both."""
    return restart(runner=runner, data_dir=data_dir, units=("aria-duty.service",))


def states_line(states: dict[str, dict] | None = None, *,
                runner=None) -> str:
    """One-line state summary for headers: 'aria-bot ◉ · aria-duty ◉'."""
    states = states if states is not None else service_states(runner)
    parts = []
    for unit, s in states.items():
        name = unit.replace(".service", "")
        mark = ("◉" if s.get("active") else
                "▪" if s.get("active") is False else "?")
        parts.append(f"{name} {mark}")
    return " · ".join(parts)


def render_states(states: dict[str, dict] | None = None, *,
                  runner=None) -> str:
    """The full cockpit block — state + pid per unit, systemd-authoritative."""
    states = states if states is not None else service_states(runner)
    lines = ["🎛 Discord services (systemd = the one truth):"]
    for unit, s in states.items():
        if s.get("active"):
            lines.append(f"  ◉ {unit} — RUNNING (pid {s.get('pid', 0)})")
        elif s.get("active") is False:
            lines.append(f"  ▪ {unit} — {s.get('state', 'stopped')}")
        else:
            lines.append(f"  ? {unit} — unknown (couldn't ask systemd)")
    lines.append("  toggle: /bots on · /bots off · state: /bots status")
    return "\n".join(lines)


PRODUCTION_UNIT = "aria-duty.service"


def _production_flag_path(data_dir: Path) -> Path:
    return Path(data_dir) / "movie_production.json"


def write_production_flag(data_dir: Path, *, eta_minutes: float | None = None,
                          reason: str = "movie production") -> None:
    """Kevin, 2026-07-29: 'if people try to message her or do pings in
    the discord while she is in production... send them a message saying
    she is in a production period and bots are on pause and maybe leave
    an ETA.' aria-bot's own on_message handler reads this (see
    discord_admin/bot.py) to auto-reply instead of processing the
    message normally — same "check a sentinel file" shape as
    protocol_zero.py's HALT flag, just carrying real content (an ETA)
    instead of a bare boolean."""
    path = _production_flag_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "active": True,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "eta_minutes": eta_minutes,
        "reason": reason,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def clear_production_flag(data_dir: Path) -> None:
    _production_flag_path(data_dir).unlink(missing_ok=True)


def read_production_flag(data_dir: Path) -> dict | None:
    """Never raises — a corrupt/missing flag file degrades to "not in
    production" rather than blocking real Discord replies."""
    path = _production_flag_path(data_dir)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) and data.get("active") else None
    except Exception:  # noqa: BLE001
        return None


def _resolve_data_dir(data_dir: Path | None) -> Path:
    if data_dir is not None:
        return Path(data_dir)
    from sovereign_agent.config import SETTINGS
    return SETTINGS.paths.data_dir


def pause_for_production(*, runner=None, data_dir: Path | None = None,
                         eta_minutes: float | None = None) -> tuple[bool, str]:
    """Kevin, 2026-07-29: "make sure the bots automatically pause while
    episodes are being produced... to prevent memory leaks" — then,
    immediately after: "if people try to message her or do pings...
    make sure we send them a message." Those two asks combined mean this
    can't stop BOTH bots: aria-bot (the Discord gateway) has to stay up
    to actually reply to anyone. Only aria-duty.service (the real
    Playwright-scraper RAM leak, confirmed live 2026-07-29) gets paused;
    aria-bot switches into an away-reply mode instead, driven by the
    production flag this writes.

    Returns (was_active, receipt) — was_active records whether aria-duty
    was actually running. The caller MUST pass it back into
    resume_after_production() so a human who had ALREADY stopped it
    deliberately never gets it turned back on by this mechanism. Meant
    to be called ONCE per production session (one clip, one batch, or
    one whole Auto Series run) — never per clip inside a loop."""
    data_dir = _resolve_data_dir(data_dir)
    write_production_flag(data_dir, eta_minutes=eta_minutes)
    states = service_states(runner=runner)
    was_active = bool(states.get(PRODUCTION_UNIT, {}).get("active"))
    if not was_active:
        return False, "aria-duty already stopped — nothing to pause for production"
    receipt = toggle(False, runner=runner, data_dir=data_dir, units=(PRODUCTION_UNIT,))
    return True, receipt


def resume_after_production(was_active: bool, *, runner=None, data_dir: Path | None = None) -> str:
    """The other half of pause_for_production() — pass back exactly the
    `was_active` it returned. If it's False, this is a deliberate no-op:
    aria-duty was already off before production started, so leaving it
    off is respecting that, not a bug. Always clears the production
    flag regardless, so aria-bot stops auto-replying the moment
    production genuinely ends."""
    data_dir = _resolve_data_dir(data_dir)
    clear_production_flag(data_dir)
    if not was_active:
        return "aria-duty was already stopped before production started — leaving it off"
    return toggle(True, runner=runner, data_dir=data_dir, units=(PRODUCTION_UNIT,))
