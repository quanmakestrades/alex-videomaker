"""DALL-E / gpt-image-1 provider (OpenAI)."""
from __future__ import annotations

import base64
import json
import os
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional

from .base import ImageProvider, ImageError
from ..registry import register_image


DEFAULT_MODEL = os.environ.get("OPENAI_IMAGE_MODEL", "gpt-image-1")


class DalleProvider(ImageProvider):
    name = "dalle"

    def __init__(self):
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ImageError("OPENAI_API_KEY not set. Run `videomaker auth setup`.")
        self.api_key = api_key

    def generate(
        self,
        prompt: str,
        out_path: Path,
        width: int = 1024,
        height: int = 1024,
        aspect_ratio: Optional[str] = None,
    ) -> Path:
        # OpenAI images API accepts size as "{w}x{h}"; gpt-image-1 supports 1024x1024, 1024x1536, 1536x1024.
        size = f"{width}x{height}"
        if aspect_ratio == "16:9" and (width, height) != (1536, 1024):
            size = "1536x1024"
        body = {
            "model": DEFAULT_MODEL,
            "prompt": prompt,
            "size": size,
            "n": 1,
        }
        req = urllib.request.Request(
            "https://api.openai.com/v1/images/generations",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise ImageError(f"OpenAI images HTTP {e.code}: {e.read().decode(errors='ignore')[:300]}") from e
        except urllib.error.URLError as e:
            raise ImageError(f"OpenAI images request failed: {e}") from e

        try:
            b64 = data["data"][0]["b64_json"]
        except (KeyError, IndexError) as e:
            raise ImageError(f"OpenAI images: unexpected response shape: {json.dumps(data)[:300]}") from e
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(base64.b64decode(b64))
        return out_path


register_image("dalle", DalleProvider)
