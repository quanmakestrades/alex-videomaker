"""Replicate image provider. Fallback for SDXL / Flux / any hosted model."""
from __future__ import annotations

import json
import os
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional

from .base import ImageProvider, ImageError
from ..registry import register_image


# Default to Flux Schnell — cheap and good. Override with REPLICATE_IMAGE_MODEL.
DEFAULT_MODEL = os.environ.get("REPLICATE_IMAGE_MODEL", "black-forest-labs/flux-schnell")


class ReplicateProvider(ImageProvider):
    name = "replicate"

    def __init__(self):
        token = os.environ.get("REPLICATE_API_TOKEN")
        if not token:
            raise ImageError("REPLICATE_API_TOKEN not set. Run `videomaker auth setup`.")
        self.token = token

    def generate(
        self,
        prompt: str,
        out_path: Path,
        width: int = 1024,
        height: int = 1024,
        aspect_ratio: Optional[str] = None,
    ) -> Path:
        body = {
            "input": {
                "prompt": prompt,
                "aspect_ratio": aspect_ratio or "1:1",
                "output_format": "png",
                "num_outputs": 1,
            }
        }
        req = urllib.request.Request(
            f"https://api.replicate.com/v1/models/{DEFAULT_MODEL}/predictions",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "Prefer": "wait",  # sync-wait up to 60s
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise ImageError(f"Replicate HTTP {e.code}: {e.read().decode(errors='ignore')[:300]}") from e
        except urllib.error.URLError as e:
            raise ImageError(f"Replicate request failed: {e}") from e

        # Poll if still processing
        while data.get("status") in ("starting", "processing"):
            time.sleep(2)
            get_url = data.get("urls", {}).get("get")
            if not get_url:
                raise ImageError(f"Replicate: no polling URL in response: {data}")
            preq = urllib.request.Request(get_url, headers={"Authorization": f"Bearer {self.token}"})
            with urllib.request.urlopen(preq, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))

        if data.get("status") != "succeeded":
            raise ImageError(f"Replicate prediction failed: {data.get('error') or data.get('status')}")
        output = data.get("output")
        img_url = output[0] if isinstance(output, list) else output
        if not img_url:
            raise ImageError(f"Replicate: no output URL: {data}")

        with urllib.request.urlopen(img_url, timeout=60) as resp:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(resp.read())
        return out_path


register_image("replicate", ReplicateProvider)
