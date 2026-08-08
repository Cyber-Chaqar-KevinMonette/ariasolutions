"""geo.py — zip/place geocoding + distance, for member-area matching.

location-filter-d (Kevin, 2026-07-27): "wire zip/radius location
filtering into tracker alerts." Reuses weather.py's open-meteo
geocoding endpoint (already a live, no-key project dependency) rather
than adding a new provider or a bundled zip database — same honesty as
the rest of this session: a real geocode call, not a fabricated
distance approximation. Scope note (see store_mentions.py): this
resolves a member's ZIP and a post's mentioned ZIP/"City, ST" to
city-level coordinates — it is NOT the real per-store address lookup
`store_mentions.rank_stores_by_distance` reserves for a future
store-locator API key. "How far is the mentioned city from you" is the
honest ceiling here.
"""
from __future__ import annotations

import json
import math
import time
import urllib.parse
import urllib.request
from pathlib import Path

__all__ = ["geocode", "haversine_mi", "cached_geocode",
          "resolved_member_point", "is_nearby"]

_GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
_CACHE_MAX_AGE_S = 30 * 86400.0   # a zip's coordinates never change; 30d is generous


def _default_get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=10) as resp:  # noqa: S310
        return json.loads(resp.read().decode("utf-8"))


def geocode(place: str, *, getter=None) -> tuple[float, float] | None:
    """A raw ZIP or 'City, ST' string -> (lat, lon), US-preferred. A
    real network call (open-meteo, free, no key) — never fabricated;
    None on anything unresolvable."""
    place = (place or "").strip()
    if not place:
        return None
    get = getter or _default_get
    try:
        q = urllib.parse.quote(place)
        data = get(f"{_GEO_URL}?name={q}&count=10&language=en&format=json")
    except Exception:  # noqa: BLE001 — network down ≠ crash the caller
        return None
    results = (data or {}).get("results") or []
    if not results:
        return None
    us = [r for r in results if r.get("country_code") == "US"]
    # prefer a hit whose own postcodes list literally contains our zip
    exact = [r for r in us if place in (r.get("postcodes") or [])]
    pick = (exact or us or results)[0]
    try:
        return float(pick["latitude"]), float(pick["longitude"])
    except Exception:  # noqa: BLE001
        return None


def haversine_mi(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in miles — plain math, no dependency."""
    r_mi = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = (math.sin(dphi / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2)
    return 2 * r_mi * math.asin(math.sqrt(min(1.0, a)))


def _cache_path(data_dir) -> Path:
    return Path(data_dir) / "geo" / "geocode_cache.json"


def _load_cache(data_dir) -> dict:
    try:
        return json.loads(_cache_path(data_dir).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _save_cache(data_dir, cache: dict) -> None:
    p = _cache_path(data_dir)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(cache), encoding="utf-8")
        tmp.replace(p)
    except Exception:  # noqa: BLE001
        pass


def cached_geocode(data_dir, place: str, *, getter=None,
                   now: float | None = None) -> tuple[float, float] | None:
    """`geocode()` with a durable cache — a zip's coordinates don't
    change, so a live call per item/member/tick would be pure waste.
    Caches misses too (as a None entry) so a bad query isn't retried
    every tick either, just re-checked after `_CACHE_MAX_AGE_S`."""
    place = (place or "").strip()
    if not place:
        return None
    now = time.time() if now is None else now
    cache = _load_cache(data_dir)
    hit = cache.get(place)
    if hit and (now - hit.get("ts", 0)) < _CACHE_MAX_AGE_S:
        return (hit["lat"], hit["lon"]) if hit.get("lat") is not None else None
    point = geocode(place, getter=getter)
    cache[place] = ({"lat": point[0], "lon": point[1], "ts": now} if point
                    else {"lat": None, "lon": None, "ts": now})
    _save_cache(data_dir, cache)
    return point


def resolved_member_point(data_dir, area: dict, *,
                          getter=None) -> tuple[float, float] | None:
    """A member's saved area -> ONE representative (lat, lon) — its
    first zip (the most precise signal they gave)."""
    zips = (area or {}).get("zips") or []
    if not zips:
        return None
    return cached_geocode(data_dir, zips[0], getter=getter)


def is_nearby(data_dir, item_location: str, area: dict, *,
             getter=None) -> bool:
    """Real distance check: geocode both sides (cached), compare
    against the member's saved radius. False — never a silent True —
    on anything unresolvable; this never guesses a member is "near"
    something it couldn't actually place on the map."""
    if not item_location or not area:
        return False
    member_pt = resolved_member_point(data_dir, area, getter=getter)
    item_pt = cached_geocode(data_dir, item_location, getter=getter)
    if member_pt is None or item_pt is None:
        return False
    dist = haversine_mi(member_pt[0], member_pt[1], item_pt[0], item_pt[1])
    return dist <= float(area.get("radius_mi") or 25)
