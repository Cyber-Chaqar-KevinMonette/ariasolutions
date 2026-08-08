"""Tests for real_estate_connections.py."""
from __future__ import annotations

from sovereign_agent.real_estate_connections import suggest_connections
from sovereign_agent.real_estate_strategy import suggest_strategy


def test_subject_to_strategy_gets_subject_to_connections():
    strategy = suggest_strategy("facing foreclosure, behind on payments")
    connections = suggest_connections(strategy)
    names = [c.name for c in connections]
    assert any("attorney" in n.lower() for n in names)


def test_seller_financing_strategy_gets_title_company_connection():
    strategy = suggest_strategy("inherited property, estate sale")
    connections = suggest_connections(strategy)
    names = [c.name for c in connections]
    assert any("title company" in n.lower() for n in names)


def test_divorce_case_maps_to_seller_financing_connections_too():
    """suggest_strategy's divorce rule text starts with 'Seller financing
    or quick-cash-close candidate' -- must still match the Seller
    financing category prefix, not fall through to the default."""
    strategy = suggest_strategy("motivated by divorce")
    connections = suggest_connections(strategy)
    names = [c.name for c in connections]
    assert any("title company" in n.lower() for n in names)


def test_brrrr_strategy_gets_hard_money_connection():
    strategy = suggest_strategy("needs work, fixer upper")
    connections = suggest_connections(strategy)
    names = [c.name for c in connections]
    assert any("hard money" in n.lower() or "hard-money" in n.lower() for n in names)


def test_cash_close_strategy_gets_auction_and_buyer_network():
    strategy = suggest_strategy("motivated seller, must sell quick")
    connections = suggest_connections(strategy)
    names = [c.name for c in connections]
    assert any("auction" in n.lower() for n in names)


def test_default_strategy_no_distress_signal_gets_default_connections():
    strategy = suggest_strategy("charming 3 bedroom home in a quiet neighborhood")
    connections = suggest_connections(strategy)
    names = [c.name for c in connections]
    assert any("loopnet" in n.lower() for n in names)


def test_universal_connections_always_present_regardless_of_category():
    for text in ("facing foreclosure", "inherited", "needs work",
                 "motivated seller", "no signal at all"):
        strategy = suggest_strategy(text)
        connections = suggest_connections(strategy)
        names = [c.name for c in connections]
        assert any("craigslist" in n.lower() for n in names)
        assert any("biggerpockets" in n.lower() for n in names)


def test_every_connection_has_a_name_and_note():
    for text in ("facing foreclosure", "", "generic listing"):
        strategy = suggest_strategy(text)
        for c in suggest_connections(strategy):
            assert c.name
            assert c.note
