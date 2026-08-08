"""test_real_estate_requirements.py — buy-box storage, key=value parsing,
and the requirement_passes gate."""
from __future__ import annotations

from unittest.mock import patch

from sovereign_agent.real_estate_deal_analyzer import analyze_deal
from sovereign_agent.real_estate_requirements import (
    BuyBoxRequirements, apply_command, load_requirements,
    requirement_passes, requirements_path, save_requirements, summarize,
)


def test_load_requirements_defaults_when_no_file(tmp_path):
    reqs = load_requirements(tmp_path)
    assert reqs == BuyBoxRequirements()


def test_save_then_load_round_trips(tmp_path):
    reqs = BuyBoxRequirements(
        zip_codes=["90210"], radius_miles=15.0, property_types=["condo"],
        price_min=100000, price_max=300000, min_cash_flow_monthly=200.0,
        min_cap_rate_pct=6.0, min_cash_on_cash_pct=10.0,
        financing_preference="seller-financing", notes="near the coast",
    )
    save_requirements(tmp_path, reqs)
    assert requirements_path(tmp_path).is_file()

    loaded = load_requirements(tmp_path)
    assert loaded == reqs


def test_save_is_atomic_no_tmp_file_left_behind(tmp_path):
    save_requirements(tmp_path, BuyBoxRequirements(zip_codes=["12345"]))
    tmp_file = requirements_path(tmp_path).with_suffix(".json.tmp")
    assert not tmp_file.exists()


def test_apply_command_parses_key_value_pairs():
    existing = BuyBoxRequirements()
    updated = apply_command(
        existing,
        "zips=90210,90211 radius=20 price_max=300000 min_cash_flow=200 "
        "types=single-family,condo financing=seller-financing",
    )
    assert updated.zip_codes == ["90210", "90211"]
    assert updated.radius_miles == 20.0
    assert updated.price_max == 300000.0
    assert updated.min_cash_flow_monthly == 200.0
    assert updated.property_types == ["single-family", "condo"]
    assert updated.financing_preference == "seller-financing"


def test_apply_command_leaves_unspecified_fields_untouched():
    existing = BuyBoxRequirements(zip_codes=["11111"], radius_miles=10.0)
    updated = apply_command(existing, "price_max=250000")
    assert updated.zip_codes == ["11111"]      # untouched
    assert updated.radius_miles == 10.0        # untouched
    assert updated.price_max == 250000.0       # newly set


def test_apply_command_ignores_unrecognized_tokens_never_raises():
    existing = BuyBoxRequirements()
    updated = apply_command(existing, "hello there price_max=200000 whatever=nonsense")
    assert updated.price_max == 200000.0


def test_apply_command_ignores_bad_numeric_value():
    existing = BuyBoxRequirements(price_max=999.0)
    updated = apply_command(existing, "price_max=not-a-number")
    assert updated.price_max == 999.0   # unchanged, didn't raise


def test_requirement_passes_no_filters_set_always_true(tmp_path):
    reqs = BuyBoxRequirements()
    assert requirement_passes(data_dir=tmp_path, requirements=reqs) is True


def test_requirement_passes_price_bounds(tmp_path):
    reqs = BuyBoxRequirements(price_min=100000, price_max=200000)
    assert requirement_passes(data_dir=tmp_path, price=150000, requirements=reqs) is True
    assert requirement_passes(data_dir=tmp_path, price=50000, requirements=reqs) is False
    assert requirement_passes(data_dir=tmp_path, price=300000, requirements=reqs) is False


def test_requirement_passes_location_gate_uses_geo_is_nearby(tmp_path):
    reqs = BuyBoxRequirements(zip_codes=["90210"], radius_miles=20.0)
    with patch("sovereign_agent.geo.is_nearby", return_value=True) as m:
        assert requirement_passes(
            data_dir=tmp_path, item_location="90211", requirements=reqs) is True
    m.assert_called_once()

    with patch("sovereign_agent.geo.is_nearby", return_value=False):
        assert requirement_passes(
            data_dir=tmp_path, item_location="10001", requirements=reqs) is False


def test_requirement_passes_skips_location_gate_when_zips_not_set(tmp_path):
    """zip/radius is optional per tracker — an empty zip_codes list means
    no location filtering at all, never a silent False."""
    reqs = BuyBoxRequirements()
    with patch("sovereign_agent.geo.is_nearby") as m:
        assert requirement_passes(
            data_dir=tmp_path, item_location="", requirements=reqs) is True
    m.assert_not_called()


def test_requirement_passes_cash_flow_and_cap_rate_thresholds(tmp_path):
    reqs = BuyBoxRequirements(min_cash_flow_monthly=500.0, min_cap_rate_pct=10.0)
    good = analyze_deal(100000, 1500, 1500, 1500, down_payment_pct=0.20,
                        interest_rate_pct=0.0, loan_term_years=10.0)
    bad = analyze_deal(500000, 600, 600, 600, down_payment_pct=0.20,
                       interest_rate_pct=7.0, loan_term_years=30.0)
    assert requirement_passes(data_dir=tmp_path, analysis=good, requirements=reqs) is True
    assert requirement_passes(data_dir=tmp_path, analysis=bad, requirements=reqs) is False


def test_summarize_includes_set_fields():
    reqs = BuyBoxRequirements(zip_codes=["90210"], radius_miles=15.0,
                              price_max=300000.0, financing_preference="hard-money")
    text = summarize(reqs)
    assert "90210" in text
    assert "15.0" in text
    assert "300000" in text
    assert "hard-money" in text
