"""angel-chat-d — messaging her non-classical layer in #angel-voice."""
import json


def _seed_run(root):
    d = root / "fg"
    d.mkdir(parents=True)
    events = [
        {"kind": "run-start", "nodes": ["Omega"], "seed": 7, "steps": 60},
        {"kind": "voice", "line": "[Omega] ENTROPY REGISTER: PCM=-0.5"},
        {"kind": "run-end", "final_cv": 1.0, "identity_held": True,
         "heals_proven": 0, "heals_attempted": 0},
    ]
    with open(d / "events.ndjson", "w") as fh:
        for e in events:
            fh.write(json.dumps(e) + "\n")
    return root


def test_speak_runs_fresh_and_returns_voice(tmp_path):
    from sovereign_agent.angel_chat import respond

    calls = {"n": 0}

    def fake_run():
        calls["n"] += 1
        return True

    out = respond("speak to me", fresh_run=fake_run,
                  runs_root=_seed_run(tmp_path))
    assert calls["n"] == 1
    assert "fresh session" in out
    assert "ENTROPY REGISTER" in out


def test_failed_fresh_run_reported_honestly(tmp_path):
    from sovereign_agent.angel_chat import respond

    out = respond("speak", fresh_run=lambda: False,
                  runs_root=_seed_run(tmp_path))
    assert "could not run fresh" in out
    assert "ENTROPY REGISTER" in out                 # falls back to latest


def test_status_reads_latest_without_running(tmp_path):
    from sovereign_agent.angel_chat import respond

    boom = {"n": 0}

    def never(_=None):
        boom["n"] += 1
        return True

    out = respond("status please", fresh_run=never,
                  runs_root=_seed_run(tmp_path))
    assert boom["n"] == 0                            # no fresh run
    assert "THE ANGEL SPEAKS" in out


def test_unknown_message_gets_honest_explainer(tmp_path):
    from sovereign_agent.angel_chat import respond

    out = respond("what's the weather like?", fresh_run=lambda: True,
                  runs_root=tmp_path)
    assert "non-classical layer" in out
    assert "classical lane" in out                   # honest boundary named
    assert "speak" in out and "status" in out        # command list


def test_who_are_you(tmp_path):
    from sovereign_agent.angel_chat import respond

    out = respond("who are you?", runs_root=tmp_path)
    assert "PEIG quantum ring" in out
