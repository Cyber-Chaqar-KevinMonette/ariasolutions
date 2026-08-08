"""Tests for tickets — the private ticket state machine."""
from __future__ import annotations

from sovereign_agent import tickets as tk


def test_open_assigns_readable_id_and_lists_open(tmp_path):
    t = tk.open_ticket(tmp_path, "111", "Alice", "support", "bot is down")
    assert t["id"] == "T0001" and t["status"] == tk.OPEN
    t2 = tk.open_ticket(tmp_path, "222", "Bob", "order", "where's my role")
    assert t2["id"] == "T0002"
    ids = [t["id"] for t in tk.list_open(tmp_path)]
    assert ids == ["T0001", "T0002"]


def test_bad_category_falls_back(tmp_path):
    t = tk.open_ticket(tmp_path, "1", "A", "nonsense", "hi")
    assert t["category"] == "other"


def test_full_lifecycle_open_claim_resolve_close(tmp_path):
    t = tk.open_ticket(tmp_path, "111", "Alice", "support", "help")
    ok, msg, t = tk.claim(tmp_path, "T0001", "900", "StaffSam")
    assert ok and t["status"] == tk.CLAIMED and t["claimed_name"] == "StaffSam"
    ok, _, t = tk.resolve(tmp_path, "T0001", "900", "StaffSam")
    assert ok and t["status"] == tk.RESOLVED
    ok, _, t = tk.close(tmp_path, "T0001", "900", "StaffSam")
    assert ok and t["status"] == tk.CLOSED
    # closing drops it from the open board
    assert tk.list_open(tmp_path) == []


def test_claim_conflict(tmp_path):
    tk.open_ticket(tmp_path, "111", "Alice", "support", "help")
    tk.claim(tmp_path, "T0001", "900", "Sam")
    ok, msg, _ = tk.claim(tmp_path, "T0001", "901", "Other")
    assert not ok and "already claimed" in msg.lower()
    # the same staffer re-claiming is fine (idempotent)
    ok2, _, _ = tk.claim(tmp_path, "T0001", "900", "Sam")
    assert ok2


def test_illegal_transition_blocked(tmp_path):
    tk.open_ticket(tmp_path, "111", "Alice", "support", "help")
    tk.close(tmp_path, "T0001", "900", "Sam")           # open→closed ok
    # closed can only reopen, not jump straight to resolved
    assert not tk.can_transition(tk.CLOSED, tk.RESOLVED)
    ok, _, _ = tk.resolve(tmp_path, "T0001", "900")
    assert not ok


def test_reopen_puts_it_back_on_the_board(tmp_path):
    tk.open_ticket(tmp_path, "111", "Alice", "support", "help")
    tk.close(tmp_path, "T0001", "900", "Sam")
    assert tk.list_open(tmp_path) == []
    ok, _, t = tk.reopen(tmp_path, "T0001", "111", "Alice")
    assert ok and t["status"] == tk.OPEN
    assert [x["id"] for x in tk.list_open(tmp_path)] == ["T0001"]


def test_list_for_user_and_board_and_events(tmp_path):
    tk.open_ticket(tmp_path, "111", "Alice", "support", "one")
    tk.open_ticket(tmp_path, "111", "Alice", "order", "two")
    tk.open_ticket(tmp_path, "222", "Bob", "billing", "three")
    assert len(tk.list_for_user(tmp_path, "111")) == 2
    board = tk.compose_board(tmp_path)
    assert "3 open" in board and "T0001" in board
    tk.claim(tmp_path, "T0001", "900", "Sam")
    t = tk.load(tmp_path, "T0001")
    actions = [e["action"] for e in t["events"]]
    assert "opened" in actions and "claimed" in actions   # audited
