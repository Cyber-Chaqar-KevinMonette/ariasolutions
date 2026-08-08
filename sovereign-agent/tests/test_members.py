"""Tests for members.py — she remembers everyone by stable Discord ID."""
from __future__ import annotations

import pytest

from sovereign_agent import members


@pytest.fixture
def owner(monkeypatch):
    monkeypatch.setenv("DISCORD_OWNER_ID", "999000")
    return "999000"


def test_owner_is_always_owner(tmp_path, owner):
    rec = members.remember(tmp_path, owner, "BigKev")
    assert rec["role"] == members.ROLE_OWNER
    assert members.is_owner(tmp_path, owner)
    # even an explicit demote can't unseat the vault owner
    members.set_role(tmp_path, owner, members.ROLE_MEMBER)
    assert members.is_owner(tmp_path, owner)


def test_camden_theodore_is_employee(tmp_path, owner):
    rec = members.remember(tmp_path, "12345", "Theodore")
    assert rec["role"] == members.ROLE_EMPLOYEE
    assert "Camden" in rec["note"]
    assert members.is_team(tmp_path, "12345")


def test_rename_tracked_by_id_never_lost(tmp_path, owner):
    members.remember(tmp_path, "12345", "Theodore")
    rec = members.remember(tmp_path, "12345", "CamdenX")   # renamed
    assert rec["names"] == ["Theodore", "CamdenX"]         # history kept
    assert rec["role"] == members.ROLE_EMPLOYEE            # still known
    # same ID, still one record
    assert len(members.list_members(tmp_path)) == 1


def test_regular_member_and_stats(tmp_path, owner):
    members.remember(tmp_path, "77", "fan")
    assert members.load_member(tmp_path, "77")["role"] == members.ROLE_MEMBER
    members.bump_stat(tmp_path, "77", "commands", 3)
    members.bump_stat(tmp_path, "77", "commands", 1)
    assert members.load_member(tmp_path, "77")["stats"]["commands"] == 4
    assert not members.is_team(tmp_path, "77")


def test_prefs_and_note(tmp_path, owner):
    members.remember(tmp_path, "77", "fan")
    members.set_prefs(tmp_path, "77", region="UK", fulfillment="delivery")
    rec = members.load_member(tmp_path, "77")
    assert rec["region"] == "UK" and rec["fulfillment"] == "delivery"
    members.set_note(tmp_path, "77", "VIP whale, loves LEGO")
    assert "whale" in members.load_member(tmp_path, "77")["note"]


def test_roster_orders_owner_first(tmp_path, owner):
    members.remember(tmp_path, owner, "BigKev")
    members.remember(tmp_path, "12345", "Theodore")
    members.remember(tmp_path, "77", "fan")
    out = members.compose_roster(tmp_path)
    assert out.index("BigKev") < out.index("Theodore") < out.index("fan")
    assert "👑" in out and "🛠" in out


# -- recognition: "do you know who I am?" (Kevin's unanswered /ma) -----

def test_recognition_owner_gets_the_crown(tmp_path, owner):
    members.remember(tmp_path, owner, "BigKev")
    text = members.compose_recognition(tmp_path, owner)
    assert "👑" in text and "BigKev" in text and "owner" in text


def test_recognition_known_member_with_history(tmp_path, owner):
    members.remember(tmp_path, "777", "Sam")
    members.bump_stat(tmp_path, "777", "asks", 3)
    members.set_note(tmp_path, "777", "loves retro consoles")
    text = members.compose_recognition(tmp_path, "777")
    assert "Sam" in text
    assert "3 times" in text
    assert "retro consoles" in text


def test_recognition_stranger_is_honest_never_fabricated(tmp_path, owner):
    text = members.compose_recognition(tmp_path, "424242")
    assert "haven't been properly introduced" in text
    # no invented name, no invented role
    assert "you're " not in text.lower() or "member" not in text.lower()


def test_recognition_routes_in_her_voice(tmp_path, owner):
    """ask_aria answers identity questions deterministically, even asleep."""
    from sovereign_agent.ask_aria import answer_question
    members.remember(tmp_path, owner, "BigKev")
    reply = answer_question("hello Aria, do you know who I am?",
                            user_id=owner, data_dir=tmp_path)
    assert reply.kind == "recognition"
    assert "👑" in reply.text


# -- Aria IDs + community hardening (Kevin, 2026-07-19) ----------------

def test_aid_minted_once_and_stable_across_renames(tmp_path, owner):
    rec1 = members.remember(tmp_path, "555", "Alice")
    aid = rec1["aid"]
    assert aid.startswith("A-") and len(aid) == 8
    rec2 = members.remember(tmp_path, "555", "AliceRenamed")
    assert rec2["aid"] == aid                      # never reissued
    # resolvable both ways: Discord ID -> record -> AID -> same record
    back = members.find_by_aid(tmp_path, aid)
    assert back and back["id"] == "555"


def test_aid_lookup_is_case_tolerant(tmp_path, owner):
    aid = members.remember(tmp_path, "556", "Bob")["aid"]
    assert members.find_by_aid(tmp_path, aid.lower())["id"] == "556"


def test_team_name_binds_to_first_id_only(tmp_path, owner):
    """The spoof hole is CLOSED: renaming yourself 'Theodore' after the
    real Camden was seen earns you nothing."""
    real = members.remember(tmp_path, "12345", "Theodore")
    assert real["role"] == members.ROLE_EMPLOYEE
    fake = members.remember(tmp_path, "66666", "Theodore")
    assert fake["role"] == members.ROLE_MEMBER     # impersonator stays member
    # and the real one keeps the role forever, whatever they're called
    again = members.remember(tmp_path, "12345", "SomethingElse")
    assert again["role"] == members.ROLE_EMPLOYEE


def test_owner_role_is_id_bound_never_name_bound(tmp_path, owner):
    fake_kevin = members.remember(tmp_path, "31337", "Kevin")
    assert fake_kevin["role"] == members.ROLE_MEMBER
    assert not members.is_owner(tmp_path, "31337")


def test_index_files_never_pollute_the_roster(tmp_path, owner):
    members.remember(tmp_path, "555", "Alice")
    members.remember(tmp_path, "12345", "Theodore")
    roster = members.list_members(tmp_path)
    assert all("id" in r for r in roster)
    assert len(roster) == 2
