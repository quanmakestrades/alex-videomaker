# Telegram wiring: Botler → videomaker

How to hook videomaker into an OpenClaw agent that receives Telegram messages.

## The glue

When Botler (or any OpenClaw agent) sees a message starting with `/video`, it should:

1. Extract the topic after `/video `.
2. If the message has PDF attachments, download them to `/tmp/tg-attachments/$CHAT_ID/`.
3. Shell out to `videomaker run` with the topic, PDFs, and chat id.
4. Let videomaker post its own status updates back to the same chat.

## Handler script (bash)

Save this as `~/.openclaw/hooks/videomaker-handler.sh` and wire it to the `/video` command in your agent config:

```bash
#!/usr/bin/env bash
# Invoked by OpenClaw's Telegram handler when a message starts with /video.
# Expects env vars:
#   MESSAGE_TEXT — the full message body
#   CHAT_ID      — the Telegram chat id
#   ATTACHMENTS  — optional, newline-separated paths to downloaded attachments

set -euo pipefail

TOPIC="$(echo "$MESSAGE_TEXT" | sed 's|^/video ||')"
ASSISTANT_EMAIL="${VIDEOMAKER_ASSISTANT_EMAIL:-}"

# Gather PDF attachments if any
PDF_FLAGS=()
if [ -n "${ATTACHMENTS:-}" ]; then
  while IFS= read -r path; do
    if [[ "$path" =~ \.pdf$ ]]; then
      PDF_FLAGS+=(--pdfs "$path")
    fi
  done <<< "$ATTACHMENTS"
fi

# Run in background so the handler returns immediately — video gen takes 5-15 min.
videomaker run \
  --topic "$TOPIC" \
  ${ASSISTANT_EMAIL:+--assistant-email "$ASSISTANT_EMAIL"} \
  --telegram-chat-id "$CHAT_ID" \
  "${PDF_FLAGS[@]}" \
  > "/tmp/videomaker-${CHAT_ID}-$(date +%s).log" 2>&1 &

echo "Kicked off video. You'll get updates here every ~20 scenes."
```

## OpenClaw agent config

In the agent's SOUL.md or skill config, add:

```yaml
tools:
  - name: video_maker
    trigger: "^/video\\s+"
    handler: ~/.openclaw/hooks/videomaker-handler.sh
    description: "Produce a 15-min YouTube video from a topic. Usage: /video <topic>"
```

Adjust path/syntax for whichever OpenClaw version you're on — verify against current docs before editing (`openclaw tools.profile list`, etc.).

## Progress updates

When videomaker is invoked with `--telegram-chat-id`, it posts status messages to that chat every 20 completed scenes:

```
[tts] 40/200 done
[tts] 60/200 done
...
[tts] 200/200 done
[image] 20/200 done
...
[image] 200/200 done
✅ Video done: The Origins of the Babylonian Zodiac
Duration: 14m 52s
Path: /home/quan/.videomaker/runs/20260419-110142/final.mp4
Email: sent
```

This requires `TELEGRAM_BOT_TOKEN` in the env (same token Botler uses). Updates are fire-and-forget — if Telegram is unreachable, the run continues without blocking.

## Failure mode

If videomaker exits non-zero, the last 40 lines of `run.log` are what the agent should relay. The Telegram handler script above just logs the exit — you can extend it to tail the log and post on failure:

```bash
# At the end of videomaker-handler.sh, replace the `&` background launch with:
if ! videomaker run ...; then
  LOG=$(tail -40 ~/.videomaker/runs/*/run.log | tail -40)
  # Post to Telegram via bot API
  curl -s "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/sendMessage" \
    --data-urlencode "chat_id=$CHAT_ID" \
    --data-urlencode "text=❌ videomaker failed:
\`\`\`
$LOG
\`\`\`" \
    --data-urlencode "parse_mode=Markdown" >/dev/null
fi
```
