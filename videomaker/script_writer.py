"""Script writer — two-pass flow.

Pass 1: generate title + full narration prose.
Pass 2: split the narration into scenes and generate image prompts.
Assembly: combine into the final dict expected by the rest of the pipeline.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from .providers import get_llm
from .providers.llm.base import LLMError


# prompts dir is a sibling of the package.
_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def load_prompt(name: str) -> str:
    """Load a prompt file by basename (without .md)."""
    path = _PROMPTS_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt not found: {path}")
    return path.read_text()


def write_script(
    topic: str,
    word_count: int,
    scene_count: int,
    llm_provider_name: str,
    pdfs: Optional[List[Path]] = None,
) -> Dict:
    """Two-pass script generation.

    Returns a dict shaped as:
        {
          "title": str,
          "full_script": str,
          "scenes": [{"narration": str, "image_prompt": str}, ...],
          "meta": {"word_count": int, "scene_count": int, "model": str, "provider": str}
        }
    """
    provider = get_llm(llm_provider_name)

    # ── Pass 1: narration script ──────────────────────────────────────────────
    word_count_min = int(word_count * 0.90)
    word_count_max = int(word_count * 1.10)
    narration_system = (
        load_prompt("narration_system")
        .replace("{{WORD_COUNT}}", str(word_count))
        .replace("{{WORD_COUNT_MIN}}", str(word_count_min))
        .replace("{{WORD_COUNT_MAX}}", str(word_count_max))
    )
    narration_prompt = (
        f"TOPIC: {topic}\n\n"
        f"TARGET WORD COUNT: {word_count} (minimum {word_count_min} words)\n\n"
        "Return ONLY the JSON object described in the system prompt. "
        "No prose, no markdown fences."
    )

    print(f"[script] pass 1 — generating narration for: {topic!r}")
    narration_data = provider.generate_json(
        narration_prompt, narration_system, pdfs=pdfs, schema_name="narration"
    )

    # Handle refusal
    if "error" in narration_data and narration_data["error"] == "refusal":
        raise LLMError(f"Topic refused by LLM: {narration_data.get('reason', 'no reason given')}")

    _require_fields(narration_data, ("title", "full_script"), "pass-1 narration")
    title = str(narration_data["title"]).strip()
    full_script = str(narration_data["full_script"]).strip()

    if not title:
        raise LLMError("Pass-1 returned empty title")
    if not full_script:
        raise LLMError("Pass-1 returned empty full_script")

    actual_words = len(full_script.split())

    # If the script is shorter than 80% of target, attempt one expansion pass.
    if actual_words < word_count * 0.80:
        print(
            f"[script] pass 1 too short ({actual_words} words, need {word_count_min}); "
            "attempting expansion..."
        )
        expand_prompt = (
            f"The script you wrote has {actual_words} words but needs at least {word_count_min}. "
            f"Here is your current script:\n\nTITLE: {title}\n\nSCRIPT:\n{full_script}\n\n"
            f"Expand it to at least {word_count_min} words by: adding more specific examples, "
            "deeper explanations of each mechanism, concrete numbers and names, "
            "additional narrative beats, and richer transitions. "
            "Keep the same title and voice. "
            "Return ONLY the JSON object with the expanded full_script. "
            "No prose, no markdown fences."
        )
        try:
            expanded = provider.generate_json(expand_prompt, narration_system, schema_name="narration")
            if "error" not in expanded:
                exp_title = str(expanded.get("title", title)).strip() or title
                exp_script = str(expanded.get("full_script", "")).strip()
                exp_words = len(exp_script.split())
                if exp_words > actual_words:
                    title = exp_title
                    full_script = exp_script
                    actual_words = exp_words
                    print(f"[script] expansion done — {actual_words} words")
        except Exception as e:
            print(f"[script] expansion failed ({e}), using original")

    if actual_words < word_count * 0.6:
        raise LLMError(
            f"Pass-1 script too short: {actual_words} words (target {word_count}). "
            "Try again or reduce word_count."
        )

    print(f"[script] pass 1 done — {actual_words} words, title: {title!r}")

    # ── Pass 2: scene breakdown ───────────────────────────────────────────────
    breakdown_system = (
        load_prompt("scene_breakdown_system")
        .replace("{{SCENE_COUNT}}", str(scene_count))
    )
    breakdown_prompt = (
        f"TITLE: {title}\n\n"
        f"FULL SCRIPT:\n{full_script}\n\n"
        f"TARGET SCENE COUNT: {scene_count}\n\n"
        "Break the script into scenes as described in the system prompt. "
        "Return ONLY the JSON object. No prose, no markdown fences."
    )

    print(f"[script] pass 2 — generating scene breakdown ({scene_count} scenes)")
    breakdown_data = provider.generate_json(
        breakdown_prompt, breakdown_system, schema_name="breakdown"
    )

    _require_fields(breakdown_data, ("scenes",), "pass-2 breakdown")
    scenes = breakdown_data["scenes"]

    if not isinstance(scenes, list) or not scenes:
        raise LLMError("Pass-2 returned empty scenes list")

    # Normalize common field-name variations before strict validation
    scenes = [_normalize_scene(s) for s in scenes]

    for i, scene in enumerate(scenes, 1):
        for field in ("narration", "image_prompt"):
            if field not in scene:
                raise LLMError(f"Pass-2 scene {i} missing field: {field!r}")

    actual_scenes = len(scenes)
    if actual_scenes < scene_count * 0.5:
        raise LLMError(
            f"Pass-2 too few scenes: {actual_scenes} (target {scene_count}). "
            "Try again or reduce scene_count."
        )

    print(f"[script] pass 2 done — {actual_scenes} scenes")

    # ── Assemble ──────────────────────────────────────────────────────────────
    return {
        "title": title,
        "full_script": full_script,
        "scenes": scenes,
        "meta": {
            "word_count": actual_words,
            "scene_count": actual_scenes,
            "model": getattr(provider, "model", llm_provider_name),
            "provider": llm_provider_name,
        },
    }


def _require_fields(data: Dict, fields, context: str) -> None:
    for f in fields:
        if f not in data:
            raise LLMError(f"{context} output missing required field: {f!r}")


# Alternative field names that some models use instead of the canonical ones.
_NARRATION_ALIASES = ("text", "script", "content", "dialogue", "voiceover")
_IMAGE_ALIASES = ("image", "prompt", "visual", "description", "visual_description", "scene_description")


def _normalize_scene(scene: Dict) -> Dict:
    """Map common field-name variants to the canonical narration/image_prompt names."""
    if not isinstance(scene, dict):
        return scene
    out = dict(scene)
    if "narration" not in out:
        for alias in _NARRATION_ALIASES:
            if alias in out:
                out["narration"] = out.pop(alias)
                break
    if "image_prompt" not in out:
        for alias in _IMAGE_ALIASES:
            if alias in out:
                out["image_prompt"] = out.pop(alias)
                break
    return out
