"""Tests for weather — her keyless Open-Meteo lookup (no network ever)."""
from __future__ import annotations

from sovereign_agent.weather import (
    extract_place,
    get_weather,
    is_weather_query,
    weather_answer,
)


def _fake_get(url: str) -> dict:
    if "geocoding" in url:
        if "hopkinsville" in url:
            return {"results": [{"name": "Hopkinsville", "admin1": "Kentucky",
                                 "country_code": "US", "latitude": 36.87,
                                 "longitude": -87.49}]}
        return {"results": []}
    return {
        "current": {"temperature_2m": 91.4, "apparent_temperature": 97.0,
                    "relative_humidity_2m": 62, "precipitation": 0.0,
                    "weather_code": 1, "wind_speed_10m": 6.3},
        "daily": {"temperature_2m_max": [94.0], "temperature_2m_min": [72.0],
                  "precipitation_probability_max": [20]},
    }


def test_trigger_matrix():
    for q in ("how is the weather is hopkinsville ky today",
              "weather in Paris?", "what's the temperature in denver",
              "forecast for tokyo", "is it raining in seattle"):
        assert is_weather_query(q), q
    for q in ("what do you sell", "how much is basic", "are the bots up",
              "tell me about yourself"):
        assert not is_weather_query(q), q


def test_place_extraction_survives_kevins_real_sentence(monkeypatch):
    monkeypatch.delenv("WEATHER_HOME_PLACE", raising=False)
    assert extract_place("How is the weather is hopkinsville ky today") == \
        "hopkinsville ky"
    assert extract_place("weather in Paris?") == "paris"
    # no place + no home set → empty (the report will ask for one)
    assert extract_place("how's the weather today?") == ""
    monkeypatch.setenv("WEATHER_HOME_PLACE", "Hopkinsville KY")
    assert extract_place("how's the weather today?") == "Hopkinsville KY"


def test_full_lookup_with_state_suffix_retry():
    # "hopkinsville ky" doesn't geocode as-is — the retry drops "ky"
    def get(url):
        if "geocoding" in url and "hopkinsville%20ky" in url:
            return {"results": []}
        return _fake_get(url)
    out = weather_answer("how is the weather is hopkinsville ky today",
                         getter=get)
    assert "Hopkinsville, Kentucky, US" in out
    assert "91°F" in out and "feels 97°F" in out
    assert "high 94°F / low 72°F" in out and "20% chance" in out
    assert "Open-Meteo" in out


def test_honest_failures_never_raise():
    assert "couldn't find a place" in get_weather(
        "atlantis", getter=lambda u: {"results": []})
    assert "Tell me where" in get_weather("", getter=_fake_get)

    def broken(url):
        raise OSError("no network")
    assert "isn't reachable" in get_weather("x", getter=broken)


def test_ask_aria_routes_weather(monkeypatch, tmp_path):
    import sovereign_agent.weather as w
    monkeypatch.setattr(w, "_default_get", _fake_get)
    from sovereign_agent.ask_aria import answer_question
    reply = answer_question("how is the weather is hopkinsville ky today",
                            user_id="kev", data_dir=tmp_path)
    assert reply.kind == "weather"
    assert "Hopkinsville" in reply.text and "°F" in reply.text
    # non-weather questions still route where they always did
    assert answer_question("what do you sell", data_dir=tmp_path).kind == "shop"
