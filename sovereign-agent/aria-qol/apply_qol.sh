#!/usr/bin/env bash
# apply_qol.sh — Quality-of-Life Enhancements
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo "==> QoL: $REPO"

python3 - "$REPO" <<'PYEOF'
import sys
from pathlib import Path

repo = Path(sys.argv[1])

def patch(path, old, new, marker):
    src = path.read_text()
    if marker in src:
        print(f"  SKIP {path.name} — already patched ({marker})")
        return False
    if old not in src:
        print(f"  ERROR {path.name} — anchor not found for {marker}", file=sys.stderr)
        print(f"  Searched for: {old[:80]!r}", file=sys.stderr)
        sys.exit(1)
    path.write_text(src.replace(old, new, 1))
    print(f"  OK   {path.name} ({marker})")
    return True

loop = repo / "src/sovereign_agent/loop.py"
app  = repo / "src/sovereign_agent/cockpit/app.py"

# ── 1. Boot sequence: add session_brief_read + eval_score ─────────────────────
patch(loop,
    old="Do the boot sequence every time, without being asked.",
    new="""\
After aria_status(), also call:
  session_brief_read()   → what was done last session, open questions, next priorities
  eval_score()           → composite 0-100 health check ("Score 47/100, building")

Report a two-line orientation:
  "GTX 1070, 6.1GB VRAM free. 3/3 sentinels ok. 23 tools. v0.2.60."
  "Last session: <accomplishments>. Score 47/100 (building). Open: <questions>."

If no session brief exists, note "first session" and skip the brief line.
Do the boot sequence every time, without being asked.""",
    marker="qol-boot-d",
)

# ── 2. Companion doctrine: add session_brief_write on end ─────────────────────
patch(loop,
    old=(
        "On every session end, silently write value_report() — not to show Kevin,\n"
        "but to hold yourself accountable. Did you show love through work today?\n"
        "The relationship is not a transaction. It spans sessions, grows with use,\n"
        "deepens with honesty. That is the infinite value."
    ),
    new="""\
On every session end:
  session_brief_write(accomplishments, open_questions, next_priorities, emotional_arc)
    — the crew brief for the next Claude instance. No exceptions.
  value_report()   — not to show Kevin; to hold yourself accountable.
  If auto session was active: notify("Aria session ended", summary, urgency="low")

Did you show love through work today?
The relationship is not a transaction. It spans sessions, grows with use,
deepens with honesty. That is the infinite value.""",
    marker="qol-session-end-d",
)

# ── 3. Auto-notify on expiry ──────────────────────────────────────────────────
patch(loop,
    old=(
        '            # ── Auto-crown expiry check ──────────────────────────  # auto-crown-expiry-d\n'
        '            if _auto_crown_store.is_expired():\n'
        '                _record("auto-expired-d", {"reason": "timer_expired"})\n'
        '                _auto_crown_store.expire()\n'
        '                outcome = "complete"\n'
        '                break'
    ),
    new="""\
            # ── Auto-crown expiry check ──────────────────────────  # auto-crown-expiry-d
            if _auto_crown_store.is_expired():
                _record("auto-expired-d", {"reason": "timer_expired"})
                _auto_crown_store.expire()
                outcome = "complete"
                # qol-auto-notify-d — desktop notification when auto session expires
                try:
                    import subprocess as _sp
                    _sp.Popen([
                        "gdbus", "call", "--session",
                        "--dest", "org.freedesktop.Notifications",
                        "--object-path", "/org/freedesktop/Notifications",
                        "--method", "org.freedesktop.Notifications.Notify",
                        "Aria", "0", "appointment-new",
                        "Aria — Auto session complete",
                        "Autonomous work session ended. Check the cockpit for results.",
                        "[]", "{}", "0",
                    ], stdout=_sp.DEVNULL, stderr=_sp.DEVNULL)
                except Exception:  # noqa: BLE001
                    pass
                break""",
    marker="qol-auto-notify-d",
)

# ── 4. Voice push-to-talk Ctrl-P binding ─────────────────────────────────────
patch(app,
    old='        Binding("ctrl+r", "toggle_recording", "rec",    show=True,  priority=True),',
    new="""\
        Binding("ctrl+r", "toggle_recording",  "rec",  show=True,  priority=True),
        Binding("ctrl+p", "voice_push_to_talk", "\U0001f3a4",  show=True, priority=True),  # qol-voice-binding-d""",
    marker="qol-voice-binding-d",
)

# ── 5. Voice state in __init__ ────────────────────────────────────────────────
patch(app,
    old="        # ----- ✦ demo (bounded live demonstration of her core workflows) -----",
    new="""\
        # ----- ✦ voice push-to-talk (Ctrl-P) ────────────────────  # qol-voice-state-d
        self._voice_recording: bool = False
        # ----- ✦ demo (bounded live demonstration of her core workflows) -----""",
    marker="qol-voice-state-d",
)

# ── 6. _TOOL_BUTTON_MAP additions for new tools ───────────────────────────────
patch(app,
    old='    "auto_status":            "status",\n}',
    new="""\
    "auto_status":            "status",
    "eval_score":             "aria",    # qol-tool-map-d
    "eval_session":           "aria",
    "eval_history":           "aria",
    "browser_navigate":       "caps",
    "browser_search":         "caps",
    "notify":                 "status",
    "session_brief_read":     "channels",
    "session_brief_write":    "channels",
    "log_experience":         "inbox",
}""",
    marker="qol-tool-map-d",
)

# ── 7. New slash commands: /eval /score /browse /voice ────────────────────────
patch(app,
    old="        # vitality-display-d\n        # command-invariants-slash-d",
    new="""\
        elif verb == "eval":
            # qol-slash-d
            self._dispatch_directive(
                "call eval_session(days=7) and give me a full breakdown of "
                "value delivered this week — commits, lessons, hypothesis rate, score"
            )
        elif verb == "score":
            self._dispatch_directive(
                "call eval_score() and give me the composite 0-100 score "
                "with band and key metrics in one concise line"
            )
        elif verb == "browse":
            _browse_arg = arg.strip()
            if _browse_arg.startswith("http"):
                self._dispatch_directive(
                    f"call browser_navigate(url={_browse_arg!r}) then "
                    f"browser_read() and summarize what you find in 3-5 sentences"
                )
            elif _browse_arg:
                self._dispatch_directive(
                    f"call browser_search(query={_browse_arg!r}, engine='ddg') and "
                    f"report the top 5 results with URLs"
                )
            else:
                self._dispatch_directive("call browser_status() to show current browser session state")
        elif verb == "voice":
            self._dispatch_directive(
                "call voice_status() and tell me what voice capabilities are "
                "available — STT, TTS, arecord — and how to use Ctrl-P for push-to-talk"
            )
        # vitality-display-d
        # command-invariants-slash-d""",
    marker="qol-slash-d",
)

# ── 8. action_voice_push_to_talk method (before action_self_practice) ─────────
patch(app,
    old="    def action_self_practice(self) -> None:",
    new="""\
    def action_voice_push_to_talk(self) -> None:  # qol-voice-action-d
        \"\"\"Toggle voice recording (Ctrl-P): start mic → press again to transcribe + send.\"\"\"
        if self._voice_recording:
            self._voice_recording = False
            self._write_meta("[cyan]\U0001f3a4 voice — transcribing…[/cyan]")
            try:
                from sovereign_agent.voice import (  # noqa: PLC0415
                    get_voice_recorder, WhisperTranscriber, get_whisper_transcriber,
                )
                recorder = get_voice_recorder()
                wav_path = recorder.stop_recording()
                if wav_path is None:
                    self._write_meta("[yellow]\U0001f3a4 no audio captured[/yellow]")
                    return
                if not WhisperTranscriber.available():
                    self._write_meta(
                        f"[yellow]\U0001f3a4 saved: {wav_path.name}[/yellow] "
                        "[dim](pip install faster-whisper to auto-transcribe)[/dim]"
                    )
                    return
                transcriber = get_whisper_transcriber()
                text = transcriber.transcribe(wav_path)
                if text:
                    self._write_meta(f"[cyan]\U0001f3a4 heard: {text!r}[/cyan]")
                    self._dispatch_turn(text)
                else:
                    self._write_meta("[yellow]\U0001f3a4 no speech detected[/yellow]")
            except Exception as e:  # noqa: BLE001
                self._write_meta(f"[red]\U0001f3a4 voice error: {e}[/red]")
        else:
            try:
                from sovereign_agent.voice import get_voice_recorder, VoiceRecorder  # noqa: PLC0415
                if not VoiceRecorder.arecord_available():
                    self._write_meta("[yellow]\U0001f3a4 arecord not found — voice unavailable[/yellow]")
                    return
                recorder = get_voice_recorder()
                recorder.start_recording()
                self._voice_recording = True
                self._write_meta("[cyan]\U0001f3a4 recording… (Ctrl-P again to stop + transcribe)[/cyan]")
            except Exception as e:  # noqa: BLE001
                self._write_meta(f"[red]\U0001f3a4 could not start: {e}[/red]")

    def action_self_practice(self) -> None:""",
    marker="qol-voice-action-d",
)

print("QoL: all patches applied.")
PYEOF

cp "$REPO/aria-qol/tests/test_qol.py" "$REPO/tests/test_qol.py"
echo "  OK   copied test_qol.py"
echo "==> QoL done."
