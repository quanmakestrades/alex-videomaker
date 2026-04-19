"""Email handoff. Sends final MP4 + script to the assistant.

Primary: SMTP (any provider, Gmail app-password being typical).
Fallback hook: if the agent has a Gmail MCP tool wired, the pipeline logs a hint and
emits a structured `email_instruction.json` the agent can pick up and send via MCP.
"""
from __future__ import annotations

import json
import mimetypes
import os
import smtplib
from email.message import EmailMessage
from pathlib import Path
from typing import Dict, List, Optional


def send_handoff(
    to_address: str,
    topic: str,
    title: str,
    run_dir: Path,
    final_mp4: Path,
    script_txt: Path,
    extra_attachments: Optional[List[Path]] = None,
    subject_template: str = "[videomaker] {topic} — ready for review",
) -> bool:
    """Returns True if email was sent via SMTP. Returns False if no SMTP creds are set —
    in that case we write an email_instruction.json for the agent to act on.
    """
    host = os.environ.get("SMTP_HOST")
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASSWORD")
    from_addr = os.environ.get("SMTP_FROM") or user

    subject = subject_template.format(topic=topic, title=title)
    body = _build_body(topic=topic, title=title, run_dir=run_dir)

    if not (host and user and password):
        # Emit an instruction file for the agent to send via Gmail MCP.
        instruction = {
            "to": to_address,
            "from": from_addr,
            "subject": subject,
            "body": body,
            "attachments": [str(final_mp4), str(script_txt)] + [str(p) for p in (extra_attachments or [])],
            "note": "SMTP not configured. Send via Gmail MCP tool or configure SMTP_* env vars.",
        }
        (run_dir / "email_instruction.json").write_text(json.dumps(instruction, indent=2))
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_address
    msg.set_content(body)

    # Attach MP4, script, and any extras
    attachments = [final_mp4, script_txt]
    attachments.extend(extra_attachments or [])
    for path in attachments:
        if not path.exists():
            continue
        ctype, encoding = mimetypes.guess_type(str(path))
        if ctype is None or encoding is not None:
            ctype = "application/octet-stream"
        maintype, subtype = ctype.split("/", 1)
        # Don't inline the 100+ MB MP4 in memory if it's huge — read in binary anyway for SMTP.
        msg.add_attachment(
            path.read_bytes(),
            maintype=maintype,
            subtype=subtype,
            filename=path.name,
        )

    with smtplib.SMTP(host, port) as s:
        s.starttls()
        s.login(user, password)
        s.send_message(msg)
    return True


def _build_body(topic: str, title: str, run_dir: Path) -> str:
    return (
        f"Hi,\n\n"
        f"A new video is ready for review.\n\n"
        f"  Topic: {topic}\n"
        f"  Title: {title}\n"
        f"  Run:   {run_dir.name}\n\n"
        f"Attached:\n"
        f"  - final.mp4  (the stitched video)\n"
        f"  - script.txt (the full narration text)\n\n"
        f"Please review for:\n"
        f"  - Factual accuracy of the script\n"
        f"  - Image pacing and clarity\n"
        f"  - Audio balance and pronunciation issues\n"
        f"  - Anything off-brand or visually odd\n\n"
        f"When approved, upload to YouTube with title, description, tags, and thumbnail.\n\n"
        f"— videomaker (automated)\n"
    )
