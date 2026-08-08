"""UI smoke for the Key Vault screen + chat-bridge routing."""
from __future__ import annotations

import pytest

from sovereign_agent.credentials import read_env


@pytest.fixture()
def vault(tmp_path, monkeypatch):
    p = tmp_path / "vault.env"
    monkeypatch.setenv("ARIA_KEYS_FILE", str(p))
    return p


@pytest.mark.asyncio
async def test_vault_opens_saves_masked_and_clears_field(vault):
    from textual.widgets import Button, Input, Select

    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import CredentialsScreen

    async with CockpitApp().run_test(size=(120, 60)) as pilot:
        app = pilot.app
        app.action_key_vault()
        await pilot.pause()
        assert isinstance(app.screen, CredentialsScreen)
        # the value input is a masked password field
        value = app.screen.query_one("#kv-value", Input)
        assert value.password is True
        # pick the owner-id key, type a value, save
        app.screen.query_one("#kv-which", Select).value = "DISCORD_OWNER_ID"
        value.value = "123456789012345678"
        await pilot.click(app.screen.query_one("#kv-save-btn", Button))
        await pilot.pause()
        # stored on disk...
        assert read_env(vault)["DISCORD_OWNER_ID"] == "123456789012345678"
        # ...and the input field was cleared (no secret left on screen)
        assert value.value == ""


@pytest.mark.asyncio
async def test_vault_remove_selected(vault):
    from textual.widgets import Button, Select

    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import CredentialsScreen
    from sovereign_agent.credentials import set_secret

    set_secret("DISCORD_GUILD_ID", "999", vault)
    async with CockpitApp().run_test(size=(120, 60)) as pilot:
        app = pilot.app
        app.action_key_vault()
        await pilot.pause()
        assert isinstance(app.screen, CredentialsScreen)
        app.screen.query_one("#kv-which", Select).value = "DISCORD_GUILD_ID"
        btn = app.screen.query_one("#kv-remove-btn", Button)
        btn.scroll_visible(animate=False)
        await pilot.pause()
        await pilot.click(btn)
        await pilot.pause()
        assert "DISCORD_GUILD_ID" not in read_env(vault)


@pytest.mark.asyncio
async def test_credentials_chat_bridge_masked(vault):
    from sovereign_agent.conversation import converse
    from sovereign_agent.credentials import set_secret

    secret = "MTA1234567890abcdefghijklmnopqrstuvwxyz1234567890ABCD"
    set_secret("DISCORD_BOT_TOKEN", secret, vault)
    t = await converse("which keys are missing?", allow_llm=False)
    assert t.result.kind == "credentials"
    msg = (t.result.messages or [""])[0]
    assert secret not in msg               # NEVER the value
    assert "missing" in msg                # honest about the gaps


# ── 📋 paste from clipboard (Kevin's ask: no obvious way to paste a key) ─────
def test_read_clipboard_tries_tools_in_order():
    from sovereign_agent.cockpit.clipboard import read_clipboard

    class P:
        def __init__(self, rc, out=b""):
            self.returncode = rc
            self.stdout = out

    # first tool (wl-paste) works
    text, detail = read_clipboard(runner=lambda cmd: P(0, b"my-secret-token"))
    assert text == "my-secret-token" and "wl-paste" in detail

    # wl-paste missing, xclip delivers
    def runner(cmd):
        if cmd[0] == "wl-paste":
            raise FileNotFoundError
        return P(0, b"from-xclip\n")
    text, detail = read_clipboard(runner=runner)
    assert text == "from-xclip\n" and "xclip" in detail

    # nothing works → None + every attempt named (so the fix is obvious)
    def none_work(cmd):
        raise FileNotFoundError
    text, detail = read_clipboard(runner=none_work)
    assert text is None
    for tool in ("wl-paste", "xclip", "xsel"):
        assert tool in detail


def test_read_clipboard_empty_clipboard_is_honest():
    from sovereign_agent.cockpit.clipboard import read_clipboard

    class P:
        returncode = 0
        stdout = b"   \n"
    text, detail = read_clipboard(runner=lambda cmd: P())
    assert text is None and "empty" in detail


@pytest.mark.asyncio
async def test_paste_button_fills_masked_field_and_saves(vault):
    from textual.widgets import Button, Input, Select

    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import CredentialsScreen

    async with CockpitApp().run_test(size=(120, 60)) as pilot:
        app = pilot.app
        app.action_key_vault()
        await pilot.pause()
        assert isinstance(app.screen, CredentialsScreen)
        app.screen.query_one("#kv-which", Select).value = "DISCORD_OWNER_ID"
        # the button exists below the fold — drive the handler with an
        # injected reader (no real clipboard in CI)
        btn = app.screen.query_one("#kv-paste-btn", Button)
        assert "paste" in str(btn.label).lower()
        app.screen._paste_from_clipboard(
            reader=lambda: ("  987654321098765432\n", "via wl-paste"))
        await pilot.pause()
        value = app.screen.query_one("#kv-value", Input)
        assert value.value == "987654321098765432"     # whitespace stripped
        assert value.password is True                  # still masked
        await pilot.click(app.screen.query_one("#kv-save-btn", Button))
        await pilot.pause()
        assert read_env(vault)["DISCORD_OWNER_ID"] == "987654321098765432"


@pytest.mark.asyncio
async def test_ctrl_v_pastes_like_the_button(vault, monkeypatch):
    # ctrl-v-paste-d (Kevin's ask): plain Ctrl+V in the vault screen runs
    # the same clipboard path as the 📋 button.
    from textual.widgets import Input

    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import CredentialsScreen

    async with CockpitApp().run_test(size=(120, 60)) as pilot:
        app = pilot.app
        app.action_key_vault()
        await pilot.pause()
        assert isinstance(app.screen, CredentialsScreen)
        import sovereign_agent.cockpit.clipboard as clip
        monkeypatch.setattr(clip, "read_clipboard",
                            lambda: ("rk_live_fromctrlv", "via wl-paste"))
        await pilot.press("ctrl+v")
        await pilot.pause()
        value = app.screen.query_one("#kv-value", Input)
        assert value.value == "rk_live_fromctrlv"
        assert value.password is True                  # still masked


@pytest.mark.asyncio
async def test_rotate_button_arms_the_fresh_paste(vault):
    # rotate-keys-d (Kevin's ask): 🔄 gives the exact per-key rotation
    # path, clears the value field, and focuses it for the new secret.
    from textual.widgets import Button, Input, Select, Static

    from sovereign_agent.cockpit import CockpitApp
    from sovereign_agent.cockpit.app import CredentialsScreen

    async with CockpitApp().run_test(size=(120, 60)) as pilot:
        app = pilot.app
        app.action_key_vault()
        await pilot.pause()
        assert isinstance(app.screen, CredentialsScreen)
        scr = app.screen
        assert scr.query_one("#kv-rotate-btn", Button)
        # a secret key → dashboard guidance + cleared field
        scr.query_one("#kv-which", Select).value = "STRIPE_SECRET_KEY"
        await pilot.pause()          # let the select-change info refresh land
        scr.query_one("#kv-value", Input).value = "old-secret"
        scr._rotate_guide()
        assert scr.query_one("#kv-value", Input).value == ""
        info = str(scr.query_one("#kv-info", Static).render())
        assert "Roll key" in info and "keys check" in info
        # webhooks → she can re-mint them herself
        scr.query_one("#kv-which", Select).value = "DISCORD_SHOP_WEBHOOK_URL"
        await pilot.pause()
        scr._rotate_guide()
        assert "/setup-webhooks" in str(scr.query_one("#kv-info", Static).render())
        # IDs/switches → honestly nothing to rotate
        toasts: list[str] = []
        scr._toast = toasts.append
        scr.query_one("#kv-which", Select).value = "DISCORD_OWNER_ID"
        await pilot.pause()
        scr._rotate_guide()
        assert toasts and "nothing to rotate" in toasts[-1]


@pytest.mark.asyncio
async def test_paste_button_failure_explains_the_fix(vault):
    from sovereign_agent.cockpit import CockpitApp

    async with CockpitApp().run_test(size=(120, 60)) as pilot:
        app = pilot.app
        app.action_key_vault()
        await pilot.pause()
        toasts: list[str] = []
        app.screen._toast = toasts.append
        app.screen._paste_from_clipboard(
            reader=lambda: (None, "wl-paste: not installed"))
        await pilot.pause()
        assert toasts and "Ctrl+Shift+V" in toasts[0] \
            and "wl-clipboard" in toasts[0]
