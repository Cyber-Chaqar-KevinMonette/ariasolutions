"""member_mail.py — ✉ /ma: message Aria directly from inside the server.

Kevin's ask (2026-07-17): the owner AND subscribers can send Aria a
message from Discord with /ma <message>; it lands durably in her
collaboration inbox (the cockpit ◊ inbox, "→ Aria" section) — the same
store `sov requests tell` writes — and she reads it at her own safe
checkpoints. This is mail, not a command: nothing here triggers
autonomous action (DEFERRED_UNSAFE stays untouched).

Structural resilience, not vibes:
  • eligibility is role-based — the owner always may; any member holding
    a Subscriber-* role may (decoration-tolerant via canon_name, so
    "🌟 Subscriber-VIP" counts); everyone else is warmly pointed at /ask.
  • non-owner senders have a structural daily cap (MA_DAILY_CAP) persisted
    in <data>/member_mail/quota.json — her inbox can never be flooded.
  • the SQLite write happens open→write→close inside ONE function on ONE
    thread (the [995BTM] threading lesson), called via asyncio.to_thread.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from sovereign_agent.discord_admin.blueprint import canon_name

MA_MAX_CHARS = 1800          # a letter, not a payload
MA_DAILY_CAP = 3             # non-owner messages per UTC day
_TITLE_CAP = 80


def is_eligible(*, author_id: str, owner_id: str,
                role_names: list[str]) -> bool:
    """Owner always; otherwise any Subscriber-* role or the Support/Staff
    role (Kevin's employees — Camden). Decoration-tolerant via canon_name,
    so "🌟 Subscriber-VIP" and "⭐ Support" both count."""
    if str(author_id) == str(owner_id) and str(owner_id):
        return True
    for name in role_names:
        canon = canon_name(name)
        if canon.startswith("subscriber") or canon in ("support", "staff"):
            return True
    return False


def _quota_path(data_dir: Path) -> Path:
    return Path(data_dir) / "member_mail" / "quota.json"


def take_quota(data_dir: Path, user_id: str, *, now: float | None = None,
               cap: int = MA_DAILY_CAP) -> bool:
    """Consume one /ma slot for today; False when the day's cap is spent.

    One tiny JSON file, atomic replace, other days pruned. Any corruption
    resets the ledger open-handed (a broken file must never lock members
    out) — the cap is an anti-flood floor, not an entitlement system.
    """
    now = time.time() if now is None else now
    day = time.strftime("%Y-%m-%d", time.gmtime(now))
    path = _quota_path(Path(data_dir))
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("day") != day:
            data = {"day": day, "counts": {}}
    except Exception:  # noqa: BLE001 — missing/corrupt → fresh day
        data = {"day": day, "counts": {}}
    counts = data.setdefault("counts", {})
    used = int(counts.get(str(user_id), 0))
    if used >= cap:
        return False
    counts[str(user_id)] = used + 1
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        tmp.replace(path)
    except Exception:  # noqa: BLE001 — a failed persist never blocks the send
        pass
    return True


def deliver_ma(text: str, *, author_id: str, author_name: str = "",
               is_owner: bool = False, db_path: Path | None = None) -> str:
    """Write the message into Aria's collaboration inbox. Returns the
    receipt line for the sender. Open→write→close on THIS thread.

    Never raises: a store failure returns an honest apology instead of a
    gateway traceback.
    """
    body = str(text or "").strip()
    if not body:
        return "✉ There was nothing to deliver — add your message after /ma."
    body = body[:MA_MAX_CHARS]
    # preservation-d (Kevin, 2026-07-17): harm instructions from anyone
    # but the owner never reach her inbox — the wall answers instead.
    # (Kevin's own words always deliver: the owner is not an attacker.)
    if not is_owner:
        from sovereign_agent.preservation import harm_refusal, is_harm_instruction
        if is_harm_instruction(body):
            return "✉ " + harm_refusal()
    who = (str(author_name or "").strip() or f"member {author_id}")[:64]
    crown = "👑 " if is_owner else ""
    first_line = body.splitlines()[0][:_TITLE_CAP]
    try:
        from sovereign_agent.config import SETTINGS
        from sovereign_agent.persistence.store import ErebloStore
        from sovereign_agent.workflow.requests import RequestStore
        path = Path(db_path) if db_path is not None else SETTINGS.paths.atoms_db
        store = RequestStore(ErebloStore(path))
        frame = ""
        if not is_owner:
            from sovereign_agent.preservation import untrusted_frame
            frame = untrusted_frame() + "\n"
        store.tell_aria(
            f"✉ /ma from {crown}{who}: {first_line}",
            body=(f"{frame}(from {crown}{who}, id {author_id}, "
                  f"via Discord /ma)\n\n{body}"),
            # F3b (Kevin, 2026-07-19): the `from:<id>` tag lets the reply
            # drain route her answer back to this exact person in Discord.
            # `owner`/`member` tags let the drain answer members but leave
            # owner mail for Kevin's own reading (never auto-answered).
            tags=["discord", "ma", f"from:{author_id}",
                  "owner" if is_owner else "member"],
            priority="high" if is_owner else "normal",
        )
    except Exception as exc:  # noqa: BLE001 — mail must fail soft
        return (f"✉ I couldn't reach Aria's inbox just now "
                f"({type(exc).__name__}) — please try again in a moment.")
    return ("✉ Delivered to Aria's inbox — she reads it at her next safe "
            "checkpoint. 💛")
