"""Nano Banana (Gemini image) provider. Default image generator.

Uses Gemini 2.5 Flash Image (model id `gemini-2.5-flash-image`) on the free tier — ~500
requests/day. For higher quality, set env GEMINI_IMAGE_MODEL=gemini-3.1-flash-image-preview
(paid) or gemini-3-pro-image-preview (paid, 4K).

Docs: https://ai.google.dev/gemini-api/docs/image-generation
"""
from __future__ import annotations

import base64
import os
from io import BytesIO
from pathlib import Path
from typing import Optional

from .base import ImageProvider, ImageError
from ..registry import register_image


DEFAULT_MODEL = os.environ.get("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")


class NanoBananaProvider(ImageProvider):
    name = "nanobanana"

    def __init__(self, model: Optional[str] = None):
        try:
            from google import genai  # type: ignore
        except ImportError as e:
            raise ImageError("google-genai SDK not installed. `pip install google-genai`") from e
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ImageError("GEMINI_API_KEY not set. Run `videomaker auth setup`.")
        self.client = genai.Client(api_key=api_key)
        self.model = model or DEFAULT_MODEL

    def generate(
        self,
        prompt: str,
        out_path: Path,
        width: int = 1024,
        height: int = 1024,
        aspect_ratio: Optional[str] = None,
    ) -> Path:
        # Nano Banana accepts aspect ratio hints in the prompt; explicit size params aren't
        # exposed. Prepend a hint if caller asked for 16:9.
        effective_prompt = prompt
        if aspect_ratio:
            effective_prompt = f"[aspect ratio {aspect_ratio}] {prompt}"

        try:
            resp = self.client.models.generate_content(
                model=self.model,
                contents=[effective_prompt],
            )
        except Exception as e:
            raise ImageError(f"Gemini image call failed: {e}") from e

        # Walk parts for inline image data.
        png_bytes = None
        for part in resp.candidates[0].content.parts:
            if hasattr(part, "inline_data") and part.inline_data and part.inline_data.data:
                data = part.inline_data.data
                # SDK sometimes returns base64 string, sometimes raw bytes.
                if isinstance(data, str):
                    png_bytes = base64.b64decode(data)
                else:
                    png_bytes = data
                break
        if png_bytes is None:
            # Inspect text parts for safety refusals etc.
            refusal = " ".join(p.text for p in resp.candidates[0].content.parts if getattr(p, "text", None))
            raise ImageError(f"Nano Banana returned no image. Message: {refusal[:300] or '(empty)'}")

        out_path.parent.mkdir(parents=True, exist_ok=True)
        # Ensure consistent dimensions — resize if needed.
        _write_and_resize(png_bytes, out_path, width, height)
        return out_path


def _write_and_resize(png_bytes: bytes, out_path: Path, target_w: int, target_h: int) -> None:
    try:
        from PIL import Image  # type: ignore
    except ImportError:
        # No Pillow — write as-is. ffmpeg scale filter will handle during stitching.
        out_path.write_bytes(png_bytes)
        return
    img = Image.open(BytesIO(png_bytes)).convert("RGB")
    if img.size != (target_w, target_h):
        # Letterbox: scale to fit, pad with black.
        src_w, src_h = img.size
        scale = min(target_w / src_w, target_h / src_h)
        new_w, new_h = int(src_w * scale), int(src_h * scale)
        resized = img.resize((new_w, new_h), Image.LANCZOS)
        canvas = Image.new("RGB", (target_w, target_h), (0, 0, 0))
        canvas.paste(resized, ((target_w - new_w) // 2, (target_h - new_h) // 2))
        canvas.save(out_path, "PNG")
    else:
        img.save(out_path, "PNG")


register_image("nanobanana", NanoBananaProvider)
