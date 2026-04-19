"""Abstract base for image generation providers."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional


class ImageProvider(ABC):
    name: str = "base"

    @abstractmethod
    def generate(
        self,
        prompt: str,
        out_path: Path,
        width: int = 1024,
        height: int = 1024,
        aspect_ratio: Optional[str] = None,
    ) -> Path:
        """Generate image from prompt, write PNG to `out_path`. Return path on success."""
        raise NotImplementedError


class ImageError(RuntimeError):
    pass
