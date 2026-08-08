"""Tests for attention.py — the observable attention queue + Kevin's policy."""
from __future__ import annotations

from sovereign_agent.attention import (
    ENTRY_TTL_S,
    LANE_BOT,
    LANE_CUSTOMER,
    LANE_KEVIN,
    AttentionQueue,
)


def test_priority_order_bots_then_customers_then_kevin(tmp_path):
    q = AttentionQueue(tmp_path)
    k = q.enqueue(LANE_KEVIN, "kevin: refactor", now=100.0)      # first to arrive
    c = q.enqueue(LANE_CUSTOMER, "customer u42", now=101.0)
    b = q.enqueue(LANE_BOT, "restock delivery", now=102.0)       # last to arrive
    snap = q.snapshot(now=103.0)
    assert [e.lane for e in snap] == [LANE_BOT, LANE_CUSTOMER, LANE_KEVIN]
    # positions are observable: the bot is #1 despite arriving last;
    # the customer outranks Kevin despite Kevin arriving first
    assert q.position(b, now=103.0) == 1
    assert q.position(c, now=103.0) == 2
    assert q.position(k, now=103.0) == 3


def test_fifo_within_a_lane(tmp_path):
    q = AttentionQueue(tmp_path)
    c1 = q.enqueue(LANE_CUSTOMER, "customer one", now=100.0)
    c2 = q.enqueue(LANE_CUSTOMER, "customer two", now=101.0)
    assert q.position(c1, now=102.0) == 1 and q.position(c2, now=102.0) == 2


def test_done_removes_and_positions_shift(tmp_path):
    q = AttentionQueue(tmp_path)
    c1 = q.enqueue(LANE_CUSTOMER, "one", now=100.0)
    c2 = q.enqueue(LANE_CUSTOMER, "two", now=101.0)
    q.done(c1, now=102.0)
    assert q.position(c1, now=102.0) is None
    assert q.position(c2, now=102.0) == 1


def test_stale_entries_sweep_crash_safe(tmp_path):
    q = AttentionQueue(tmp_path)
    dead = q.enqueue(LANE_CUSTOMER, "crashed holder", now=100.0)
    live = q.enqueue(LANE_CUSTOMER, "alive", now=100.0 + ENTRY_TTL_S + 5)
    assert q.position(dead, now=100.0 + ENTRY_TTL_S + 6) is None   # swept
    assert q.position(live, now=100.0 + ENTRY_TTL_S + 6) == 1


def test_eta_and_render(tmp_path):
    q = AttentionQueue(tmp_path)
    q.enqueue(LANE_BOT, "delivery", now=100.0)
    c = q.enqueue(LANE_CUSTOMER, "customer u1", now=101.0)
    assert q.eta_s(c, now=102.0) == 15.0                # one ahead
    out = q.render(now=102.0)
    assert "🎯" in out and "delivery" in out and "customer u1" in out
    q2 = AttentionQueue(tmp_path / "fresh")
    assert "empty" in q2.render(now=100.0)


def test_cross_process_visibility(tmp_path):
    """Two independent instances (≈ two processes) see the same line."""
    a = AttentionQueue(tmp_path)
    b = AttentionQueue(tmp_path)
    t = a.enqueue(LANE_CUSTOMER, "from process A", now=100.0)
    assert b.position(t, now=101.0) == 1
    b.done(t, now=102.0)
    assert a.position(t, now=103.0) is None


def test_corrupt_queue_file_recovers(tmp_path):
    q = AttentionQueue(tmp_path)
    q._path.parent.mkdir(parents=True, exist_ok=True)
    q._path.write_text("{torn", encoding="utf-8")
    assert q.snapshot(now=100.0) == []
    t = q.enqueue(LANE_CUSTOMER, "recovered", now=100.0)
    assert q.position(t, now=101.0) == 1


def test_ask_aria_reports_queue_position(tmp_path):
    """A customer waiting behind others sees their number, not a shrug."""
    from sovereign_agent.ask_aria import AskLimiter, answer_question
    from sovereign_agent.attention import LANE_BOT, AttentionQueue
    from sovereign_agent.presence import touch_heartbeat
    touch_heartbeat(tmp_path, now=1000.0)
    # two bot-immediate deliveries already hold the line
    q = AttentionQueue(tmp_path)
    q.enqueue(LANE_BOT, "delivery a", now=999.0)
    q.enqueue(LANE_BOT, "delivery b", now=999.5)
    # LLM cap exhausted → fallback path must include the position note
    lim = AskLimiter(user_cooldown_s=0.0, global_per_minute=0)
    r = answer_question("freeform question", user_id="u1", data_dir=tmp_path,
                        limiter=lim, llm_fn=lambda *a: "hi", now=1000.0)
    assert r.kind == "limited" and "#3" in r.text       # visible place in line
    # and her ticket was released (no wedged queue)
    assert len(q.snapshot(now=1000.5)) == 2


def test_attention_rows_in_timers(tmp_path):
    from sovereign_agent.timers import gather_timers
    q = AttentionQueue(tmp_path)
    q.enqueue(LANE_CUSTOMER, "customer u7", now=1000.0)
    rows = gather_timers(tmp_path, now=1001.0)
    att = [r for r in rows if r.kind == "attention"]
    assert len(att) == 1 and "customer u7" in att[0].name


def test_concurrent_enqueues_never_lose_entries(tmp_path):
    """Hardening: the cross-process lock means racing writers can't clobber
    each other's entries (bot process + cockpit share this file)."""
    import threading
    q = AttentionQueue(tmp_path)
    ids: list[str] = []
    lock = threading.Lock()

    def worker(i: int) -> None:
        t = q.enqueue(LANE_CUSTOMER, f"c{i}", now=1000.0 + i / 100)
        with lock:
            ids.append(t)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    snap = q.snapshot(now=1001.0)
    assert len(snap) == 12 and len({e.entry_id for e in snap}) == 12
    # and done() under the same lock removes exactly one
    q.done(ids[0], now=1001.0)
    assert len(q.snapshot(now=1001.0)) == 11
