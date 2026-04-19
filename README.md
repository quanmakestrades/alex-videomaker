# videomaker

One-shot YouTube video producer for OpenClaw. Takes a topic, outputs a finished MP4.

**Input:** a topic string (+ optional reference PDFs).
**Output:** a 12–15 minute stick-figure educational video, emailed to your assistant for review.

```
videomaker run --topic "the origins of the Babylonian zodiac"
```

---

## What it does

1. **One LLM call** to Claude (default) produces a ~3,500-word script + 200 scene breakdown in a single structured JSON response.
2. **~200 TTS calls** to Gemini (free tier default) produce per-scene MP3s at 1.45x speaking rate.
3. **~200 image calls** to Nano Banana (Gemini 2.5 Flash Image, free tier default) produce per-scene stick-figure illustrations.
4. **ffmpeg** stitches each image+audio pair into a per-scene segment, then concatenates all segments into `final.mp4` at 1080p/30fps.
5. **SMTP** (or Gmail MCP) emails the final MP4 + script to your assistant.

Total cost on defaults: **~$0.15 per video** (just the Claude call; TTS and images are free tier).

---

## Install

```bash
git clone https://github.com/YOUR_ORG/videomaker.git
cd videomaker
bash setup.sh
videomaker auth setup
```

`setup.sh` verifies ffmpeg, installs Python deps, writes `~/.videomaker/config.yaml` + `~/.videomaker/.env` (chmod 600), and puts `videomaker` on your PATH.

`videomaker auth setup` walks you through adding API keys for whichever providers you'll use. You can skip providers you don't need — the pipeline only requires keys for the three you've configured (default: `claude` + `gemini` + `nanobanana`).

**Prerequisites:**
- Python 3.10+
- ffmpeg + ffprobe (`brew install ffmpeg` on macOS, `apt install ffmpeg` on Linux)

---

## Usage

### Simplest

```bash
videomaker run --topic "how volcanoes actually work"
```

Output lands in `~/.videomaker/runs/<timestamp>/final.mp4`.

### With reference PDFs

```bash
videomaker run \
  --topic "the 1908 Tunguska event" \
  --pdfs /path/to/tunguska-paper.pdf /path/to/eyewitness-accounts.pdf
```

Claude reads the PDFs natively and cites their specifics in the script.

### With assistant handoff

```bash
videomaker run \
  --topic "the 1908 Tunguska event" \
  --assistant-email you@assistant.com
```

SMTP-emails the final MP4 + script.txt. If SMTP isn't configured, writes an `email_instruction.json` the Gmail MCP agent can pick up and send.

### Resume a failed run

If scene 147 of 200 fails (rate limit, key expired, provider down), the run exits and tells you the run id. Fix the issue and resume:

```bash
videomaker run --topic "..." --resume 20260419-110142
```

The manifest tracks per-scene completion atomically — you never re-generate a scene that already succeeded.

### Switch providers

```bash
# persistent
videomaker config set tts elevenlabs
videomaker config set image dalle

# one-run override
videomaker run --topic "..." --tts ai33pro --image replicate
```

See `references/providers.md` for every provider and its auth requirements.

### Dry run (script only, no media)

```bash
videomaker run --topic "..." --dry-run
```

Writes `script.txt` and `script.json` but skips TTS/image/stitch. Useful for iterating on prompts.

---

## Cost model (defaults)

| Step | Calls | Provider | Free tier covers? |
|------|-------|----------|-------------------|
| Script | 1 | Claude Sonnet | No (~$0.15) |
| TTS | ~200 | Gemini TTS | Yes |
| Image | ~200 | Nano Banana (Gemini 2.5 Flash Image) | Yes (~500/day limit) |
| Stitch | 201 ffmpeg calls | local | N/A |
| **Total** | | | **~$0.15 / video** |

Swap providers to tune cost vs. quality (`references/providers.md`).

---

## File layout

```
videomaker/                              ← this repo
├── SKILL.md                             ← OpenClaw agent-facing instructions
├── README.md                            ← you are here
├── setup.sh                             ← installer
├── videomaker.sh                        ← local CLI shim
├── requirements.txt
├── .env.example
│
├── videomaker/                          ← Python package
│   ├── cli.py
│   ├── config.py
│   ├── auth.py
│   ├── pipeline.py                      ← orchestrator
│   ├── script_writer.py
│   ├── scene_manager.py                 ← scene dataclass + manifest I/O
│   ├── video_builder.py                 ← ffmpeg
│   ├── email_handoff.py                 ← SMTP + Gmail MCP handoff
│   └── providers/
│       ├── llm/    {claude, gemini, ollama}
│       ├── tts/    {gemini, ai33pro, elevenlabs, openai, xai}
│       └── image/  {nanobanana, dalle, replicate}
│
├── prompts/
│   ├── script_system.md                 ← the LLM system prompt (the most important file)
│   └── image_style.md                   ← style prefix for every image prompt
│
├── config/
│   └── defaults.yaml                    ← mirror of baked defaults, human-editable
│
└── references/                          ← load as needed
    ├── providers.md
    ├── telegram_wiring.md
    ├── email_templates.md
    ├── ffmpeg_reference.md
    ├── script_dna_extraction.md         ← voice calibration system
    └── strict_scene_split.md            ← 80-line-batch strict mode
```

At runtime, the skill creates `~/.videomaker/`:

```
~/.videomaker/
├── config.yaml                          ← user overrides (copied from defaults.yaml)
├── .env                                 ← API keys (chmod 600)
└── runs/
    └── 20260419-110142/
        ├── run.log
        ├── manifest.json                ← per-scene completion flags
        ├── script.txt                   ← narration only, plain text
        ├── script.json                  ← full LLM output
        ├── audio/scene_001.mp3 ... scene_200.mp3
        ├── images/scene_001.png ... scene_200.png
        ├── segments/scene_001.mp4 ... scene_200.mp4
        └── final.mp4
```

---

## Customization

### Change the narration style

Edit `prompts/script_system.md`. This is the biggest lever. Change the "voice" section, the structural arc, the self-check rules — anything. Next run picks it up.

### Match a specific creator's voice

Use the **Script DNA Extraction** workflow in `references/script_dna_extraction.md`. Pre-extract a Style Codex from 3–5 reference scripts, save it, append it to `prompts/script_system.md` under a `## Voice Codex` section.

### Change the image style

Edit the first paragraph of `prompts/image_style.md`. Only the first paragraph is used as the style prefix — everything after `---` is notes for humans. The prefix is prepended to every image prompt deterministically.

### Per-scene strict fidelity

If you find the LLM's default scene split is skipping lines, use `references/strict_scene_split.md` for the 80-line-batch approach. Higher token cost, perfect fidelity.

### Video quality / file size

Edit `video.crf` in `~/.videomaker/config.yaml`:
- `18` — near-lossless, ~300 MB for 15 min
- `20` — default, ~180 MB
- `23` — good, ~100 MB
- `28` — email-friendly, ~40 MB

See `references/ffmpeg_reference.md` for the full knob list.

---

## Troubleshooting

**"LLM output missing field: scenes"** → the model returned malformed JSON. Rare with Claude; more common with smaller models. Re-run. If persistent, shorten `word_count` or use Claude.

**Images all look wrong** → edit `prompts/image_style.md`. The first paragraph is the prefix applied to every prompt.

**TTS rate-limited** → lower `parallelism.tts_workers` in config.yaml (try 2 or 1). The pipeline will still complete; it just serializes more.

**Nano Banana refuses a scene (named public figure)** → auto-retried once with name scrubbed. If it still fails, that scene gets an error flag in the manifest — edit the prompt in script.json manually and `--resume`.

**ffmpeg concat fails** → the fallback re-encode path in `video_builder.concat_segments` usually handles it. If that also fails, check the log for codec mismatches.

**Run is stuck** → check `~/.videomaker/runs/<run_id>/run.log`. Every step prints `[step N/M] done` lines.

---

## Contributing

Providers, prompts, and references are the easiest extension points. Add a new TTS provider by dropping a file in `videomaker/providers/tts/` that inherits `TTSProvider` and calls `register_tts(name, cls)`. Same pattern for LLM and image.

---

## License

TBD.
