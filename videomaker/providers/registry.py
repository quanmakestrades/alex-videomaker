"""Provider registry. Kept in its own module so concrete provider files can import
register_llm/register_tts/register_image without triggering the family __init__.py
(which would cause a circular import)."""
from __future__ import annotations

from typing import Dict, Type, TYPE_CHECKING

if TYPE_CHECKING:
    from .llm.base import LLMProvider
    from .tts.base import TTSProvider
    from .image.base import ImageProvider


_LLM_REGISTRY: Dict[str, Type] = {}
_TTS_REGISTRY: Dict[str, Type] = {}
_IMAGE_REGISTRY: Dict[str, Type] = {}


def register_llm(name: str, cls) -> None:
    _LLM_REGISTRY[name] = cls


def register_tts(name: str, cls) -> None:
    _TTS_REGISTRY[name] = cls


def register_image(name: str, cls) -> None:
    _IMAGE_REGISTRY[name] = cls


def get_llm(name: str, **kwargs):
    _lazy_load_llm()
    if name not in _LLM_REGISTRY:
        raise ValueError(f"Unknown LLM provider: {name}. Known: {sorted(_LLM_REGISTRY)}")
    return _LLM_REGISTRY[name](**kwargs)


def get_tts(name: str, **kwargs):
    _lazy_load_tts()
    if name not in _TTS_REGISTRY:
        raise ValueError(f"Unknown TTS provider: {name}. Known: {sorted(_TTS_REGISTRY)}")
    return _TTS_REGISTRY[name](**kwargs)


def get_image(name: str, **kwargs):
    _lazy_load_image()
    if name not in _IMAGE_REGISTRY:
        raise ValueError(f"Unknown image provider: {name}. Known: {sorted(_IMAGE_REGISTRY)}")
    return _IMAGE_REGISTRY[name](**kwargs)


def _lazy_load_llm() -> None:
    from . import llm  # noqa: F401  — triggers registrations


def _lazy_load_tts() -> None:
    from . import tts  # noqa: F401


def _lazy_load_image() -> None:
    from . import image  # noqa: F401
