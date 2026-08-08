"""voice.py — Voice I/O for Aria (M47).

STT: faster-whisper CPU mode (zero VRAM) or mock fallback.
TTS: piper-tts subprocess or mock fallback.
Recording: arecord subprocess (ALSA, system-wide, zero deps).

All backends fail gracefully when deps are not installed.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ── Recording via arecord (ALSA) ──────────────────────────────────────────────


class VoiceRecorder:
    """Record audio from microphone using arecord.

    Simple: start_recording() opens the process, stop_recording() kills it
    and returns the WAV path. Thread-safe for single recording at a time.
    """

    def __init__(self, data_dir: Optional[Path] = None) -> None:
        from sovereign_agent.config import SETTINGS
        self._data_dir = data_dir or (SETTINGS.paths.data_dir / "voice")
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._process: Optional[subprocess.Popen] = None
        self._wav_path: Optional[Path] = None

    def start_recording(self) -> None:
        if self._process is not None:
            return  # already recording
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self._wav_path = self._data_dir / f"voice-{ts}.wav"
        self._process = subprocess.Popen(
            [
                "arecord",
                "-f", "S16_LE",
                "-r", "16000",
                "-c", "1",
                str(self._wav_path),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def stop_recording(self) -> Optional[Path]:
        if self._process is None:
            return None
        self._process.terminate()
        try:
            self._process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self._process.kill()
        self._process = None
        path = self._wav_path
        self._wav_path = None
        return path

    def is_recording(self) -> bool:
        return self._process is not None

    @staticmethod
    def arecord_available() -> bool:
        try:
            subprocess.run(["arecord", "--version"], capture_output=True, timeout=2)
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False


# ── STT via faster-whisper ────────────────────────────────────────────────────


class WhisperTranscriber:
    """CPU-mode faster-whisper transcription. Zero VRAM."""

    def __init__(self, model_size: str = "base.en") -> None:
        self._model_size = model_size
        self._model = None  # lazy-loaded

    def _load_model(self):
        if self._model is None:
            from faster_whisper import WhisperModel  # noqa: PLC0415
            self._model = WhisperModel(self._model_size, device="cpu", compute_type="int8")
        return self._model

    def transcribe(self, wav_path: Path) -> str:
        model = self._load_model()
        segments, _info = model.transcribe(str(wav_path), beam_size=5)
        return " ".join(seg.text.strip() for seg in segments).strip()

    @staticmethod
    def available() -> bool:
        try:
            import faster_whisper  # noqa: F401, PLC0415
            return True
        except ImportError:
            return False

    @property
    def model_size(self) -> str:
        return self._model_size


# ── TTS via piper-tts ─────────────────────────────────────────────────────────


class PiperSynthesizer:
    """CPU-only TTS via piper-tts Python package.

    Requires: pip install piper-tts
    Models: downloaded automatically on first use.
    """

    DEFAULT_VOICE = "en_US-lessac-medium"
    _PIPER_BINARY_PATHS = [
        "piper-tts",
        os.path.expanduser("~/.local/bin/piper"),
        "/usr/local/bin/piper-tts",
    ]

    def __init__(self, voice: str = DEFAULT_VOICE, data_dir: Optional[Path] = None) -> None:
        from sovereign_agent.config import SETTINGS
        self._voice = voice
        self._data_dir = data_dir or (SETTINGS.paths.data_dir / "voice")
        self._data_dir.mkdir(parents=True, exist_ok=True)

    def speak(self, text: str) -> None:
        wav = self.synthesize(text)
        if wav and wav.exists():
            subprocess.run(
                ["aplay", "-q", str(wav)],
                check=False,
                capture_output=True,
            )

    def synthesize(self, text: str) -> Optional[Path]:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out_path = self._data_dir / f"tts-{ts}.wav"
        try:
            from piper.voice import PiperVoice  # noqa: PLC0415
            model_dir = self._data_dir / "models"
            model_dir.mkdir(parents=True, exist_ok=True)
            voice = PiperVoice.load(self._voice, download=True, data_dir=model_dir)
            with out_path.open("wb") as f:
                voice.synthesize(text, f)
            return out_path
        except Exception:  # noqa: BLE001
            return None

    @staticmethod
    def available() -> bool:
        try:
            import piper.voice  # noqa: F401, PLC0415
            return True
        except ImportError:
            return False

    @property
    def voice(self) -> str:
        return self._voice


# ── Singletons ────────────────────────────────────────────────────────────────


_voice_recorder: Optional[VoiceRecorder] = None
_whisper_transcriber: Optional[WhisperTranscriber] = None
_piper_synthesizer: Optional[PiperSynthesizer] = None


def get_voice_recorder() -> VoiceRecorder:
    global _voice_recorder
    if _voice_recorder is None:
        _voice_recorder = VoiceRecorder()
    return _voice_recorder


def get_whisper_transcriber(model_size: str = "base.en") -> WhisperTranscriber:
    global _whisper_transcriber
    if _whisper_transcriber is None:
        _whisper_transcriber = WhisperTranscriber(model_size)
    return _whisper_transcriber


def get_piper_synthesizer(voice: str = PiperSynthesizer.DEFAULT_VOICE) -> PiperSynthesizer:
    global _piper_synthesizer
    if _piper_synthesizer is None:
        _piper_synthesizer = PiperSynthesizer(voice)
    return _piper_synthesizer
