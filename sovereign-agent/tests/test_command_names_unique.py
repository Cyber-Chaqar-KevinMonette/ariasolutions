"""Every slash command name must be unique.

collision-d (2026-08-03): `/buy` and `/leaderboard` were each defined twice.
discord.py raises CommandAlreadyRegistered inside `on_ready`, which aborts
the ENTIRE tree sync — so one duplicate silently un-registers every command
in the bot. It looks fine from the outside: the process is up, the gateway
is connected, and nothing works. Both were only found by reading the live
journal after a restart.

This is a source-level check on purpose. Importing the module doesn't
register anything (the decorators live inside `run_admin_bot`), and running
the real bot needs a token and a network, so parsing is what can actually
run in CI.
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

BOT = Path(__file__).resolve().parents[1] / "src/sovereign_agent/discord_admin/bot.py"
_DECL = re.compile(r'@tree\.command\(\s*\n?\s*name="([a-z0-9_-]+)"')


def test_no_duplicate_slash_command_declarations():
    names = _DECL.findall(BOT.read_text(encoding="utf-8"))
    assert names, "found no @tree.command declarations — regex is stale"
    dupes = sorted(n for n, c in Counter(names).items() if c > 1)
    assert not dupes, (
        f"duplicate slash command name(s): {dupes}. discord.py raises "
        f"CommandAlreadyRegistered in on_ready and NO command registers.")


def test_no_duplicate_entries_in_the_help_registry():
    from sovereign_agent.discord_admin.bot import COMMANDS
    names = [c[0] for c in COMMANDS]
    dupes = sorted(n for n, c in Counter(names).items() if c > 1)
    assert not dupes, f"duplicate COMMANDS entries: {dupes}"


def test_declared_commands_appear_in_the_help_registry():
    """A command nobody can discover may as well not exist."""
    from sovereign_agent.discord_admin.bot import COMMANDS
    declared = set(_DECL.findall(BOT.read_text(encoding="utf-8")))
    listed = {c[0].lstrip("/") for c in COMMANDS}
    missing = sorted(declared - listed)
    assert not missing, f"declared but not in COMMANDS (undiscoverable): {missing}"


def test_no_command_description_exceeds_discord_limit():
    """Discord rejects descriptions over 100 chars with error 50035 — and it
    rejects the WHOLE payload, so one long description silently blocks every
    command from registering. `clear-all-channels` sat at 108 chars and no
    new command registered for as long as it did; the bot looked healthy the
    entire time because the sync failure was swallowed."""
    src = BOT.read_text(encoding="utf-8")
    # Only descriptions inside an @tree.command(...) decorator count. An
    # embed's description= is unrelated and may be any length — scoping this
    # matters, because a false positive here would train someone to ignore
    # the very test that catches a real sync-breaker.
    decl = re.compile(r"@tree\.command\((.*?)\)\s*\n\s*(?:@|async def)",
                      re.DOTALL)
    lit = re.compile(r'"((?:[^"\\]|\\.)*)"')
    field = re.compile(r'description=((?:\s*"(?:[^"\\]|\\.)*")+)', re.DOTALL)
    too_long = []
    for block in decl.findall(src):
        m = field.search(block)
        if not m:
            continue
        text = "".join(lit.findall(m.group(1)))
        if len(text) > 100:
            too_long.append((len(text), text[:70]))
    assert not too_long, (
        "command description(s) over Discord's 100-char limit: "
        + "; ".join(f"{n} chars: {s!r}" for n, s in too_long))
