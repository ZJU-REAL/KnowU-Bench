"""Runtime proxy configuration helpers."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


DEFAULT_SMART_PROXY_PORT = 8118
DEFAULT_ANDROID_SMART_PROXY_HOST = "10.0.2.2"

_DOTENV_LOADED = False


def load_proxy_dotenv() -> None:
    """Load proxy settings from .env without overriding existing env vars."""
    global _DOTENV_LOADED
    if _DOTENV_LOADED:
        return

    candidates: list[Path] = []
    if env_file := os.getenv("SMART_PROXY_ENV_FILE"):
        candidates.append(Path(env_file))
    candidates.extend([Path("/app/service/.env"), Path.cwd() / ".env"])

    seen: set[Path] = set()
    for path in candidates:
        resolved = path.expanduser()
        if resolved in seen:
            continue
        seen.add(resolved)
        if resolved.exists():
            load_dotenv(resolved, override=False)

    _DOTENV_LOADED = True


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value else default


def smart_proxy_port() -> int:
    load_proxy_dotenv()
    return _env_int("SMART_PROXY_PORT", DEFAULT_SMART_PROXY_PORT)


def android_smart_proxy() -> str:
    """Return the Android-visible smart proxy endpoint."""
    load_proxy_dotenv()
    host = os.getenv("ANDROID_SMART_PROXY_HOST", DEFAULT_ANDROID_SMART_PROXY_HOST)
    return f"{host}:{smart_proxy_port()}"


def android_proxy_setting_command() -> str:
    return f"settings put global http_proxy {android_smart_proxy()}"
