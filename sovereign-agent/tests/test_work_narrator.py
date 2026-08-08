"""F5 — the live shift narration to #owner-bridge."""
from __future__ import annotations

from sovereign_agent import work_narrator


class _Result:
    def __init__(self, sent):
        self.sent = sent


def _fresh(monkeypatch, sends: list):
    monkeypatch.setattr(work_narrator, "_state", {"last_post": 0.0, "pending": ""})

    class _Delivery:
        def __init__(self, env, live=False):
            self.env = env

        def send(self, text, username=""):
            sends.append((self.env, text, username))
            return _Result(True)

    import sovereign_agent.discord_runtime.delivery as d
    monkeypatch.setattr(d, "WebhookDelivery", _Delivery)


def test_narrates_and_throttles(monkeypatch):
    sends: list = []
    _fresh(monkeypatch, sends)
    assert work_narrator.narrate("line one", now=1000.0) is True
    # inside the 60s gap: held as pending, not sent
    assert work_narrator.narrate("line two", now=1030.0) is False
    assert len(sends) == 1
    # after the gap: pending + new line ship together
    assert work_narrator.narrate("line three", now=1070.0) is True
    assert "line two" in sends[-1][1] and "line three" in sends[-1][1]


def test_prefers_owner_bridge_when_minted(monkeypatch):
    sends: list = []
    _fresh(monkeypatch, sends)
    monkeypatch.setenv("DISCORD_OWNER_WEBHOOK_URL", "https://discord/hook")
    work_narrator.narrate("hello", now=1000.0)
    assert sends[0][0] == "DISCORD_OWNER_WEBHOOK_URL"
    assert sends[0][2] == "Aria — at the cockpit"


def test_falls_back_to_control(monkeypatch):
    sends: list = []
    _fresh(monkeypatch, sends)
    monkeypatch.delenv("DISCORD_OWNER_WEBHOOK_URL", raising=False)
    work_narrator.narrate("hello", now=1000.0)
    assert sends[0][0] == "DISCORD_WEBHOOK_URL"


def test_never_raises_even_when_delivery_explodes(monkeypatch):
    monkeypatch.setattr(work_narrator, "_state", {"last_post": 0.0, "pending": ""})

    class _Boom:
        def __init__(self, *a, **k):
            raise RuntimeError("no network")

    import sovereign_agent.discord_runtime.delivery as d
    monkeypatch.setattr(d, "WebhookDelivery", _Boom)
    assert work_narrator.narrate("x", now=1000.0) is False   # silent, honest


def test_subtask_line_shape(monkeypatch):
    sends: list = []
    _fresh(monkeypatch, sends)
    ok = work_narrator.narrate_subtask("sess_abcdef123456", 3, 16,
                                       "ranked the impact list", now=1000.0)
    assert ok
    assert "3/16" in sends[0][1]
    assert "ranked the impact list" in sends[0][1]
    assert "sess_abcdef1" in sends[0][1]


# ── full-observability-d: narrate the PLAN, not just the result ─────────────
# Kevin, 2026-07-26: "I want her to be upfront about everything she plans
# to do, is doing, and wants to do."


def test_narrate_intent_line_shape(monkeypatch):
    sends: list = []
    _fresh(monkeypatch, sends)
    ok = work_narrator.narrate_intent("sess_abcdef123456",
                                      "read the config and rank the impact list",
                                      now=1000.0)
    assert ok
    assert "read the config and rank the impact list" in sends[0][1]
    assert "sess_abcdef1" in sends[0][1]
    assert "starting" in sends[0][1]


def test_narrate_intent_falls_back_to_a_generic_line_when_blank(monkeypatch):
    sends: list = []
    _fresh(monkeypatch, sends)
    ok = work_narrator.narrate_intent("sess_abcdef123456", "", now=1000.0)
    assert ok
    assert "a subtask" in sends[0][1]


def test_narrate_intent_shares_the_same_throttle_as_narrate_subtask(monkeypatch):
    """Both draw from the same underlying narrate() — an intent line and
    a completion line moments apart must coalesce, never double-post."""
    sends: list = []
    _fresh(monkeypatch, sends)
    assert work_narrator.narrate_intent("sess_1", "step one", now=1000.0) is True
    assert work_narrator.narrate_subtask("sess_1", 1, 2, "step one done",
                                         now=1010.0) is False
    assert len(sends) == 1


def test_blueprint_carries_the_command_category():
    from sovereign_agent.discord_admin.blueprint import shop_blueprint
    bp = shop_blueprint()
    cats = {c.name: c for c in bp.categories}
    assert "COMMAND" in cats
    cmd = cats["COMMAND"]
    assert cmd.private is True
    chans = {ch.name: ch for ch in cmd.channels}
    assert set(chans) == {"owner-bridge", "angel-voice", "staff-room"}
    assert "Staff" in chans["owner-bridge"].hide_from     # owner+Aria only
    assert "Staff" in chans["angel-voice"].hide_from      # owner+Aria only
    assert "Staff" in cmd.allow_roles                     # staff sees the room


def test_owner_bridge_webhook_spec_registered():
    from sovereign_agent.discord_admin.webhook_provision import WEBHOOK_SPECS
    names = {s.channel: s.env_name for s in WEBHOOK_SPECS}
    assert names.get("owner-bridge") == "DISCORD_OWNER_WEBHOOK_URL"


def test_owner_bridge_webhook_is_cataloged_and_probed():
    """owner-bridge-catalog-d (Kevin, 2026-07-25): "she used to send me
    updates... she stopped." This webhook existed in three call sites but
    was never in CRED_CATALOG — invisible to /keys AND never covered by
    sov keys check's automatic webhook-liveness probing."""
    from sovereign_agent.credentials import CRED_CATALOG
    names = {c.name for c in CRED_CATALOG}
    assert "DISCORD_OWNER_WEBHOOK_URL" in names


def test_a_failed_send_emits_an_observable_event(monkeypatch):
    """Before this, a dead/unset webhook failed with ZERO trace anywhere —
    exactly how a stale URL could go silently quiet indefinitely."""
    monkeypatch.setattr(work_narrator, "_state", {"last_post": 0.0, "pending": ""})

    class _Delivery:
        def __init__(self, env, live=False):
            pass

        def send(self, text, username=""):
            return _Result(False)  # never actually sent

    import sovereign_agent.discord_runtime.delivery as d
    monkeypatch.setattr(d, "WebhookDelivery", _Delivery)

    emitted = []
    monkeypatch.setattr(
        "sovereign_agent.events.emit_event",
        lambda flag, **kw: emitted.append((flag, kw)))

    assert work_narrator.narrate("hello", now=1000.0) is False
    assert emitted and emitted[0][0] == "work-narrate-x"


def test_an_exception_during_send_also_emits_an_observable_event(monkeypatch):
    monkeypatch.setattr(work_narrator, "_state", {"last_post": 0.0, "pending": ""})

    class _Boom:
        def __init__(self, *a, **k):
            raise RuntimeError("no network")

    import sovereign_agent.discord_runtime.delivery as d
    monkeypatch.setattr(d, "WebhookDelivery", _Boom)

    emitted = []
    monkeypatch.setattr(
        "sovereign_agent.events.emit_event",
        lambda flag, **kw: emitted.append((flag, kw)))

    assert work_narrator.narrate("x", now=1000.0) is False
    assert emitted and "RuntimeError" in emitted[0][1]["payload"]["detail"]
