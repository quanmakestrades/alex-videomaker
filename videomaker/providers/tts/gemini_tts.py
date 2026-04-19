"""Gemini TTS provider. Default free option — same API key as nanobanana.

Uses Gemini's TTS-capable model (gemini-2.5-flash-preview-tts or newer). Speaking rate is
controlled via a natural-language prefix ("Read quickly:") since Gemini doesn't expose a
rate parameter. Output is PCM → re-encoded to MP3 via ffmpeg (or pydub fallback).
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from .base import TTSProvider, TTSError
from ..registry import register_tts


DEFAULT_MODEL = os.environ.get("GEMINI_TTS_MODEL", "gemini-2.5-flash-preview-tts")
DEFAULT_VOICE = os.environ.get("GEMINI_TTS_VOICE", "Kore")  # Neutral, confident. Others: Puck, Enceladus, Charon, Fenrir, Aoede.


class GeminiTTS(TTSProvider):
    name = "gemini"

    def __init__(self, model: Optional[str] = None):
        try:
            from google import genai  # type: ignore
            from google.genai import types  # type: ignore
        except ImportError as e:
            raise TTSError("google-genai SDK not installed. `pip install google-genai`") from e
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise TTSError("GEMINI_API_KEY not set. Run `videomaker auth setup`.")
        self.client = genai.Client(api_key=api_key)
        self.types = types
        self.model = model or DEFAULT_MODEL

    def synth(
        self,
        text: str,
        out_path: Path,
        voice_id: Optional[str] = None,
        speaking_rate: float = 1.0,
        language: str = "en",
    ) -> Path:
        voice = voice_id or DEFAULT_VOICE
        # Gemini TTS doesn't have a rate parameter — use a performance directive.
        # Rate >= 1.3 triggers "fast"; 1.0-1.3 "natural"; <1.0 "slow".
        if speaking_rate >= 1.3:
            perf = "Read quickly and energetically: "
        elif speaking_rate <= 0.85:
            perf = "Read slowly and clearly: "
        else:
            perf = ""
        prompt = f"{perf}{text}"

        try:
            resp = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=self.types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=self.types.SpeechConfig(
                        voice_config=self.types.VoiceConfig(
                            prebuilt_voice_config=self.types.PrebuiltVoiceConfig(
                                voice_name=voice,
                            )
                        )
                    ),
                ),
            )
        except Exception as e:
            raise TTSError(f"Gemini TTS call failed: {e}") from e

        # Extract the audio bytes from the response
        pcm_data = None
        for part in resp.candidates[0].content.parts:
            if hasattr(part, "inline_data") and part.inline_data:
                pcm_data = part.inline_data.data
                break
        if pcm_data is None:
            raise TTSError("Gemini TTS returned no audio data")

        # Gemini returns raw PCM (L16, 24kHz, mono). Write as WAV first, then encode to MP3.
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as wav_f:
            wav_path = Path(wav_f.name)
        try:
            _pcm_to_wav(pcm_data, wav_path, sample_rate=24000)
            _wav_to_mp3(wav_path, out_path)
        finally:
            wav_path.unlink(missing_ok=True)
        return out_path


def _pcm_to_wav(pcm_bytes: bytes, out_path: Path, sample_rate: int = 24000) -> None:
    """Write raw 16-bit PCM mono bytes as a WAV file."""
    import wave
    with wave.open(str(out_path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)        # 16-bit
        w.setframerate(sample_rate)
        w.writeframes(pcm_bytes)


def _wav_to_mp3(wav_path: Path, mp3_path: Path) -> None:
    """Encode WAV → MP3 using ffmpeg."""
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(wav_path),
        "-codec:a", "libmp3lame", "-qscale:a", "2",
        str(mp3_path),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        raise TTSError(f"ffmpeg encode failed: {e.stderr.decode(errors='ignore')}") from e
    except FileNotFoundError as e:
        raise TTSError("ffmpeg not found on PATH. Install with `brew install ffmpeg` (macOS) or `apt install ffmpeg` (Linux).") from e


register_tts("gemini", GeminiTTS)
