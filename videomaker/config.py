"""Config loader. Layered: baked defaults → ~/.videomaker/config.yaml → env vars → CLI flags."""
from __future__ import annotations

import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, Optional

try:
    import yaml  # type: ignore
except ImportError:
    yaml = None

CONFIG_DIR = Path(os.environ.get("VIDEOMAKER_HOME", Path.home() / ".videomaker"))
CONFIG_FILE = CONFIG_DIR / "config.yaml"
ENV_FILE = CONFIG_DIR / ".env"
RUNS_DIR = CONFIG_DIR / "runs"

# Baked defaults — the skill ships with sane values so it runs on a fresh install
# with nothing but `videomaker auth setup`.
BAKED_DEFAULTS: Dict = {
    # 3500 words / ~233 wpm (1.45x speaking rate) ≈ 15 min.
    # 200 scenes / 15 min ≈ 4.5 s/scene.
    "word_count": 3500,
    "scene_count": 200,
    "max_words": 5000,
    "max_scenes": 300,
    "image_style": "stick_figure_educational",
    "video": {
        "width": 1920,
        "height": 1080,
        "fps": 30,
        "codec": "libx264",
        "audio_codec": "aac",
        "audio_bitrate": "192k",
        "crf": 20,
        "crossfade_ms": 100,
    },
    "providers": {
        "llm": "claude",
        "tts": "gemini",
        "image": "nanobanana",
    },
    "tts": {
        "voice_id": None,      # provider-specific default is used when None
        "speaking_rate": 1.45, # ~233 wpm → fits 3500 words in ~15 min
        "language": "en",
    },
    "image": {
        "width": 1024,
        "height": 1024,
        "aspect_ratio": "16:9",
    },
    "parallelism": {
        "tts_workers": 4,
        "image_workers": 4,
    },
    "email": {
        "from": None,
        "subject_template": "[videomaker] {topic} — ready for review",
    },
    "assistant_email": None,
}


@dataclass
class Config:
    word_count: int = BAKED_DEFAULTS["word_count"]
    scene_count: int = BAKED_DEFAULTS["scene_count"]
    max_words: int = BAKED_DEFAULTS["max_words"]
    max_scenes: int = BAKED_DEFAULTS["max_scenes"]
    image_style: str = BAKED_DEFAULTS["image_style"]
    video: Dict = field(default_factory=lambda: dict(BAKED_DEFAULTS["video"]))
    providers: Dict = field(default_factory=lambda: dict(BAKED_DEFAULTS["providers"]))
    tts: Dict = field(default_factory=lambda: dict(BAKED_DEFAULTS["tts"]))
    image: Dict = field(default_factory=lambda: dict(BAKED_DEFAULTS["image"]))
    parallelism: Dict = field(default_factory=lambda: dict(BAKED_DEFAULTS["parallelism"]))
    email: Dict = field(default_factory=lambda: dict(BAKED_DEFAULTS["email"]))
    assistant_email: Optional[str] = None

    @classmethod
    def load(cls) -> "Config":
        cfg = cls()
        # Load env from .env file if present
        if ENV_FILE.exists():
            _load_dotenv(ENV_FILE)
        # Layer user config
        if CONFIG_FILE.exists() and yaml is not None:
            with CONFIG_FILE.open("r") as f:
                user = yaml.safe_load(f) or {}
            for k, v in user.items():
                if hasattr(cfg, k):
                    existing = getattr(cfg, k)
                    if isinstance(existing, dict) and isinstance(v, dict):
                        existing.update(v)
                    else:
                        setattr(cfg, k, v)
        # Env overrides for a few common ones
        if os.environ.get("VIDEOMAKER_ASSISTANT_EMAIL"):
            cfg.assistant_email = os.environ["VIDEOMAKER_ASSISTANT_EMAIL"]
        return cfg

    def save(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        if yaml is None:
            raise RuntimeError("PyYAML not installed — run `pip install pyyaml`")
        with CONFIG_FILE.open("w") as f:
            yaml.safe_dump(self.to_dict(), f, sort_keys=False)

    def to_dict(self) -> Dict:
        return asdict(self)


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader. Does NOT overwrite existing env vars.

    Supports inline comments after values and treats blank/placeholder values as empty.
    """
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip()
        if not v:
            parsed = ""
        elif v[0] in ('"', "'"):
            quote = v[0]
            end = v.rfind(quote)
            parsed = v[1:end] if end > 0 else v[1:]
        else:
            parsed = v.split("#", 1)[0].strip()
        if k and k not in os.environ:
            os.environ[k] = parsed
