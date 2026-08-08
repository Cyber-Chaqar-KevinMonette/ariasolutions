"""weather.py — ☀ real weather in her voice (free, keyless, open data).

Kevin's ask (2026-07-17): "/ma how is the weather in hopkinsville ky
today" → Aria looks it up and answers. Powered by Open-Meteo
(open-meteo.com) — free for non-commercial use, NO API key, no account:
one geocoding GET + one forecast GET. Nothing about the asker is sent —
only the place name.

Resilience by construction:
  • geocoding retries with the last token dropped ("hopkinsville ky" →
    "hopkinsville") because gazetteers match names, not state suffixes;
  • place extraction is filler-stripping, not grammar-parsing — Kevin's
    real sentence ("how is the weather is hopkinsville ky today") works;
  • every network failure → an honest one-liner, never an exception;
  • injectable getter — tests never touch the network.
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request

_TIMEOUT_S = 8.0
_GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
_FC_URL = "https://api.open-meteo.com/v1/forecast"

# WMO weather interpretation codes → plain words
_WMO = {
    0: "clear sky", 1: "mostly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "icy fog", 51: "light drizzle", 53: "drizzle",
    55: "heavy drizzle", 56: "freezing drizzle", 57: "freezing drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain", 66: "freezing rain",
    67: "freezing rain", 71: "light snow", 73: "snow", 75: "heavy snow",
    77: "snow grains", 80: "light showers", 81: "showers",
    82: "violent showers", 85: "snow showers", 86: "heavy snow showers",
    95: "thunderstorm", 96: "thunderstorm with hail",
    99: "thunderstorm with heavy hail",
}

_TRIGGERS = ("weather", "forecast", "temperature", "how hot", "how cold",
             "is it raining", "is it snowing", "rain today", "snow today")

# words that are ABOUT the question, not the place
_FILLER = {
    "how", "hows", "how's", "is", "the", "what", "whats", "what's", "like",
    "weather", "forecast", "temperature", "temp", "today", "tonight",
    "tomorrow", "now", "right", "currently", "in", "at", "for", "outside",
    "out", "there", "it", "gonna", "going", "to", "be", "rain", "raining",
    "snow", "snowing", "hot", "cold", "this", "week", "please", "aria",
    "me", "tell", "check", "look", "up", "hey", "can", "you", "and",
}


def _default_get(url: str) -> dict:  # pragma: no cover - network
    req = urllib.request.Request(
        url, headers={"User-Agent": "sovereign-agent-weather/1.0"})
    with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as r:
        return json.loads(r.read().decode("utf-8"))


def is_weather_query(text: str) -> bool:
    from sovereign_agent.bridge_patterns import normalize
    return any(t in normalize(text) for t in _TRIGGERS)


def extract_place(text: str) -> str:
    """Strip question-filler; whatever survives is the place. Empty →
    the WEATHER_HOME_PLACE env fallback (Kevin can vault his hometown)."""
    from sovereign_agent.bridge_patterns import normalize
    words = [w for w in normalize(text).replace("?", " ").replace(",", " ")
             .split() if w not in _FILLER and not w.isdigit()]
    place = " ".join(words).strip()
    return place or (os.environ.get("WEATHER_HOME_PLACE") or "").strip()


def _geocode(place: str, get) -> dict | None:
    """Name → lat/lon; drops trailing tokens until the gazetteer bites
    ("hopkinsville ky" → "hopkinsville")."""
    tokens = place.split()
    while tokens:
        q = urllib.parse.quote(" ".join(tokens))
        data = get(f"{_GEO_URL}?name={q}&count=1&language=en&format=json")
        results = data.get("results") or []
        if results:
            return results[0]
        tokens = tokens[:-1]
    return None


def get_weather(place: str, *, getter=None) -> str:
    """The friendly report — current conditions + today's range. Never
    raises; failure modes come back as honest sentences."""
    get = getter or _default_get
    place = (place or "").strip()
    if not place:
        return ("Tell me where! Try: weather in Hopkinsville KY "
                "(or set WEATHER_HOME_PLACE in the vault so I know home).")
    try:
        loc = _geocode(place, get)
    except Exception:  # noqa: BLE001 — network down ≠ place unknown
        return ("The weather service isn't reachable right now — "
                "try me again in a minute!")
    if loc is None:
        return (f"I couldn't find a place called \"{place}\" on the map — "
                f"try adding the state or country?")
    try:
        lat, lon = float(loc["latitude"]), float(loc["longitude"])
        url = (f"{_FC_URL}?latitude={lat}&longitude={lon}"
               "&current=temperature_2m,apparent_temperature,"
               "relative_humidity_2m,precipitation,weather_code,wind_speed_10m"
               "&daily=temperature_2m_max,temperature_2m_min,"
               "precipitation_probability_max&forecast_days=1"
               "&temperature_unit=fahrenheit&wind_speed_unit=mph"
               "&timezone=auto")
        data = get(url)
        cur = data.get("current") or {}
        day = data.get("daily") or {}
        where = ", ".join(x for x in (loc.get("name"), loc.get("admin1"),
                                      loc.get("country_code")) if x)
        sky = _WMO.get(int(cur.get("weather_code", -1)), "mixed conditions")
        t = cur.get("temperature_2m")
        feels = cur.get("apparent_temperature")
        wind = cur.get("wind_speed_10m")
        hum = cur.get("relative_humidity_2m")
        hi = (day.get("temperature_2m_max") or [None])[0]
        lo = (day.get("temperature_2m_min") or [None])[0]
        pop = (day.get("precipitation_probability_max") or [None])[0]
        bits = [f"Right now in {where}: {sky}"]
        if t is not None:
            bits.append(f"{round(float(t))}°F"
                        + (f" (feels {round(float(feels))}°F)"
                           if feels is not None else ""))
        if wind is not None:
            bits.append(f"wind {round(float(wind))} mph")
        if hum is not None:
            bits.append(f"humidity {round(float(hum))}%")
        line1 = ", ".join(bits) + "."
        line2 = ""
        if hi is not None and lo is not None:
            line2 = (f"Today: high {round(float(hi))}°F / "
                     f"low {round(float(lo))}°F"
                     + (f", {round(float(pop))}% chance of precipitation"
                        if pop is not None else "") + ".")
        tail = "(live data from Open-Meteo)"
        return " ".join(x for x in (line1, line2, tail) if x)
    except Exception:  # noqa: BLE001
        return ("I found the place but the weather service didn't answer "
                "just now — try me again in a minute!")


def weather_answer(question: str, *, getter=None) -> str:
    """The one-call lane for her voice: extract the place, fetch, report."""
    return get_weather(extract_place(question), getter=getter)


__all__ = ["is_weather_query", "extract_place", "get_weather",
           "weather_answer"]
