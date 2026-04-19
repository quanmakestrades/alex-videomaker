"""Ollama local LLM provider."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Dict, List, Optional

import urllib.request
import urllib.error

from .base import LLMProvider, LLMError
from ..registry import register_llm
from .anthropic_claude import _extract_json, _validate_script_output


DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.1:8b")
DEFAULT_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(self, model: Optional[str] = None, host: Optional[str] = None):
        self.model = model or DEFAULT_MODEL
        self.host = host or DEFAULT_HOST

    def generate_json(
        self,
        user_prompt: str,
        system_prompt: str,
        pdfs: Optional[List[Path]] = None,
        schema_name: Optional[str] = None,  # unused by Ollama; accepted for interface compat
    ) -> Dict:
        """Make one Ollama call and return a parsed JSON dict."""
        if pdfs:
            extracted = []
            for pdf in pdfs:
                try:
                    from pypdf import PdfReader  # type: ignore
                except ImportError as e:
                    raise LLMError("pypdf not installed (needed for Ollama + PDFs). `pip install pypdf`") from e
                reader = PdfReader(str(pdf))
                txt = "\n\n".join(page.extract_text() or "" for page in reader.pages)
                extracted.append(f"--- {pdf.name} ---\n{txt}")
            reference_text = "\n\n".join(extracted)
            full_prompt = f"REFERENCE MATERIAL:\n{reference_text}\n\n{user_prompt}"
        else:
            full_prompt = user_prompt

        payload = {
            "model": self.model,
            "system": system_prompt,
            "prompt": full_prompt,
            "stream": False,
            "format": "json",
            "options": {"num_predict": 32000, "temperature": 0.7},
        }
        req = urllib.request.Request(
            f"{self.host}/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=600) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as e:
            raise LLMError(f"Ollama call failed ({self.host}): {e}") from e

        text = body.get("response", "")
        return _extract_json(text)

    # ------------------------------------------------------------------ legacy
    def write_script_and_scenes(self, topic, word_count, scene_count, system_prompt, pdfs=None):
        """Legacy single-shot method — not called by the pipeline anymore."""
        if pdfs:
            extracted = []
            for pdf in pdfs:
                try:
                    from pypdf import PdfReader  # type: ignore
                except ImportError as e:
                    raise LLMError("pypdf not installed. `pip install pypdf`") from e
                reader = PdfReader(str(pdf))
                txt = "\n\n".join(page.extract_text() or "" for page in reader.pages)
                extracted.append(f"--- {pdf.name} ---\n{txt}")
            reference_text = "\n\n".join(extracted)
            user_msg = (
                f"REFERENCE MATERIAL:\n{reference_text}\n\n"
                f"TOPIC: {topic}\n"
                f"TARGET WORD COUNT: {word_count}\n"
                f"TARGET SCENE COUNT: {scene_count}\n\n"
                "Return ONLY the JSON object described in the system prompt."
            )
        else:
            user_msg = (
                f"TOPIC: {topic}\n"
                f"TARGET WORD COUNT: {word_count}\n"
                f"TARGET SCENE COUNT: {scene_count}\n\n"
                "Return ONLY the JSON object described in the system prompt."
            )

        payload = {
            "model": self.model,
            "system": system_prompt,
            "prompt": user_msg,
            "stream": False,
            "format": "json",
            "options": {"num_predict": 16000, "temperature": 0.7},
        }
        req = urllib.request.Request(
            f"{self.host}/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=600) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as e:
            raise LLMError(f"Ollama call failed ({self.host}): {e}") from e
        text = body.get("response", "")
        data = _extract_json(text)
        _validate_script_output(data, word_count, scene_count)
        data.setdefault("meta", {})
        data["meta"].update({"model": self.model, "provider": "ollama"})
        return data


register_llm("ollama", OllamaProvider)
