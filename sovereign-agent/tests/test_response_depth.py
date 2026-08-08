"""
test_response_depth.py — verify the interpreter system prompt contains depth guidance.

These are structural tests: they verify depth-matching guidance is present
in the response field of the interpreter's system prompt.

This module (`aria-response-depth`, v0.2.42.0) was never actually applied
via its own apply script — but the exact capability it set out to add
(match response depth to question complexity) turned out to have already
been superseded by a richer, independently-written "DEPTH DOCTRINE"
section already live in interpreter.py (confirmed: the staged patch's own
anchor text no longer matches live — it's evolved, not missing). Root-
cause fix, matching "fix the test expectation when reality disagrees":
these tests now check for the actual live phrasing and structure rather
than the old, superseded exact wording the never-applied patch expected.
The underlying capability (depth-matching, casual→brief, technical→
thorough) is confirmed present and MORE elaborate than originally
planned — this module's own apply script is now correctly obsolete and
should not be run (it would just fail its stale anchor check forever).
"""
from __future__ import annotations


def test_system_prompt_contains_depth_guidance():
    """The _SYSTEM_PROMPT must contain depth-matching guidance in the
    response field — live phrasing is "DEPTH DOCTRINE", richer than this
    module's own originally-planned "Depth: match depth" wording."""
    from sovereign_agent.interpreter import _SYSTEM_PROMPT
    assert "DEPTH DOCTRINE" in _SYSTEM_PROMPT
    assert "match depth to complexity" in _SYSTEM_PROMPT


def test_system_prompt_retains_voice_guidance():
    """The 'your voice' instruction must be present, matching Kevin's tone."""
    from sovereign_agent.interpreter import _SYSTEM_PROMPT
    assert "your voice" in _SYSTEM_PROMPT
    assert "Match Kevin's tone" in _SYSTEM_PROMPT


def test_system_prompt_mentions_thorough():
    """The prompt must call for thorough, multi-paragraph responses to
    technical/architectural questions."""
    from sovereign_agent.interpreter import _SYSTEM_PROMPT
    assert "THOROUGH" in _SYSTEM_PROMPT
    assert "Multiple paragraphs" in _SYSTEM_PROMPT


def test_system_prompt_mentions_casual_chat():
    """The prompt must distinguish casual chat from technical questions."""
    from sovereign_agent.interpreter import _SYSTEM_PROMPT
    assert "casual chat" in _SYSTEM_PROMPT
    assert "2-3 warm sentences" in _SYSTEM_PROMPT


def test_brief_is_fine_removed():
    """The old blanket 'Brief is fine' instruction must be gone — depth
    is now a function of question complexity, not a flat default."""
    from sovereign_agent.interpreter import _SYSTEM_PROMPT
    assert "Brief is fine." not in _SYSTEM_PROMPT
