"""API key and auth management.

Keys are stored in ~/.videomaker/.env (chmod 600). Never committed, never printed.
"""
from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Dict, List

from .config import Config, CONFIG_DIR, ENV_FILE


# Each provider declares which env vars it needs.
PROVIDER_KEYS: Dict[str, Dict[str, List[Dict]]] = {
    "llm": {
        "claude":   [{"var": "ANTHROPIC_API_KEY", "url": "https://console.anthropic.com/settings/keys"}],
        "gemini":   [{"var": "GEMINI_API_KEY", "url": "https://aistudio.google.com/app/apikey"}],
        "ollama":   [],  # local, no key
    },
    "tts": {
        "gemini":     [{"var": "GEMINI_API_KEY", "url": "https://aistudio.google.com/app/apikey"}],
        "elevenlabs": [{"var": "ELEVENLABS_API_KEY", "url": "https://elevenlabs.io/app/settings/api-keys"}],
        "openai":     [{"var": "OPENAI_API_KEY", "url": "https://platform.openai.com/api-keys"}],
        "xai":        [{"var": "XAI_API_KEY", "url": "https://console.x.ai"}],
        "ai33pro":    [
            {"var": "AI33PRO_API_KEY", "url": "https://ai33.pro/app/api-document (requires premium credits)", "note": "ai33.pro proxies ElevenLabs; header used is xi-api-key."},
        ],
    },
    "image": {
        "nanobanana": [{"var": "GEMINI_API_KEY", "url": "https://aistudio.google.com/app/apikey"}],
        "dalle":      [{"var": "OPENAI_API_KEY", "url": "https://platform.openai.com/api-keys"}],
        "replicate":  [{"var": "REPLICATE_API_TOKEN", "url": "https://replicate.com/account/api-tokens"}],
    },
    "email": {
        "smtp":   [
            {"var": "SMTP_HOST", "url": "(e.g. smtp.gmail.com)"},
            {"var": "SMTP_PORT", "url": "(e.g. 587)"},
            {"var": "SMTP_USER", "url": "(your email address)"},
            {"var": "SMTP_PASSWORD", "url": "(Gmail: https://myaccount.google.com/apppasswords)"},
        ],
    },
}


def _present(var: str) -> bool:
    value = os.environ.get(var)
    if value is None:
        return False
    normalized = value.strip()
    return normalized not in {"", "null", "None"}


def check_all() -> List[str]:
    """Return list of missing env var names required by currently-configured providers."""
    cfg = Config.load()
    missing: List[str] = []
    for family in ("llm", "tts", "image"):
        provider = cfg.providers.get(family)
        entries = PROVIDER_KEYS.get(family, {}).get(provider, [])
        for entry in entries:
            if entry.get("optional"):
                continue
            var = entry["var"]
            if not _present(var):
                missing.append(f"{var} (required by {family}={provider})")
    # Email is only required when assistant_email is actually configured.
    if cfg.assistant_email and str(cfg.assistant_email).strip() not in {"", "null", "None"}:
        for entry in PROVIDER_KEYS["email"]["smtp"]:
            var = entry["var"]
            if not _present(var):
                missing.append(f"{var} (required for email handoff)")
    return missing


def set_key(var: str, value: str) -> None:
    """Set or update a single env var in ~/.videomaker/.env."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    lines: List[str] = []
    if ENV_FILE.exists():
        lines = ENV_FILE.read_text().splitlines()
    updated = False
    out: List[str] = []
    for line in lines:
        if line.startswith(f"{var}="):
            out.append(f'{var}="{value}"')
            updated = True
        else:
            out.append(line)
    if not updated:
        out.append(f'{var}="{value}"')
    ENV_FILE.write_text("\n".join(out) + "\n")
    ENV_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 600
    os.environ[var] = value


def interactive_setup() -> int:
    """Walk the user through setting keys for currently-configured providers."""
    cfg = Config.load()
    print("videomaker auth setup")
    print("=====================")
    print(f"config: {cfg.providers}")
    print()
    print(f"keys will be stored in: {ENV_FILE} (chmod 600)")
    print()

    needed: List[Dict] = []
    for family in ("llm", "tts", "image"):
        provider = cfg.providers.get(family)
        for entry in PROVIDER_KEYS.get(family, {}).get(provider, []):
            needed.append({**entry, "family": family, "provider": provider})
    if cfg.assistant_email:
        for entry in PROVIDER_KEYS["email"]["smtp"]:
            needed.append({**entry, "family": "email", "provider": "smtp"})

    # Deduplicate by var name (GEMINI_API_KEY might be needed by both tts and image)
    seen = set()
    unique = []
    for n in needed:
        if n["var"] in seen:
            continue
        seen.add(n["var"])
        unique.append(n)

    for n in unique:
        var = n["var"]
        existing = os.environ.get(var, "")
        note = n.get("note", "")
        optional = n.get("optional", False)
        masked = ("*" * 8 + existing[-4:]) if len(existing) >= 4 else ("(not set)" if not existing else "****")
        tag = " [optional]" if optional else ""
        print(f"\n{var}{tag}")
        print(f"  used by: {n['family']}={n['provider']}")
        print(f"  get from: {n['url']}")
        if note:
            print(f"  note: {note}")
        print(f"  current: {masked}")
        try:
            # Use getpass for real keys; fall back to input on systems without it.
            import getpass
            new = getpass.getpass("  new value (leave blank to keep): ")
        except Exception:
            new = input("  new value (leave blank to keep): ")
        if new.strip():
            set_key(var, new.strip())
            print(f"  [ok] {var} stored")

    print("\nDone. Run `videomaker auth check` to verify.")
    return 0
