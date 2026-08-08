"""Tests for member_mail — /ma, the direct line to Aria's inbox."""
from __future__ import annotations

from sovereign_agent.member_mail import (
    MA_DAILY_CAP,
    MA_MAX_CHARS,
    deliver_ma,
    is_eligible,
    take_quota,
)


def test_eligibility_matrix():
    owner = dict(author_id="42", owner_id="42", role_names=[])
    assert is_eligible(**owner)
    # subscribers, decorated or plain
    assert is_eligible(author_id="7", owner_id="42",
                       role_names=["🌟 Subscriber-VIP"])
    assert is_eligible(author_id="7", owner_id="42",
                       role_names=["Subscriber-Basic"])
    # staff (Kevin's future employees) — decorated too
    assert is_eligible(author_id="8", owner_id="42", role_names=["⭐ Support"])
    assert is_eligible(author_id="8", owner_id="42", role_names=["support"])
    # plain member / customer → not eligible
    assert not is_eligible(author_id="9", owner_id="42",
                           role_names=["Customer", "Veteran"])
    assert not is_eligible(author_id="9", owner_id="42", role_names=[])
    # empty owner_id never grants owner status by accident
    assert not is_eligible(author_id="", owner_id="", role_names=[])


def test_quota_caps_per_day_and_rolls_over(tmp_path):
    now = 1_784_000_000.0
    for _ in range(MA_DAILY_CAP):
        assert take_quota(tmp_path, "u1", now=now)
    assert not take_quota(tmp_path, "u1", now=now)          # cap spent
    assert take_quota(tmp_path, "u2", now=now)              # per-user
    assert take_quota(tmp_path, "u1", now=now + 86_400)     # next day resets


def test_quota_corrupt_file_resets_open_handed(tmp_path):
    (tmp_path / "member_mail").mkdir()
    (tmp_path / "member_mail" / "quota.json").write_text("{broken")
    assert take_quota(tmp_path, "u1", now=1000.0)


def test_deliver_lands_in_arias_inbox(tmp_path):
    db = tmp_path / "atoms.db"
    out = deliver_ma("Hey Aria, great work today!\nsecond line",
                     author_id="42", author_name="BigKev",
                     is_owner=True, db_path=db)
    assert "Delivered" in out
    from sovereign_agent.persistence.store import ErebloStore
    from sovereign_agent.workflow.requests import RequestStore
    notes = RequestStore(ErebloStore(db)).list_for_aria()
    assert len(notes) == 1
    assert "BigKev" in notes[0].title
    assert "Hey Aria" in notes[0].title          # first line in the title
    assert "second line" in notes[0].body
    assert notes[0].priority == "high"           # owner mail rides high


def test_deliver_member_is_normal_priority_and_capped(tmp_path):
    db = tmp_path / "atoms.db"
    out = deliver_ma("x" * (MA_MAX_CHARS + 500), author_id="7",
                     author_name="fan", is_owner=False, db_path=db)
    assert "Delivered" in out
    from sovereign_agent.persistence.store import ErebloStore
    from sovereign_agent.workflow.requests import RequestStore
    note = RequestStore(ErebloStore(db)).list_for_aria()[0]
    assert note.priority == "normal"
    assert len(note.body) < MA_MAX_CHARS + 200   # capped, not the raw 2300


def test_deliver_empty_and_store_failure_never_raise(tmp_path):
    assert "nothing to deliver" in deliver_ma(
        "   ", author_id="7", db_path=tmp_path / "db")
    # a directory where the db file should be → store blows up → soft fail
    bad = tmp_path / "bad.db"
    bad.mkdir()
    out = deliver_ma("hello", author_id="7", db_path=bad)
    assert "couldn't reach" in out
