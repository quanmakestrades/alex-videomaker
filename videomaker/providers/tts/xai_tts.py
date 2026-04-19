"""xAI Text-to-Speech provider.

Docs: https://docs.x.ai/developers/model-capabilities/audio/text-to-speech
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


DEFAULT_VOICE = os.environ.get("XAI_TTS_VOICE", "eve")


class XaiTTS(TTSProvider):
    name = "xai"

    def __init__(self):
        api_key = os.environ.get("XAI_API_KEY")
        if not api_key:
            raise TTSError("XAI_API_KEY not set. Run `videomaker auth setup`.")
        self.api_key = api_key

    def synth(
        self,
        text: str,
        out_path: Path,
        voice_id: Optional[str] = None,
        speaking_rate: float = 1.0,
        language: str = "en",
    ) -> Path:
        # xAI TTS has no rate parameter exposed publicly; emulate via speech tags if needed.
        effective_text = text
        if speaking_rate >= 1.3:
            effective_text = f"[faster] {text}"
        body = {
            "text": effective_text,
            "voice_id": voice_id or DEFAULT_VOICE,
            "language": language,
        }
        req = urllib.request.Request(
            "https://api.x.ai/v1/tts",
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
            raise TTSError(f"xAI TTS HTTP {e.code}: {body_text[:300]}") from e
        except urllib.error.URLError as e:
            raise TTSError(f"xAI TTS request failed: {e}") from e

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(audio)
        return out_path


register_tts("xai", XaiTTS)
