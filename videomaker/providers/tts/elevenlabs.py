"""ElevenLabs TTS provider. Direct — no proxy.

Docs: https://elevenlabs.io/docs/api-reference/text-to-speech/convert
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional

from .base import TTSProvider, TTSError
from ..registry import register_tts


BASE_URL = "https://api.elevenlabs.io"
DEFAULT_VOICE = os.environ.get("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")  # Rachel
DEFAULT_MODEL_ID = os.environ.get("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2")


class ElevenLabsTTS(TTSProvider):
    name = "elevenlabs"

    def __init__(self):
        api_key = os.environ.get("ELEVENLABS_API_KEY")
        if not api_key:
            raise TTSError("ELEVENLABS_API_KEY not set. Run `videomaker auth setup`.")
        self.api_key = api_key

    def synth(
        self,
        text: str,
        out_path: Path,
        voice_id: Optional[str] = None,
        speaking_rate: float = 1.0,
        language: str = "en",
    ) -> Path:
        voice = voice_id or DEFAULT_VOICE
        url = f"{BASE_URL}/v1/text-to-speech/{urllib.parse.quote(voice)}?output_format=mp3_44100_128"
        body = {
            "text": text,
            "model_id": DEFAULT_MODEL_ID,
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
                "speed": speaking_rate,
            },
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "xi-api-key": self.api_key,
                "Accept": "audio/mpeg",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                audio = resp.read()
        except urllib.error.HTTPError as e:
            body_text = e.read().decode("utf-8", errors="ignore")
            raise TTSError(f"ElevenLabs HTTP {e.code}: {body_text[:300]}") from e
        except urllib.error.URLError as e:
            raise TTSError(f"ElevenLabs request failed: {e}") from e

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(audio)
        return out_path


register_tts("elevenlabs", ElevenLabsTTS)
