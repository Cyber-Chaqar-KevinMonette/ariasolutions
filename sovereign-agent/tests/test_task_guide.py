"""Tests for task_guide.py — the grounded capability menu.

Kevin, 2026-07-26: "Create a menu for things she can do... so I can test
everything following the guide." The one thing that matters most: every
tool name the guide claims exists must actually be registered — a
renamed or removed tool must fail this test immediately, not quietly
turn the guide into fiction.
"""
from __future__ import annotations


def _registered_tool_names() -> set[str]:
    import sovereign_agent.tools  # noqa: F401 — registers every tool
    from sovereign_agent.authority import all_tools
    return {m.name for m in all_tools()}


def test_every_referenced_tool_actually_exists():
    from sovereign_agent.task_guide import all_referenced_tool_names
    referenced = all_referenced_tool_names()
    registered = _registered_tool_names()
    missing = referenced - registered
    assert not missing, f"task_guide.py claims tools that don't exist: {missing}"


def test_every_category_has_at_least_one_entry():
    from sovereign_agent.task_guide import CATEGORIES
    assert len(CATEGORIES) >= 5
    for cat in CATEGORIES:
        assert cat.entries, f"{cat.title} has no entries"


def test_every_entry_has_a_real_example_to_type():
    from sovereign_agent.task_guide import CATEGORIES
    for cat in CATEGORIES:
        for entry in cat.entries:
            assert entry.label.strip()
            assert entry.example.strip()


def test_total_tool_count_matches_the_live_registry():
    from sovereign_agent.task_guide import total_tool_count
    assert total_tool_count() == len(_registered_tool_names())
    assert total_tool_count() > 100  # sanity: this is a big real registry


def test_all_tools_returns_every_registered_tool():
    from sovereign_agent.authority import all_tools
    import sovereign_agent.tools  # noqa: F401
    names = {m.name for m in all_tools()}
    assert "write_file" in names
    assert "generate_image" in names
    assert "acknowledge_inbox_note" in names  # the one added this session
    assert len(names) == len(all_tools())  # no duplicate names
