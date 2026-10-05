"""Fetch news headlines from RSS feeds and drop anything unsafe to joke about."""

from __future__ import annotations

import calendar
from datetime import UTC, datetime, timedelta

import feedparser
import requests

from . import settings
from .store import Store, iso, now_utc

USER_AGENT = "Mozilla/5.0 (compatible; threads-overlord-bot/0.1)"


def _published(entry) -> datetime | None:
    t = entry.get("published_parsed") or entry.get("updated_parsed")
    return datetime.fromtimestamp(calendar.timegm(t), UTC) if t else None


def is_blocked(title: str, blocklist: list[str]) -> bool:
    return any(word in title for word in blocklist)


def fetch(st: Store) -> list[dict]:
    """Return fresh, unused, non-blocked headlines across all configured feeds."""
    cfg = settings.config()["news"]
    used = set(st.meta().get("used_news", []))
    cutoff = now_utc() - timedelta(hours=cfg.get("max_age_hours", 36))
    items: list[dict] = []
    for url in cfg.get("feeds", []):
        try:
            r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
            r.raise_for_status()
        except requests.RequestException as e:
            st.log("news_feed_error", feed=url, error=str(e)[:200])
            continue
        feed = feedparser.parse(r.content)
        source = feed.feed.get("title", url)
        for entry in feed.entries[: cfg.get("max_items_per_feed", 15)]:
            title = (entry.get("title") or "").strip()
            link = entry.get("link") or ""
            published = _published(entry)
            if not title or link in used or is_blocked(title, cfg.get("blocklist", [])):
                continue
            if published and published < cutoff:
                continue
            items.append(
                {
                    "title": title,
                    "link": link,
                    "source": source,
                    "published": iso(published) if published else None,
                }
            )
    return items


def mark_used(st: Store, link: str, limit: int = 300) -> None:
    used = st.meta().get("used_news", [])
    st.set_meta(used_news=(used + [link])[-limit:])
