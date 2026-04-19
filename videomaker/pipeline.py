"""Pipeline orchestrator.

Responsibilities:
  1. Generate (or resume) a run id + run dir.
  2. Call the LLM once to produce script + scenes.
  3. Apply the image style prefix to each scene.
  4. Generate TTS per scene in parallel (bounded).
  5. Generate images per scene in parallel (bounded).
  6. Stitch with ffmpeg.
  7. Email to assistant.
"""
from __future__ import annotations

import json
import time
import traceback
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional

from .config import Config, RUNS_DIR
from .scene_manager import Scene, Manifest
from .script_writer import write_script, load_prompt
from .providers import get_tts, get_image
from .providers.tts.base import TTSError
from .providers.image.base import ImageError
from . import video_builder
from . import email_handoff


def _new_run_id() -> str:
    """Simple timestamp-based ID. ULID would need a dep; this is fine for humans."""
    return time.strftime("%Y%m%d-%H%M%S")


class Pipeline:
    def __init__(self, cfg: Config):
        self.cfg = cfg

    def run(
        self,
        topic: str,
        pdfs: Optional[List[Path]] = None,
        resume_run_id: Optional[str] = None,
        telegram_chat_id: Optional[str] = None,
        dry_run: bool = False,
    ) -> Dict:
        # 1. Set up run dir
        if resume_run_id:
            run_dir = RUNS_DIR / resume_run_id
            if not run_dir.exists():
                raise RuntimeError(f"No such run: {resume_run_id}")
            print(f"[resume] {run_dir}")
        else:
            run_id = _new_run_id()
            run_dir = RUNS_DIR / run_id
            run_dir.mkdir(parents=True, exist_ok=True)
            print(f"[run] {run_dir}")

        (run_dir / "audio").mkdir(exist_ok=True)
        (run_dir / "images").mkdir(exist_ok=True)

        # 2. Load or generate manifest
        manifest = Manifest.load_or_new(run_dir)
        if not manifest.data.get("topic"):
            manifest.data["topic"] = topic
            manifest.data["providers"] = dict(self.cfg.providers)
            manifest.data["config"] = {
                "word_count": self.cfg.word_count,
                "scene_count": self.cfg.scene_count,
                "image_style": self.cfg.image_style,
            }
            manifest.save()

        # 3. Script (skip if resuming and script already exists)
        script_json_path = run_dir / "script.json"
        if script_json_path.exists() and manifest.scenes:
            print(f"[script] reusing existing script.json ({len(manifest.scenes)} scenes)")
            data = json.loads(script_json_path.read_text())
        else:
            print(f"[script] calling {self.cfg.providers['llm']}... (PDFs: {len(pdfs or [])})")
            data = write_script(
                topic=topic,
                word_count=self.cfg.word_count,
                scene_count=self.cfg.scene_count,
                llm_provider_name=self.cfg.providers["llm"],
                pdfs=pdfs,
            )
            script_json_path.write_text(json.dumps(data, indent=2))
            (run_dir / "script.txt").write_text(data["full_script"])
            manifest.data["title"] = data.get("title")
            # Apply style prefix and build Scene objects
            style_prefix = load_prompt(f"image_style").strip()
            # image_style.md contains:  "<STYLE PREFIX SENTENCE.>" followed by notes for humans.
            # We only take the first paragraph as the actual prefix to append.
            style_prefix = style_prefix.split("\n\n", 1)[0].strip()
            scenes: List[Scene] = []
            for i, s in enumerate(data["scenes"], 1):
                sc = Scene(
                    index=i,
                    narration=s["narration"],
                    image_prompt=s["image_prompt"],
                    styled_prompt=f"{style_prefix} {s['image_prompt'].strip()}",
                    audio_path=str(run_dir / "audio" / f"scene_{i:03d}.mp3"),
                    image_path=str(run_dir / "images" / f"scene_{i:03d}.png"),
                )
                scenes.append(sc)
            manifest.scenes = scenes
            manifest.save()
            print(f"[script] done ({len(scenes)} scenes, {len(data['full_script'].split())} words)")

        if dry_run:
            return {
                "run_id": run_dir.name,
                "run_dir": str(run_dir),
                "title": manifest.data.get("title"),
                "scene_count": len(manifest.scenes),
                "word_count": len(data["full_script"].split()),
                "dry_run": True,
            }

        # 4. TTS in parallel
        tts_name = self.cfg.providers["tts"]
        print(f"[tts] provider={tts_name}, rate={self.cfg.tts['speaking_rate']}x")
        tts_provider = get_tts(tts_name)
        self._run_tts(manifest, tts_provider, telegram_chat_id)

        # 5. Images in parallel
        img_name = self.cfg.providers["image"]
        print(f"[image] provider={img_name}")
        image_provider = get_image(img_name)
        self._run_images(manifest, image_provider, telegram_chat_id)

        # 6. Stitch
        print("[stitch] building final video...")
        final_mp4 = video_builder.build_final_video(manifest, self.cfg.video)

        # 7. Email handoff
        script_txt = run_dir / "script.txt"
        email_sent = False
        assistant_email = self.cfg.assistant_email
        if assistant_email:
            print(f"[email] sending to {assistant_email}...")
            email_sent = email_handoff.send_handoff(
                to_address=assistant_email,
                topic=topic,
                title=manifest.data.get("title") or topic,
                run_dir=run_dir,
                final_mp4=final_mp4,
                script_txt=script_txt,
                subject_template=self.cfg.email["subject_template"],
            )
            if email_sent:
                print("[email] sent")
            else:
                print(f"[email] SMTP not configured — instruction written to {run_dir / 'email_instruction.json'}")
        else:
            print("[email] no assistant_email configured — skipping")

        # Final Telegram nudge
        if telegram_chat_id:
            total_s = sum((s.duration_s or 0) for s in manifest.scenes)
            self._telegram_post(
                telegram_chat_id,
                f"✅ Video done: {manifest.data.get('title') or topic}\n"
                f"Duration: {video_builder.format_duration(total_s)}\n"
                f"Path: {final_mp4}\n"
                f"Email: {'sent' if email_sent else 'not sent — see ' + str(run_dir / 'email_instruction.json')}"
            )

        total_s = sum((s.duration_s or 0) for s in manifest.scenes)
        return {
            "run_id": run_dir.name,
            "run_dir": str(run_dir),
            "title": manifest.data.get("title"),
            "final_mp4": str(final_mp4),
            "script_txt": str(script_txt),
            "duration": video_builder.format_duration(total_s),
            "duration_seconds": total_s,
            "scene_count": len(manifest.scenes),
            "email_sent": email_sent,
            "assistant_email": assistant_email,
        }

    def _run_tts(self, manifest: Manifest, provider, telegram_chat_id: Optional[str]) -> None:
        incomplete = manifest.incomplete_audio_scenes()
        if not incomplete:
            print("[tts] all scenes already have audio — skipping")
            return
        voice_id = self.cfg.tts.get("voice_id")
        rate = self.cfg.tts.get("speaking_rate", 1.0)
        lang = self.cfg.tts.get("language", "en")
        total = len(manifest.scenes)
        n_workers = 1 if getattr(provider, "serial_only", False) else self.cfg.parallelism.get("tts_workers", 4)

        def _do(scene: Scene) -> Scene:
            try:
                provider.synth(scene.narration, Path(scene.audio_path), voice_id=voice_id, speaking_rate=rate, language=lang)
                scene.audio_done = True
                scene.error = None
            except TTSError as e:
                scene.error = f"tts: {e}"
            return scene

        completed = 0
        with ThreadPoolExecutor(max_workers=n_workers) as ex:
            futures = {ex.submit(_do, s): s for s in incomplete}
            for fut in as_completed(futures):
                scene = fut.result()
                manifest.update_scene(scene)
                completed += 1
                status = "done" if scene.audio_done else f"FAIL ({scene.error})"
                print(f"[tts {scene.index}/{total}] {status}")
                if telegram_chat_id and completed % 20 == 0:
                    self._telegram_post(telegram_chat_id, f"[tts] {completed}/{len(incomplete)} done")

        failed = [s.index for s in manifest.scenes if not s.audio_done]
        if failed:
            raise RuntimeError(f"TTS failed for {len(failed)} scenes: {failed[:10]}{'...' if len(failed)>10 else ''}. Fix provider and rerun with --resume {manifest.run_dir.name}")

    def _run_images(self, manifest: Manifest, provider, telegram_chat_id: Optional[str]) -> None:
        incomplete = manifest.incomplete_image_scenes()
        if not incomplete:
            print("[image] all scenes already have images — skipping")
            return
        total = len(manifest.scenes)
        n_workers = self.cfg.parallelism.get("image_workers", 4)
        w = self.cfg.image.get("width", 1024)
        h = self.cfg.image.get("height", 1024)
        aspect = self.cfg.image.get("aspect_ratio", "16:9")

        def _do(scene: Scene) -> Scene:
            try:
                provider.generate(
                    scene.styled_prompt or scene.image_prompt,
                    Path(scene.image_path),
                    width=w, height=h, aspect_ratio=aspect,
                )
                scene.image_done = True
                scene.error = None
            except ImageError as e:
                # One retry with name scrubbing — nanobanana occasionally refuses real public figures
                err_str = str(e).lower()
                if "person" in err_str or "public figure" in err_str or "refus" in err_str:
                    scrubbed = _scrub_named_people(scene.styled_prompt or scene.image_prompt)
                    try:
                        provider.generate(scrubbed, Path(scene.image_path), width=w, height=h, aspect_ratio=aspect)
                        scene.image_done = True
                        scene.error = None
                    except ImageError as e2:
                        scene.error = f"image: {e2}"
                else:
                    scene.error = f"image: {e}"
            return scene

        completed = 0
        with ThreadPoolExecutor(max_workers=n_workers) as ex:
            futures = {ex.submit(_do, s): s for s in incomplete}
            for fut in as_completed(futures):
                scene = fut.result()
                manifest.update_scene(scene)
                completed += 1
                status = "done" if scene.image_done else f"FAIL ({scene.error})"
                print(f"[image {scene.index}/{total}] {status}")
                if telegram_chat_id and completed % 20 == 0:
                    self._telegram_post(telegram_chat_id, f"[image] {completed}/{len(incomplete)} done")

        failed = [s.index for s in manifest.scenes if not s.image_done]
        if failed:
            raise RuntimeError(f"Image gen failed for {len(failed)} scenes: {failed[:10]}{'...' if len(failed)>10 else ''}. Fix provider and rerun with --resume {manifest.run_dir.name}")

    def _telegram_post(self, chat_id: str, text: str) -> None:
        """Post a status update back to Telegram. Requires TELEGRAM_BOT_TOKEN env var.
        Failures here are non-fatal — they just print a warning."""
        import os
        token = os.environ.get("TELEGRAM_BOT_TOKEN")
        if not token:
            return
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode()
        try:
            urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=10)
        except Exception as e:
            print(f"[telegram] post failed (non-fatal): {e}")


def _scrub_named_people(prompt: str) -> str:
    """Replace likely real-person names with generic descriptors. Very naive — good enough
    as a single retry before giving up on a scene."""
    import re
    # Replace sequences of 2+ Capitalized Words with "a figure"
    return re.sub(r"\b(?:[A-Z][a-z]+\s+){1,2}[A-Z][a-z]+\b", "a figure", prompt)
