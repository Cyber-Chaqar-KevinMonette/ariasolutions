"""work_narrator — her cockpit shift, narrated live to #owner-bridge.

F5 (Kevin, 2026-07-19): "a channel where me and Aria work together and
she keeps me updated on what she is doing in the cockpit — full
communication bridges." Every subtask boundary in an auto/work session
posts one line to the owner's bridge webhook, so watching Discord IS
watching her work.

Contracts:
- best-effort ALWAYS: narration can never break a work session;
- throttled: at most one post per _MIN_GAP_S (bursts collapse to the
  latest line at the next allowed moment via a tiny pending slot);
- webhook: DISCORD_OWNER_WEBHOOK_URL (the #owner-bridge mint), falling
  back to DISCORD_WEBHOOK_URL (#aria-control) so updates flow even
  before /setup-webhooks re-runs.
"""
from __future__ import annotations

import time

_MIN_GAP_S = 60.0
_state = {"last_post": 0.0, "pending": ""}


def _env_name() -> str:
    import os

    if (os.environ.get("DISCORD_OWNER_WEBHOOK_URL") or "").strip():
        return "DISCORD_OWNER_WEBHOOK_URL"
    return "DISCORD_WEBHOOK_URL"


def narrate(line: str, *, now: float | None = None, force: bool = False) -> bool:
    """Post one work line (throttled). Returns True only on a real send."""
    now = time.time() if now is None else now
    line = (line or "").strip()[:1500]
    if not line:
        return False
    if not force and now - _state["last_post"] < _MIN_GAP_S:
        _state["pending"] = line          # newest line wins the next slot
        return False
    try:
        from sovereign_agent.discord_runtime.delivery import WebhookDelivery

        text = line
        if _state["pending"] and _state["pending"] != line:
            text = f"{_state['pending']}\n{line}"
        result = WebhookDelivery(_env_name(), live=True).send(
            text, username="Aria — at the cockpit")
        if getattr(result, "sent", False):
            _state["last_post"] = now
            _state["pending"] = ""
            return True
        # observability-d (Kevin, 2026-07-25): "she used to send me
        # updates... she stopped." Before this, a dead/unset webhook
        # failed with ZERO trace anywhere — the exact way a stale webhook
        # URL (e.g. a recreated #owner-bridge channel) could silently go
        # quiet for who knows how long. Never blocks narration; just makes
        # a real failure findable instead of invisible.
        _emit_narration_failure(getattr(result, "detail", "not sent"))
        return False
    except Exception as exc:  # noqa: BLE001 — narration never breaks the shift
        _emit_narration_failure(f"{type(exc).__name__}: {exc}")
        return False


def _emit_narration_failure(detail: str) -> None:
    try:
        from sovereign_agent.events import emit_event
        emit_event("work-narrate-x", plane="control", trace_id="work-narrator",
                  payload={"detail": str(detail)[:200], "env": _env_name()})
    except Exception:  # noqa: BLE001
        pass


def narrate_subtask(session_id: str, n_done: int, n_total: int,
                    summary: str, *, now: float | None = None) -> bool:
    sid = (session_id or "")[:12]
    summary = (summary or "").strip()[:220]
    return narrate(
        f"🛠 **{n_done}/{n_total}** · {summary or 'subtask finished'} · "
        f"`{sid}`", now=now)


def narrate_intent(session_id: str, description: str, *,
                   now: float | None = None) -> bool:
    """full-observability-d (Kevin, 2026-07-26): "I want her to be upfront
    about everything she plans to do, is doing, and wants to do." Before
    this, narration only ever reported a subtask's RESULT after the fact
    (narrate_subtask) — nothing announced the plan before she started
    it. Called once, right as a subtask begins."""
    sid = (session_id or "")[:12]
    description = (description or "").strip()[:220]
    return narrate(
        f"▸ starting: {description or 'a subtask'} · `{sid}`", now=now)


__all__ = ["narrate", "narrate_subtask", "narrate_intent"]
