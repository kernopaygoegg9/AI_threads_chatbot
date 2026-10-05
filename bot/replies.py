"""Reply to comments under our own posts.

Layered routing adapted from linzoie/threads-bot-template (MIT):
  0. hard skips (own comment, already handled, empty)
  1. escalation keywords -> notify a human, never auto-reply
  2. emoji / short praise -> canned persona line, no LLM
  3. Claude decides whether to reply and drafts it, then the guard reviews it
"""

from __future__ import annotations

import random
import re
from datetime import datetime, timedelta

from . import discord, guard, jobs, llm, persona, scheduler, settings, threads
from .store import Store, now_utc, parse_iso

REPLY_SCHEMA = llm.obj(
    {
        "should_reply": {"type": "boolean"},
        "reason": {"type": "string"},
        "reply": {"type": "string"},
    }
)

REPLY_TASK = """有人在你的貼文底下留言。判斷要不要回，要回的話用人設寫一則回覆。

要回：真心的互動、玩梗、提問、捧場、配合你的「統治」設定演戲。
不回（should_reply = false，reply 填空字串）：看不懂意圖、廣告、引戰、跟貼文無關、回了可能踩到紅線。
回覆規則：不超過 {max_chars} 字，1～2 句，接住對方的梗再加一記反差，不要每次都用同一個句型。

你的貼文：「{post}」
@{user} 的留言：「{comment}」"""


def _cfg() -> dict:
    return settings.config()["replies"]


def _is_trivial(text: str) -> bool:
    return not re.search(r"\w", text) or text in set(_cfg().get("short_praise", []))


def _replies_last_24h(st: Store, now: datetime) -> int:
    since = now - timedelta(hours=24)
    sent = sum(1 for h in st.history() if h.get("kind") == "reply" and parse_iso(h["ts"]) > since)
    queued = sum(1 for d in st.drafts() if d["kind"] == "reply" and d["status"] in ("pending", "approved"))
    return sent + queued


def route(comment: dict, post: dict, st: Store, rng: random.Random) -> tuple[str, str | None]:
    """Return (action, reply_text). Actions: skip:*, escalate:*, reply:ack, reply:llm."""
    text = (comment.get("text") or "").strip()
    if comment.get("is_reply_owned_by_me") or comment.get("username") == settings.load_secrets().threads_username:
        return "skip:self", None
    if comment["id"] in st.handled_comment_ids():
        return "skip:handled", None
    if not text:
        return "skip:empty", None
    for kw in _cfg().get("escalate_keywords", []):
        if kw in text:
            return f"escalate:{kw}", None
    if _is_trivial(text):
        acks = _cfg().get("ack_replies", [])
        return ("reply:ack", rng.choice(acks)) if acks else ("skip:trivial", None)

    max_chars = _cfg().get("max_chars", 120)
    out = llm.generate_json(
        persona.system_prompt(),
        REPLY_TASK.format(max_chars=max_chars, post=post.get("text", ""), user=comment.get("username", ""), comment=text),
        REPLY_SCHEMA,
    )
    reply = out["reply"].strip()
    if not out["should_reply"] or not reply:
        return f"skip:llm:{out['reason'][:60]}", None
    if len(reply) > max_chars or guard.rule_violation(reply):
        return "skip:rule", None
    if _cfg().get("llm_review", True):
        (verdict,) = guard.review([reply], context=f"這是回覆留言「{text}」的內容。")
        if not verdict["safe"]:
            return f"skip:review:{verdict['reason'][:60]}", None
    return "reply:llm", reply


def process(st: Store, now: datetime | None = None, rng: random.Random | None = None) -> list[dict]:
    cfg = _cfg()
    now = now or now_utc()
    rng = rng or random.Random()
    if not cfg.get("enabled") or scheduler.is_quiet_hour(now.astimezone(settings.tz()), cfg.get("quiet_hours")):
        return []
    budget = min(cfg.get("max_per_run", 10), cfg.get("max_per_day", 60) - _replies_last_24h(st, now))
    results = []
    for post in threads.my_recent_threads(cfg.get("recent_posts", 8)):
        for comment in threads.replies(post["id"]):
            if budget <= 0:
                return results
            try:
                action, reply = route(comment, post, st, rng)
            except llm.LLMError as e:
                st.log("reply_llm_error", comment=comment["id"], error=str(e)[:200])
                continue
            if action == "skip:handled":
                continue
            st.mark_comment_handled(comment["id"])
            st.log("comment_routed", comment=comment["id"], action=action)
            if action.startswith("escalate"):
                discord.notify(
                    f"🙋 這則留言需要你親自處理（關鍵字「{action.split(':', 1)[1]}」）："
                    f"@{comment.get('username')}「{comment.get('text')}」 {post.get('permalink', '')}"
                )
            if reply:
                draft = jobs.submit(
                    st,
                    {
                        "text": reply,
                        "reply_to_id": comment["id"],
                        "reply_to_text": comment.get("text"),
                        "reply_to_user": comment.get("username"),
                    },
                    "reply",
                )
                results.append(draft)
                budget -= 1
    return results
