"""Tests for reaction_roles.py — all pure-function, no discord.py mocking,
matching this repo's actual convention (tests/test_discord_admin.py's ~30
tests are almost entirely pure-helper tests, not gateway-object mocks)."""
from __future__ import annotations

import json

import pytest

from sovereign_agent import reaction_roles as rr


# ── bindings CRUD / storage ──────────────────────────────────────────────────


def test_add_binding_persists_and_round_trips(tmp_path):
    entry = rr.add_binding(
        tmp_path, "111", message_id="222", channel_id="333",
        emoji_key="😀", emoji_display="😀", role_id="444", created_by="555",
    )
    assert entry["binding_id"]
    bindings = rr.list_bindings(tmp_path, "111")
    assert len(bindings) == 1
    assert bindings[0]["message_id"] == "222"
    assert bindings[0]["role_id"] == "444"


def test_remove_binding_removes_only_that_one(tmp_path):
    a = rr.add_binding(tmp_path, "111", message_id="222", channel_id="333",
                        emoji_key="😀", emoji_display="😀", role_id="444", created_by="555")
    b = rr.add_binding(tmp_path, "111", message_id="222", channel_id="333",
                        emoji_key="🎮", emoji_display="🎮", role_id="666", created_by="555")
    assert rr.remove_binding(tmp_path, "111", a["binding_id"]) is True
    remaining = rr.list_bindings(tmp_path, "111")
    assert len(remaining) == 1
    assert remaining[0]["binding_id"] == b["binding_id"]


def test_remove_binding_unknown_id_returns_false(tmp_path):
    assert rr.remove_binding(tmp_path, "111", "not-a-real-id") is False


def test_find_binding_matches_message_and_emoji_key(tmp_path):
    rr.add_binding(tmp_path, "111", message_id="222", channel_id="333",
                    emoji_key="😀", emoji_display="😀", role_id="444", created_by="555")
    found = rr.find_binding(tmp_path, "111", "222", "😀")
    assert found is not None and found["role_id"] == "444"
    assert rr.find_binding(tmp_path, "111", "222", "🎮") is None
    assert rr.find_binding(tmp_path, "111", "999", "😀") is None


def test_bindings_for_message_filters_by_message_id(tmp_path):
    rr.add_binding(tmp_path, "111", message_id="222", channel_id="333",
                    emoji_key="😀", emoji_display="😀", role_id="444", created_by="555")
    rr.add_binding(tmp_path, "111", message_id="999", channel_id="333",
                    emoji_key="🎮", emoji_display="🎮", role_id="666", created_by="555")
    only_222 = rr.bindings_for_message(tmp_path, "111", "222")
    assert len(only_222) == 1 and only_222[0]["emoji_key"] == "😀"


def test_corrupt_bindings_file_returns_empty_list(tmp_path):
    path = rr.bindings_path(tmp_path, "111")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not valid json[[[", encoding="utf-8")
    assert rr.list_bindings(tmp_path, "111") == []


def test_missing_bindings_file_returns_empty_list(tmp_path):
    assert rr.list_bindings(tmp_path, "does-not-exist-guild") == []


def test_bindings_are_per_guild_scoped(tmp_path):
    """The actual proof this isn't hardcoded to one server: the same
    message/emoji in two different guilds stay fully independent."""
    rr.add_binding(tmp_path, "guild-a", message_id="222", channel_id="333",
                    emoji_key="😀", emoji_display="😀", role_id="444", created_by="555")
    rr.add_binding(tmp_path, "guild-b", message_id="222", channel_id="333",
                    emoji_key="😀", emoji_display="😀", role_id="999", created_by="555")
    a = rr.list_bindings(tmp_path, "guild-a")
    b = rr.list_bindings(tmp_path, "guild-b")
    assert len(a) == 1 and len(b) == 1
    assert a[0]["role_id"] == "444"
    assert b[0]["role_id"] == "999"
    # Removing guild-a's binding must not touch guild-b's.
    rr.remove_binding(tmp_path, "guild-a", a[0]["binding_id"])
    assert rr.list_bindings(tmp_path, "guild-a") == []
    assert len(rr.list_bindings(tmp_path, "guild-b")) == 1


def test_storage_is_atomic_write_json(tmp_path):
    rr.add_binding(tmp_path, "111", message_id="222", channel_id="333",
                    emoji_key="😀", emoji_display="😀", role_id="444", created_by="555")
    raw = json.loads(rr.bindings_path(tmp_path, "111").read_text(encoding="utf-8"))
    assert isinstance(raw, list) and len(raw) == 1


# ── emoji_key ─────────────────────────────────────────────────────────────


def test_emoji_key_distinguishes_custom_from_unicode():
    unicode_key = rr.emoji_key(None, "😀")
    custom_key = rr.emoji_key(999888777, "pepe")
    assert unicode_key == "😀"
    assert custom_key == "999888777"
    assert unicode_key != custom_key


def test_emoji_key_custom_ignores_name_uses_id():
    """A custom emoji's key must survive a rename (Discord admins can rename
    custom emoji without changing their id) — matched by id, not name."""
    assert rr.emoji_key(999888777, "old_name") == rr.emoji_key(999888777, "new_name")


# ── decide_reaction_role_action ──────────────────────────────────────────────


def test_decide_action_no_binding_is_noop():
    decision = rr.decide_reaction_role_action(None, "add", live=True)
    assert decision.action == "none"


def test_decide_action_dry_run_never_marks_applied():
    binding = {"role_id": "444"}
    decision = rr.decide_reaction_role_action(binding, "add", live=False)
    assert decision.action == "grant"
    assert decision.dry_run is True
    assert "would grant" in decision.message


def test_decide_action_live_grant_and_revoke():
    binding = {"role_id": "444"}
    grant = rr.decide_reaction_role_action(binding, "add", live=True)
    revoke = rr.decide_reaction_role_action(binding, "remove", live=True)
    assert grant.action == "grant" and grant.dry_run is False
    assert revoke.action == "revoke" and revoke.dry_run is False


# ── build_audit_entry ─────────────────────────────────────────────────────


def test_build_audit_entry_includes_guild_id():
    binding = {"role_id": "444"}
    decision = rr.decide_reaction_role_action(binding, "add", live=True)
    entry = rr.build_audit_entry(decision, "111", "555", "222", "444")
    assert entry["guild_id"] == "111"
    assert entry["action"] == "grant"
    assert entry["op"] == "reaction_role"


def test_validate_panel_options_rejects_empty():
    with pytest.raises(ValueError, match="at least one option"):
        rr.validate_panel_options([])


def test_validate_panel_options_rejects_duplicate():
    with pytest.raises(ValueError, match="duplicate"):
        rr.validate_panel_options(["😀", "🎮", "😀"])


def test_validate_panel_options_accepts_valid():
    rr.validate_panel_options(["😀", "🎮", "🎨"])  # no raise


def test_audit_entry_survives_real_audit_log(tmp_path):
    """Matches tests/test_discord_admin.py::test_audit_log_writes' style —
    confirm the entry shape actually works with the real audit_log()."""
    from sovereign_agent.discord_admin.bot import audit_log
    binding = {"role_id": "444"}
    decision = rr.decide_reaction_role_action(binding, "add", live=True)
    entry = rr.build_audit_entry(decision, "111", "555", "222", "444")
    path = tmp_path / "sub" / "audit.jsonl"
    audit_log(path, entry)
    rec = json.loads(path.read_text().splitlines()[0])
    assert rec["op"] == "reaction_role" and rec["guild_id"] == "111" and "ts" in rec
