"""
test_deep_mind.py — verify the deep-mind reasoning patches.
"""
from __future__ import annotations


def test_interpreter_has_depth_doctrine():
    """interpreter.py must contain the DEPTH DOCTRINE."""
    from sovereign_agent.interpreter import _SYSTEM_PROMPT
    assert "DEPTH DOCTRINE" in _SYSTEM_PROMPT
    assert "THOROUGH" in _SYSTEM_PROMPT
    assert "SHOW YOUR THINKING" in _SYSTEM_PROMPT


def test_interpreter_drops_brief_is_fine():
    """'Brief is fine.' must not appear in the interpreter prompt."""
    from sovereign_agent.interpreter import _SYSTEM_PROMPT
    assert "Brief is fine." not in _SYSTEM_PROMPT, (
        "'Brief is fine.' still in interpreter — depth doctrine not applied"
    )


def test_interpreter_has_genius_doctrine():
    """The interpreter must contain the genius / full-capacity doctrine."""
    from sovereign_agent.interpreter import _SYSTEM_PROMPT
    assert "genius" in _SYSTEM_PROMPT.lower()
    assert "full capacity" in _SYSTEM_PROMPT.lower()


def test_interpreter_reasoning_is_chain_of_thought():
    """The reasoning field must require chain-of-thought, not just one sentence."""
    from sovereign_agent.interpreter import _SYSTEM_PROMPT
    assert "chain of thought" in _SYSTEM_PROMPT.lower()
    assert "audit trail" in _SYSTEM_PROMPT.lower()


def test_loop_has_deep_reasoning_section():
    """loop.py must contain the DEEP REASONING section."""
    from sovereign_agent.loop import SYSTEM_PROMPT_TEMPLATE
    assert "DEEP REASONING" in SYSTEM_PROMPT_TEMPLATE
    assert "PATHS CONSIDERED" in SYSTEM_PROMPT_TEMPLATE
    assert "MOST ADVANCED SOLUTION" in SYSTEM_PROMPT_TEMPLATE.upper() or \
           "most advanced" in SYSTEM_PROMPT_TEMPLATE.lower()


def test_loop_has_tradeoff_instruction():
    """loop.py must instruct Aria to name tradeoffs."""
    from sovereign_agent.loop import SYSTEM_PROMPT_TEMPLATE
    assert "tradeoff" in SYSTEM_PROMPT_TEMPLATE.lower() or "TRADEOFF" in SYSTEM_PROMPT_TEMPLATE


def test_loop_autonomy_has_thoroughness():
    """loop.py AUTONOMY section must include the thoroughness doctrine."""
    from sovereign_agent.loop import SYSTEM_PROMPT_TEMPLATE
    assert "THOROUGHNESS" in SYSTEM_PROMPT_TEMPLATE or "thoroughness" in SYSTEM_PROMPT_TEMPLATE.lower()
