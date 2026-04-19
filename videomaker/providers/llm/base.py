"""Abstract base for LLM providers."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Optional


class LLMProvider(ABC):
    name: str = "base"

    @abstractmethod
    def generate_json(
        self,
        user_prompt: str,
        system_prompt: str,
        pdfs: Optional[List[Path]] = None,
        schema_name: Optional[str] = None,
    ) -> Dict:
        """Make one LLM call and return a parsed JSON dict.

        Implementations must:
        - Accept optional PDFs as primary reference material (Pass 1 only; pass None for Pass 2)
        - Return a parsed Python dict (not a string)
        - Raise LLMError on API failure or unparseable JSON

        schema_name is a hint to structured-output providers (e.g. Gemini) about what
        JSON shape to enforce.  Values: "narration" (Pass 1) or "breakdown" (Pass 2).
        Providers that don't support schemas simply ignore it.
        """
        raise NotImplementedError

    def write_script_and_scenes(
        self,
        topic: str,
        word_count: int,
        scene_count: int,
        system_prompt: str,
        pdfs: Optional[List[Path]] = None,
    ) -> Dict:
        """Legacy single-shot method. Kept for backward compatibility; not called by the pipeline."""
        raise NotImplementedError(
            "write_script_and_scenes is deprecated. Use script_writer.write_script() instead."
        )


class LLMError(RuntimeError):
    pass
