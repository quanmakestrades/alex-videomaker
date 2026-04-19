"""Abstract base for TTS providers."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional


class TTSProvider(ABC):
    name: str = "base"
    # If True, pipeline must serialize calls (no thread pool).
    serial_only: bool = False

    @abstractmethod
    def synth(
        self,
        text: str,
        out_path: Path,
        voice_id: Optional[str] = None,
        speaking_rate: float = 1.0,
        language: str = "en",
    ) -> Path:
        """Synthesize `text` to an MP3 at `out_path`. Return the path on success.

        Must raise TTSError on failure.
        """
        raise NotImplementedError


class TTSError(RuntimeError):
    pass
