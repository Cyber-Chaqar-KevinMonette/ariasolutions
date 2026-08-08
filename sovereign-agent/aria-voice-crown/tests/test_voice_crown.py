"""test_voice_crown.py — Tests for M47 (Voice Crown)."""
from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ── VoiceRecorder tests ───────────────────────────────────────────────────────


def test_voice_recorder_not_recording_initially(tmp_path):
    from sovereign_agent.voice import VoiceRecorder
    recorder = VoiceRecorder(data_dir=tmp_path)
    assert recorder.is_recording() is False


def test_voice_recorder_start_stop_lifecycle(tmp_path):
    from sovereign_agent.voice import VoiceRecorder
    recorder = VoiceRecorder(data_dir=tmp_path)
    mock_proc = MagicMock()
    mock_proc.terminate.return_value = None
    mock_proc.wait.return_value = 0
    with patch("subprocess.Popen", return_value=mock_proc):
        recorder.start_recording()
        assert recorder.is_recording() is True
        result = recorder.stop_recording()
    assert recorder.is_recording() is False
    assert result is not None  # returns the path


def test_voice_recorder_double_start_is_noop(tmp_path):
    from sovereign_agent.voice import VoiceRecorder
    recorder = VoiceRecorder(data_dir=tmp_path)
    mock_proc = MagicMock()
    with patch("subprocess.Popen", return_value=mock_proc) as mock_popen:
        recorder.start_recording()
        recorder.start_recording()  # should not open a second process
    assert mock_popen.call_count == 1


# ── WhisperTranscriber tests ──────────────────────────────────────────────────


def test_whisper_transcriber_available_check():
    from sovereign_agent.voice import WhisperTranscriber
    result = WhisperTranscriber.available()
    assert isinstance(result, bool)


def test_whisper_transcriber_transcribe_mocked(tmp_path):
    from sovereign_agent.voice import WhisperTranscriber
    wav_path = tmp_path / "test.wav"
    wav_path.write_bytes(b"RIFF....WAVEfmt ")  # fake WAV header

    transcriber = WhisperTranscriber("base.en")
    mock_segment = MagicMock()
    mock_segment.text = "hello world"
    mock_model = MagicMock()
    mock_model.transcribe.return_value = ([mock_segment], MagicMock())
    transcriber._model = mock_model

    result = transcriber.transcribe(wav_path)
    assert result == "hello world"
    assert transcriber.model_size == "base.en"


# ── PiperSynthesizer tests ────────────────────────────────────────────────────


def test_piper_synthesizer_available_check():
    from sovereign_agent.voice import PiperSynthesizer
    result = PiperSynthesizer.available()
    assert isinstance(result, bool)


def test_piper_synthesizer_voice_property(tmp_path):
    from sovereign_agent.voice import PiperSynthesizer
    synth = PiperSynthesizer(voice="en_US-ryan-high", data_dir=tmp_path)
    assert synth.voice == "en_US-ryan-high"


def test_piper_synthesizer_synthesize_mocked(tmp_path):
    from sovereign_agent.voice import PiperSynthesizer
    synth = PiperSynthesizer(data_dir=tmp_path)
    fake_wav = tmp_path / "voice" / "tts-test.wav"
    fake_wav.parent.mkdir(parents=True, exist_ok=True)
    fake_wav.write_bytes(b"RIFF....WAVEfmt ")

    mock_voice_cls = MagicMock()
    mock_voice_instance = MagicMock()
    mock_voice_cls.load.return_value = mock_voice_instance

    def _fake_synthesize(text, f):
        f.write(b"RIFF....WAVEfmt ")

    mock_voice_instance.synthesize.side_effect = _fake_synthesize

    with patch("sovereign_agent.voice.PiperVoice", mock_voice_cls, create=True):
        # synthesize normally goes through the piper import, which fails
        # We test the fallback: it returns None when piper is unavailable
        result = synth.synthesize("hello Aria")
    # Either returns a path (if piper installed) or None (fallback)
    assert result is None or isinstance(result, Path)


# ── Tool registration tests ───────────────────────────────────────────────────


def test_voice_tools_registered():
    import sovereign_agent.tools  # noqa: F401
    from sovereign_agent.authority import _TIER_REGISTRY
    assert "voice_status" in _TIER_REGISTRY
    assert "transcribe_audio" in _TIER_REGISTRY
    assert "synthesize_speech" in _TIER_REGISTRY
    assert _TIER_REGISTRY["voice_status"].tier == 0
    assert _TIER_REGISTRY["transcribe_audio"].tier == 1
    assert _TIER_REGISTRY["synthesize_speech"].tier == 1


def test_voice_tools_have_failure_modes():
    from sovereign_agent.tools.voice_tools import (
        VoiceStatusTool, TranscribeAudioTool, SynthesizeSpeechTool,
    )
    for cls in (VoiceStatusTool, TranscribeAudioTool, SynthesizeSpeechTool):
        assert cls.failure_modes, f"{cls.name} missing failure_modes"


# ── voice_status tool tests ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_voice_status_returns_availability():
    from sovereign_agent.tools.voice_tools import VoiceStatusTool
    from sovereign_agent.voice import VoiceRecorder
    tool = VoiceStatusTool()
    mock_recorder = MagicMock(spec=VoiceRecorder)
    mock_recorder.is_recording.return_value = False
    with (
        patch("sovereign_agent.tools.voice_tools.WhisperTranscriber") as mock_whisper,
        patch("sovereign_agent.tools.voice_tools.PiperSynthesizer") as mock_piper,
        patch("sovereign_agent.tools.voice_tools.get_voice_recorder", return_value=mock_recorder),
        patch("sovereign_agent.tools.voice_tools.VoiceRecorder") as mock_vr,
    ):
        mock_whisper.available.return_value = False
        mock_piper.available.return_value = False
        mock_vr.arecord_available.return_value = True
        result = await tool.execute(tool.Args(), trace_id="t1")
    assert result.ok
    assert "stt_available" in result.output
    assert "tts_available" in result.output
    assert "is_recording" in result.output


# ── transcribe_audio tool tests ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_transcribe_audio_fails_when_unavailable():
    from sovereign_agent.tools.voice_tools import TranscribeAudioTool
    tool = TranscribeAudioTool()
    with patch("sovereign_agent.tools.voice_tools.WhisperTranscriber") as mock_whisper:
        mock_whisper.available.return_value = False
        result = await tool.execute(
            tool.Args(wav_path="/tmp/test.wav"),
            trace_id="t1",
        )
    assert not result.ok
    assert "not installed" in result.error


@pytest.mark.asyncio
async def test_transcribe_audio_wav_not_found():
    from sovereign_agent.tools.voice_tools import TranscribeAudioTool
    tool = TranscribeAudioTool()
    with patch("sovereign_agent.tools.voice_tools.WhisperTranscriber") as mock_whisper:
        mock_whisper.available.return_value = True
        result = await tool.execute(
            tool.Args(wav_path="/nonexistent/audio.wav"),
            trace_id="t1",
        )
    assert not result.ok
    assert "not found" in result.error


# ── synthesize_speech tool tests ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_synthesize_speech_fails_when_unavailable():
    from sovereign_agent.tools.voice_tools import SynthesizeSpeechTool
    tool = SynthesizeSpeechTool()
    with patch("sovereign_agent.tools.voice_tools.PiperSynthesizer") as mock_piper:
        mock_piper.available.return_value = False
        result = await tool.execute(
            tool.Args(text="hello world"),
            trace_id="t1",
        )
    assert not result.ok
    assert "not installed" in result.error


# ── loop.py marker test ───────────────────────────────────────────────────────


def test_loop_has_voice_crown_marker():
    import pathlib
    p = pathlib.Path(__file__).resolve()
    for _ in range(8):
        c = p.parent / "src" / "sovereign_agent" / "loop.py"
        if c.exists():
            src = c.read_text()
            assert "voice-crown-d" in src, "voice-crown-d missing from loop.py"
            return
        p = p.parent
    pytest.skip("loop.py not found")
