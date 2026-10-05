"""Top-level jobs run by the CLI / GitHub Actions: generate, sync reviews, publish."""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from . import content, discord, guard, images, news, scheduler, settings, threads
from .store import APPROVED, EXPIRED, FAILED, PENDING, PUBLISHED, REJECTED, Store, iso, now_utc, parse_iso


def _local(dt: datetime) -> datetime:
    return dt.astimezone(settings.tz())


def submit(st: Store, draft: dict, kind: str, image=None) -> dict:
    """Store a new draft and route it by review mode: auto-approve, or send to Discord."""
    mode = settings.review_mode(kind)
    status = APPROVED if mode == "auto" else PENDING
    draft = st.add_draft({"kind": kind, "status": status, **draft})
    if mode == "discord":
        if not discord.configured():
            st.log("review_unavailable", draft=draft["id"], reason="Discord not configured; draft stays pending")
            return draft
        msg_id = discord.send_draft(draft, image)
        draft = st.update_draft(draft["id"], discord_message_id=msg_id)
    st.log("draft_created", draft=draft["id"], kind=kind, status=draft["status"])
    return draft


# ---- generate --------------------------------------------------------------
def generate_today(
    st: Store, now: datetime | None = None, *, force: bool = False, rng: random.Random | None = None
) -> list[dict]:
    """Create today's post drafts once per local day, at or after schedule.generate_at (force skips both checks)."""
    now = now or now_utc()
    local = _local(now)
    today = local.date()
    if not force:
        if st.meta().get("last_generated_date") == today.isoformat():
            return []
        if f"{local:%H:%M}" < settings.config()["schedule"].get("generate_at", "00:00"):
            return []

    created = []
    for slot in scheduler.slots_for_day(today, rng=rng):
        if slot <= now and not force:
            continue
        created.append(create_post_draft(st, slot, rng=rng))
    st.set_meta(last_generated_date=today.isoformat())
    return [d for d in created if d]


def create_post_draft(
    st: Store, slot: datetime, *, use_news: bool | None = None, rng: random.Random | None = None
) -> dict | None:
    try:
        post = content.generate_post(st, use_news=use_news, rng=rng)
    except Exception as e:  # one bad slot must not kill the whole run
        st.log("generate_failed", slot=iso(slot), error=str(e)[:300])
        discord.notify(f"⚠️ 貼文生成失敗（{_local(slot):%m/%d %H:%M}）：{str(e)[:300]}")
        return None

    draft = {
        **post,
        "scheduled_at": iso(slot),
        "scheduled_at_local": f"{_local(slot):%m/%d %H:%M}",
    }
    image_path = None
    if images.enabled() and post["image_prompt"]:
        name = f"{_local(slot):%Y%m%d-%H%M}-{random.randrange(16**6):06x}"
        try:
            image_path = images.generate(st, post["image_prompt"], name)
            draft["image_file"] = image_path.name
            draft["image_url"] = images.public_url(image_path)
        except Exception as e:
            st.log("image_failed", error=str(e)[:300])
            if settings.config()["image"].get("required", False):
                discord.notify(f"⚠️ 配圖失敗，這篇貼文沒有產生：{str(e)[:300]}")
                return None
    if post.get("news"):
        news.mark_used(st, post["news"]["link"])
    return submit(st, draft, "post", image_path)


# ---- review sync -----------------------------------------------------------
def sync_reviews(st: Store, now: datetime | None = None) -> None:
    """Pull ✅/❌ decisions from Discord and expire drafts nobody reviewed in time."""
    now = now or now_utc()
    timeout = timedelta(hours=settings.config()["review"].get("timeout_hours", 24))
    for d in st.drafts():
        if d["status"] != PENDING:
            continue
        verdict = None
        if d.get("discord_message_id") and discord.configured():
            try:
                verdict = discord.decision(d["discord_message_id"])
            except discord.DiscordError as e:
                st.log("review_sync_error", draft=d["id"], error=str(e)[:200])
        if verdict is None and now - parse_iso(d["created_at"]) > timeout:
            verdict = EXPIRED
        if verdict:
            set_status(st, d["id"], verdict)


def set_status(st: Store, draft_id: str, status: str, **extra) -> dict | None:
    """Change a draft's status and mirror it to its Discord message."""
    draft = st.update_draft(draft_id, status=status, **extra)
    if draft:
        st.log("draft_status", draft=draft_id, status=status)
        if discord.configured():
            try:
                discord.update_draft_message(draft)
            except discord.DiscordError as e:
                st.log("discord_update_error", draft=draft_id, error=str(e)[:200])
    return draft


# ---- publish ---------------------------------------------------------------
def _in_window(now: datetime) -> bool:
    start, end = settings.config()["schedule"]["window"]
    return start <= f"{_local(now):%H:%M}" <= end


def publish_due(st: Store, now: datetime | None = None) -> list[dict]:
    """Publish approved drafts whose time has come. Late-approved posts wait for the posting window."""
    now = now or now_utc()
    done = []
    for d in st.drafts():
        if d["status"] != APPROVED:
            continue
        if d["kind"] == "post" and (parse_iso(d.get("scheduled_at")) or now) > now:
            continue
        if d["kind"] == "post" and not _in_window(now):
            continue
        done.append(publish_draft(st, d))
    return done


def publish_draft(st: Store, d: dict) -> dict:
    if settings.dry_run():
        st.log("publish_dry_run", draft=d["id"], text=d["text"])
        result = {"id": f"dry-run-{d['id']}"}
    else:
        try:
            result = threads.publish(d["text"], image_url=d.get("image_url"), reply_to_id=d.get("reply_to_id"))
        except Exception as e:
            discord.notify(f"⚠️ 發布失敗 `{d['id']}`：{str(e)[:300]}")
            return set_status(st, d["id"], FAILED, error=str(e)[:500])
    link = None if settings.dry_run() or d["kind"] != "post" else threads.permalink(result["id"])
    st.add_history({"kind": d["kind"], "text": d["text"], "threads_id": result["id"], "draft": d["id"]})
    return set_status(
        st,
        d["id"],
        PUBLISHED,
        published_id=result["id"],
        published_at=iso(now_utc()),
        permalink=link,
        dry_run=settings.dry_run(),
    )


def reject(st: Store, draft_id: str) -> dict | None:
    return set_status(st, draft_id, REJECTED)


def approve(st: Store, draft_id: str) -> dict | None:
    return set_status(st, draft_id, APPROVED)


def edit_text(st: Store, draft_id: str, text: str) -> dict:
    """Manually rewrite an open draft. Hard rules still apply; the Claude review is skipped (a human wrote it)."""
    draft = st.get_draft(draft_id)
    if not draft or draft["status"] not in (PENDING, APPROVED):
        raise ValueError("only pending or approved drafts can be edited")
    if reason := guard.rule_violation(text):
        raise ValueError(f"text rejected by guard: {reason}")
    return set_status(st, draft_id, draft["status"], text=text.strip(), edited=True)
