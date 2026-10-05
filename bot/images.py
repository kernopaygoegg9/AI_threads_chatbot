"""Image generation behind a provider switch, plus public hosting for Threads (needs an image URL)."""

from __future__ import annotations

import base64
from pathlib import Path

import requests

from . import settings
from .store import Store

TIMEOUT = 180


class ImageError(RuntimeError):
    pass


def _full_prompt(scene: str) -> str:
    style = settings.config()["image"].get("style", "").strip()
    return f"{style}\n\n畫面：{scene}" if style else scene


def _openai(prompt: str) -> bytes:
    cfg = settings.config()["image"]
    key = settings.load_secrets().openai_api_key
    if not key:
        raise ImageError("OPENAI_API_KEY is not set")
    r = requests.post(
        "https://api.openai.com/v1/images/generations",
        headers={"Authorization": f"Bearer {key}"},
        json={
            "model": cfg["openai_model"],
            "prompt": prompt,
            "size": cfg.get("size", "1024x1024"),
            "quality": cfg.get("openai_quality", "medium"),
            "n": 1,
        },
        timeout=TIMEOUT,
    )
    if r.status_code >= 400:
        raise ImageError(f"openai {r.status_code}: {r.text[:300]}")
    return base64.b64decode(r.json()["data"][0]["b64_json"])


def _gemini(prompt: str) -> bytes:
    cfg = settings.config()["image"]
    key = settings.load_secrets().gemini_api_key
    if not key:
        raise ImageError("GEMINI_API_KEY is not set")
    r = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{cfg['gemini_model']}:generateContent",
        headers={"x-goog-api-key": key},
        json={"contents": [{"parts": [{"text": prompt}]}]},
        timeout=TIMEOUT,
    )
    if r.status_code >= 400:
        raise ImageError(f"gemini {r.status_code}: {r.text[:300]}")
    for cand in r.json().get("candidates", []):
        for part in cand.get("content", {}).get("parts", []):
            data = (part.get("inlineData") or part.get("inline_data") or {}).get("data")
            if data:
                return base64.b64decode(data)
    raise ImageError("gemini returned no image")


PROVIDERS = {"openai": _openai, "gemini": _gemini}


def enabled() -> bool:
    cfg = settings.config()["image"]
    return bool(cfg.get("enabled")) and cfg.get("provider") in PROVIDERS


def generate(st: Store, scene: str, name: str) -> Path:
    """Render `scene` with the configured provider and save it under STATE_DIR/media/<name>.png."""
    provider = settings.config()["image"]["provider"]
    if provider not in PROVIDERS:
        raise ImageError(f"unknown image provider: {provider!r}")
    path = st.media_path(f"{name}.png")
    path.write_bytes(PROVIDERS[provider](_full_prompt(scene)))
    return path


def public_url(path: Path) -> str | None:
    """URL Threads can fetch. github_raw serves files committed to the public state branch."""
    cfg = settings.config()
    if cfg["image"].get("host") != "github_raw":
        return None
    repo = settings.load_secrets().github_repository
    if not repo:
        raise ImageError("GITHUB_REPOSITORY is not set; cannot build a public image URL")
    branch = cfg.get("state_branch", "state")
    return f"https://raw.githubusercontent.com/{repo}/{branch}/media/{path.name}"
