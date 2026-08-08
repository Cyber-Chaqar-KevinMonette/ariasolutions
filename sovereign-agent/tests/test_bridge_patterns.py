"""Tests for bridge_patterns — the hardened NL matcher + THE COLLISION MATRIX.

The matrix is the important part: every trigger phrase of every chat bridge
is pushed through ALL detectors in conversation.py's dispatch order, and the
FIRST detector that fires must be the phrase's owner. The 'any suggestions'
shadowing bug (a later bridge's phrase captured by an earlier bridge) can
never be reintroduced without this test failing by name.
"""
from __future__ import annotations

import pytest

from sovereign_agent.bridge_patterns import match_any, normalize

# ── the bridges, in conversation.py dispatch order ──────────────────────────
from sovereign_agent import (  # noqa: E402
    bot_health,
    bot_projects,
    credentials,
    discord_watch,
    doc_registry,
    health_report,
    journal,
    next_report,
    self_report,
    shop,
    success_patterns,
    suggestions,
    work_report,
    work_suggestions,
)

BRIDGES = [
    ("self",        self_report.is_self_query,        self_report._ALL_TRIGGERS),
    ("work",        work_report.is_work_query,        work_report._TRIGGERS),
    ("health",      health_report.is_health_query,    health_report._TRIGGERS),
    ("next",        next_report.is_next_query,        next_report._TRIGGERS),
    ("work-suggestions", work_suggestions.is_suggestions_query,
     work_suggestions._TRIGGERS),
    ("journal",     journal.is_journal_read_query,    journal._READ_TRIGGERS),
    ("bots",        bot_projects.is_bots_query,       bot_projects._BOTS_TRIGGERS),
    ("shop",        shop.is_shop_query,               shop._SHOP_TRIGGERS),
    ("bot-health",  bot_health.is_bot_health_query,   bot_health._HEALTH_TRIGGERS),
    ("suggestions", suggestions.is_suggestions_query, suggestions._SUGGEST_TRIGGERS),
    ("credentials", credentials.is_credentials_query, credentials._CRED_TRIGGERS),
    ("success",     success_patterns.is_success_query, success_patterns._SUCCESS_TRIGGERS),
    ("docs",        doc_registry.is_docs_query,        doc_registry._DOCS_TRIGGERS),
    ("discord-watch", discord_watch.is_discord_watch_query,
     discord_watch._WATCH_TRIGGERS),
]


# ── normalization ───────────────────────────────────────────────────────────
def test_normalize_curly_quotes_and_spaces():
    assert normalize("What’s   in the “shop”?") == 'what\'s in the "shop"?'


def test_normalize_nfkc_fullwidth():
    assert normalize("ｓｈｏｐ") == "shop"


def test_match_any_survives_typographic_input():
    # a phone's curly apostrophe must not defeat the shop bridge
    assert shop.is_shop_query("hey, what’s in the shop?")
    assert shop.is_shop_query("WHAT'S   IN THE SHOP")


def test_match_any_empty_safe():
    assert match_any("", ("x",)) is False
    assert match_any("x", ()) is False


# ── THE COLLISION MATRIX ────────────────────────────────────────────────────
@pytest.mark.parametrize("owner,phrase", [
    (name, phrase) for name, _fn, triggers in BRIDGES for phrase in triggers
])
def test_every_trigger_routes_to_its_own_bridge(owner, phrase):
    """The first bridge (in dispatch order) that fires on a phrase must be
    the phrase's owner — no earlier bridge may shadow it."""
    for name, fn, _trigs in BRIDGES:
        if fn(phrase):
            assert name == owner, (
                f"ROUTING COLLISION: trigger {phrase!r} belongs to "
                f"'{owner}' but '{name}' (earlier in conversation.py) "
                f"fires first and would shadow it")
            return
    pytest.fail(f"{owner} trigger {phrase!r} fired NO bridge — dead trigger")


def test_matrix_covers_all_bridges():
    assert len(BRIDGES) == 14
    assert all(len(triggers) > 0 for _n, _f, triggers in BRIDGES)
