"""Gemini LLM provider. Cheaper alternative to Claude for script writing.

Reuses the same GEMINI_API_KEY as the nanobanana and gemini-tts providers.
"""
from __future__ import annotations

import json
import math
import os
import re
from pathlib import Path
from typing import Dict, List, Optional

from .base import LLMProvider, LLMError
from ..registry import register_llm


DEFAULT_MODEL = os.environ.get("GEMINI_LLM_MODEL", "gemini-2.5-flash")


def _repair_json_string_content(text: str) -> str:
    """Single-pass repair: fix literal control chars AND unescaped double quotes in JSON string values.

    Gemini with response_mime_type='application/json' but no schema can emit:
      - Literal newlines/tabs inside string values (invalid JSON control chars)
      - Unescaped double quotes like "quoted term" inside string values

    Both issues are handled together so they don't interfere with string-state tracking.

    Heuristic for distinguishing end-of-string `"` from internal unescaped `"`:
    If the next non-whitespace character after the `"` is a JSON structural char
    (`:`, `,`, `}`, `]`) or end-of-input, treat it as the end of the string.
    Otherwise, escape it as `\\"`.
    """
    out: List[str] = []
    in_string = False
    i = 0
    while i < len(text):
        c = text[i]
        if in_string:
            if c == "\\":
                # Existing escape sequence — pass through unchanged.
                out.append(c)
                i += 1
                if i < len(text):
                    out.append(text[i])
            elif c == '"':
                # End-of-string vs. internal unescaped quote.
                j = i + 1
                while j < len(text) and text[j] in " \t\r\n":
                    j += 1
                next_ch = text[j] if j < len(text) else ""
                if next_ch in (":", ",", "}", "]", ""):
                    in_string = False
                    out.append(c)
                else:
                    out.append("\\")
                    out.append('"')
            elif c == "\n":
                out.append("\\n")
            elif c == "\r":
                out.append("\\r")
            elif c == "\t":
                out.append("\\t")
            elif ord(c) < 0x20:
                out.append(f"\\u{ord(c):04x}")
            else:
                out.append(c)
        else:
            if c == '"':
                in_string = True
                out.append(c)
            else:
                out.append(c)
        i += 1
    return "".join(out)


def _extract_json(text: str) -> Dict:
    """Strip markdown fences if present, parse JSON; apply progressive repairs on failure."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    for candidate in (text, _repair_json_string_content(text)):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    # Try extracting the outermost {} block then applying repair
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        chunk = m.group(0)
        for candidate in (chunk, _repair_json_string_content(chunk)):
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass

    try:
        json.loads(text)
    except json.JSONDecodeError as _e:
        ctx = text[max(0, _e.pos - 40): _e.pos + 40]
        raise LLMError(
            f"Gemini did not return valid JSON. Error at pos {_e.pos}: {_e.msg}\n"
            f"Context: {repr(ctx)}\nFirst 500 chars:\n{text[:500]}"
        ) from _e
    raise LLMError(f"Gemini did not return valid JSON.\nFirst 500 chars:\n{text[:500]}")


def _get_gemini_schema(name: str):
    """Return a google.genai Schema for the named output shape, or None if unavailable."""
    try:
        from google.genai import types as _gtypes
    except ImportError:
        return None

    _schemas = {
        "narration": _gtypes.Schema(
            type=_gtypes.Type.OBJECT,
            properties={
                "title": _gtypes.Schema(type=_gtypes.Type.STRING),
                "full_script": _gtypes.Schema(type=_gtypes.Type.STRING),
            },
            required=["title", "full_script"],
        ),
        "breakdown": _gtypes.Schema(
            type=_gtypes.Type.OBJECT,
            properties={
                "scenes": _gtypes.Schema(
                    type=_gtypes.Type.ARRAY,
                    items=_gtypes.Schema(
                        type=_gtypes.Type.OBJECT,
                        properties={
                            "narration": _gtypes.Schema(type=_gtypes.Type.STRING),
                            "image_prompt": _gtypes.Schema(type=_gtypes.Type.STRING),
                        },
                        required=["narration", "image_prompt"],
                    ),
                ),
            },
            required=["scenes"],
        ),
    }
    return _schemas.get(name)


def _validate_script_output(data: Dict, target_words: int, target_scenes: int) -> None:
    for field in ("title", "full_script", "scenes"):
        if field not in data:
            raise LLMError(f"Gemini output missing required field: {field}")
    if not isinstance(data["scenes"], list) or not data["scenes"]:
        raise LLMError("Gemini returned empty scenes list")
    for i, scene in enumerate(data["scenes"], 1):
        for f in ("narration", "image_prompt"):
            if f not in scene:
                raise LLMError(f"Scene {i} missing field: {f}")
    actual_words = len(data["full_script"].split())
    actual_scenes = len(data["scenes"])
    if actual_words < max(1, math.floor(target_words * 0.80)):
        raise LLMError(
            f"Script too short: {actual_words} words (target {target_words}, need at least 80%)"
        )
    if actual_scenes < max(1, math.floor(target_scenes * 0.80)):
        raise LLMError(
            f"Too few scenes: {actual_scenes} (target {target_scenes}, need at least 80%)"
        )


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self, model: Optional[str] = None):
        try:
            from google import genai  # type: ignore
        except ImportError as e:
            raise LLMError("google-genai SDK not installed. `pip install google-genai`") from e
        self._genai = genai
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise LLMError("GEMINI_API_KEY not set. Run `videomaker auth setup`.")
        self.client = genai.Client(api_key=api_key)
        self.model = model or DEFAULT_MODEL

    def generate_json(
        self,
        user_prompt: str,
        system_prompt: str,
        pdfs: Optional[List[Path]] = None,
        schema_name: Optional[str] = None,
    ) -> Dict:
        """Make one Gemini call and return a parsed JSON dict.

        schema_name: optional key into _GEMINI_SCHEMAS (e.g. "narration", "breakdown").
        Using a schema enforces correct field names and types; recommended for known outputs.
        """
        contents: List = []
        if pdfs:
            for pdf in pdfs:
                uploaded = self.client.files.upload(file=str(pdf))
                contents.append(uploaded)
        contents.append(user_prompt)

        config: Dict = {
            "system_instruction": system_prompt,
            "max_output_tokens": 65536,
            "response_mime_type": "application/json",
        }
        if schema_name:
            schema = _get_gemini_schema(schema_name)
            if schema is not None:
                config["response_schema"] = schema

        try:
            resp = self.client.models.generate_content(
                model=self.model,
                contents=contents,
                config=config,
            )
        except Exception as e:
            raise LLMError(f"Gemini API call failed: {e}") from e

        text = getattr(resp, "text", None)
        if not text:
            text = _extract_text_from_candidates(resp)
        if not text:
            raise LLMError(f"Gemini returned no text payload: {resp}")
        return _extract_json(text)

    # ------------------------------------------------------------------ legacy
    def write_script_and_scenes(self, topic, word_count, scene_count, system_prompt, pdfs=None):
        """Legacy single-shot method — not called by the pipeline anymore."""
        contents: List = []
        if pdfs:
            for pdf in pdfs:
                uploaded = self.client.files.upload(file=str(pdf))
                contents.append(uploaded)
        contents.append(
            f"TOPIC: {topic}\n\n"
            f"TARGET WORD COUNT: {word_count}\n"
            f"TARGET SCENE COUNT: {scene_count}\n\n"
            "Produce the JSON object described in the system prompt. "
            "Length matters. Do not summarize. Expand until the script is at least 95% of the target word count "
            "and the scenes list is at least 95% of the target scene count. "
            "Return ONLY the JSON — no prose, no markdown fences."
        )
        from google.genai import types as _gtypes
        _scene_schema = _gtypes.Schema(
            type=_gtypes.Type.OBJECT,
            properties={
                "narration": _gtypes.Schema(type=_gtypes.Type.STRING),
                "image_prompt": _gtypes.Schema(type=_gtypes.Type.STRING),
            },
            required=["narration", "image_prompt"],
        )
        _response_schema = _gtypes.Schema(
            type=_gtypes.Type.OBJECT,
            properties={
                "title": _gtypes.Schema(type=_gtypes.Type.STRING),
                "full_script": _gtypes.Schema(type=_gtypes.Type.STRING),
                "scenes": _gtypes.Schema(type=_gtypes.Type.ARRAY, items=_scene_schema),
            },
            required=["title", "full_script", "scenes"],
        )
        try:
            resp = self.client.models.generate_content(
                model=self.model,
                contents=contents,
                config={
                    "system_instruction": system_prompt,
                    "max_output_tokens": 65536,
                    "response_mime_type": "application/json",
                    "response_schema": _response_schema,
                },
            )
        except Exception as e:
            raise LLMError(f"Gemini API call failed: {e}") from e
        text = getattr(resp, "text", None)
        if not text:
            text = _extract_text_from_candidates(resp)
        if not text:
            raise LLMError(f"Gemini returned no text payload: {resp}")
        data = _extract_json(text)
        actual_words = len(data.get("full_script", "").split())
        actual_scenes = len(data.get("scenes", []) or [])
        if actual_words < max(1, int(word_count * 0.80)) or actual_scenes < max(1, int(scene_count * 0.80)):
            repair_prompt = (
                "Your first response was structurally valid but too short. "
                f"Current word count: {actual_words}. Required minimum: {int(word_count * 0.95)}. "
                f"Current scene count: {actual_scenes}. Required minimum: {int(scene_count * 0.95)}. "
                "Rewrite and expand the script substantially. Return a complete fresh JSON object only."
            )
            try:
                repair_resp = self.client.models.generate_content(
                    model=self.model,
                    contents=[repair_prompt],
                    config={
                        "system_instruction": system_prompt,
                        "max_output_tokens": 65536,
                        "response_mime_type": "application/json",
                        "response_schema": _response_schema,
                    },
                )
                repair_text = getattr(repair_resp, "text", None) or _extract_text_from_candidates(repair_resp)
                if repair_text:
                    repaired = _extract_json(repair_text)
                    if (len(repaired.get("full_script", "").split()) > actual_words
                            or len(repaired.get("scenes", []) or []) > actual_scenes):
                        data = repaired
            except Exception:
                pass
        _validate_script_output(data, word_count, scene_count)
        data.setdefault("meta", {})
        data["meta"].update({"model": self.model, "provider": "gemini"})
        return data


def _extract_text_from_candidates(resp) -> str:
    candidates = getattr(resp, "candidates", None) or []
    parts: List[str] = []
    for cand in candidates:
        content = getattr(cand, "content", None)
        if not content:
            continue
        for part in getattr(content, "parts", None) or []:
            txt = getattr(part, "text", None)
            if txt:
                parts.append(txt)
    return "".join(parts).strip()


register_llm("gemini", GeminiProvider)
