"""test_real_estate_gate_connections.py — county-connections-d: the
strategy note process_real_estate_item() returns now also carries a
"who to contact" line, appended by real_estate_gate.py's own try/except
wrapper around real_estate_connections.suggest_connections()."""
from __future__ import annotations

from sovereign_agent.real_estate_gate import process_real_estate_item
from sovereign_agent.real_estate_requirements import BuyBoxRequirements


def test_process_item_appends_connections_line_to_strategy_note(tmp_path):
    should_post, _analysis, strategy_note = process_real_estate_item(
        text="Facing foreclosure, behind on payments, $180,000.",
        url="", property_type="single-family", data_dir=tmp_path,
        requirements=BuyBoxRequirements(),
    )
    assert should_post is True
    assert "🤝 Connections:" in strategy_note
    assert "attorney" in strategy_note.lower()


def test_rejected_item_never_gets_a_connections_line(tmp_path):
    should_post, _analysis, strategy_note = process_real_estate_item(
        text="Single family home, $900,000, must sell.",
        url="", property_type="single-family", data_dir=tmp_path,
        requirements=BuyBoxRequirements(price_max=300000),
    )
    assert should_post is False
    assert strategy_note == ""
