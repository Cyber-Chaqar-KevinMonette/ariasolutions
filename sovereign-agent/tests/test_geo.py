"""location-filter-d (Kevin, 2026-07-27): geo.py — real geocode + distance,
no network in tests (injectable getter, matching weather.py's pattern)."""
from __future__ import annotations

from urllib.parse import unquote

from sovereign_agent.geo import (
    cached_geocode,
    geocode,
    haversine_mi,
    is_nearby,
    resolved_member_point,
)

# Hopkinsville, KY (42240) and Clarksville, TN — real-ish coords, ~25mi apart
_HOPKINSVILLE = (36.86561, -87.49117)
_CLARKSVILLE = (36.52981, -87.35944)
_NASHVILLE = (36.16589, -86.78444)   # ~65mi from Hopkinsville


def _fake_get(zip_to_point: dict):
    def get(url: str) -> dict:
        decoded = unquote(url)
        for place, (lat, lon) in zip_to_point.items():
            if place in decoded:
                return {"results": [{"country_code": "US", "latitude": lat,
                                     "longitude": lon, "postcodes": [place]}]}
        return {"results": []}
    return get


def test_geocode_resolves_a_known_zip():
    get = _fake_get({"42240": _HOPKINSVILLE})
    assert geocode("42240", getter=get) == _HOPKINSVILLE


def test_geocode_none_for_unresolvable_place():
    get = _fake_get({})
    assert geocode("not a real place", getter=get) is None


def test_geocode_empty_place_is_none_without_a_network_call():
    calls = []
    def get(url):
        calls.append(url)
        return {"results": []}
    assert geocode("", getter=get) is None
    assert calls == []


def test_haversine_zero_for_same_point():
    assert haversine_mi(*_HOPKINSVILLE, *_HOPKINSVILLE) < 0.01


def test_haversine_roughly_matches_known_distance():
    d = haversine_mi(*_HOPKINSVILLE, *_NASHVILLE)
    assert 55 < d < 75   # Hopkinsville KY -> Nashville TN is ~65mi


def test_cached_geocode_only_calls_network_once(tmp_path):
    calls = []
    def get(url):
        calls.append(url)
        return {"results": [{"country_code": "US", "latitude": _HOPKINSVILLE[0],
                             "longitude": _HOPKINSVILLE[1], "postcodes": ["42240"]}]}
    p1 = cached_geocode(tmp_path, "42240", getter=get)
    p2 = cached_geocode(tmp_path, "42240", getter=get)
    assert p1 == p2 == _HOPKINSVILLE
    assert len(calls) == 1


def test_cached_geocode_caches_misses_too(tmp_path):
    calls = []
    def get(url):
        calls.append(url)
        return {"results": []}
    assert cached_geocode(tmp_path, "00000", getter=get) is None
    assert cached_geocode(tmp_path, "00000", getter=get) is None
    assert len(calls) == 1


def test_resolved_member_point_uses_first_zip(tmp_path):
    get = _fake_get({"42240": _HOPKINSVILLE})
    area = {"zips": ["42240", "37040"], "radius_mi": 50}
    assert resolved_member_point(tmp_path, area, getter=get) == _HOPKINSVILLE


def test_resolved_member_point_none_without_zips(tmp_path):
    assert resolved_member_point(tmp_path, {"radius_mi": 50}, getter=lambda u: {}) is None


def test_is_nearby_true_within_radius(tmp_path):
    get = _fake_get({"42240": _HOPKINSVILLE, "Clarksville, TN": _CLARKSVILLE})
    area = {"zips": ["42240"], "radius_mi": 50}
    assert is_nearby(tmp_path, "Clarksville, TN", area, getter=get) is True


def test_is_nearby_false_outside_radius(tmp_path):
    get = _fake_get({"42240": _HOPKINSVILLE, "Nashville, TN": _NASHVILLE})
    area = {"zips": ["42240"], "radius_mi": 25}
    assert is_nearby(tmp_path, "Nashville, TN", area, getter=get) is False


def test_is_nearby_false_never_guesses_on_unresolvable_location(tmp_path):
    get = _fake_get({"42240": _HOPKINSVILLE})
    area = {"zips": ["42240"], "radius_mi": 1000}
    assert is_nearby(tmp_path, "Nowhereville, ZZ", area, getter=get) is False


def test_is_nearby_false_without_area_or_location(tmp_path):
    get = _fake_get({"42240": _HOPKINSVILLE})
    assert is_nearby(tmp_path, "", {"zips": ["42240"], "radius_mi": 50},
                     getter=get) is False
    assert is_nearby(tmp_path, "Clarksville, TN", None, getter=get) is False
