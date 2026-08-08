"""tools/voice_tools.py — Voice I/O tools (M47).

  voice_status()                                T0 — STT/TTS availability + recording state
  transcribe_audio(wav_path)                    T1 — CPU Whisper transcription
  synthesize_speech(text, voice=...)            T1 — Piper TTS → WAV
"""
from __future__ import annotations

import asyncio
from typing import Optional

from pydantic import BaseModel, Field

from .base import Tool, ToolResult

# Module-level imports for testability
try:
    from sovereign_agent.voice import (
        VoiceRecorder,
        WhisperTranscriber,
        PiperSynthesizer,
        get_voice_recorder,
        get_whisper_transcriber,
        get_piper_synthesizer,
    )
except ImportError:
    VoiceRecorder = None  # type: ignore[assignment]
    WhisperTranscriber = None  # type: ignore[assignment]
    PiperSynthesizer = None  # type: ignore[assignment]
    get_voice_recorder = None  # type: ignore[assignment]
    get_whisper_transcriber = None  # type: ignore[assignment]
    get_piper_synthesizer = None  # type: ignore[assignment]


# ── voice_status ──────────────────────────────────────────────────────────────


class _StatusArgs(BaseModel):
    pass


class VoiceStatusTool(Tool[_StatusArgs]):
    name = "voice_status"
    tier = 0
    description = (
        "Check voice I/O availability. Returns STT (Whisper) and TTS (Piper) availability, "
        "recording hardware status (arecord), and whether a recording is currently active. "
        "Call before attempting transcription or synthesis to know what's available."
    )
    failure_modes = ("voice_unavailable",)
    Args = _StatusArgs

    async def execute(self, args: _StatusArgs, *, trace_id: str) -> ToolResult:  # noqa: ARG002
        try:
            stt_available = WhisperTranscriber.available()
            tts_available = PiperSynthesizer.available()
            recorder = get_voice_recorder()
            arecord_ok = await asyncio.to_thread(VoiceRecorder.arecord_available)

            return ToolResult(ok=True, output={
                "stt_available": stt_available,
                "stt_backend": "faster-whisper (CPU)" if stt_available else "not installed",
                "stt_install": "pip install -e '.[media]' to install faster-whisper",
                "tts_available": tts_available,
                "tts_backend": "piper-tts (CPU)" if tts_available else "not installed",
                "tts_install": "pip install piper-tts to install",
                "arecord_available": arecord_ok,
                "arecord_note": "System arecord for microphone capture",
                "is_recording": recorder.is_recording(),
                "voice_mode_ready": stt_available and tts_available and arecord_ok,
            })
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"voice_status failed: {e}")


# ── transcribe_audio ──────────────────────────────────────────────────────────


class _TranscribeArgs(BaseModel):
    wav_path: str = Field(description="Absolute path to WAV file to transcribe.")
    model_size: str = Field(
        default="base.en",
        description="Whisper model: base.en (fast) | small.en (better) | medium.en (best CPU)",
    )


class TranscribeAudioTool(Tool[_TranscribeArgs]):
    name = "transcribe_audio"
    tier = 1
    description = (
        "Transcribe a WAV audio file using faster-whisper in CPU mode. Zero VRAM. "
        "Returns the transcription text. "
        "Requires: pip install -e '.[media]' (faster-whisper). "
        "Base.en model: ~150MB, excellent English quality, 2-3x real-time on CPU."
    )
    failure_modes = ("whisper_unavailable", "wav_not_found", "transcription_failed")
    Args = _TranscribeArgs

    async def execute(self, args: _TranscribeArgs, *, trace_id: str) -> ToolResult:
        try:
            if not WhisperTranscriber.available():
                return ToolResult(
                    ok=False,
                    error=(
                        "faster-whisper not installed. "
                        "Install with: pip install -e '.[media]'"
                    ),
                )
            from pathlib import Path as _Path
            wav = _Path(args.wav_path)
            if not wav.exists():
                return ToolResult(ok=False, error=f"WAV file not found: {args.wav_path}")

            transcriber = get_whisper_transcriber(args.model_size)
            text = await asyncio.to_thread(transcriber.transcribe, wav)

            return ToolResult(ok=True, output={
                "transcript": text,
                "wav_path": args.wav_path,
                "model": args.model_size,
                "word_count": len(text.split()),
            })
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"transcribe_audio failed: {e}")


# ── synthesize_speech ─────────────────────────────────────────────────────────


class _SynthesizeArgs(BaseModel):
    text: str = Field(max_length=2000, description="Text to speak.")
    voice: str = Field(
        default="en_US-lessac-medium",
        description="Piper voice name (e.g. en_US-lessac-medium, en_US-ryan-high).",
    )
    play: bool = Field(
        default=False,
        description="If True, play audio via aplay immediately after synthesis.",
    )


class SynthesizeSpeechTool(Tool[_SynthesizeArgs]):
    name = "synthesize_speech"
    tier = 1
    description = (
        "Synthesize speech using piper-tts (CPU-only, 50MB models). "
        "Returns path to WAV file. Optionally plays via aplay. "
        "Requires: pip install piper-tts + model download on first use. "
        "Voice: en_US-lessac-medium is natural and fast."
    )
    failure_modes = ("piper_unavailable", "synthesis_failed")
    Args = _SynthesizeArgs

    async def execute(self, args: _SynthesizeArgs, *, trace_id: str) -> ToolResult:
        try:
            if not PiperSynthesizer.available():
                return ToolResult(
                    ok=False,
                    error="piper-tts not installed. Install with: pip install piper-tts",
                )

            synth = get_piper_synthesizer(args.voice)
            if args.play:
                await asyncio.to_thread(synth.speak, args.text)
                wav_path = None
            else:
                wav_path = await asyncio.to_thread(synth.synthesize, args.text)

            return ToolResult(ok=True, output={
                "wav_path": str(wav_path) if wav_path else None,
                "text_length": len(args.text),
                "voice": args.voice,
                "played": args.play,
                "message": (
                    "Audio played via aplay."
                    if args.play
                    else f"WAV saved to {wav_path}"
                ),
            })
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"synthesize_speech failed: {e}")


__all__ = [
    "VoiceStatusTool",
    "TranscribeAudioTool",
    "SynthesizeSpeechTool",
]
