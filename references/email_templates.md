# Email handoff templates

## Default subject / body

Set in `videomaker/email_handoff.py::_build_body`:

> Subject: `[videomaker] {topic} — ready for review`
>
> Body:
> ```
> Hi,
>
> A new video is ready for review.
>
>   Topic: {topic}
>   Title: {title}
>   Run:   {run_id}
>
> Attached:
>   - final.mp4  (the stitched video)
>   - script.txt (the full narration text)
>
> Please review for:
>   - Factual accuracy of the script
>   - Image pacing and clarity
>   - Audio balance and pronunciation issues
>   - Anything off-brand or visually odd
>
> When approved, upload to YouTube with title, description, tags, and thumbnail.
>
> — videomaker (automated)
> ```

## Customizing

### Change the subject
In `~/.videomaker/config.yaml`:
```yaml
email:
  subject_template: "🎬 {title} — QA please ({topic})"
```
Available vars: `{topic}`, `{title}`.

### Change the body
Edit `_build_body` in `videomaker/email_handoff.py`. It's a plain function, returns a string.

For more flexibility without code edits, a future version will load the body from `prompts/email_handoff.md` — not implemented yet.

## SMTP vs Gmail MCP

The pipeline prefers SMTP when credentials are set. If they aren't, it writes `<run_dir>/email_instruction.json`:

```json
{
  "to": "assistant@example.com",
  "from": null,
  "subject": "[videomaker] ...",
  "body": "...",
  "attachments": ["/path/to/final.mp4", "/path/to/script.txt"],
  "note": "SMTP not configured. Send via Gmail MCP tool or configure SMTP_* env vars."
}
```

An OpenClaw agent with the Gmail MCP tool connected can read this file and send the email. Example agent prompt after a run:

> "Check ~/.videomaker/runs/latest/email_instruction.json and send that email via the Gmail MCP tool. Attach the files listed."

## Attachment size

Gmail caps attachments at 25 MB per email. A 15-minute 1080p video at CRF 20 is typically 80–150 MB. Two options:

1. **Upload to Drive, link in the email** (recommended). Modify `_build_body` to upload via the Google Drive MCP and include the share link instead of attaching.
2. **Lower quality.** Set `video.crf: 28` and `video.audio_bitrate: 128k` in config.yaml. Brings a 15-min video to ~30 MB at cost of visible compression.

## Thumbnail

Not currently generated. To add: pick a visually strong scene from the first 30 seconds, save its image as `thumbnail.png`, attach it. A future version will do this automatically using a "thumbnail_image_prompt" field returned by the script writer.
