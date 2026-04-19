"""Video builder. Stitches per-scene (image + audio) pairs into one MP4.

Strategy:
  1. For each scene, measure the MP3 duration with ffprobe.
  2. Build a concat-list format file referencing per-scene .mp4 segments.
  3. Encode each segment from its still image, held for the audio duration, with the audio
     muxed in. Each segment is re-encoded (not stream-copied) so concat works reliably.
  4. Concat all segments with the concat demuxer into final.mp4.

This is the robust path: no complex filter graphs, easy to debug, each intermediate
artifact is on disk. Slower than a single-filter-chain approach but far more reliable
for 200-scene videos.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Dict, List

from .scene_manager import Scene, Manifest


def probe_duration_s(audio_path: Path) -> float:
    """Return duration in seconds for a media file."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "json",
        str(audio_path),
    ]
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"ffprobe failed for {audio_path}: {e.stderr}") from e
    data = json.loads(result.stdout)
    return float(data["format"]["duration"])


def build_segment(scene: Scene, run_dir: Path, video_cfg: Dict) -> Path:
    """Build a single scene segment MP4 from its image + audio."""
    seg_dir = run_dir / "segments"
    seg_dir.mkdir(parents=True, exist_ok=True)
    seg_path = seg_dir / f"scene_{scene.index:03d}.mp4"
    if seg_path.exists():
        return seg_path

    img = Path(scene.image_path)
    aud = Path(scene.audio_path)
    w, h = video_cfg["width"], video_cfg["height"]
    fps = video_cfg["fps"]
    crf = video_cfg.get("crf", 20)
    codec = video_cfg.get("codec", "libx264")
    acodec = video_cfg.get("audio_codec", "aac")
    abitrate = video_cfg.get("audio_bitrate", "192k")

    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-loop", "1", "-i", str(img),
        "-i", str(aud),
        "-c:v", codec,
        "-tune", "stillimage",
        "-pix_fmt", "yuv420p",
        "-crf", str(crf),
        "-r", str(fps),
        "-vf", f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black,setsar=1",
        "-c:a", acodec,
        "-b:a", abitrate,
        "-shortest",
        "-movflags", "+faststart",
        str(seg_path),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"ffmpeg segment build failed (scene {scene.index}): {e.stderr.decode(errors='ignore')}") from e
    return seg_path


def concat_segments(segment_paths: List[Path], out_path: Path) -> Path:
    """Concat pre-built segments into final MP4 using the concat demuxer."""
    list_file = out_path.with_suffix(".list.txt")
    # concat demuxer requires forward-slashes + single-quoted paths
    with list_file.open("w") as f:
        for seg in segment_paths:
            f.write(f"file '{seg.absolute().as_posix()}'\n")
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "concat", "-safe", "0",
        "-i", str(list_file),
        "-c", "copy",
        "-movflags", "+faststart",
        str(out_path),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        # If stream-copy concat fails (usually codec mismatch across segments), re-encode.
        cmd_reencode = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "concat", "-safe", "0",
            "-i", str(list_file),
            "-c:v", "libx264", "-crf", "20",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            str(out_path),
        ]
        try:
            subprocess.run(cmd_reencode, check=True, capture_output=True)
        except subprocess.CalledProcessError as e2:
            raise RuntimeError(f"ffmpeg concat failed (both copy and re-encode): {e2.stderr.decode(errors='ignore')}") from e2
    finally:
        list_file.unlink(missing_ok=True)
    return out_path


def build_final_video(manifest: Manifest, video_cfg: Dict) -> Path:
    """Full build: probe durations, build segments, concat. Returns final mp4 path."""
    run_dir = manifest.run_dir
    scenes = manifest.scenes
    if not scenes:
        raise RuntimeError("Manifest has no scenes")
    if not all(s.audio_done and s.image_done for s in scenes):
        missing = [s.index for s in scenes if not (s.audio_done and s.image_done)]
        raise RuntimeError(f"Cannot build: scenes not complete: {missing[:20]}{'...' if len(missing) > 20 else ''}")

    # Probe durations (fills scene.duration_s for the manifest record)
    for scene in scenes:
        if scene.duration_s is None:
            scene.duration_s = probe_duration_s(Path(scene.audio_path))
            manifest.update_scene(scene)

    # Build per-scene segments
    segment_paths: List[Path] = []
    for i, scene in enumerate(scenes, 1):
        seg = build_segment(scene, run_dir, video_cfg)
        segment_paths.append(seg)
        print(f"[stitch {i}/{len(scenes)}] segment ready")

    # Concat
    final_path = run_dir / "final.mp4"
    concat_segments(segment_paths, final_path)
    print(f"[stitch] final.mp4 written ({final_path.stat().st_size / 1_000_000:.1f} MB)")
    return final_path


def format_duration(total_s: float) -> str:
    m, s = divmod(int(total_s), 60)
    return f"{m}m {s}s"
