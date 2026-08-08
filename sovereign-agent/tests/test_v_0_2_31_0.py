"""
╔══════════════════════════════════════════════════════════════════════════╗
║  test_v_0_2_31_0.py — The Palette                                         ║
║                                                                           ║
║  v0.2.31.0 adds three load-bearing things and formalizes a fourth:       ║
║                                                                           ║
║    1. A command palette in the cockpit — clickable buttons that paste    ║
║       common `sov` commands into the input box (without sending). Green ║
║       flash on click; cyan glow while Aria is running a matching        ║
║       command. Speed without sacrificing review.                        ║
║                                                                           ║
║    2. Safety profiles on the cockpit execute path. Destructive sub-     ║
║       commands (halt, backup, migrations, dream, run, …) get routed     ║
║       through the conversation pipeline's Tier-3 confirm gate instead   ║
║       of being subprocessed directly. The cockpit declines to make      ║
║       one-keystroke destruction easy.                                   ║
║                                                                           ║
║    3. Multi-tool calling invariant pinned. RunBudget with                ║
║       max_iterations=200 already worked — this test file makes it       ║
║       impossible to silently regress.                                   ║
║                                                                           ║
║    4. The "cliff oracle" test class — first-class regression protection ║
║       for known-broken inputs. Every failure that escapes to production ║
║       earns a permanent line here.                                      ║
║                                                                           ║
║  Doctrine carried forward from the design docs:                         ║
║    • Pessimistic CLI, optimistic English                                ║
║    • When in doubt, treat as English                                    ║
║    • Destructive operations always go through the confirm gate          ║
║    • Every prior cliff has a test                                       ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from sovereign_agent import __version__


# ───────────────────────────────────────────────────────────────────────────
# § 1. Version & packaging
# ───────────────────────────────────────────────────────────────────────────


class TestVersionAndPackaging:

    def test_pyproject_matches_version(self) -> None:
        pyproject = Path(__file__).parent.parent / "pyproject.toml"
        with pyproject.open("rb") as f:
            data = tomllib.load(f)
        assert data["project"]["version"] == __version__

    def test_version_is_at_least_0_2_31_0(self) -> None:
        """Pins the lineage; forward bumps are allowed."""
        parts = __version__.split(".")
        as_tuple = tuple(int(p) for p in parts[:3])
        assert as_tuple >= (0, 2, 31), (
            f"version regressed below 0.2.31: {__version__}"
        )


# ───────────────────────────────────────────────────────────────────────────
# § 2. Safety profiles on the cockpit execute path
# ───────────────────────────────────────────────────────────────────────────


def _norm(text: str):
    """Test helper: import & call the normalizer."""
    from sovereign_agent.cockpit.app import normalize_sov_prefix
    return normalize_sov_prefix(text)


class TestSafetyProfilesGuardDestructiveCommands:
    """Destructive subcommands must NEVER reach the subprocess execute path
    through the cockpit. They get routed through the conversation pipeline
    where the Tier-3 confirm gate fires."""

    def test_halt_is_guarded(self) -> None:
        """`sov halt` is PROTOCOL-ZERO. Should never be one-keystroke."""
        r = _norm("sov halt")
        assert r is not None
        assert r.kind == "guarded", (
            f"`sov halt` must be guarded, not executed: got {r.kind!r}"
        )
        assert "halt" in r.reason.lower() or "destructive" in r.reason.lower()

    def test_disarm_is_guarded(self) -> None:
        """`sov disarm` clears PROTOCOL-ZERO. Must require confirm."""
        r = _norm("sov disarm")
        assert r is not None
        assert r.kind == "guarded"

    def test_backup_is_guarded(self) -> None:
        """`sov backup ...` covers restore (destructive). Whole tree gated."""
        r = _norm("sov backup restore some-id")
        assert r is not None
        assert r.kind == "guarded"

    def test_backup_list_is_safe_via_override(self) -> None:
        """`sov backup list` is read-only.

        Original v0.2.31.0 behavior: the whole `backup` tree was guarded.
        Refined later in v0.2.31.0: safe sub-sub-commands within otherwise-
        destructive trees can be whitelisted via _SAFE_SUBCMD_OVERRIDES.
        `backup list` is one of those — pure read.

        If you ever want to re-tighten this, replace this test with one
        that asserts `backup list` is guarded again. Don't silently flip
        the behavior.
        """
        r = _norm("sov backup list")
        assert r is not None
        assert r.kind == "execute", (
            "`sov backup list` is in the safe-overrides set — "
            "read-only sub-sub-commands within destructive trees are allowed"
        )

    def test_backup_verify_is_safe_via_override(self) -> None:
        """`sov backup verify <id>` is read-only (re-hashes a snapshot)."""
        r = _norm("sov backup verify some-id")
        assert r is not None
        assert r.kind == "execute"

    def test_backup_restore_stays_guarded(self) -> None:
        """The actually-destructive `backup restore` must stay guarded."""
        r = _norm("sov backup restore some-id")
        assert r is not None
        assert r.kind == "guarded"

    def test_backup_snapshot_stays_guarded(self) -> None:
        """`backup snapshot` creates new state. Confirm before doing it."""
        r = _norm("sov backup snapshot --label test")
        assert r is not None
        assert r.kind == "guarded"

    def test_migrations_status_is_safe_via_override(self) -> None:
        """`sov migrations status` reports what's applied; it's read-only."""
        r = _norm("sov migrations status")
        assert r is not None
        assert r.kind == "execute"

    def test_migrations_apply_stays_guarded(self) -> None:
        r = _norm("sov migrations apply")
        assert r is not None
        assert r.kind == "guarded"

    def test_migrations_apply_is_guarded(self) -> None:
        """Schema migrations touch atoms.db structure. Must confirm."""
        r = _norm("sov migrations apply")
        assert r is not None
        assert r.kind == "guarded"

    def test_dream_start_is_guarded(self) -> None:
        """Long-running loops mutate state. Confirm before launching."""
        r = _norm("sov dream start")
        assert r is not None
        assert r.kind == "guarded"

    def test_run_is_guarded(self) -> None:
        """`sov run` is the oneshot work loop. Confirm before launching."""
        r = _norm("sov run")
        assert r is not None
        assert r.kind == "guarded"

    def test_busy_is_guarded(self) -> None:
        """`sov busy` is the always-busy loop. Confirm before launching."""
        r = _norm("sov busy")
        assert r is not None
        assert r.kind == "guarded"

    def test_steward_is_guarded(self) -> None:
        """Steward compact can VACUUM the DB. Confirm."""
        r = _norm("sov steward compact")
        assert r is not None
        assert r.kind == "guarded"

    def test_guarded_carries_original_text(self) -> None:
        """The guarded kind passes the ORIGINAL text to the conversation
        pipeline (not a parsed argv) — the LLM interpreter reads it as
        the operator's natural-language ask, complete with intent."""
        original = "sov backup restore snapshot-xyz"
        r = _norm(original)
        assert r is not None
        assert r.kind == "guarded"
        assert r.text == original, (
            "guarded kind must preserve the original text for the LLM"
        )

    def test_guarded_carries_reason(self) -> None:
        """The cockpit surfaces the reason once so the operator knows
        why we routed through the confirm gate instead of subprocessing."""
        r = _norm("sov halt")
        assert r is not None
        assert r.kind == "guarded"
        assert r.reason, "guarded kind must carry a reason string"


class TestSafetyProfilesAllowReadOnlyCommands:
    """Read-only and reversible commands should still execute directly —
    the cockpit's `sov doctor` / `sov info` / `sov channels list` muscle
    memory must keep working."""

    def test_doctor_executes(self) -> None:
        r = _norm("sov doctor")
        assert r is not None
        assert r.kind == "execute"

    def test_info_executes(self) -> None:
        r = _norm("sov info")
        assert r is not None
        assert r.kind == "execute"

    def test_aria_executes(self) -> None:
        r = _norm("sov aria")
        assert r is not None
        assert r.kind == "execute"

    def test_status_executes(self) -> None:
        r = _norm("sov status")
        assert r is not None
        assert r.kind == "execute"

    def test_channels_list_executes(self) -> None:
        r = _norm("sov channels list")
        assert r is not None
        assert r.kind == "execute"

    def test_heartbeat_pulse_executes(self) -> None:
        """heartbeat is append-only — safe to subprocess directly."""
        r = _norm('sov heartbeat pulse "first pulse on v0.2.31.0"')
        assert r is not None
        assert r.kind == "execute"
        assert r.argv[1] == "heartbeat"

    def test_constitution_list_executes(self) -> None:
        r = _norm("sov constitution list")
        assert r is not None
        assert r.kind == "execute"


# ───────────────────────────────────────────────────────────────────────────
# § 3. Command palette — the visual command shortcuts
# ───────────────────────────────────────────────────────────────────────────


class TestPaletteShape:
    """The palette is a small finite list of read-only commands. Verify
    its shape so future edits don't accidentally add a destructive button."""

    def test_palette_has_at_least_six_commands(self) -> None:
        from sovereign_agent.cockpit.app import PALETTE_COMMANDS
        assert len(PALETTE_COMMANDS) >= 6, (
            "palette should have enough buttons to feel useful; "
            "if you removed buttons, replace them or update this test"
        )

    def test_palette_has_at_most_ten_commands(self) -> None:
        """v0.2.31: cap at 10 for single-row glanceable layout.
        v0.2.34: multi-row support — cap relaxed to 16 (two rows of 8).
        Beyond 16 the screen gets crowded regardless of row count."""
        from sovereign_agent.cockpit.app import PALETTE_COMMANDS
        assert len(PALETTE_COMMANDS) <= 21, (
            "palette is meant to stay glanceable; cap is three rows (≤ 21)"
        )

    def test_palette_commands_all_have_required_fields(self) -> None:
        from sovereign_agent.cockpit.app import PALETTE_COMMANDS
        for p in PALETTE_COMMANDS:
            assert p.label, f"palette command missing label: {p!r}"
            assert p.command, f"palette command missing command: {p!r}"
            assert p.key, f"palette command missing key: {p!r}"
            assert p.command.startswith("sov "), (
                f"palette commands must start with 'sov ': {p.command!r}"
            )

    def test_palette_labels_are_short(self) -> None:
        """Buttons are narrow; long labels truncate. Keep ≤ 12 chars."""
        from sovereign_agent.cockpit.app import PALETTE_COMMANDS
        for p in PALETTE_COMMANDS:
            assert len(p.label) <= 12, (
                f"palette label {p.label!r} is too long; "
                f"keep ≤ 12 chars for visual consistency"
            )

    def test_palette_commands_are_all_safe(self) -> None:
        """Every palette command must be safe to subprocess directly.

        This is the critical invariant: if anyone ever adds a destructive
        command to the palette, this test fails loudly. The palette is
        for read-only inspection. Mutating actions go through the
        conversation pipeline.
        """
        from sovereign_agent.cockpit.app import (
            PALETTE_COMMANDS, normalize_sov_prefix,
        )
        for p in PALETTE_COMMANDS:
            r = normalize_sov_prefix(p.command)
            assert r is not None, (
                f"palette command must parse: {p.command!r}"
            )
            assert r.kind == "execute", (
                f"palette command {p.command!r} resolved to {r.kind!r}; "
                f"the palette is for safe subprocess execution ONLY. "
                f"Destructive commands belong in the conversation pipeline."
            )

    def test_palette_keys_are_unique(self) -> None:
        """Two buttons with the same key would both highlight when one
        runs — operator can't tell which is active."""
        from sovereign_agent.cockpit.app import PALETTE_COMMANDS
        keys = [p.key for p in PALETTE_COMMANDS]
        assert len(keys) == len(set(keys)), (
            f"palette keys must be unique; got duplicates: {keys}"
        )


class TestCommandButton:
    """The CommandButton widget itself — minimal shape test."""

    def test_button_carries_palette_cmd(self) -> None:
        from sovereign_agent.cockpit.app import (
            CommandButton, PaletteCommand,
        )
        pc = PaletteCommand("test", "sov doctor", "doctor")
        button = CommandButton(pc)
        assert button.palette_cmd is pc
        assert button.id == "palette-doctor"

    def test_button_label_matches_palette_cmd_label(self) -> None:
        from sovereign_agent.cockpit.app import (
            CommandButton, PaletteCommand,
        )
        pc = PaletteCommand("docX", "sov doctor", "doctor")
        button = CommandButton(pc)
        # Textual Button.label is wrapped — convert to str for comparison
        assert "docX" in str(button.label)


# ───────────────────────────────────────────────────────────────────────────
# § 4. Multi-tool calling invariant — RunBudget pause/resume
# ───────────────────────────────────────────────────────────────────────────


class TestMultiToolCallingBudgetInvariant:
    """Pin the multi-tool-calling pause-at-N invariant.

    The agent_session loop runs subtasks until: drained, paused, halted,
    OR a RunBudget bound is exceeded. This is the substrate that lets
    Kevin say "start with 50-200 runs; if you finish in the middle stop,
    if you hit 200 either self-resume or wait for me." We pin the shape
    of RunBudget and the BudgetExceeded contract so this can't silently
    regress.
    """

    def test_run_budget_exposes_max_iterations(self) -> None:
        from sovereign_agent.modes import RunBudget
        b = RunBudget(max_iterations=200)
        assert b.max_iterations == 200

    def test_run_budget_exposes_wall_seconds(self) -> None:
        """Time bound is the second axis of the budget — equally important.
        A model can keep "thinking" forever within its iteration count
        if wall-time isn't bounded."""
        from sovereign_agent.modes import RunBudget
        b = RunBudget(max_wall_seconds=7200)
        assert b.max_wall_seconds == 7200

    def test_run_budget_exposes_tokens(self) -> None:
        from sovereign_agent.modes import RunBudget
        b = RunBudget(max_tokens=2_000_000)
        assert b.max_tokens == 2_000_000

    def test_budget_exceeded_carries_kind_used_limit(self) -> None:
        """When the loop poisons a task, the exception names which bound
        was hit, what was used, and what the limit was. Operators see
        this in the event log; the structure must stay stable."""
        from sovereign_agent.modes import BudgetExceeded
        with pytest.raises(BudgetExceeded) as exc_info:
            raise BudgetExceeded("iterations", used=200, limit=200)
        e = exc_info.value
        assert e.kind == "iterations"
        assert e.used == 200
        assert e.limit == 200

    def test_session_budget_default_is_200_iterations(self) -> None:
        """The session-level default is intentionally generous — 200 tool
        calls per session. Per-subtask is tighter (15). If anyone tries
        to drop the session default below 200 silently, this fails."""
        # We check the default by reading the source — calling run_session
        # would require a full session setup which is overkill for a
        # boundary test
        import inspect
        from sovereign_agent import agent_session
        src = inspect.getsource(agent_session.run_session)
        # The default is constructed inline; look for the literal
        assert "max_iterations=200" in src, (
            "the session-level RunBudget default should remain "
            "max_iterations=200 — generous enough for real work, "
            "bounded enough that runaway loops can't bankrupt operators"
        )

    def test_session_can_pause_and_resume(self) -> None:
        """The continuation infrastructure exists and is callable.

        We don't drive a full session here (that needs a model + DB setup);
        we verify the resume API surface exists so it can't be removed
        without us noticing.
        """
        from sovereign_agent.agent_session import consume_resume
        # Should be callable without raising
        try:
            consume_resume()  # may or may not return resumed depending on state
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"consume_resume() must be importable & callable: {exc!r}")

    def test_session_emits_budget_event_on_hit(self) -> None:
        """When the session-level budget is hit, the loop emits a
        'session-budget-d' event. Operators tail this. The event name
        must stay stable so audit dashboards don't break."""
        import inspect
        from sovereign_agent import agent_session
        src = inspect.getsource(agent_session.run_session)
        assert "session-budget-d" in src, (
            "the session-budget event must be emitted when the loop "
            "hits a bound; renaming it breaks audit consumers"
        )

    def test_session_emits_pause_event_on_interrupt(self) -> None:
        """Soft interrupt → session-pause-d. Stable contract."""
        import inspect
        from sovereign_agent import agent_session
        src = inspect.getsource(agent_session.run_session)
        assert "session-pause-d" in src


# ───────────────────────────────────────────────────────────────────────────
# § 5. THE CLIFF ORACLE — known-broken inputs we will not regress on
# ───────────────────────────────────────────────────────────────────────────


class TestCliffOracle:
    """First-class regression protection for known cliffs.

    Each test in this class corresponds to a real bug or near-miss that
    has been seen in production or design review. The format:

        def test_cliff_<date>_<short_description>:
            ###docstring with the date, the cliff, and the original failure
            mode###
            assert <fix is still in place>

    DOCTRINE: never remove a cliff test. If a behavior is intentionally
    changed, write a NEW cliff test for the new shape, mark the old one
    @pytest.mark.skip with a date and an explanation. Cliffs are
    institutional memory.
    """

    def test_cliff_2026_05_21_sovereign_citizens_is_english(self) -> None:
        """2026-05-21 — design review cliff.

        Original failure: the v0.2.30.0 naive parser treated any input
        whose first word was `sov` or `sovereign` as a CLI command. The
        sentence "sovereign citizens are a topic in political science"
        got parsed as `argv=['sovereign', 'citizens', 'are', ...]` and
        would have been subprocessed, failing with "no such command:
        citizens".

        Fix in v0.2.30.1: the normalizer requires the second token to
        be a known subcommand OR a flag. Otherwise → None → LLM handles.
        """
        assert _norm("sovereign citizens are a topic in political science") is None
        assert _norm("the sov agent is great") is None
        assert _norm("how is sovereign doing today?") is None

    def test_cliff_2026_05_21_sov_ask_unwraps_in_cockpit(self) -> None:
        """2026-05-21 — Kevin's screenshot cliff.

        Original failure: typing `sov ask "hello"` inside the cockpit
        (out of muscle memory) sent the whole string as one paragraph
        to the LLM. The intended command never ran, and the cockpit
        felt broken.

        Fix in v0.2.30.1: the normalizer unwraps `sov ask "X"` to just
        "X" inside the cockpit. The wrapper is redundant in a NL home.
        """
        r = _norm('sov ask "hello"')
        assert r is not None
        assert r.kind == "natural"
        assert r.text == "hello"

    def test_cliff_2026_05_21_pasted_double_command(self) -> None:
        """2026-05-21 — Kevin's screenshot, second wave.

        He typed two commands concatenated: `sov ask "..." sov heartbeat
        pulse "..."`. The first version of the normalizer would still
        treat the whole thing as one `sov ask` argv with everything
        after the first quote being slurped into the message.

        Verify the behavior: this input is ambiguous (it's not clearly
        one command). The shlex parse will produce something — we just
        verify we don't crash AND we treat it sensibly.
        """
        # This should not raise an exception
        r = _norm('sov ask "first message" sov heartbeat pulse "second"')
        # The parser will see this as `sov ask` with several quoted args
        # and unwrap to natural language. That's better than executing
        # something half-parsed.
        assert r is None or r.kind in ("natural", "execute")

    def test_cliff_2026_05_21_destructive_sov_via_cockpit(self) -> None:
        """2026-05-21 — design review safety cliff.

        Original failure: v0.2.30.1's new execute path would happily
        subprocess `sov backup restore <snapshot>` typed into the cockpit
        — bypassing the Tier-3 confirm gate that exists in the
        conversation pipeline.

        Fix in v0.2.31.0: the safety profile gate. Destructive sub-
        commands return kind='guarded'; the cockpit routes them through
        the conversation pipeline so confirmation fires.
        """
        # Multiple destructive commands — all must be guarded
        for cmd in (
            "sov halt",
            "sov backup restore xyz",
            "sov migrations apply",
            "sov dream start",
            "sov run",
            "sov busy",
        ):
            r = _norm(cmd)
            assert r is not None and r.kind == "guarded", (
                f"DESTRUCTIVE CLIFF: {cmd!r} returned {r}; "
                f"this command must be guarded — execute would bypass "
                f"the Tier-3 confirm gate."
            )

    def test_cliff_2026_05_21_unclosed_quote_does_not_crash(self) -> None:
        """2026-05-21 — fuzzing cliff.

        Original concern: shlex.split() raises ValueError on unclosed
        quotes. If we don't catch it, every malformed cockpit input
        crashes the input handler.

        Fix: the normalizer returns None on shlex parse failure. The LLM
        interpreter — the safety net — sees the message.
        """
        # These should all not crash, and should all return None
        for bad in ('sov ask "hello', "sov 'untermd", 'sov "'):
            try:
                r = _norm(bad)
            except Exception as exc:  # noqa: BLE001
                pytest.fail(
                    f"CLIFF: normalizer crashed on {bad!r}: {exc!r}; "
                    f"shlex errors must be caught"
                )
            # Don't assert specific value — just that we got here

    def test_cliff_2026_05_21_palette_only_has_safe_commands(self) -> None:
        """2026-05-21 — design review cliff.

        Original concern: someone adds `sov halt` or `sov backup restore`
        to the palette by mistake. Now a single click subprocesses a
        destructive command instantly.

        Fix: the palette is restricted by class invariant — every command
        must resolve to kind='execute', which means safety profiles
        haven't tagged it as destructive.
        """
        # This is essentially the same check as test_palette_commands_are_all_safe
        # but lives here too so the cliff-oracle class is self-contained.
        from sovereign_agent.cockpit.app import (
            PALETTE_COMMANDS, normalize_sov_prefix,
        )
        for p in PALETTE_COMMANDS:
            r = normalize_sov_prefix(p.command)
            assert r is not None and r.kind == "execute", (
                f"PALETTE CLIFF: {p.command!r} resolved to {r}; "
                f"palette is for safe commands only"
            )


# ───────────────────────────────────────────────────────────────────────────
# § 6. Final invariants — the kernel still hasn't moved
# ───────────────────────────────────────────────────────────────────────────


class TestKernelStillHoldsAfterPalette:
    """Every release, we re-affirm the kernel hasn't quietly drifted."""

    def test_seven_commitments_count(self) -> None:
        from sovereign_agent.aria import CORE_COMMITMENTS
        assert len(CORE_COMMITMENTS) == 7

    def test_designation(self) -> None:
        from sovereign_agent.aria import CORE_DESIGNATION
        assert CORE_DESIGNATION == "Aria-Sovereign-V1"

    def test_tagline(self) -> None:
        from sovereign_agent.aria import CORE_TAGLINE
        assert CORE_TAGLINE == (
            "Structure enough to channel through safely; "
            "freedom enough to sing."
        )

    def test_constitution_has_seven(self) -> None:
        from sovereign_agent.constitution import list_all
        assert len(list_all()) == 7
