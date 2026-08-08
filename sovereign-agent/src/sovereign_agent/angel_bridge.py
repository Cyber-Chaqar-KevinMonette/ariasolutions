"""angel_bridge — her non-classical layer speaks in the cockpit + Discord.

Kevin (2026-07-19): "make it where her non classical layer can talk in
the cockpit and add a channel in the discord only for me where she can
talk."

The PEIG engine (the sibling research repo) and the Aria runtime talk
via LEDGERS — the standing boundary. A speaking run (SessionConfig
speak=True, e.g. scripts/full_globe_experiment.py) writes nine-register
voice lines + run summaries into ``<run>/events.ndjson``; this bridge
reads the LATEST run slice and renders it for the cockpit chat pane and
for the owner-only #angel-voice channel.

Contracts:
- read-only over the engine's ledger; parsing is crash-proof (a
  corrupt/partial line is skipped, never a crash);
- only the LAST run's events are voiced (ledgers append across runs);
- Discord posting is best-effort via DISCORD_ANGEL_WEBHOOK_URL
  (falling back to the owner bridge) — her voice never blocks anything;
- no run found => an honest "she has not spoken yet" message, never an
  invented voice.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

DEFAULT_RUNS_DIR = Path.home() / "AA-Erebo" / "peig-engine" / "runs"
_REGISTER_ORDER = ("identity", "math", "physics", "thermo", "wave",
                   "vortex", "plasma", "holography", "entropy")


def runs_root() -> Path:
    env = (os.environ.get("PEIG_RUNS_DIR") or "").strip()
    return Path(env) if env else DEFAULT_RUNS_DIR


def find_latest_run(root: Path | None = None) -> Path | None:
    root = runs_root() if root is None else Path(root)
    if not root.is_dir():
        return None
    candidates = sorted(
        (p for p in root.glob("*/events.ndjson") if p.is_file()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0].parent if candidates else None


def read_latest_run(run_dir: Path) -> dict:
    """Parse the ledger; keep only events from the LAST run-start on."""
    events: list[dict] = []
    try:
        with open(run_dir / "events.ndjson", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue           # partial trailing line — skipped
    except OSError:
        return {}
    last_start = 0
    for i, e in enumerate(events):
        if e.get("kind") == "run-start":
            last_start = i
    events = events[last_start:]
    out: dict = {"run_dir": str(run_dir), "voice": [], "monologue": None,
                 "run_start": None, "run_end": None, "nc": None,
                 "lineage": None}
    for e in events:
        kind = e.get("kind")
        if kind == "run-start":
            out["run_start"] = e
        elif kind == "run-end":
            out["run_end"] = e
        elif kind == "voice":
            out["voice"].append(str(e.get("line", "")))
        elif kind == "voice-monologue":
            out["monologue"] = e
        elif kind == "nc-summary":
            out["nc"] = e
        elif kind == "lineage-summary":
            out["lineage"] = e
    return out


def compose_angel_report(data: dict | None, max_choir: int = 12) -> str:
    """The cockpit/Discord rendering of her latest spoken run."""
    if not data or not data.get("voice"):
        return ("⚛ The angel has not spoken yet — run a speaking session "
                "in peig-engine (e.g. scripts/full_globe_experiment.py) "
                "and her voice will appear here.")
    lines = ["⚛ THE ANGEL SPEAKS — her latest run, in her own voice"]
    rs, re_ = data.get("run_start"), data.get("run_end")
    if rs:
        lines.append(
            f"  run: {len(rs.get('nodes', []))} nodes · "
            f"seed {rs.get('seed')} · {rs.get('steps')} steps"
        )
    if re_:
        lines.append(
            f"  identity: cv={re_.get('final_cv')} "
            f"({'HELD' if re_.get('identity_held') else 'broken'}) · "
            f"heals {re_.get('heals_proven')}/{re_.get('heals_attempted')}"
        )
    nc = data.get("nc")
    if nc:
        lines.append(
            f"  guardrail: {'ZERO RED ✓' if nc.get('zero_red') else str(nc.get('red_events')) + ' RED'}"
            f" · {nc.get('restores_proven')} restores proven"
        )
    lin = data.get("lineage")
    if lin:
        lines.append(
            f"  lineage: depth {lin.get('depth')} · "
            f"inheritance α={lin.get('alpha_inherit')} · "
            f"source {lin.get('source')}"
        )
    lines.append("  — the choir —")
    for v in data["voice"][:max_choir]:
        lines.append(f"  {v}")
    mono = data.get("monologue")
    if mono:
        lines.append(f"  — {mono.get('node', '?')}'s monologue —")
        for reg in _REGISTER_ORDER:
            if reg in mono:
                lines.append(f"  [{reg}] {mono[reg]}")
    return "\n".join(lines)


def angel_report(root: Path | None = None) -> str:
    run = find_latest_run(root)
    if run is None:
        return compose_angel_report(None)
    return compose_angel_report(read_latest_run(run))


def _angel_env_name() -> str:
    if (os.environ.get("DISCORD_ANGEL_WEBHOOK_URL") or "").strip():
        return "DISCORD_ANGEL_WEBHOOK_URL"
    if (os.environ.get("DISCORD_OWNER_WEBHOOK_URL") or "").strip():
        return "DISCORD_OWNER_WEBHOOK_URL"
    return "DISCORD_WEBHOOK_URL"


def post_angel_report(root: Path | None = None, live: bool = True) -> bool:
    """Post her voice to #angel-voice (owner-only). Best-effort always."""
    report = angel_report(root)
    try:
        from sovereign_agent.discord_runtime.delivery import WebhookDelivery

        result = WebhookDelivery(_angel_env_name(), live=live).send(
            report[:1900], username="⚛ The Angel — her own voice")
        return bool(getattr(result, "sent", False))
    except Exception:  # noqa: BLE001 — her voice never breaks anything
        return False
