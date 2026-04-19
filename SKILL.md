---
name: videomaker
version: 0.1.0
description: |
  Produces a 12–15 minute YouTube video (stick-figure educational style) from a single topic prompt.
  Triggered by phrases like "make a video about X", "produce a video on Y", "videomaker + topic",
  or a Telegram message beginning with /video. Writes a narrated script (~2,500 words), splits it
  into ~200 scene beats, generates AI voiceover + one AI image per beat, stitches everything into
  an MP4 with ffmpeg, and emails the result to the user's assistant for QA before posting.
  Use this skill whenever the user asks for a video, YouTube video, explainer video, educational
  video, or video essay — even if they don't explicitly say "videomaker". Do NOT use for short
  clips under 3 minutes — use the clip-maker skill instead.
triggers:
  - "make a video about *"
  - "produce a video on *"
  - "videomaker *"
  - "/video *"
  - "new youtube video *"
inputs:
  topic: string (required)
  reference_pdfs: list<path> (optional — passed as --pdfs /path/*.pdf)
  word_count: int (optional, default 2500)
  scene_count: int (optional, default 200)
  assistant_email: string (optional, falls back to config)
outputs:
  final_mp4: path to stitched video
  script_txt: path to full narration script
  handoff_email: boolean — true if email was sent
providers:
  llm: claude | gemini | ollama          # default claude
  tts: gemini | ai33pro | elevenlabs | openai | xai   # default gemini
  image: nanobanana | dalle | replicate   # default nanobanana
---

# videomaker

**One-shot YouTube video producer.** Takes a topic, outputs a finished MP4 ready for your assistant to polish and post.

## When to trigger this skill

Trigger whenever the user asks for anything that produces a multi-minute narrated video with AI voiceover and AI images. Common phrasings:

- "make a video about [topic]"
- "produce a YouTube video on [topic]"
- "/video [topic]" (Telegram)
- "new video, topic is [topic]"

Do **not** trigger for:
- Short social clips (< 3 min) — use `clip-maker` skill
- Live-action or screen-recording video — use `remotion` or `screenshot-to-video` skills
- Audio-only podcasts — use `podcast-maker` skill

## How to run

From the OpenClaw agent shell:

```bash
videomaker run --topic "the origins of the Babylonian zodiac" \
  --pdfs /mnt/refs/zodiac-paper.pdf /mnt/refs/babylonian-astro.pdf \
  --assistant-email assistant@example.com
```

From Telegram (if bot handler is wired to this skill — see `references/telegram_wiring.md`):

```
/video the origins of the Babylonian zodiac
```

(Any PDFs attached to the Telegram message are forwarded as `--pdfs`.)

## What happens (pipeline overview)

```
topic + PDFs
    │
    ▼
┌──────────────────────────────────────────────┐
│ 1. script_writer  →  LLM (Claude by default) │
│    Single LLM call. Returns structured JSON: │
│      - full narration (~2,500 words)         │
│      - 200 scenes, each with:                │
│         · narration chunk                    │
│         · image_prompt (style-baked-in)      │
└──────────────────────────────────────────────┘
    │
    ├──► tts_provider (parallel)   → scene_001.mp3 … scene_200.mp3
    ├──► image_provider (parallel) → scene_001.png … scene_200.png
    │
    ▼
┌──────────────────────────────────────────────┐
│ 2. video_builder  →  ffmpeg concat           │
│    Per-scene image × matching audio duration │
│    + optional bgm bed + 100ms crossfades     │
│    → final.mp4 (1080p, 30fps, h264, AAC)     │
└──────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────┐
│ 3. email_handoff  →  SMTP / Gmail API        │
│    Attaches final.mp4 + script.txt + thumb   │
│    Sends to assistant_email with standard    │
│    handoff template                          │
└──────────────────────────────────────────────┘
```

**Only one LLM call** in the entire pipeline (the script). Everything else is deterministic Python + API calls to TTS/image providers. This is intentional — conserves tokens for users on cloud compute.

## Provider model

Providers are swappable like OpenClaw's own model layer. Three provider families:

| Family | Default   | Alternates                              | Why default |
|--------|-----------|-----------------------------------------|-------------|
| LLM    | claude    | gemini, ollama                          | Best long-form script quality, PDF-native |
| TTS    | gemini    | ai33pro, elevenlabs, openai, xai        | Free tier, same API key as nanobanana |
| Image  | nanobanana| dalle, replicate                        | ~500 free images/day, same key as Gemini TTS |

**Check current provider config:**
```bash
videomaker config show
```

**Switch provider:**
```bash
videomaker config set tts elevenlabs
videomaker config set image dalle
```

**Set API keys (interactive):**
```bash
videomaker auth setup
```

This walks the user through adding keys for whichever providers they want enabled. Keys are stored in `~/.videomaker/.env` with `chmod 600`. Never in the repo. Never in chat output.

See `references/providers.md` for full auth details per provider.

## Defaults (stored in `config/defaults.yaml`)

```yaml
word_count: 2500          # ~15 min at 160 wpm. User can override.
scene_count: 200          # ~4.5s per scene
video:
  width: 1920
  height: 1080
  fps: 30
  codec: libx264
  audio_codec: aac
  audio_bitrate: 192k
providers:
  llm: claude
  tts: gemini
  image: nanobanana
image_style: stick_figure_educational   # maps to prompts/image_style.md
```

The user can override any of these per-run with CLI flags or persistently with `videomaker config set`.

## Style — the "stick figure educational" look

Every image prompt gets a style prefix appended that forces the reference aesthetic: simple stick-figure characters, clean line art, occasional detailed illustrated backgrounds (Primer / Kurzgesagt / Minute Physics hybrid). See `prompts/image_style.md` for the exact prefix string and examples.

The LLM is instructed to generate image prompts that describe **scene content only** — the style prefix is auto-prepended by `scene_manager.apply_style()` so the user (or agent) never has to think about it.

## Agent instructions — step by step

When you (the agent) receive a trigger, execute in this order:

1. **Parse the trigger.** Extract `topic` from the user message. If PDFs are attached, save them to `/tmp/videomaker-refs/<run-id>/` and pass paths via `--pdfs`.

2. **Check provider readiness.** Run `videomaker auth check`. If any configured provider is missing its key, ask the user once:
   > "You have `tts=gemini` configured but `GEMINI_API_KEY` isn't set. Want me to run `videomaker auth setup` first?"
   Don't guess or proceed without keys — the run will waste time and fail partway.

3. **Kick off the run.** Invoke:
   ```bash
   videomaker run --topic "<topic>" [--pdfs path/to/*.pdf] --assistant-email "<email>"
   ```
   Tail the log at `~/.videomaker/runs/<run-id>/run.log`. The script prints progress to stdout in plain lines (`[script] done`, `[tts 47/200] done`, `[image 193/200] done`, `[stitch] done`).

4. **Report back.** When the run exits 0, message the user in Telegram:
   > Video done. Final MP4: `~/.videomaker/runs/<run-id>/final.mp4`. Emailed to `<assistant_email>`. Script: `~/.videomaker/runs/<run-id>/script.txt`. Duration: `<x> min <y> sec`.

   If the run exits non-zero, tail the last 40 lines of `run.log` and post them — do not speculate about the cause.

5. **Do NOT retry automatically** on failure. The pipeline has idempotent resume built in — if a run fails at scene 127 of 200, the user can re-run with `--resume <run-id>` and it picks up from scene 127. Tell them that option exists; let them decide.

## Resume & idempotency

Every run gets a ULID and its own directory:

```
~/.videomaker/runs/01HXYZ.../
├── run.log
├── manifest.json        ← scene list + completion flags (updated atomically)
├── script.txt
├── script.json          ← LLM output
├── audio/
│   ├── scene_001.mp3
│   └── …
├── images/
│   ├── scene_001.png
│   └── …
└── final.mp4            ← only exists after successful stitch
```

`manifest.json` tracks per-scene completion. `videomaker run --resume <run-id>` reads it, skips already-complete scenes, and restarts from the first incomplete one. This is critical for cloud-compute users on metered tokens or credits.

## Telegram intake contract

If OpenClaw's Telegram handler is routing messages to this skill, it should pass them as:

```bash
videomaker run \
  --topic "$(echo "$MESSAGE_TEXT" | sed 's|^/video ||')" \
  --pdfs $(ls /tmp/tg-attachments/$CHAT_ID/*.pdf 2>/dev/null) \
  --assistant-email "$ASSISTANT_EMAIL" \
  --telegram-chat-id "$CHAT_ID"
```

The `--telegram-chat-id` flag enables progress updates back to the same Telegram chat every 20 scenes. See `references/telegram_wiring.md` for the full Botler → videomaker glue.

## Token budget

For a default 2,500-word / 200-scene run:

| Call | Input | Output | Approx cost (Claude Sonnet 4.7) |
|------|-------|--------|--------------------------------|
| script_writer | ~5k tokens (topic + PDFs + system) | ~8k tokens (script + scene JSON) | ~$0.15 |
| **Total LLM** | | | **~$0.15** |

Plus ~200 image generations (nanobanana free tier covers this) and ~200 TTS calls (Gemini TTS free tier covers this). **Default config is ~$0.15 per video.**

If you swap in ElevenLabs TTS: add ~$0.30/video. DALL-E 3: add ~$8/video. Claude → Gemini LLM: drops LLM cost to ~$0.03.

## Safety / limits

- Hard cap: 300 scenes per run (prevents runaway generation).
- Hard cap: 4,000 words script (prevents runaway token burn).
- Skill will **refuse** topics that trip the LLM's safety filter — it returns a structured error, not an apology string. The agent should relay the refusal verbatim, not retry with different wording.
- Nanobanana / Gemini image occasionally refuses prompts depicting real public figures by name. The skill auto-retries those scenes with the name replaced by a generic descriptor ("a 19th-century astronomer") once; if it fails again it drops the scene and renumbers.

## Files in this skill

- `videomaker/cli.py` — entry point. Argparse, dispatches to pipeline.
- `videomaker/pipeline.py` — orchestrator. Runs script → media gen → stitch → email.
- `videomaker/script_writer.py` — single LLM call. Returns structured JSON.
- `videomaker/scene_manager.py` — scene data model, style application, manifest I/O.
- `videomaker/video_builder.py` — ffmpeg stitching. Concat demuxer, per-scene timing.
- `videomaker/email_handoff.py` — SMTP via Gmail app password. (MCP Gmail tool also supported.)
- `videomaker/providers/` — pluggable TTS, image, LLM providers. All inherit from `base.py`.
- `prompts/script_system.md` — the big Claude system prompt. Structured-output JSON schema.
- `prompts/image_style.md` — the stick-figure style prefix.
- `config/defaults.yaml` — all tunable defaults.
- `scripts/bootstrap_keys.sh` — interactive `videomaker auth setup` script.

## References (load as needed)

- `references/providers.md` — per-provider auth, endpoints, known quirks
- `references/telegram_wiring.md` — how to hook Botler → videomaker
- `references/email_templates.md` — handoff email template variations
- `references/ffmpeg_reference.md` — the exact ffmpeg commands used, with explanations

---

**Golden rule:** if the skill fails, surface the log and stop. Do not guess, do not hallucinate next steps, do not suggest CLI commands that aren't verified in this SKILL.md or its references.
