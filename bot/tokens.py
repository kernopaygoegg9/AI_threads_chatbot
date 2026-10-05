"""Keep the 60-day Threads token alive by refreshing it and writing it back to GitHub Secrets.

The token itself never touches the state branch; only the refresh timestamp does.
"""

from __future__ import annotations

import os
import subprocess
from datetime import datetime, timedelta

from . import discord, settings, threads
from .store import Store, iso, now_utc, parse_iso

SECRET_NAME = "THREADS_ACCESS_TOKEN"


def _write_secret(token: str) -> None:
    repo = settings.load_secrets().github_repository
    if not (repo and os.environ.get("GH_TOKEN")):
        raise RuntimeError("GH_TOKEN (a PAT allowed to edit secrets) and GITHUB_REPOSITORY are required")
    subprocess.run(
        ["gh", "secret", "set", SECRET_NAME, "--repo", repo], input=token.encode(), check=True, capture_output=True
    )


def refresh_if_needed(st: Store, now: datetime | None = None, *, force: bool = False) -> str:
    now = now or now_utc()
    days = settings.config().get("token", {}).get("refresh_after_days", 30)
    last = parse_iso(st.meta().get("token_refreshed_at"))
    if last is None and not force:
        # First run: we don't know the token's age, so start counting from now.
        st.set_meta(token_refreshed_at=iso(now))
        return "baseline"
    if not force and now - last < timedelta(days=days):
        return "fresh"
    if settings.dry_run():
        st.log("token_refresh_dry_run")
        return "dry_run"
    try:
        resp = threads.refresh_long_lived(settings.load_secrets().threads_token)
        _write_secret(resp["access_token"])
    except Exception as e:
        st.log("token_refresh_failed", error=str(e)[:300])
        discord.notify(f"⚠️ Threads token 自動更新失敗，請盡快手動處理：{str(e)[:300]}")
        return "error"
    st.set_meta(token_refreshed_at=iso(now))
    st.log("token_refreshed", expires_in=resp.get("expires_in"))
    return "refreshed"
