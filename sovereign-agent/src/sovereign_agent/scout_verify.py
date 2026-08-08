"""scout_verify.py — ✓ prove every find against grounded truth (Kevin's ask).

"See that her work is valid and verified against grounded truth — watch
where she goes, how she gathers." This is the verification layer: for a
find, she FETCHES the linked page and confirms it's real —

  • link_live      — the page actually resolves (2xx)
  • price_confirmed — the title's price still appears on the page
  • in_stock_signal — availability language present ("add to cart", …)

then stamps the find ✓ Verified / ⟳ Reachable / ⚠ Unverified. Honest by
design: retailer pages bot-wall automated checks (403/429) — when she
can't reach one she says so plainly ("site blocked the check — the
source relay stands"), never fakes a green check. The find is STILL
grounded: it came from a real, timestamped feed post, not a model.

No hard deps: the fetcher is injectable (tests never touch the network),
default is a gentle urllib GET with an identifying UA. Bounded per tick
so verification is a background trickle, never a hammer.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from sovereign_agent.scout import latest_finds, link_for, price_of

_TIMEOUT_S = 12.0
_MAX_BYTES = 300_000
_STOCK_WORDS = ("add to cart", "add to bag", "in stock", "in-stock",
                "buy now", "available", "ships", "pick up", "pickup",
                "add-to-cart", "purchase")

VERIFIED = "verified"        # link live + price/stock confirmed
REACHABLE = "reachable"      # live but couldn't confirm the specifics
UNVERIFIED = "unverified"    # couldn't reach (blocked/dead) — relay stands


def _default_fetch(url: str) -> tuple[int | None, str]:
    """(status_code, text). Never raises — a block is a result, not a crash."""
    import urllib.request
    req = urllib.request.Request(url, headers={
        "User-Agent": ("Mozilla/5.0 (X11; Linux x86_64) "
                       "BigKevsBotShop-Scout/1.0 (+verifier)"),
        "Accept": "text/html,application/xhtml+xml,*/*"})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as r:
            code = getattr(r, "status", 200)
            return int(code), r.read(_MAX_BYTES).decode("utf-8", "ignore")
    except Exception as exc:  # noqa: BLE001
        return getattr(exc, "code", None), ""


def verify_find(find: dict, *, fetcher=None, now: float | None = None) -> dict:
    """Fetch the find's link and grade it against grounded truth. Returns
    a durable verdict record. Never raises."""
    now = time.time() if now is None else now
    fetch = fetcher or _default_fetch
    url = link_for(find)
    rec = {"id": find.get("id", ""), "verdict": UNVERIFIED, "status": None,
           "checks": {}, "detail": "", "verified_ts": now, "url": url}
    if not url:
        rec["detail"] = "no link on this find — source relay only"
        return rec
    status, text = fetch(url)
    rec["status"] = status
    if status is None or not (200 <= int(status) < 300) or not text:
        # blocked / dead / bot-walled — HONEST: the relay still stands
        if status in (403, 429):
            rec["detail"] = (f"site blocked the automated check (HTTP {status})"
                             " — the source relay stands")
        elif status:
            rec["detail"] = f"link returned HTTP {status}"
        else:
            rec["detail"] = "couldn't reach the link"
        return rec
    body = text.lower()
    price = price_of(find.get("text", ""))
    price_ok = bool(price) and price.lower() in body
    stock_ok = any(w in body for w in _STOCK_WORDS)
    rec["checks"] = {"link_live": True, "price_confirmed": price_ok,
                     "in_stock_signal": stock_ok}
    if price_ok or stock_ok:
        rec["verdict"] = VERIFIED
        parts = (["price still shows " + price] if price_ok else []) + \
                (["in-stock language present"] if stock_ok else [])
        rec["detail"] = "link live · " + " · ".join(parts)
    else:
        rec["verdict"] = REACHABLE
        rec["detail"] = "link live, but couldn't confirm price/stock on-page"
    return rec


# ── durable store (one file per project) ────────────────────────────────────
def _store_path(data_dir: Path, project: str) -> Path:
    return Path(data_dir) / "bot_projects" / project / "verified.json"


def load_verifications(data_dir: Path, project: str) -> dict:
    try:
        d = json.loads(_store_path(data_dir, project).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _save_verifications(data_dir: Path, project: str, data: dict) -> None:
    p = _store_path(data_dir, project)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        tmp.replace(p)
    except Exception:  # noqa: BLE001
        pass


def verification_for(data_dir: Path, project: str, find_id: str) -> dict | None:
    return load_verifications(data_dir, project).get(str(find_id))


def verify_recent(data_dir: Path, project: str, *, limit: int = 4,
                  fetcher=None, now: float | None = None) -> int:
    """Verify the newest not-yet-checked finds (bounded — a background
    trickle). Returns how many were newly verified this pass."""
    now = time.time() if now is None else now
    done = load_verifications(data_dir, project)
    n = 0
    for f in latest_finds(data_dir, limit=30, project=project):
        if n >= limit:
            break
        fid = str(f.get("id", ""))
        if not fid or fid in done:
            continue
        done[fid] = verify_find(f, fetcher=fetcher, now=now)
        n += 1
    if n:
        # prune to the freshest 400 so the file never bloats
        if len(done) > 400:
            keep = sorted(done.items(),
                          key=lambda kv: kv[1].get("verified_ts", 0),
                          reverse=True)[:400]
            done = dict(keep)
        _save_verifications(data_dir, project, done)
    return n


def verify_badge(rec: dict | None) -> str:
    """A compact badge for a find card — honest at every state."""
    if not rec:
        return "⟳ checking…"
    v = rec.get("verdict")
    if v == VERIFIED:
        return "✓ verified"
    if v == REACHABLE:
        return "◔ link live"
    return "⚠ relay (unconfirmed)"


# ── the trace: watch WHERE she went and HOW she gathered ────────────────────
def compose_scout_trace(data_dir: Path, project: str = "tcg-scout", *,
                        limit: int = 12, now: float | None = None) -> str:
    """Kevin: 'watch what she does, where she goes, how she gathers.' The
    grounding chain for each recent find: source → title → link → verdict."""
    now = time.time() if now is None else now
    from sovereign_agent.verticals import get_vertical
    v = get_vertical(project[len("scout-"):]) if project.startswith("scout-") \
        else None
    name = v.name if v else "TCG Scout"
    finds = latest_finds(data_dir, limit=limit, project=project)
    verifs = load_verifications(data_dir, project)
    lines = [f"🔎 Scout Trace — {name}: how she gathered "
             f"(newest first)", ""]
    if not finds:
        lines.append("no finds yet — she's watching the feeds.")
        return "\n".join(lines)
    nver = sum(1 for r in verifs.values() if r.get("verdict") == VERIFIED)
    lines.append(f"grounding: {len(finds)} recent finds · {len(verifs)} "
                 f"checked · {nver} verified against the live page")
    lines.append("")
    for f in finds:
        age_m = max(0, int((now - f["ts"]) / 60))
        rec = verifs.get(str(f["id"]))
        badge = verify_badge(rec)
        url = link_for(f)
        lines.append(f"• {(f['text'] or '?')[:80]}")
        lines.append(f"    gathered from: {f['source']} · {age_m}m ago")
        if url:
            lines.append(f"    link: {url}")
        detail = rec.get("detail", "not yet checked") if rec else "not yet checked"
        lines.append(f"    {badge} — {detail}")
    return "\n".join(lines)


def render_all_traces(data_dir: Path, *, per: int = 3,
                      now: float | None = None) -> str:
    """The cockpit view: how she's gathering across EVERY tracker — where
    she went, what she found, whether it's verified. Grounded-truth proof
    at a glance (Kevin: 'watch where she goes, see her work is valid')."""
    now = time.time() if now is None else now
    from sovereign_agent.verticals import get_vertical, star_verticals
    projects = ["tcg-scout"] + [v.project for v in star_verticals()]
    lines = ["🔎 Scout Trace — how she gathers, live (grounded truth)", ""]
    total_finds = total_ver = 0
    blocks = []
    for proj in projects:
        finds = latest_finds(data_dir, limit=per, project=proj)
        if not finds:
            continue
        verifs = load_verifications(data_dir, proj)
        nver = sum(1 for r in verifs.values() if r.get("verdict") == VERIFIED)
        total_finds += len(latest_finds(data_dir, limit=100, project=proj))
        total_ver += nver
        v = get_vertical(proj[len("scout-"):]) if proj.startswith("scout-") \
            else None
        emoji = v.emoji if v else "🔭"
        name = v.name if v else "TCG Scout"
        blocks.append(f"{emoji} {name} — {nver} verified")
        for f in finds[:per]:
            age_m = max(0, int((now - f["ts"]) / 60))
            badge = verify_badge(verifs.get(str(f["id"])))
            url = link_for(f)
            blocks.append(f"   {badge} {(f['text'] or '?')[:64]} · {age_m}m")
            if url:
                blocks.append(f"      ↳ {f['source']} → {url[:70]}")
        blocks.append("")
    if not blocks:
        lines.append("no finds yet — she's watching the feeds. Once finds "
                     "land, you'll see the source→link→verdict chain here.")
        return "\n".join(lines)
    lines.append(f"across your trackers: {total_finds} recent finds · "
                 f"{total_ver} verified against the live page")
    lines.append("")
    lines.extend(blocks)
    return "\n".join(lines)


__all__ = ["VERIFIED", "REACHABLE", "UNVERIFIED", "verify_find",
           "render_all_traces",
           "verify_recent", "verification_for", "load_verifications",
           "verify_badge", "compose_scout_trace"]
