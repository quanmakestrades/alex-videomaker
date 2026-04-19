# Providers reference

All per-provider auth, endpoints, quirks, and cost notes. When a provider breaks, start here.

---

## LLM providers

### claude (default)

- **Env:** `ANTHROPIC_API_KEY`
- **Model override:** `ANTHROPIC_MODEL` env var (defaults to `claude-sonnet-4-6`)
- **PDFs:** native support. Up to 100 pages per PDF, ~5 PDFs per request is safe.
- **Cost:** ~$0.15 per 3,500-word script.
- **Keys:** https://console.anthropic.com/settings/keys

### gemini

- **Env:** `GEMINI_API_KEY` (shared with nanobanana + gemini TTS)
- **Model override:** `GEMINI_LLM_MODEL` (defaults to `gemini-2.5-flash`)
- **PDFs:** uploaded via the Files API then passed as content references.
- **Cost:** free tier generous, ~$0.03 per script on paid tier.
- **Keys:** https://aistudio.google.com/app/apikey

### ollama (local)

- **Env:** `OLLAMA_HOST` (default `http://127.0.0.1:11434`), `OLLAMA_MODEL` (default `llama3.1:8b`)
- **PDFs:** no native support — the provider uses `pypdf` to extract text locally.
- **Cost:** zero tokens, electricity only.
- **Perf note:** on Intel MacBook Pro 2019 (no GPU), inference is CPU-bound and slow. A 3,500-word script takes 10–20 minutes. Acceptable as a zero-cost fallback, not a default.

---

## TTS providers

### gemini (default)

- **Env:** `GEMINI_API_KEY`
- **Voice override:** `GEMINI_TTS_VOICE` (default `Kore`). Other voices: `Puck`, `Enceladus`, `Charon`, `Fenrir`, `Aoede`, `Leda`, `Orus`, `Zephyr`.
- **Rate control:** no explicit rate parameter. The provider prepends a natural-language directive ("Read quickly:") when `speaking_rate >= 1.3`. This is approximate — for precise rate, use ElevenLabs or OpenAI TTS.
- **Output:** Gemini returns raw 24kHz PCM. The provider re-encodes to MP3 via ffmpeg.
- **Free tier:** effectively unlimited for this use case (500 req/day on AI Studio, higher via API).

### ai33pro

- **Env:** `AI33PRO_API_KEY`
- **Voice override:** `AI33PRO_VOICE_ID` (default `21m00Tcm4TlvDq8ikWAM` = Rachel)
- **Model override:** `AI33PRO_MODEL_ID` (default `eleven_multilingual_v2`)
- **Endpoint:** `POST https://api.ai33.pro/v1/text-to-speech/{voice_id}?output_format=mp3_44100_128`
- **Auth header:** `xi-api-key: {key}` (ElevenLabs-compatible proxy)
- **Response shapes handled:**
  1. Sync: raw audio bytes (`Content-Type: audio/mpeg`)
  2. Sync: JSON with `audio_url` / `url` / `output` field
  3. Async: JSON with `job_id` + poll via `/v1/text-to-speech/status/{job_id}`
- **Known unknowns:** The docs page (https://ai33.pro/app/api-document) is gated behind premium login. If the response shape differs from the three patterns above, edit `_handle_response` in `videomaker/providers/tts/ai33pro.py`.
- **Speaking rate:** passed opportunistically as `voice_settings.speed`. Server may ignore if unrecognized.
- **Credits:** requires premium credits to access the API key. See https://ai33.pro.

### elevenlabs

- **Env:** `ELEVENLABS_API_KEY`
- **Voice override:** `ELEVENLABS_VOICE_ID`
- **Model override:** `ELEVENLABS_MODEL_ID` (default `eleven_multilingual_v2`)
- **Cost:** ~$0.30 per 3,500-word video at default tier.
- **Keys:** https://elevenlabs.io/app/settings/api-keys

### openai

- **Env:** `OPENAI_API_KEY`
- **Model override:** `OPENAI_TTS_MODEL` (default `gpt-4o-mini-tts`)
- **Voice override:** `OPENAI_TTS_VOICE` (default `nova`). Others: `alloy`, `ash`, `coral`, `echo`, `fable`, `onyx`, `sage`, `shimmer`, `marin`, `cedar`.
- **Rate control:** explicit `speed` param, range 0.25–4.0.
- **Cost:** ~$0.10 per 3,500-word video with gpt-4o-mini-tts.

### xai

- **Env:** `XAI_API_KEY`
- **Voice override:** `XAI_TTS_VOICE` (default `eve`)
- **Rate control:** no explicit param; provider prepends `[faster]` tag when `speaking_rate >= 1.3`.
- **Docs:** https://docs.x.ai/developers/model-capabilities/audio/text-to-speech

---

## Image providers

### nanobanana (default)

- **Env:** `GEMINI_API_KEY`
- **Model override:** `GEMINI_IMAGE_MODEL` (default `gemini-2.5-flash-image`)
  - Free tier: `gemini-2.5-flash-image` (~500/day)
  - Paid: `gemini-3.1-flash-image-preview` (faster, better)
  - Paid 4K: `gemini-3-pro-image-preview`
- **Aspect ratio:** hint is prepended to prompt; Gemini respects reasonably well.
- **Resolution:** native 1024x1024; provider letterboxes to 1920x1080 via Pillow.
- **Known refusal:** real named public figures. Pipeline auto-retries once with name scrubbed.

### dalle

- **Env:** `OPENAI_API_KEY`
- **Model:** `gpt-image-1` (current OpenAI image model; DALL-E 3 is legacy path via `dall-e-3`)
- **Size:** 1024x1024, 1024x1536, or 1536x1024. Provider picks 1536x1024 for 16:9.
- **Cost:** ~$8 per 200-image video. Expensive. Use for hero thumbnails, not full runs.

### replicate

- **Env:** `REPLICATE_API_TOKEN`
- **Model override:** `REPLICATE_IMAGE_MODEL` (default `black-forest-labs/flux-schnell`)
- **Any model on replicate that follows the standard prediction API works. Swap the model id.**
- **Cost:** Flux Schnell ~$0.003/image = ~$0.60 for 200 images.

---

## Email

SMTP auth is standard. For Gmail, use an **app password**, not your login password: https://myaccount.google.com/apppasswords (requires 2FA enabled on the account).

If no SMTP credentials are set but `assistant_email` is configured, the pipeline writes `<run_dir>/email_instruction.json` with the full message payload. An agent with the Gmail MCP tool can pick up that file and send the email itself.
