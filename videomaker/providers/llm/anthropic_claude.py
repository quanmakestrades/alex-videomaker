"""Claude (Anthropic) LLM provider."""
from __future__ import annotations

import base64
import json
import os
import re
from pathlib import Path
from typing import Dict, List, Optional

from .base import LLMProvider, LLMError
from ..registry import register_llm


DEFAULT_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")


class ClaudeProvider(LLMProvider):
    name = "claude"

    def __init__(self, model: Optional[str] = None):
        try:
            import anthropic  # type: ignore
        except ImportError as e:
            raise LLMError("anthropic SDK not installed. `pip install anthropic`") from e
        self._anthropic = anthropic
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise LLMError("ANTHROPIC_API_KEY not set. Run `videomaker auth setup`.")
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model or DEFAULT_MODEL

    def generate_json(
        self,
        user_prompt: str,
        system_prompt: str,
        pdfs: Optional[List[Path]] = None,
        schema_name: Optional[str] = None,  # unused by Claude; accepted for interface compat
    ) -> Dict:
        """Make one Claude call and return a parsed JSON dict."""
        user_parts: List[Dict] = []
        if pdfs:
            for pdf in pdfs:
                data = base64.standard_b64encode(pdf.read_bytes()).decode("ascii")
                user_parts.append({
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": data,
                    },
                })
        user_parts.append({"type": "text", "text": user_prompt})

        try:
            with self.client.messages.stream(
                model=self.model,
                max_tokens=32000,
                system=system_prompt,
                messages=[{"role": "user", "content": user_parts}],
            ) as stream:
                text = stream.get_final_text()
        except Exception as e:
            raise LLMError(f"Claude API call failed: {e}") from e

        return _extract_json(text)

    # ------------------------------------------------------------------ legacy
    def write_script_and_scenes(self, topic, word_count, scene_count, system_prompt, pdfs=None):
        """Legacy single-shot method — not called by the pipeline anymore."""
        user_parts: List[Dict] = []
        if pdfs:
            for pdf in pdfs:
                data = base64.standard_b64encode(pdf.read_bytes()).decode("ascii")
                user_parts.append({
                    "type": "document",
                    "source": {"type": "base64", "media_type": "application/pdf", "data": data},
                })
        user_parts.append({
            "type": "text",
            "text": (
                f"TOPIC: {topic}\n\n"
                f"TARGET WORD COUNT: {word_count}\n"
                f"TARGET SCENE COUNT: {scene_count}\n\n"
                "Produce the JSON object described in the system prompt. "
                "Return ONLY the JSON — no prose, no markdown fences."
            ),
        })
        try:
            resp = self.client.messages.create(
                model=self.model,
                max_tokens=16000,
                system=system_prompt,
                messages=[{"role": "user", "content": user_parts}],
            )
        except Exception as e:
            raise LLMError(f"Claude API call failed: {e}") from e
        text = "".join(block.text for block in resp.content if getattr(block, "type", None) == "text")
        data = _extract_json(text)
        _validate_script_output(data, word_count, scene_count)
        data.setdefault("meta", {})
        data["meta"].update({"model": self.model, "provider": "claude"})
        return data


def _repair_json_string_content(text: str) -> str:
    """Single-pass repair: fix literal control chars AND unescaped double quotes in JSON strings."""
    out: List[str] = []
    in_string = False
    i = 0
    while i < len(text):
        c = text[i]
        if in_string:
            if c == "\\":
                out.append(c)
                i += 1
                if i < len(text):
                    out.append(text[i])
            elif c == '"':
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
    """Strip markdown fences if present, parse JSON, raise LLMError on failure."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    for candidate in (text, _repair_json_string_content(text)):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        for candidate in (m.group(0), _repair_json_string_content(m.group(0))):
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass

    try:
        json.loads(text)
    except json.JSONDecodeError as e:
        raise LLMError(f"Claude did not return valid JSON: {e}\nFirst 500 chars:\n{text[:500]}") from e
    raise LLMError(f"Claude did not return valid JSON.\nFirst 500 chars:\n{text[:500]}")


def _validate_script_output(data: Dict, target_words: int, target_scenes: int) -> None:
    for field in ("title", "full_script", "scenes"):
        if field not in data:
            raise LLMError(f"LLM output missing field: {field}")
    if not isinstance(data["scenes"], list) or not data["scenes"]:
        raise LLMError("LLM returned empty scenes list")
    for i, scene in enumerate(data["scenes"], 1):
        for f in ("narration", "image_prompt"):
            if f not in scene:
                raise LLMError(f"Scene {i} missing field: {f}")
    actual_words = len(data["full_script"].split())
    actual_scenes = len(data["scenes"])
    if actual_words < target_words * 0.6:
        raise LLMError(f"Script too short: {actual_words} words (target {target_words})")
    if actual_scenes < target_scenes * 0.5:
        raise LLMError(f"Too few scenes: {actual_scenes} (target {target_scenes})")


register_llm("claude", ClaudeProvider)
