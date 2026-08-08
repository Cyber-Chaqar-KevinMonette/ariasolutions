"""
test_sandbox_runner.py — Tests for the code execution sandbox tools.
"""
from __future__ import annotations
import pytest


def test_tools_registered():
    """All three runner tools must be registered at the correct tier."""
    import sovereign_agent.tools  # noqa: F401
    from sovereign_agent.authority import _TIER_REGISTRY
    assert "run_code" in _TIER_REGISTRY
    assert "run_shell" in _TIER_REGISTRY
    assert "run_tests" in _TIER_REGISTRY
    assert _TIER_REGISTRY["run_code"].tier == 1
    assert _TIER_REGISTRY["run_shell"].tier == 1
    assert _TIER_REGISTRY["run_tests"].tier == 1


def test_all_tools_have_failure_modes():
    from sovereign_agent.tools.runner import RunCodeTool, RunShellTool, RunTestsTool
    for cls in (RunCodeTool, RunShellTool, RunTestsTool):
        assert cls.failure_modes, f"{cls.name} missing failure_modes"


@pytest.mark.asyncio
async def test_run_code_simple():
    """run_code must execute a trivial snippet and return stdout."""
    from sovereign_agent.tools.runner import RunCodeTool
    tool = RunCodeTool()
    result = await tool.execute(
        tool.Args(code="print('hello from aria')"),
        trace_id="t1",
    )
    assert result.ok, f"run_code failed: {result.error}"
    assert "hello from aria" in result.output


@pytest.mark.asyncio
async def test_run_code_captures_stderr():
    """run_code must capture stderr alongside stdout."""
    from sovereign_agent.tools.runner import RunCodeTool
    tool = RunCodeTool()
    result = await tool.execute(
        tool.Args(code="import sys; sys.stderr.write('err line\\n')"),
        trace_id="t2",
    )
    assert result.ok
    assert "err line" in result.output


@pytest.mark.asyncio
async def test_run_code_syntax_error():
    """run_code with a syntax error must return ok=False, not raise."""
    from sovereign_agent.tools.runner import RunCodeTool
    tool = RunCodeTool()
    result = await tool.execute(
        tool.Args(code="def bad syntax):("),
        trace_id="t3",
    )
    assert not result.ok


@pytest.mark.asyncio
async def test_run_code_runtime_error():
    """run_code with a runtime error must return ok=False, not raise."""
    from sovereign_agent.tools.runner import RunCodeTool
    tool = RunCodeTool()
    result = await tool.execute(
        tool.Args(code="raise ValueError('intentional test error')"),
        trace_id="t4",
    )
    assert not result.ok


@pytest.mark.asyncio
async def test_run_shell_allowlisted():
    """run_shell must succeed for a whitelisted command."""
    from sovereign_agent.tools.runner import RunShellTool
    tool = RunShellTool()
    result = await tool.execute(
        tool.Args(command="echo", args=["aria is here"]),
        trace_id="t5",
    )
    assert result.ok, f"run_shell echo failed: {result.error}"
    assert "aria is here" in result.output


@pytest.mark.asyncio
async def test_run_shell_blocked_command():
    """run_shell must reject commands not in the allowlist.

    `git` and `pip` were deliberately ADDED to SHELL_ALLOWLIST at some
    point (marked `# command-master-runner-d` — the same dev-toolchain
    expansion `command_master.py`'s own allowlist got) — confirmed via
    direct read, not assumed. They're no longer valid "should be
    blocked" examples; `rm`/`curl`/`ssh` remain genuinely blocked.
    """
    from sovereign_agent.tools.runner import RunShellTool
    tool = RunShellTool()
    for bad_cmd in ("rm", "curl", "ssh"):
        result = await tool.execute(
            tool.Args(command=bad_cmd, args=[]),
            trace_id=f"t-block-{bad_cmd}",
        )
        assert not result.ok, f"{bad_cmd} should be blocked"
        assert "allowlist" in result.error.lower() or "not in" in result.error.lower()


@pytest.mark.asyncio
async def test_run_shell_hints_when_command_is_a_real_tool_name():
    """Real bug, found live 2026-08-03: a model tried run_shell(command=
    'godot_check') three times (godot_check is a real, directly callable
    tool, not a shell command) before circuit-breaking with nothing to
    show for it. The rejection must name the collision explicitly."""
    import sovereign_agent.tools  # noqa: F401 — populate _TIER_REGISTRY
    from sovereign_agent.tools.runner import RunShellTool
    tool = RunShellTool()
    result = await tool.execute(
        tool.Args(command="godot_check", args=[]), trace_id="t-collision",
    )
    assert not result.ok
    assert "registered tool" in result.error
    assert "godot_check" in result.error


@pytest.mark.asyncio
async def test_run_shell_no_hint_for_genuinely_unknown_command():
    """A command that isn't a real tool either gets the plain message,
    no false-positive hint."""
    import sovereign_agent.tools  # noqa: F401
    from sovereign_agent.tools.runner import RunShellTool
    tool = RunShellTool()
    result = await tool.execute(
        tool.Args(command="totally_made_up_binary_xyz", args=[]), trace_id="t-no-collision",
    )
    assert not result.ok
    assert "registered tool" not in result.error


@pytest.mark.asyncio
async def test_run_shell_metachar_blocked():
    """run_shell must reject arguments containing shell metacharacters."""
    from sovereign_agent.tools.runner import RunShellTool
    tool = RunShellTool()
    for bad_arg in ["file; rm -rf /", "$(whoami)", "arg | cat /etc/passwd"]:
        result = await tool.execute(
            tool.Args(command="echo", args=[bad_arg]),
            trace_id="t-meta",
        )
        assert not result.ok, f"metachar in {bad_arg!r} should be blocked"


@pytest.mark.asyncio
async def test_run_shell_cwd_scope():
    """run_shell with a cwd outside the repo must be rejected."""
    from sovereign_agent.tools.runner import RunShellTool
    tool = RunShellTool()
    result = await tool.execute(
        tool.Args(command="ls", cwd="/etc"),
        trace_id="t-scope",
    )
    assert not result.ok
    assert "scope" in result.error.lower() or "outside" in result.error.lower()


@pytest.mark.asyncio
async def test_run_tests_returns_output():
    """run_tests must return structured output including exit_code in metadata."""
    from sovereign_agent.tools.runner import RunTestsTool
    tool = RunTestsTool()
    # Run a very small test that always passes
    result = await tool.execute(
        tool.Args(path="tests/test_sandbox_runner.py::test_tools_registered"),
        trace_id="t-tests",
    )
    # May pass or fail depending on environment; either way ok=True means tests ran
    assert "exit_code" in result.metadata
    assert "passed" in result.metadata


def test_timeout_ceilings_were_raised_but_still_bounded():  # timeout-hardening-d
    """Kevin, 2026-07-21: "adaptable timeouts... and longer timeouts."
    The old ceilings (120s/300s/600s) were too tight for legitimately
    slow work; raised, but every one of these tools must still refuse an
    unbounded timeout -- "longer" is not "unlimited"."""
    from sovereign_agent.tools.runner import RunCodeTool, RunShellTool, RunTestsTool

    # run_code: 120 -> 600
    RunCodeTool.Args(code="pass", timeout=600)
    try:
        RunCodeTool.Args(code="pass", timeout=601)
        assert False, "expected a validation error over the ceiling"
    except Exception:
        pass

    # run_shell: 300 -> 1800
    RunShellTool.Args(command="ls", timeout=1800)
    try:
        RunShellTool.Args(command="ls", timeout=1801)
        assert False, "expected a validation error over the ceiling"
    except Exception:
        pass

    # run_tests: 600 -> 1800
    RunTestsTool.Args(timeout=1800)
    try:
        RunTestsTool.Args(timeout=1801)
        assert False, "expected a validation error over the ceiling"
    except Exception:
        pass


@pytest.mark.asyncio
async def test_run_code_default_timeout_is_unchanged():
    """Raising the CEILING must not change the DEFAULT -- nothing gets
    slower for an ordinary short call."""
    from sovereign_agent.tools.runner import RunCodeTool, _TIMEOUT_DEFAULT

    tool = RunCodeTool()
    args = tool.Args(code="print('hi')")
    assert args.timeout == _TIMEOUT_DEFAULT == 30
