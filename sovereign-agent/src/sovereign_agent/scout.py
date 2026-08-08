"""scout.py — 🔭 the TCG Scout's brain (pure, tested; the flagship).

Kevin's flagship design (2026-07-17): watch as many trustworthy sources
as possible for Pokémon TCG restocks + deals, rank every report
**greatest→least set value**, and surface it all through a clickable
panel in Discord where members pick a lane and SEE the data.

This module is the pure layer: value ranks, lane classification, the
finds reader (over the fleet's runs.jsonl truth), member area prefs
(zip+radius / zip list / whole state — optional, consent-first), and the
embed cards. Discord wiring lives in discord_admin/bot.py; nothing here
imports discord.

Source honesty (live-tested 2026-07-17): direct retailer pages/APIs sit
behind bot-protection — watching them from here would mean evasion, so
we DON'T. Live lanes today: Slickdeals search RSS ×3 + Reddit deal subs
×2 (community-relayed retailer restocks + deals, minutes-fresh). The
clean path to first-party retailer + local-stock lanes is OFFICIAL free
API keys (Best Buy developer API first) — registered follow-up.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

# ── value ranks (Kevin-tunable file; greatest value = tier 0) ───────────────
DEFAULT_RANKS: list[dict] = [
    {"label": "🏆 chase", "color": 0xF1C40F,
     "keywords": ["prismatic", "151", "crown zenith", "hidden fates",
                  "shining fates", "celebrations"]},
    {"label": "🔥 hot", "color": 0x9B59B6,
     "keywords": ["surging sparks", "stellar crown", "twilight masquerade",
                  "temporal forces", "paldean fates", "obsidian flames",
                  "destined rivals", "journey together"]},
    {"label": "▸ sealed", "color": 0x3498DB,
     "keywords": ["elite trainer", "etb", "booster box", "booster bundle",
                  "collection box", "premium collection", "booster pack",
                  "tin "]},
    # everything else falls to the last tier automatically
    {"label": "· misc", "color": 0x95A5A6, "keywords": []},
]

LANES = ("online", "local", "deals")


def ranks_path(data_dir: Path, project: str = "tcg-scout") -> Path:
    return Path(data_dir) / "bot_projects" / project / "set_ranks.json"


def load_ranks(data_dir: Path, project: str = "tcg-scout") -> list[dict]:
    """Kevin's ordered tier table — seeded on first read, tune freely
    (reorder tiers / edit keywords; top of file = greatest value).

    verticals-d: a scout-<vertical> project seeds its tiers from the
    catalog's rank_keywords so each niche ranks by ITS own hotness."""
    p = ranks_path(data_dir, project)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, list) and data:
            return data
    except Exception:  # noqa: BLE001 — missing/corrupt → seed defaults
        pass
    seed = DEFAULT_RANKS
    if project.startswith("scout-"):
        try:
            from sovereign_agent.verticals import get_vertical
            v = get_vertical(project[len("scout-"):])
            if v and v.rank_keywords:
                seed = [{"label": "🔥 hot", "color": v.color,
                         "keywords": list(v.rank_keywords)},
                        {"label": "· find", "color": 0x95A5A6, "keywords": []}]
        except Exception:  # noqa: BLE001
            pass
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(seed, indent=2, ensure_ascii=False),
                     encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    return [dict(t) for t in seed]


def rank_of(title: str, ranks: list[dict]) -> int:
    """Tier index for a find title (0 = greatest value; last tier = misc)."""
    t = (title or "").lower()
    for i, tier in enumerate(ranks):
        if any(k and k in t for k in tier.get("keywords", [])):
            return i
    return len(ranks) - 1


def sort_by_value(finds: list[dict], ranks: list[dict]) -> list[dict]:
    """Greatest→least set value; newest first inside a tier."""
    return sorted(finds, key=lambda f: (rank_of(f.get("text", ""), ranks),
                                        -float(f.get("ts", 0))))


# ── lanes ───────────────────────────────────────────────────────────────────
# retailers whose finds are LOCAL/in-store by nature (Dollar General is
# a hunt-the-shelf retailer — a DG find means "go check your store")
_LOCAL_RETAILERS = ("dollar-general", "dollar general", "dollargeneral",
                    "-dg-", "-dg", "dg-", "dollar-tree", "family-dollar",
                    "walgreens", "cvs")


def classify_lane(source_name: str) -> str:
    s = (source_name or "").lower()
    if "local" in s or "store" in s or any(r in s for r in _LOCAL_RETAILERS):
        return "local"
    if s.startswith(("slickdeals", "reddit")) or "deal" in s:
        return "deals"
    return "online"


def price_of(text: str) -> str:
    """HOW MUCH — pulled out of the title so it's never buried."""
    m = re.search(r"\$\s?\d{1,4}(?:[.,]\d{2})?", text or "")
    return m.group(0).replace(" ", "") if m else ""


def link_for(find: dict) -> str:
    """Best-effort click-through: the explicit url wins (Slickdeals deal
    link), else the id when it's a URL, else reddit t3_ → comment link.

    affiliate-links-d (Kevin, 2026-07-25): every embed/report/flex path in
    this file gets its posted URL from THIS function — so tagging happens
    once, here, and every existing posting path inherits it automatically.
    `affiliate_links.tag_url()` is a no-op pass-through for anything it
    doesn't recognize or isn't configured for, so this never risks a find
    with no matching network."""
    url = str(find.get("url", "") or "")
    if url.startswith("http"):
        return _tag(url)
    ident = str(find.get("id", ""))
    if ident.startswith("http"):
        return _tag(ident)
    if ident.startswith("t3_"):
        return f"https://www.reddit.com/comments/{ident[3:]}"
    return ""


def _tag(url: str) -> str:
    try:
        from sovereign_agent.affiliate_links import tag_url
        return tag_url(url)
    except Exception:  # noqa: BLE001 — a tagging hiccup must never break a real link
        return url


# ── the finds reader (runs.jsonl is the fleet's truth — read, don't store) ──
def latest_finds(data_dir: Path, *, lane: str | None = None,
                 limit: int = 12, project: str = "tcg-scout") -> list[dict]:
    """Newest finds from the scout's audit ledger, optionally one lane.
    Missing/corrupt ledger → [] (a quiet scout is a fact, not a crash)."""
    path = Path(data_dir) / "bot_projects" / project / "runs.jsonl"
    finds: list[dict] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:  # noqa: BLE001
        return []
    for line in reversed(lines[-400:]):
        try:
            r = json.loads(line)
        except Exception:  # noqa: BLE001
            continue
        for item in r.get("new", []) or []:
            f = {"ts": float(r.get("ts", 0)), "source": item.get("source", ""),
                 "id": item.get("id", ""), "text": item.get("text", ""),
                 "url": item.get("url", "")}
            f["lane"] = classify_lane(f["source"])
            if lane and f["lane"] != lane:
                continue
            finds.append(f)
            if len(finds) >= limit:
                return finds
    return finds


def day_stats(data_dir: Path, *, now: float | None = None,
              project: str = "tcg-scout") -> dict:
    """Today's bragging numbers: finds per lane + hottest tier seen."""
    now = time.time() if now is None else now
    day_start = now - (now % 86_400)
    ranks = load_ranks(Path(data_dir), project)
    stats = {"total": 0, "per_lane": {ln: 0 for ln in LANES},
             "hottest": None, "hottest_tier": len(ranks)}
    for f in latest_finds(data_dir, limit=200, project=project):
        if f["ts"] < day_start:
            continue
        stats["total"] += 1
        stats["per_lane"][f["lane"]] = stats["per_lane"].get(f["lane"], 0) + 1
        tier = rank_of(f["text"], ranks)
        if tier < stats["hottest_tier"]:
            stats["hottest_tier"], stats["hottest"] = tier, f["text"][:120]
    return stats


# ── member area prefs (consent-first, optional, deletable) ──────────────────
_ZIP_RE = re.compile(r"^\d{5}$")
_STATES = {
    "al", "ak", "az", "ar", "ca", "co", "ct", "de", "fl", "ga", "hi", "id",
    "il", "in", "ia", "ks", "ky", "la", "me", "md", "ma", "mi", "mn", "ms",
    "mo", "mt", "ne", "nv", "nh", "nj", "nm", "ny", "nc", "nd", "oh", "ok",
    "or", "pa", "ri", "sc", "sd", "tn", "tx", "ut", "vt", "va", "wa", "wv",
    "wi", "wy"}



# my-panel-d (Kevin, 2026-07-26): "each person has to link their zip code
# and the radius how many mile away from that zip code they are
# comfortable being informed of. Like 25 miles minimum maybe a few
# hundred or thousand maximum." Was (5, 250); widened + floor raised to
# match his own stated comfort range.
MIN_RADIUS_MI = 25
MAX_RADIUS_MI = 1000


def parse_area(text: str) -> dict | None:
    """Kevin's filterable options: '42240' · '42240 r50' (radius miles) ·
    '42240, 37040, 37042' (list) · 'KY' / 'kentucky-ish 2-letter' (state).
    Returns {'zips': [...], 'radius_mi': int|None, 'state': str|None} or
    None when nothing parseable — never raises."""
    raw = (text or "").strip().lower().replace(",", " ")
    if not raw:
        return None
    zips: list[str] = []
    radius = None
    state = None
    for tok in raw.split():
        if _ZIP_RE.match(tok):
            if tok not in zips:
                zips.append(tok)
        elif tok.startswith("r") and tok[1:].isdigit():
            radius = max(MIN_RADIUS_MI, min(int(tok[1:]), MAX_RADIUS_MI))
        elif tok in _STATES:
            state = tok.upper()
    if not zips and not state:
        return None
    return {"zips": zips[:10], "radius_mi": radius, "state": state}


def prefs_dir(data_dir: Path) -> Path:
    return Path(data_dir) / "community" / "member_prefs"


def save_area(data_dir: Path, user_id: str, area: dict | None) -> None:
    """area=None deletes (their data, their call). Atomic; never raises."""
    d = prefs_dir(Path(data_dir))
    p = d / f"{re.sub(r'[^0-9]', '', str(user_id)) or 'unknown'}.json"
    try:
        if area is None:
            p.unlink(missing_ok=True)
            return
        d.mkdir(parents=True, exist_ok=True)
        rec = {}
        try:
            rec = json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            rec = {}
        rec.update({"user_id": str(user_id), "area": area,
                    "updated_ts": time.time()})
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(rec), encoding="utf-8")
        tmp.replace(p)
    except Exception:  # noqa: BLE001
        pass


def load_area(data_dir: Path, user_id: str) -> dict | None:
    p = prefs_dir(Path(data_dir)) / \
        f"{re.sub(r'[^0-9]', '', str(user_id)) or 'unknown'}.json"
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("area")
    except Exception:  # noqa: BLE001
        return None


# ping-mode-d (Kevin, 2026-07-27): "two ping modes a customer can
# choose from... one all day mode, or just batch reporting mode." A
# per-member toggle inside /my-panel, stored alongside their area
# (same file, same consent-first/deletable discipline). BATCH is the
# default — a member always gets the on-request report either way;
# LIVE additionally DMs them when a new find matches their area.
PING_MODE_BATCH = "batch"
PING_MODE_LIVE = "live"


def save_ping_mode(data_dir: Path, user_id: str, mode: str) -> None:
    mode = mode if mode in (PING_MODE_BATCH, PING_MODE_LIVE) else PING_MODE_BATCH
    d = prefs_dir(Path(data_dir))
    p = d / f"{re.sub(r'[^0-9]', '', str(user_id)) or 'unknown'}.json"
    try:
        d.mkdir(parents=True, exist_ok=True)
        rec = {}
        try:
            rec = json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            rec = {}
        rec.update({"user_id": str(user_id), "ping_mode": mode,
                    "updated_ts": time.time()})
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(rec), encoding="utf-8")
        tmp.replace(p)
    except Exception:  # noqa: BLE001
        pass


def load_ping_mode(data_dir: Path, user_id: str) -> str:
    p = prefs_dir(Path(data_dir)) / \
        f"{re.sub(r'[^0-9]', '', str(user_id)) or 'unknown'}.json"
    try:
        rec = json.loads(p.read_text(encoding="utf-8"))
        return rec.get("ping_mode") or PING_MODE_BATCH
    except Exception:  # noqa: BLE001
        return PING_MODE_BATCH


def mark_live_ping_checked(data_dir: Path, user_id: str,
                          ts: float | None = None) -> None:
    """Bookkeeping for LIVE ping mode: the last time we checked this
    member's area for new nearby finds — so the periodic DM sweep only
    ever pings on what's genuinely NEW since last checked, never
    re-sends the same find every tick."""
    ts = time.time() if ts is None else ts
    d = prefs_dir(Path(data_dir))
    p = d / f"{re.sub(r'[^0-9]', '', str(user_id)) or 'unknown'}.json"
    try:
        d.mkdir(parents=True, exist_ok=True)
        rec = {}
        try:
            rec = json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            rec = {}
        rec["live_ping_last_ts"] = ts
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(rec), encoding="utf-8")
        tmp.replace(p)
    except Exception:  # noqa: BLE001
        pass


def live_ping_last_ts(data_dir: Path, user_id: str) -> float | None:
    p = prefs_dir(Path(data_dir)) / \
        f"{re.sub(r'[^0-9]', '', str(user_id)) or 'unknown'}.json"
    try:
        rec = json.loads(p.read_text(encoding="utf-8"))
        return float(rec["live_ping_last_ts"]) if "live_ping_last_ts" in rec else None
    except Exception:  # noqa: BLE001
        return None


def members_with_live_ping(data_dir: Path) -> list[tuple[str, dict]]:
    """Every member with LIVE ping mode AND a saved, usable area —
    (user_id, area) pairs, for the periodic DM sweep to iterate."""
    d = prefs_dir(Path(data_dir))
    out: list[tuple[str, dict]] = []
    try:
        files = sorted(d.glob("*.json"))
    except Exception:  # noqa: BLE001
        return []
    for f in files:
        try:
            rec = json.loads(f.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        area = rec.get("area")
        if rec.get("ping_mode") == PING_MODE_LIVE and area and area.get("zips"):
            out.append((str(rec.get("user_id") or f.stem), area))
    return out


def area_summary(area: dict | None) -> str:
    if not area:
        return "no area set"
    bits = []
    if area.get("zips"):
        bits.append("zips " + ", ".join(area["zips"]))
    if area.get("radius_mi"):
        bits.append(f"±{area['radius_mi']} mi")
    if area.get("state"):
        bits.append(f"state {area['state']}")
    return " · ".join(bits)


# location-filter-d (Kevin, 2026-07-27): "so I can enter a channel and
# request reports" — the on-request half of the two ping modes. Scans
# every tracker's runs.jsonl (the SAME truth latest_finds() already
# reads), keeps only finds naming a real, geocodable location
# (actionability.extract_location) that resolves within the member's
# saved zip+radius (geo.is_nearby) — never a guess, honest "no matches"
# when nothing's close or nothing named a place at all.
def nearby_finds(data_dir: Path, area: dict | None, *, days: float = 3.0,
                 limit: int = 10, now: float | None = None,
                 since_ts: float | None = None, getter=None) -> list[dict]:
    """`since_ts` (when given) overrides the `days` window with an exact
    cutoff — the periodic LIVE-mode sweep uses this so a member is only
    ever pinged for what's genuinely new since it last checked, never a
    re-send of something already seen."""
    if not area:
        return []
    now = time.time() if now is None else now
    cutoff = since_ts if since_ts is not None else now - (days * 86_400)
    from sovereign_agent.actionability import extract_location
    from sovereign_agent.geo import is_nearby
    from sovereign_agent.verticals import channeled_verticals
    out: list[dict] = []
    for v in channeled_verticals():
        for f in latest_finds(data_dir, limit=200, project=v.project):
            if f["ts"] < cutoff:
                continue
            loc = extract_location(f.get("text", ""))
            if not loc or not is_nearby(data_dir, loc, area, getter=getter):
                continue
            out.append({**f, "vertical": v.slug, "location": loc})
    out.sort(key=lambda f: f["ts"], reverse=True)
    return out[:limit]


# ── the cards (discord_limits discipline everywhere) ────────────────────────
_FUNNEL = "⚡ want these first, filtered to you? → #storefront"

# affiliate-links-d (Kevin, 2026-07-25): FTC 16 CFR Part 255 requires a
# clear, conspicuous disclosure wherever an affiliate-tagged link appears
# — built in at the point of posting so it can never be silently forgotten
# on a new vertical or message type. Only shown when a link in THIS
# specific message actually got tagged (never a blanket disclaimer on
# every message, which would be noise on the untagged majority).
_AFFILIATE_DISCLOSURE = ("🔗 As an Amazon Associate, purchases through some "
                        "links here may earn a commission.")


def _any_amazon_tagged(urls: list[str]) -> bool:
    return any("amazon." in (u or "") and "tag=" in (u or "") for u in urls)


def lane_embed(data_dir: Path, lane: str, *, now: float | None = None,
               project: str = "tcg-scout") -> dict:
    """One ephemeral embed: that lane's latest finds, greatest→least."""
    now = time.time() if now is None else now
    ranks = load_ranks(Path(data_dir), project)
    finds = sort_by_value(
        latest_finds(data_dir, lane=lane, limit=10, project=project), ranks)
    titles = {"online": "🌐 Online — latest restocks",
              "local": "🏪 Local — in-store finds",
              "deals": "💸 Deals — cheap + restock relays"}
    lines = []
    urls = []
    for f in finds:
        tier = ranks[rank_of(f["text"], ranks)]
        age_m = max(0, int((now - f["ts"]) / 60))
        age = f"{age_m}m" if age_m < 120 else f"{age_m // 60}h"
        url = link_for(f)
        urls.append(url)
        text = (f["text"] or f["source"] or f["id"])[:140]
        entry = f"{tier['label']} [{text}]({url})" if url \
            else f"{tier['label']} {text}"
        # what · how much · where · when — every find fully answerable
        price = price_of(f["text"])
        bits = [entry]
        if price:
            bits.append(f"💵 {price}")
        bits.append(f"via {f['source']}")
        bits.append(f"{age} ago")
        lines.append(" · ".join(bits))
    if not lines:
        if lane == "local":
            lines = ["watching Dollar General + community store sightings — "
                     "a find here means GO CHECK YOUR STORE. Per-store live "
                     "inventory (Target/Walmart/DG) unlocks with official API "
                     "keys. Set ⚙ My Area so I can tune these to you."]
        else:
            lines = ["quiet right now — the scout is watching. Check back "
                     "soon!"]
    color = ranks[0]["color"] if finds else 0x95A5A6
    footer = _FUNNEL
    if _any_amazon_tagged(urls):
        footer = f"{_AFFILIATE_DISCLOSURE}\n{_FUNNEL}"
    from sovereign_agent.discord_limits import clamp_embed
    return clamp_embed({
        "title": titles.get(lane, lane),
        "description": "\n".join(lines),
        "color": color,
        "footer": {"text": footer},
    })


def panel_embed(data_dir: Path, *, now: float | None = None) -> dict:
    """The living dashboard: heartbeat + counters + last find."""
    now = time.time() if now is None else now
    stats = day_stats(data_dir, now=now)
    finds = latest_finds(data_dir, limit=1)
    last = "—"
    if finds:
        age_m = max(0, int((now - finds[0]["ts"]) / 60))
        what = (finds[0]["text"] or f"a find via {finds[0]['source']}")[:90]
        last = f"{what} · {age_m}m ago"
    try:
        from sovereign_agent.bot_health import scan_bots  # noqa: F401
        heartbeat = "◉ hunting"
    except Exception:  # noqa: BLE001
        heartbeat = "◉ hunting"
    desc = (f"{heartbeat} · Pokémon TCG restocks + deals, ranked by value\n\n"
            f"**today:** {stats['total']} finds — "
            f"🌐 {stats['per_lane'].get('online', 0)} · "
            f"🏪 {stats['per_lane'].get('local', 0)} · "
            f"💸 {stats['per_lane'].get('deals', 0)}\n"
            f"**latest:** {last}\n\n"
            "Pick a lane below — 🔔 opts you into public pings · "
            "⚙ sets your area for local finds")
    from sovereign_agent.discord_limits import clamp_embed
    return clamp_embed({"title": "🔭 Aria's TCG Scout — live",
                        "description": desc, "color": 0xF1C40F,
                        "footer": {"text": _FUNNEL}})


def _matches_pref(find_text: str, pref: str) -> bool:
    """members-d: filter a find by the member's fulfillment preference."""
    if not pref or pref == "all":
        return True
    from sovereign_agent.fulfillment import BOTH, DELIVERY, INSTORE, fulfillment_of
    fill = fulfillment_of(find_text).get("fill", "")
    if pref == "delivery":
        return fill in (DELIVERY, BOTH) or "online" in fill
    if pref == "pickup":
        return fill in (BOTH,) or "pickup" in fill
    if pref == "local":
        return fill in (INSTORE, BOTH)
    return True


def vertical_embed(data_dir: Path, slug: str, *,
                   now: float | None = None, user_id: str = "") -> dict:
    """One niche's latest finds (the Hub button payload) — value-ranked,
    WHAT · HOW MUCH · WHERE, private-to-you. Filters to the member's
    fulfillment preference when set (members-d). verticals-d."""
    now = time.time() if now is None else now
    from sovereign_agent.discord_limits import clamp_embed
    from sovereign_agent.verticals import get_vertical
    v = get_vertical(slug)
    if v is None:
        return clamp_embed({"title": "unknown tracker",
                            "description": "try the ▸ View more menu.",
                            "color": 0x95A5A6})
    project = v.project
    ranks = load_ranks(Path(data_dir), project)
    finds = sort_by_value(latest_finds(data_dir, limit=20, project=project),
                          ranks)
    # members-d: honor the member's pickup/delivery/local preference
    pref = "all"
    if user_id:
        try:
            from sovereign_agent.members import load_member
            rec = load_member(data_dir, user_id)
            pref = (rec or {}).get("fulfillment", "all")
        except Exception:  # noqa: BLE001
            pref = "all"
    if pref != "all":
        filtered = [f for f in finds if _matches_pref(f.get("text", ""), pref)]
        finds = filtered or finds        # never show an empty niche to a pref
    from sovereign_agent.fulfillment import fulfillment_line
    from sovereign_agent.scout_verify import verification_for, verify_badge
    blocks = []
    urls = []
    for f in finds[:7]:                    # detail-rich cards; top 7
        tier = ranks[rank_of(f["text"], ranks)]
        age_m = max(0, int((now - f["ts"]) / 60))
        age = f"{age_m}m" if age_m < 120 else f"{age_m // 60}h"
        url = link_for(f)
        urls.append(url)
        text = (f["text"] or f["source"])[:150]
        price = price_of(f["text"])
        badge = verify_badge(verification_for(data_dir, project, f["id"]))
        # line 1: verify badge + tier + title (embedded link) + price + age
        head = f"{tier['label']} **[{text}]({url})**" if url \
            else f"{tier['label']} **{text}**"
        head = f"{badge} {head}" + (f" · 💵 {price}" if price else "") \
            + f" · {age} ago"
        # line 2: fulfillment — where, how to get it, hours, locator
        fl = fulfillment_line(f["text"])
        row2 = f"   ↳ {fl}" if fl else ""
        # line 3: location clue named in the post (honest — never invented)
        from sovereign_agent.store_mentions import mention_line
        ml = mention_line(f["text"])
        row3 = f"   {ml}" if ml else ""
        row4 = f"   🔗 {url}" if url else ""
        blocks.append("\n".join(x for x in (head, row2, row3, row4) if x))
    if not blocks:
        blocks = [f"quiet right now — {v.name} scout is watching. "
                  "Check back soon!"]
    footer = f"🔔 ping for {v.name} · full-speed + filtered → #storefront"
    if _any_amazon_tagged(urls):
        footer = f"{_AFFILIATE_DISCLOSURE}\n{footer}"
    return clamp_embed({
        "title": f"{v.emoji} {v.name} — latest finds",
        "description": "\n\n".join(blocks), "color": v.color,
        "footer": {"text": footer}})


# ── her voice on the wire (bounded showmanship, duty-loop driven) ───────────
FLEX_DAILY_CAP = 6          # top-tier one-liners per day, never a firehose
_FLEX_LINES = [
    "{item} just surfaced — that one never sits. ⚡",
    "Heads up: {item} is live. Blink and it's gone. 🔭",
    "The scout flagged {item} — top-tier find. Go. ⚡",
]


def _voice_state_path(data_dir: Path, project: str = "tcg-scout") -> Path:
    return Path(data_dir) / "bot_projects" / project / "voice_state.json"


def _load_voice_state(data_dir: Path, day: str,
                      project: str = "tcg-scout") -> dict:
    try:
        st = json.loads(
            _voice_state_path(data_dir, project).read_text(encoding="utf-8"))
        if st.get("day") == day:
            return st
    except Exception:  # noqa: BLE001
        pass
    return {"day": day, "count": 0, "flexed": [], "reported": False}


def _save_voice_state(data_dir: Path, st: dict,
                      project: str = "tcg-scout") -> None:
    p = _voice_state_path(data_dir, project)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(st), encoding="utf-8")
        tmp.replace(p)
    except Exception:  # noqa: BLE001
        pass


def maybe_flex(data_dir: Path, *, live: bool = False,
               now: float | None = None, project: str = "tcg-scout",
               webhook_env: str = "DISCORD_DEMO_WEBHOOK_URL") -> str | None:
    """One Aria line when a TOP-TIER find is fresh — capped per day, each
    find flexed at most once, dry-run safe. Per-vertical via project."""
    now = time.time() if now is None else now
    day = time.strftime("%Y-%m-%d", time.gmtime(now))
    st = _load_voice_state(Path(data_dir), day, project)
    if st["count"] >= FLEX_DAILY_CAP:
        return None
    ranks = load_ranks(Path(data_dir), project)
    for f in latest_finds(data_dir, limit=20, project=project):
        if now - f["ts"] > 1800:                 # only FRESH finds flex
            break
        if rank_of(f["text"], ranks) != 0 or f["id"] in st["flexed"]:
            continue
        line = _FLEX_LINES[st["count"] % len(_FLEX_LINES)].format(
            item=(f["text"] or "a chase item")[:120])
        from sovereign_agent.discord_runtime.delivery import WebhookDelivery
        WebhookDelivery(webhook_env, live=live).send(line, username="Aria")
        st["flexed"] = (st["flexed"] + [f["id"]])[-50:]
        st["count"] += 1
        _save_voice_state(Path(data_dir), st, project)
        return line
    return None


def compose_scout_report(data_dir: Path, *, now: float | None = None,
                         project: str = "tcg-scout") -> str:
    """The daily Scout Report — her voice, greatest→least value."""
    now = time.time() if now is None else now
    ranks = load_ranks(Path(data_dir), project)
    stats = day_stats(data_dir, now=now, project=project)
    finds = sort_by_value(
        latest_finds(data_dir, limit=30, project=project), ranks)[:10]
    lines = [f"🔭 **Scout Report** — {stats['total']} finds today "
             f"(🌐 {stats['per_lane'].get('online', 0)} · "
             f"🏪 {stats['per_lane'].get('local', 0)} · "
             f"💸 {stats['per_lane'].get('deals', 0)})"]
    urls = []
    for f in finds:
        tier = ranks[rank_of(f['text'], ranks)]
        what = (f['text'] or f['source'])[:120]
        url = link_for(f)
        urls.append(url)
        price = price_of(f['text'])
        line = f"{tier['label']} {what}"
        if price:
            line += f" · 💵 {price}"
        if url:
            line += f" · <{url}>"          # <> = no embed spam in the digest
        lines.append(line)
    if not finds:
        lines.append("a quiet day — I watched every source; nothing worth "
                     "your money moved. That's the report, honestly.")
    lines.append("")
    if _any_amazon_tagged(urls):
        lines.append(_AFFILIATE_DISCLOSURE)
    lines.append(_FUNNEL)
    return "\n".join(lines)


def publish_scout_report(data_dir: Path, *, live: bool = False,
                         now: float | None = None, project: str = "tcg-scout",
                         webhook_env: str = "DISCORD_DEMO_WEBHOOK_URL"):
    """Post the daily report once per day (duty-driven). Per-vertical."""
    now = time.time() if now is None else now
    day = time.strftime("%Y-%m-%d", time.gmtime(now))
    st = _load_voice_state(Path(data_dir), day, project)
    if st.get("reported"):
        return None
    from sovereign_agent.discord_limits import split_text
    from sovereign_agent.discord_runtime.delivery import WebhookDelivery
    delivery = WebhookDelivery(webhook_env, live=live)
    result = None
    for part in split_text(
            compose_scout_report(data_dir, now=now, project=project),
            1900)[:2]:
        result = delivery.send(part, username="Aria")
    st["reported"] = True
    _save_voice_state(Path(data_dir), st, project)
    return result


__all__ = ["DEFAULT_RANKS", "LANES", "load_ranks", "rank_of", "sort_by_value",
           "classify_lane", "link_for", "latest_finds", "day_stats",
           "parse_area", "save_area", "load_area", "area_summary",
           "PING_MODE_BATCH", "PING_MODE_LIVE", "save_ping_mode",
           "load_ping_mode", "nearby_finds", "mark_live_ping_checked",
           "live_ping_last_ts", "members_with_live_ping",
           "price_of", "lane_embed", "panel_embed", "vertical_embed",
           "ranks_path", "maybe_flex",
           "compose_scout_report", "publish_scout_report", "FLEX_DAILY_CAP"]
