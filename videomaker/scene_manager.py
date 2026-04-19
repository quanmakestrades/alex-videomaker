"""Scene data model and manifest I/O.

The manifest tracks per-scene completion for idempotent resume. Writes are atomic (temp
file + rename) so a crash mid-write can never corrupt the file.
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class Scene:
    index: int                   # 1-based
    narration: str
    image_prompt: str            # scene content only, style prefix NOT included
    styled_prompt: Optional[str] = None  # after apply_style()
    audio_path: Optional[str] = None
    image_path: Optional[str] = None
    audio_done: bool = False
    image_done: bool = False
    duration_s: Optional[float] = None
    error: Optional[str] = None

    @classmethod
    def from_dict(cls, d: Dict) -> "Scene":
        return cls(**{k: d.get(k) for k in cls.__dataclass_fields__})

    def to_dict(self) -> Dict:
        return asdict(self)


class Manifest:
    """Per-run scene manifest. Backed by <run_dir>/manifest.json."""

    def __init__(self, run_dir: Path):
        self.run_dir = run_dir
        self.path = run_dir / "manifest.json"
        self.data: Dict = {
            "run_id": run_dir.name,
            "topic": None,
            "title": None,
            "scenes": [],
            "providers": {},
            "config": {},
        }

    @classmethod
    def load_or_new(cls, run_dir: Path) -> "Manifest":
        m = cls(run_dir)
        if m.path.exists():
            m.data = json.loads(m.path.read_text())
        return m

    def save(self) -> None:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.data, indent=2))
        os.replace(tmp, self.path)

    @property
    def scenes(self) -> List[Scene]:
        return [Scene.from_dict(s) for s in self.data["scenes"]]

    @scenes.setter
    def scenes(self, value: List[Scene]) -> None:
        self.data["scenes"] = [s.to_dict() for s in value]

    def update_scene(self, scene: Scene) -> None:
        self.data["scenes"][scene.index - 1] = scene.to_dict()
        self.save()

    def incomplete_audio_scenes(self) -> List[Scene]:
        return [s for s in self.scenes if not s.audio_done]

    def incomplete_image_scenes(self) -> List[Scene]:
        return [s for s in self.scenes if not s.image_done]

    def all_done(self) -> bool:
        return all(s.audio_done and s.image_done for s in self.scenes)


def apply_style(scene_prompts: List[str], style_prefix: str) -> List[str]:
    """Prepend style_prefix to each scene's image_prompt."""
    return [f"{style_prefix.strip()}. {p.strip()}" for p in scene_prompts]
