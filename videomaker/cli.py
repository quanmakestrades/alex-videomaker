"""CLI entry point for videomaker.

Subcommands:
  run       Produce a video from a topic.
  config    Show/set defaults.
  auth      Manage provider API keys.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import List, Optional

from . import __version__
from .config import Config, CONFIG_DIR, ENV_FILE


def cmd_run(args: argparse.Namespace) -> int:
    # Lazy import so `videomaker config/auth` work even before providers are configured.
    from .pipeline import Pipeline

    pdfs: List[Path] = []
    if args.pdfs:
        for p in args.pdfs:
            pp = Path(p).expanduser().resolve()
            if not pp.exists():
                print(f"[error] pdf not found: {pp}", file=sys.stderr)
                return 2
            pdfs.append(pp)

    cfg = Config.load()
    # CLI overrides
    if args.llm:
        cfg.providers["llm"] = args.llm
    if args.tts:
        cfg.providers["tts"] = args.tts
    if args.image:
        cfg.providers["image"] = args.image
    if args.word_count:
        cfg.word_count = args.word_count
    if args.scene_count:
        cfg.scene_count = args.scene_count
    if args.assistant_email:
        cfg.assistant_email = args.assistant_email

    pipeline = Pipeline(cfg)
    try:
        result = pipeline.run(
            topic=args.topic,
            pdfs=pdfs,
            resume_run_id=args.resume,
            telegram_chat_id=args.telegram_chat_id,
            dry_run=args.dry_run,
        )
    except KeyboardInterrupt:
        print("\n[interrupt] stopping. run id is printed above — resume with --resume <id>.", file=sys.stderr)
        return 130

    print(json.dumps(result, indent=2))
    return 0


def cmd_config_show(args: argparse.Namespace) -> int:
    cfg = Config.load()
    print(json.dumps(cfg.to_dict(), indent=2))
    return 0


def cmd_config_set(args: argparse.Namespace) -> int:
    cfg = Config.load()
    if args.key in {"llm", "tts", "image"}:
        cfg.providers[args.key] = args.value
    elif args.key == "word_count":
        cfg.word_count = int(args.value)
    elif args.key == "scene_count":
        cfg.scene_count = int(args.value)
    elif args.key == "assistant_email":
        cfg.assistant_email = args.value
    elif args.key == "image_style":
        cfg.image_style = args.value
    else:
        print(f"[error] unknown config key: {args.key}", file=sys.stderr)
        print("valid keys: llm, tts, image, word_count, scene_count, assistant_email, image_style", file=sys.stderr)
        return 2
    cfg.save()
    print(f"[ok] {args.key} = {args.value}")
    return 0


def cmd_auth_setup(args: argparse.Namespace) -> int:
    from .auth import interactive_setup
    return interactive_setup()


def cmd_auth_check(args: argparse.Namespace) -> int:
    from .auth import check_all
    missing = check_all()
    if missing:
        print("[missing keys]")
        for k in missing:
            print(f"  - {k}")
        return 1
    print("[ok] all configured providers have keys present")
    return 0


def cmd_auth_set(args: argparse.Namespace) -> int:
    from .auth import set_key
    set_key(args.var, args.value)
    print(f"[ok] {args.var} stored in {ENV_FILE}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="videomaker",
        description="One-shot YouTube video producer.",
    )
    p.add_argument("--version", action="version", version=f"videomaker {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    # run
    pr = sub.add_parser("run", help="Produce a video from a topic.")
    pr.add_argument("--topic", required=True, help="Video topic (free-form string).")
    pr.add_argument("--pdfs", nargs="*", default=[], help="Reference PDFs (paths).")
    pr.add_argument("--word-count", type=int, help="Override target word count.")
    pr.add_argument("--scene-count", type=int, help="Override target scene count.")
    pr.add_argument("--assistant-email", help="Email for final MP4 handoff.")
    pr.add_argument("--llm", help="Override LLM provider.")
    pr.add_argument("--tts", help="Override TTS provider.")
    pr.add_argument("--image", help="Override image provider.")
    pr.add_argument("--resume", metavar="RUN_ID", help="Resume a failed run.")
    pr.add_argument("--telegram-chat-id", help="If set, progress updates post back to this chat.")
    pr.add_argument("--dry-run", action="store_true", help="Generate script only; skip media.")
    pr.set_defaults(func=cmd_run)

    # config
    pc = sub.add_parser("config", help="Show/set configuration.")
    psub = pc.add_subparsers(dest="config_cmd", required=True)
    ps = psub.add_parser("show", help="Print current config.")
    ps.set_defaults(func=cmd_config_show)
    pset = psub.add_parser("set", help="Set a config value.")
    pset.add_argument("key")
    pset.add_argument("value")
    pset.set_defaults(func=cmd_config_set)

    # auth
    pa = sub.add_parser("auth", help="Manage provider API keys.")
    asub = pa.add_subparsers(dest="auth_cmd", required=True)
    asetup = asub.add_parser("setup", help="Interactive key setup for all providers.")
    asetup.set_defaults(func=cmd_auth_setup)
    acheck = asub.add_parser("check", help="Check that configured providers have keys present.")
    acheck.set_defaults(func=cmd_auth_check)
    aset = asub.add_parser("set", help="Set a single env var (e.g. GEMINI_API_KEY).")
    aset.add_argument("var")
    aset.add_argument("value")
    aset.set_defaults(func=cmd_auth_set)

    return p


def main(argv: Optional[List[str]] = None) -> int:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
