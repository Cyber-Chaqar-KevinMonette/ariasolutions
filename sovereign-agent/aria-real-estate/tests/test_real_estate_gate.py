"""test_real_estate_gate.py — process_real_estate_item integration:
price extraction, requirement gating, and strategy note attachment,
against fakes (no real network / no real geo calls)."""
from __future__ import annotations

from unittest.mock import patch

from sovereign_agent.real_estate_gate import process_real_estate_item
from sovereign_agent.real_estate_requirements import BuyBoxRequirements


def test_process_item_extracts_price_and_runs_analysis(tmp_path):
    text = "Motivated seller! 3br home, $250,000, must sell fast."
    should_post, analysis, strategy_note = process_real_estate_item(
        text=text, url="", property_type="single-family", data_dir=tmp_path,
        requirements=BuyBoxRequirements(),
    )
    assert should_post is True
    assert analysis is not None
    assert analysis.purchase_price == 250000.0
    assert strategy_note  # non-empty


def test_process_item_k_suffix_price(tmp_path):
    should_post, analysis, _ = process_real_estate_item(
        text="Condo for sale, asking $250k, as-is.",
        url="", property_type="condo", data_dir=tmp_path,
        requirements=BuyBoxRequirements(),
    )
    assert analysis is not None
    assert analysis.purchase_price == 250000.0


def test_process_item_no_price_still_gates_on_property_type(tmp_path):
    should_post, analysis, _ = process_real_estate_item(
        text="Nice apartment building available, contact for details.",
        url="", property_type="apartments", data_dir=tmp_path,
        requirements=BuyBoxRequirements(property_types=["single-family"]),
    )
    assert should_post is False
    assert analysis is None


def test_process_item_property_type_filter_empty_means_allow_all(tmp_path):
    should_post, _analysis, _ = process_real_estate_item(
        text="Duplex available, $180,000.",
        url="", property_type="apartments", data_dir=tmp_path,
        requirements=BuyBoxRequirements(property_types=[]),
    )
    assert should_post is True


def test_process_item_rejected_by_price_requirement(tmp_path):
    should_post, analysis, strategy_note = process_real_estate_item(
        text="Single family home, $900,000, must sell.",
        url="", property_type="single-family", data_dir=tmp_path,
        requirements=BuyBoxRequirements(price_max=300000),
    )
    assert should_post is False
    assert strategy_note == ""


def test_process_item_rejected_by_location_requirement(tmp_path):
    reqs = BuyBoxRequirements(zip_codes=["90210"], radius_miles=10.0)
    with patch("sovereign_agent.geo.is_nearby", return_value=False):
        should_post, _analysis, _ = process_real_estate_item(
            text="Single family home, $200,000, motivated seller, 10001",
            url="", property_type="single-family", data_dir=tmp_path,
            requirements=reqs,
        )
    assert should_post is False


def test_process_item_loads_requirements_when_none_given(tmp_path):
    from sovereign_agent.real_estate_requirements import save_requirements
    save_requirements(tmp_path, BuyBoxRequirements(price_max=100000))
    should_post, _analysis, _ = process_real_estate_item(
        text="Single family, $250,000, motivated seller.",
        url="", property_type="single-family", data_dir=tmp_path,
    )
    assert should_post is False
