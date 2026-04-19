"""ai33.pro TTS provider.

Docs (gated, requires premium account): https://ai33.pro/app/api-document
Endpoint shape (from user-provided screenshot):

  POST https://api.ai33.pro/v1/text-to-speech/{voice_id}?output_format=mp3_44100_128
  Headers:
    Content-Type: application/json
    xi-api-key: $AI33PRO_API_KEY
  Body:
    {
      "text": "...",
      "model_id": "eleven_multilingual_v2",
      "with_transcript": false,
      "receive_url": "<optional webhook>"
    }
  Response:
    {"success": true, ...}

Response shape is partially inferred (the screenshot was truncated). This provider handles
three observed patterns defensively:
  1. Synchronous audio bytes in the response body (Content-Type: audio/mpeg)
  2. JSON with an `audio_url` / `url` / `output` field pointing to the MP3
  3. JSON with a job id that must be polled via a status endpoint

If you hit a response shape this provider doesn't handle, check the full docs and file an
issue — the _parse_response helper is the only function that needs edits.
"""
from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional

from .base import TTSProvider, TTSError
from ..registry import register_tts


BASE_URL = os.environ.get("AI33PRO_BASE_URL", "https://api.ai33.pro")
DEFAULT_VOICE = os.environ.get("AI33PRO_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")  # ElevenLabs "Rachel" — common default
DEFAULT_MODEL_ID = os.environ.get("AI33PRO_MODEL_ID", "eleven_multilingual_v2")
DEFAULT_OUTPUT_FORMAT = "mp3_44100_128"


class Ai33ProTTS(TTSProvider):
    name = "ai33pro"

    def __init__(self):
        api_key = os.environ.get("AI33PRO_API_KEY")
        if not api_key:
            raise TTSError(
                "AI33PRO_API_KEY not set. ai33.pro requires premium credits to get an "
                "API key — see https://ai33.pro/app/api-document. Run `videomaker auth setup`."
            )
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
        url = f"{BASE_URL}/v1/text-to-speech/{urllib.parse.quote(voice)}"
        qs = {"output_format": DEFAULT_OUTPUT_FORMAT}
        url = f"{url}?{urllib.parse.urlencode(qs)}"

        body = {
            "text": text,
            "model_id": DEFAULT_MODEL_ID,
            "with_transcript": False,
            # Speaking rate is not in the documented API surface. ElevenLabs-proxy engines
            # sometimes accept `voice_settings.speed`. We send it opportunistically; the
            # server will ignore if unrecognized.
            "voice_settings": {
                "speed": speaking_rate,
                "stability": 0.5,
                "similarity_boost": 0.75,
            },
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "xi-api-key": self.api_key,
                "Accept": "audio/mpeg, application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                content_type = resp.headers.get("Content-Type", "")
                raw = resp.read()
        except urllib.error.HTTPError as e:
            body_text = e.read().decode("utf-8", errors="ignore")
            raise TTSError(f"ai33.pro HTTP {e.code}: {body_text[:300]}") from e
        except urllib.error.URLError as e:
            raise TTSError(f"ai33.pro request failed: {e}") from e

        out_path.parent.mkdir(parents=True, exist_ok=True)
        self._handle_response(content_type, raw, out_path)
        return out_path

    def _handle_response(self, content_type: str, raw: bytes, out_path: Path) -> None:
        # Pattern 1: raw audio bytes
        if content_type.startswith("audio/") or (len(raw) > 1024 and raw[:3] in (b"ID3", b"\xff\xfb", b"\xff\xf3")):
            out_path.write_bytes(raw)
            return
        # Pattern 2/3: JSON
        try:
            data = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise TTSError(f"ai33.pro returned non-audio non-JSON ({content_type}): {raw[:200]!r}") from e

        if data.get("success") is False:
            raise TTSError(f"ai33.pro returned success=false: {data.get('message') or data}")

        # Sync-with-url patterns
        audio_url = data.get("audio_url") or data.get("url") or data.get("output")
        if isinstance(audio_url, list):  # some APIs return a list
            audio_url = audio_url[0] if audio_url else None
        if audio_url:
            self._download(audio_url, out_path)
            return

        # Async poll pattern — job_id + optional status endpoint
        job_id = data.get("job_id") or data.get("id") or data.get("task_id")
        if job_id:
            self._poll_job(job_id, out_path)
            return

        raise TTSError(f"ai33.pro response shape not recognized. Keys: {list(data.keys())}. First 300 chars: {json.dumps(data)[:300]}")

    def _download(self, url: str, out_path: Path) -> None:
        req = urllib.request.Request(url, headers={"xi-api-key": self.api_key})
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                out_path.write_bytes(resp.read())
        except urllib.error.URLError as e:
            raise TTSError(f"ai33.pro audio download failed: {e}") from e

    def _poll_job(self, job_id: str, out_path: Path, max_wait_s: int = 180) -> None:
        status_url = f"{BASE_URL}/v1/text-to-speech/status/{urllib.parse.quote(job_id)}"
        deadline = time.time() + max_wait_s
        while time.time() < deadline:
            req = urllib.request.Request(status_url, headers={"xi-api-key": self.api_key})
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                # If status endpoint doesn't exist, surface a clear error.
                if e.code == 404:
                    raise TTSError(
                        f"ai33.pro returned job_id={job_id} but status endpoint 404s. "
                        "Either the poll URL is wrong or the API changed — check "
                        "https://ai33.pro/app/api-document and update _poll_job in ai33pro.py."
                    ) from e
                raise TTSError(f"ai33.pro poll error HTTP {e.code}") from e
            status = data.get("status")
            if status in ("completed", "done", "success"):
                audio_url = data.get("audio_url") or data.get("url") or data.get("output")
                if not audio_url:
                    raise TTSError(f"ai33.pro job {job_id} completed without audio_url: {data}")
                self._download(audio_url, out_path)
                return
            if status in ("failed", "error"):
                raise TTSError(f"ai33.pro job {job_id} failed: {data.get('message') or data}")
            time.sleep(2)
        raise TTSError(f"ai33.pro job {job_id} did not complete within {max_wait_s}s")


register_tts("ai33pro", Ai33ProTTS)
