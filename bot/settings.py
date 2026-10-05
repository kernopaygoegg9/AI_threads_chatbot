"""Load non-secret settings from config/settings.yaml and secrets from the environment."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from ruamel.yaml import YAML

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = Path(os.environ.get("BOT_CONFIG", ROOT / "config" / "settings.yaml"))

load_dotenv(ROOT / ".env")


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _env_bool(name: str, default: bool) -> bool:
    raw = _env(name)
    if not raw:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Secrets:
    threads_user_id: str
    threads_username: str
    threads_token: str
    threads_app_secret: str
    anthropic_api_key: str
    openai_api_key: str
    gemini_api_key: str
    discord_bot_token: str
    discord_channel_id: str
    discord_reviewer_ids: tuple[str, ...]
    github_repository: str


def load_secrets() -> Secrets:
    return Secrets(
        threads_user_id=_env("THREADS_USER_ID"),
        threads_username=_env("THREADS_USERNAME"),
        threads_token=_env("THREADS_ACCESS_TOKEN"),
        threads_app_secret=_env("THREADS_APP_SECRET"),
        anthropic_api_key=_env("ANTHROPIC_API_KEY"),
        openai_api_key=_env("OPENAI_API_KEY"),
        gemini_api_key=_env("GEMINI_API_KEY"),
        discord_bot_token=_env("DISCORD_BOT_TOKEN"),
        discord_channel_id=_env("DISCORD_CHANNEL_ID"),
        discord_reviewer_ids=tuple(x for x in _env("DISCORD_REVIEWER_IDS").replace(" ", "").split(",") if x),
        github_repository=_env("GITHUB_REPOSITORY"),
    )


def dry_run() -> bool:
    return _env_bool("DRY_RUN", True)


def state_dir() -> Path:
    return Path(_env("STATE_DIR") or ROOT / "state")


def load_config(path: Path | None = None) -> dict[str, Any]:
    with open(path or CONFIG_PATH, encoding="utf-8") as f:
        return YAML(typ="safe").load(f) or {}


@lru_cache(maxsize=1)
def config() -> dict[str, Any]:
    return load_config()


def reload() -> None:
    config.cache_clear()


def tz(cfg: dict[str, Any] | None = None) -> ZoneInfo:
    return ZoneInfo((cfg or config()).get("timezone", "Asia/Taipei"))


def review_mode(kind: str = "post") -> str:
    cfg = config()
    mode = cfg["review"]["mode"]
    if kind == "reply":
        reply_mode = cfg["replies"].get("review_mode", "inherit")
        if reply_mode != "inherit":
            mode = reply_mode
    return mode
