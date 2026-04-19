"""OpenAI TTS provider.

Docs: https://platform.openai.com/docs/guides/text-to-speech
Model: gpt-4o-mini-tts (default, recommended per OpenAI)
"""
from __future__ import annotations

import json
import os
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional

from .base import TTSProvider, TTSError
from ..registry import register_tts


DEFAULT_MODEL = os.environ.get("OPENAI_TTS_MODEL", "gpt-4o-mini-tts")
DEFAULT_VOICE = os.environ.get("OPENAI_TTS_VOICE", "nova")


class OpenAITTS(TTSProvider):
    name = "openai"

    def __init__(self):
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise TTSError("OPENAI_API_KEY not set. Run `videomaker auth setup`.")
        self.api_key = api_key

    def synth(
        self,
        text: str,
        out_path: Path,
        voice_id: Optional[str] = None,
        speaking_rate: float = 1.0,
        language: str = "en",
    ) -> Path:
        body = {
            "model": DEFAULT_MODEL,
            "input": text,
            "voice": voice_id or DEFAULT_VOICE,
            "response_format": "mp3",
            "speed": max(0.25, min(4.0, speaking_rate)),  # OpenAI allows 0.25–4.0
        }
        req = urllib.request.Request(
            "https://api.openai.com/v1/audio/speech",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                audio = resp.read()
        except urllib.error.HTTPError as e:
            body_text = e.read().decode("utf-8", errors="ignore")
            raise TTSError(f"OpenAI TTS HTTP {e.code}: {body_text[:300]}") from e
        except urllib.error.URLError as e:
            raise TTSError(f"OpenAI TTS request failed: {e}") from e

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(audio)
        return out_path


register_tts("openai", OpenAITTS)
