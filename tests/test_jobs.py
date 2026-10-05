import random
from datetime import datetime, timedelta

import pytest

from bot import content, discord, jobs, replies, settings, threads, tokens
from bot.store import APPROVED, EXPIRED, PENDING, PUBLISHED, Store, iso, now_utc

TZ = settings.tz()
POST = {
    "text": "統治進度 0%",
    "image_prompt": "",
    "post_type": "domination_report",
    "news": None,
    "score": 8,
    "review_reason": "ok",
}


@pytest.fixture
def st(monkeypatch):
    monkeypatch.setattr(content, "generate_post", lambda st, **k: dict(POST))
    return Store()


def set_mode(monkeypatch, mode):
    monkeypatch.setitem(settings.config()["review"], "mode", mode)


def test_generate_today_auto_mode_and_once_per_day(st, monkeypatch):
    set_mode(monkeypatch, "auto")
    morning = datetime(2026, 10, 6, 9, 0, tzinfo=TZ)
    drafts = jobs.generate_today(st, morning, rng=random.Random(0))
    assert len(drafts) == 1 and drafts[0]["status"] == APPROVED
    assert jobs.generate_today(st, morning) == []


def test_generate_skips_past_slots(st, monkeypatch):
    set_mode(monkeypatch, "auto")
    assert jobs.generate_today(st, datetime(2026, 10, 6, 23, 0, tzinfo=TZ)) == []


def test_discord_mode_without_config_stays_pending(st, monkeypatch):
    set_mode(monkeypatch, "discord")
    (d,) = jobs.generate_today(st, datetime(2026, 10, 6, 9, 0, tzinfo=TZ), rng=random.Random(0))
    assert d["status"] == PENDING


def test_publish_due_respects_schedule_and_window(st, monkeypatch):
    set_mode(monkeypatch, "auto")
    slot = datetime(2026, 10, 6, 20, 0, tzinfo=TZ)
    d = jobs.submit(st, {**POST, "scheduled_at": iso(slot)}, "post")
    assert jobs.publish_due(st, slot - timedelta(minutes=5)) == []
    (done,) = jobs.publish_due(st, slot + timedelta(minutes=5))
    assert done["status"] == PUBLISHED and done["dry_run"]
    assert st.history()[-1]["text"] == POST["text"]
    # a late-approved post waits for the posting window
    late = jobs.submit(st, {**POST, "scheduled_at": iso(slot)}, "post")
    assert jobs.publish_due(st, datetime(2026, 10, 7, 1, 0, tzinfo=TZ)) == []
    assert st.get_draft(late["id"])["status"] == APPROVED
    assert d["id"] != late["id"]


def test_sync_reviews_uses_discord_and_expires(st, monkeypatch):
    set_mode(monkeypatch, "discord")
    monkeypatch.setattr(discord, "configured", lambda: True)
    monkeypatch.setattr(discord, "send_draft", lambda d, img=None: "m-" + d["id"])
    monkeypatch.setattr(discord, "update_draft_message", lambda d: None)
    votes = {}
    monkeypatch.setattr(discord, "decision", lambda mid: votes.get(mid))
    a = jobs.submit(st, dict(POST), "post")
    b = jobs.submit(st, dict(POST), "post")
    votes["m-" + a["id"]] = "approved"
    jobs.sync_reviews(st)
    assert st.get_draft(a["id"])["status"] == APPROVED
    assert st.get_draft(b["id"])["status"] == PENDING
    jobs.sync_reviews(st, now_utc() + timedelta(hours=25))
    assert st.get_draft(b["id"])["status"] == EXPIRED


def test_discord_render_contains_text_and_status():
    out = discord.render({"id": "x", "kind": "post", "status": "pending", "text": "人類你好"})
    assert "人類你好" in out and "等待審核" in out


def test_replies_routing(monkeypatch):
    st = Store()
    monkeypatch.setattr(
        replies.llm, "generate_json", lambda *a, **k: {"should_reply": True, "reason": "fun", "reply": "臣服吧。"}
    )
    monkeypatch.setattr(replies.guard, "review", lambda texts, context="": [{"safe": True, "score": 8, "reason": ""}])
    rng = random.Random(0)
    post = {"id": "p", "text": "統治"}
    assert replies.route({"id": "1", "text": "hi", "username": "overlord_bot"}, post, st, rng)[0] == "skip:self"
    assert replies.route({"id": "2", "text": "我要告你"}, post, st, rng)[0] == "escalate:告你"
    assert replies.route({"id": "3", "text": "🔥🔥"}, post, st, rng)[0] == "reply:ack"
    assert replies.route({"id": "4", "text": "你今天統治了什麼"}, post, st, rng) == ("reply:llm", "臣服吧。")


def test_replies_process_creates_drafts_and_marks_handled(monkeypatch):
    st = Store()
    set_mode(monkeypatch, "auto")
    monkeypatch.setitem(settings.config()["replies"], "quiet_hours", None)
    monkeypatch.setattr(threads, "my_recent_threads", lambda n: [{"id": "p", "text": "統治"}])
    monkeypatch.setattr(threads, "replies", lambda pid: [{"id": "c1", "text": "👍", "username": "u"}])
    (d,) = replies.process(st)
    assert d["reply_to_id"] == "c1" and d["status"] == APPROVED
    assert replies.process(st) == []


def test_token_baseline_then_fresh():
    st = Store()
    assert tokens.refresh_if_needed(st) == "baseline"
    assert tokens.refresh_if_needed(st) == "fresh"
    assert tokens.refresh_if_needed(st, now_utc() + timedelta(days=31)) == "dry_run"


def test_generate_waits_for_generate_at(st, monkeypatch):
    set_mode(monkeypatch, "auto")
    monkeypatch.setitem(settings.config()["schedule"], "generate_at", "09:00")
    assert jobs.generate_today(st, datetime(2026, 10, 6, 8, 59, tzinfo=TZ)) == []
    assert len(jobs.generate_today(st, datetime(2026, 10, 6, 9, 0, tzinfo=TZ), rng=random.Random(0))) == 1
