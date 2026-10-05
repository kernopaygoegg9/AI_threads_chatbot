"""Discord review channel over the REST API (no gateway needed, so it works from cron jobs).

Drafts are posted as messages with ✅ / ❌ reactions; later runs read the reactions back.
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote

import requests

from . import settings

API = "https://discord.com/api/v10"
APPROVE = "✅"
REJECT = "❌"
TIMEOUT = 30

KIND_LABEL = {"post": "📝 貼文草稿", "reply": "💬 留言回覆草稿"}
STATUS_LABEL = {
    "pending": "⏳ 等待審核",
    "approved": "✅ 已核准，等待發布",
    "rejected": "❌ 已丟棄",
    "expired": "⌛ 逾時未審核，已丟棄",
    "published": "🚀 已發布",
    "failed": "⚠️ 發布失敗",
}


class DiscordError(RuntimeError):
    pass


def configured() -> bool:
    s = settings.load_secrets()
    return bool(s.discord_bot_token and s.discord_channel_id)


def _headers() -> dict:
    return {"Authorization": f"Bot {settings.load_secrets().discord_bot_token}"}


def _channel() -> str:
    return settings.load_secrets().discord_channel_id


def _check(r: requests.Response):
    if r.status_code >= 400:
        raise DiscordError(f"{r.request.method} {r.url} -> {r.status_code}: {r.text[:300]}")
    return r.json() if r.content else None


def render(draft: dict) -> str:
    """Message body for a draft; re-rendered on every status change so the channel shows the latest state."""
    lines = [f"**{KIND_LABEL.get(draft['kind'], draft['kind'])}**　`{draft['id']}`"]
    if draft.get("scheduled_at_local"):
        lines.append(f"預定發布：{draft['scheduled_at_local']}")
    if draft.get("post_type"):
        lines.append(f"類型：{draft['post_type']}　審查分數：{draft.get('score', '-')}")
    if draft.get("news"):
        lines.append(f"新聞素材：{draft['news']['title']} <{draft['news']['link']}>")
    if draft.get("reply_to_text"):
        lines.append(f"回覆的留言（@{draft.get('reply_to_user', '?')}）：「{draft['reply_to_text']}」")
    lines += ["", draft["text"], ""]
    lines.append(f"狀態：{STATUS_LABEL.get(draft['status'], draft['status'])}")
    if draft["status"] == "pending":
        hours = settings.config()["review"].get("timeout_hours", 24)
        lines.append(f"按 {APPROVE} 核准、{REJECT} 丟棄；{hours} 小時內沒有核准會自動丟棄。")
    if draft.get("permalink"):
        lines.append(draft["permalink"])
    if draft.get("error"):
        lines.append(f"錯誤：{draft['error'][:300]}")
    return "\n".join(lines)[:2000]


def send_draft(draft: dict, image: Path | None = None) -> str:
    payload = {"content": render(draft), "allowed_mentions": {"parse": []}}
    url = f"{API}/channels/{_channel()}/messages"
    if image and image.exists():
        with image.open("rb") as f:
            files = {"files[0]": (image.name, f, "image/png")}
            msg = _check(
                requests.post(
                    url, headers=_headers(), data={"payload_json": json.dumps(payload)}, files=files, timeout=TIMEOUT
                )
            )
    else:
        msg = _check(requests.post(url, headers=_headers(), json=payload, timeout=TIMEOUT))
    for emoji in (APPROVE, REJECT):
        _check(requests.put(f"{url}/{msg['id']}/reactions/{quote(emoji)}/@me", headers=_headers(), timeout=TIMEOUT))
    return msg["id"]


def update_draft_message(draft: dict) -> None:
    if not draft.get("discord_message_id"):
        return
    url = f"{API}/channels/{_channel()}/messages/{draft['discord_message_id']}"
    _check(requests.patch(url, headers=_headers(), json={"content": render(draft)}, timeout=TIMEOUT))


def _reactors(message_id: str, emoji: str) -> list[str]:
    url = f"{API}/channels/{_channel()}/messages/{message_id}/reactions/{quote(emoji)}"
    users = _check(requests.get(url, headers=_headers(), params={"limit": 100}, timeout=TIMEOUT)) or []
    return [u["id"] for u in users if not u.get("bot")]


def decision(message_id: str) -> str | None:
    """'approved' / 'rejected' / None. Reject wins if both; DISCORD_REVIEWER_IDS limits who counts."""
    allowed = set(settings.load_secrets().discord_reviewer_ids)

    def votes(emoji: str) -> bool:
        users = _reactors(message_id, emoji)
        return any(u in allowed for u in users) if allowed else bool(users)

    if votes(REJECT):
        return "rejected"
    if votes(APPROVE):
        return "approved"
    return None


def notify(text: str) -> None:
    """Best-effort alert to the review channel; never raises."""
    if not configured():
        return
    try:
        requests.post(
            f"{API}/channels/{_channel()}/messages",
            headers=_headers(),
            json={"content": text[:2000], "allowed_mentions": {"parse": []}},
            timeout=TIMEOUT,
        )
    except requests.RequestException:
        pass
