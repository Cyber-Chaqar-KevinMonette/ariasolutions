"""advertising — professional promos for the shop, spam-proof by construction.

Kevin's ask: an advertising feature. The design leans on the same doctrine as
the bot runtime — the safety is STRUCTURAL, not a policy note:

  • **Cadence floor**: `AD_MIN_INTERVAL_S` (6h → at most 4 ads/day). The
    publisher refuses to send inside the window no matter who calls it or
    with what arguments — a mis-configured daemon or an eager double-click
    cannot turn the shop channel into a spam feed.
  • **Rotation, not repetition**: ads rotate through a deck — the general
    shop card first, then every active product — so the channel reads like
    a storefront tour, never a broken record. Rotation state persists in
    `<data>/advertising/state.json` and only advances on a REAL send (a
    dry-run preview never burns the next slot).
  • **Dry-run default**: like every send in this system, nothing goes out
    without `live=True` + a resolvable webhook (`DISCORD_ADS_WEBHOOK_URL`,
    falling back to `DISCORD_WEBHOOK_URL`).
  • **Tunable voice**: Kevin can set the ad lead-line by writing
    `<data>/advertising/copy.txt` — no code changes to re-word a campaign.
  • **Optional automation**: `maybe_publish_ad()` is safe to call from the
    fleet daemon every tick — it does nothing unless `DISCORD_ADS_AUTO=1`
    AND the cadence window has elapsed. Never raises.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "AD_MIN_INTERVAL_S",
    "AdStatus",
    "ads_dir",
    "build_deck",
    "next_ad",
    "ad_status",
    "publish_ad",
    "maybe_publish_ad",
    "render_ad_status",
]

# The structural floor: never more than one ad per 6 hours (4/day max).
# A caller may pass a LONGER interval, never a shorter one.
AD_MIN_INTERVAL_S = 6 * 3600.0

_GOLD = 0xF1C40F
_TEAL = 0x1ABC9C
_FOOTER = "BigKev's Bot Shop · full catalog in #storefront · order in #order-here"


def ads_dir(data_dir: Path) -> Path:
    p = Path(data_dir) / "advertising"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _state_path(data_dir: Path) -> Path:
    return ads_dir(data_dir) / "state.json"


def _read_state(data_dir: Path) -> dict:
    try:
        raw = json.loads(_state_path(data_dir).read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _write_state(data_dir: Path, state: dict) -> None:
    try:
        path = _state_path(data_dir)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(state), encoding="utf-8")
        with open(tmp, "r+", encoding="utf-8") as fh:
            fh.flush()
            os.fsync(fh.fileno())
        tmp.replace(path)
    except Exception:  # noqa: BLE001
        pass


def load_copy(data_dir: Path) -> str:
    """The ad lead-line. Kevin tunes it via <data>/advertising/copy.txt."""
    try:
        override = ads_dir(data_dir) / "copy.txt"
        if override.is_file():
            text = override.read_text(encoding="utf-8").strip()
            if text:
                return text[:300]
    except Exception:  # noqa: BLE001
        pass
    return ""      # default: let the embed speak for itself


# ── the deck ─────────────────────────────────────────────────────────────────
def _shop_card(data_dir: Path) -> dict:
    """The general 'what this shop is' ad — always first in the rotation."""
    lines = ["Managed Discord alert bots that never sleep — restocks, prices,"
             " feeds, scores. We host, watch, and maintain them 24/7;"
             " you just get the pings."]
    try:
        from sovereign_agent.shop import list_all
        products = list_all(data_dir, only_active=True)
        if products:
            lo = min(p.price_cents for p in products if p.price_cents) / 100
            lines.append(f"\n**{len(products)} bots & plans from ${lo:.0f}** — "
                         "run by Aria, our resident AI (say hi in #ask-aria).")
    except Exception:  # noqa: BLE001
        pass
    return {"title": "🛒 BigKev's Bot Shop — alerts that never sleep",
            "description": "\n".join(lines), "color": _TEAL,
            "footer": {"text": _FOOTER}}


def _product_card(p) -> dict:
    mode = ("🤖 runs 24/7 — even while Aria sleeps" if p.runs_without_her
            else "💛 built & run live with Aria")
    desc = (p.blurb + "\n\n" if p.blurb else "")
    desc += f"**{p.price_label()}** · {mode}"
    card = {"title": f"✨ {p.name}", "description": desc, "color": _GOLD,
            "footer": {"text": _FOOTER}}
    if p.stripe_url:
        card["url"] = p.stripe_url
    return card


def build_deck(data_dir: Path) -> list[tuple[str, dict]]:
    """(label, embed) rotation deck: the shop card, then each active product."""
    deck: list[tuple[str, dict]] = [("shop", _shop_card(data_dir))]
    try:
        from sovereign_agent.shop import list_all
        for p in list_all(data_dir, only_active=True):
            deck.append((p.name, _product_card(p)))
    except Exception:  # noqa: BLE001
        pass
    return deck


def next_ad(data_dir: Path) -> tuple[str, dict]:
    """Peek at the next ad in the rotation WITHOUT advancing it."""
    deck = build_deck(data_dir)
    idx = int(_read_state(data_dir).get("index", 0)) % len(deck)
    return deck[idx]


# ── cadence + publishing ─────────────────────────────────────────────────────
@dataclass(frozen=True)
class AdStatus:
    allowed: bool
    wait_s: float                # 0 when allowed
    next_label: str
    last_sent_ts: float | None


def ad_status(data_dir: Path, *, now: float | None = None,
              min_interval_s: float = AD_MIN_INTERVAL_S) -> AdStatus:
    now = time.time() if now is None else now
    min_interval_s = max(float(min_interval_s), AD_MIN_INTERVAL_S)  # floor
    last = _read_state(data_dir).get("last_sent_ts")
    label, _ = next_ad(data_dir)
    if last is None:
        return AdStatus(True, 0.0, label, None)
    elapsed = now - float(last)
    wait = max(0.0, min_interval_s - elapsed)
    return AdStatus(wait <= 0.0, wait, label, float(last))


def render_ad_status(data_dir: Path, *, now: float | None = None) -> str:
    s = ad_status(data_dir, now=now)
    deck = build_deck(data_dir)
    lines = [f"📣 Advertising — deck of {len(deck)} card(s), "
             f"cadence floor {AD_MIN_INTERVAL_S / 3600:.0f}h (max "
             f"{int(86400 / AD_MIN_INTERVAL_S)} ads/day)."]
    if s.last_sent_ts is None:
        lines.append("  never published yet — next up: " + s.next_label)
    elif s.allowed:
        lines.append(f"  ready — next up: {s.next_label}")
    else:
        h, m = int(s.wait_s // 3600), int(s.wait_s % 3600 // 60)
        lines.append(f"  cooling down — next ad allowed in {h}h {m:02d}m "
                     f"(then: {s.next_label})")
    return "\n".join(lines)


def publish_ad(data_dir: Path, *, live: bool = False,
               webhook_env: str = "DISCORD_ADS_WEBHOOK_URL",
               fallback_env: str = "DISCORD_WEBHOOK_URL",
               min_interval_s: float = AD_MIN_INTERVAL_S,
               now: float | None = None) -> tuple[bool, str]:
    """Publish the next ad in the rotation. Returns (published?, detail).

    Refuses inside the cadence window — structurally, for every caller.
    Dry-run (the default) previews without advancing rotation or cadence."""
    now = time.time() if now is None else now
    status = ad_status(data_dir, now=now, min_interval_s=min_interval_s)
    if not status.allowed:
        h, m = int(status.wait_s // 3600), int(status.wait_s % 3600 // 60)
        return (False, f"cadence floor: next ad allowed in {h}h {m:02d}m")

    label, embed = next_ad(data_dir)
    env = webhook_env if (os.environ.get(webhook_env) or "").strip() else fallback_env
    try:
        from sovereign_agent.discord_runtime.delivery import WebhookDelivery
        result = WebhookDelivery(env, live=live).send(
            load_copy(data_dir), embeds=[embed], username="Aria")
    except Exception as exc:  # noqa: BLE001
        return (False, f"send failed: {type(exc).__name__}")
    if result.sent:
        state = _read_state(data_dir)
        state["last_sent_ts"] = now
        state["index"] = (int(state.get("index", 0)) + 1) % max(
            1, len(build_deck(data_dir)))
        _write_state(data_dir, state)
        return (True, f"published ad: {label}")
    return (False, f"{result.detail} — ad: {label}")


def publish_announcement(data_dir: Path, text: str, *, live: bool = False,
                         webhook_env: str = "DISCORD_ADS_WEBHOOK_URL",
                         fallback_env: str = "DISCORD_WEBHOOK_URL") -> tuple[bool, str]:
    """% The owner speaks: post Kevin's announcement to #announcements.
    Owner speech is NOT an ad — no cadence floor. Text required, capped at
    Discord-safe length; dry-run unless live. Ledgered so the Discord Watch
    feed shows it."""
    text = (text or "").strip()[:1800]
    if not text:
        return (False, "nothing to announce — give me the message text")
    embed = {"title": "👑 Server Announcement",
             "description": text, "color": _GOLD,
             "footer": {"text": "BigKev's Bot Shop"}}
    env = webhook_env if (os.environ.get(webhook_env) or "").strip() else fallback_env
    try:
        from sovereign_agent.discord_runtime.delivery import WebhookDelivery
        result = WebhookDelivery(env, live=live).send(
            "", embeds=[embed], username="BigKev's Bot Shop")
    except Exception as exc:  # noqa: BLE001
        return (False, f"send failed: {type(exc).__name__}")
    if result.sent:
        try:
            from sovereign_agent.discord_watch import record_duty_tick
            record_duty_tick(data_dir, f"% owner announcement: "
                                       f"“{text[:60]}”", notable=True)
        except Exception:  # noqa: BLE001
            pass
        return (True, "announcement posted to the server 👑")
    return (False, result.detail)


def maybe_publish_ad(data_dir: Path, *, live: bool,
                     now: float | None = None) -> str | None:
    """Daemon hook: auto-advertise ONLY when Kevin opted in via
    DISCORD_ADS_AUTO=1 AND the daemon is armed (--live) — a dry-run daemon
    never advances rotation, so rehearsing every tick would just be noise
    (preview with `sov shop advertise` instead). Never raises; returns a
    short note when something happened, else None."""
    try:
        if not live or (os.environ.get("DISCORD_ADS_AUTO") or "") != "1":
            return None
        if not ad_status(data_dir, now=now).allowed:
            return None
        ok, detail = publish_ad(data_dir, live=live, now=now)
        return detail if (ok or "cadence" not in detail) else None
    except Exception:  # noqa: BLE001
        return None
