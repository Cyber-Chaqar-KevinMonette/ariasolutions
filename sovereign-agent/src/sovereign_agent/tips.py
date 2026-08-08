"""tips.py — 💛 the Tip Jar: generous folks can tip the shop.

Kevin's ask (2026-07-17): "a payment/tip system for generous folks." The
honest shape: tips are Stripe **Payment Links** (public URLs, not secrets)
that go to Kevin's Stripe — Aria SURFACES them, she never holds money. A
`/tip` command shows the tiers as clickable link-buttons; the tip flows
straight to Stripe checkout.

Links live in `<data>/tips/links.json` (seedable from Kevin's tiers).
Payment Links are safe to store + display — that's what they're for.
"""
from __future__ import annotations

import json
from pathlib import Path

# the tiers Kevin created, in cents (label is the button text)
TIP_TIERS: list[int] = [100, 500, 1000, 2000, 5000, 10000, 100000]

# Kevin's live tip Payment Links (public URLs — safe to ship as defaults)
DEFAULT_LINKS: dict[str, str] = {
    "100": "https://buy.stripe.com/eVqaEQ8AuewodQZ3iheEo0a",
    "500": "https://buy.stripe.com/7sY5kw8Au3RK8wF4mleEo0b",
    "1000": "https://buy.stripe.com/3cIdR22c6ewobIR3iheEo0c",
    "2000": "https://buy.stripe.com/14A28k182bkc28h5qpeEo0d",
    "5000": "https://buy.stripe.com/9B63co9Ey1JC8wFaKJeEo0e",
    "10000": "https://buy.stripe.com/4gMaEQg2WfAs28h8CBeEo0f",
    "100000": "https://buy.stripe.com/cNieV62c6gEw14d2edeEo0g",
}


def _path(data_dir: Path) -> Path:
    return Path(data_dir) / "tips" / "links.json"


def load_tip_links(data_dir: Path) -> dict[str, str]:
    """Stored links, seeded from DEFAULT_LINKS on first read."""
    p = _path(data_dir)
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(d, dict) and d:
            return {k: v for k, v in d.items() if str(v).startswith("http")}
    except Exception:  # noqa: BLE001
        pass
    seed = dict(DEFAULT_LINKS)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(seed, indent=2), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    return seed


def set_tip_link(data_dir: Path, cents: int, url: str) -> None:
    links = load_tip_links(data_dir)
    links[str(int(cents))] = url
    p = _path(data_dir)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(links, indent=2), encoding="utf-8")
        tmp.replace(p)
    except Exception:  # noqa: BLE001
        pass


def _dollars(cents: int) -> str:
    d = cents / 100
    return f"${int(d)}" if d == int(d) else f"${d:.2f}"


def tip_buttons(data_dir: Path) -> list[dict]:
    """[{label, url}] for each tier that has a link — for link-buttons."""
    links = load_tip_links(data_dir)
    out = []
    for cents in TIP_TIERS:
        url = links.get(str(cents))
        if url:
            out.append({"label": f"💛 {_dollars(cents)}", "url": url,
                        "cents": cents})
    return out


def tip_embed(data_dir: Path) -> dict:
    """The Tip Jar card. discord_limits-safe."""
    from sovereign_agent.discord_limits import clamp_embed
    n = len(tip_buttons(data_dir))
    desc = (
        "If Aria's scouts have saved you money or the shop's been good to "
        "you, a tip keeps the lights on and the bots hunting 24/7. 💛\n\n"
        "Every tip goes straight to secure Stripe checkout — pick an amount "
        "below. Totally optional, always appreciated. Thank you for being "
        "generous!")
    return clamp_embed({"title": "💛 Tip Jar — support the shop",
                        "description": desc, "color": 0xF1C40F,
                        "footer": {"text": f"{n} tip options · powered by "
                                           "Stripe · thank you 💛"}})


def compose_tip_report(data_dir: Path) -> str:
    """Chat/CLI text version (when buttons aren't available)."""
    btns = tip_buttons(data_dir)
    if not btns:
        return ("💛 The Tip Jar isn't set up yet — the owner adds tip links "
                "with `sov tip set`.")
    lines = ["💛 **Tip Jar** — support the shop (optional, appreciated!):"]
    for b in btns:
        lines.append(f"  {b['label']} → {b['url']}")
    lines.append("Every tip goes to secure Stripe checkout. Thank you! 💛")
    return "\n".join(lines)


_TIP_TRIGGERS = ("tip", "tip jar", "donate", "support the shop",
                 "buy you a coffee", "how do i tip", "leave a tip")


def is_tip_query(text: str) -> bool:
    from sovereign_agent.bridge_patterns import match_any
    return match_any(text, _TIP_TRIGGERS)


__all__ = ["TIP_TIERS", "DEFAULT_LINKS", "load_tip_links", "set_tip_link",
           "tip_buttons", "tip_embed", "compose_tip_report", "is_tip_query"]
