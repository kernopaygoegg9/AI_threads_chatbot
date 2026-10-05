import random
from datetime import date, datetime, timedelta

from bot import scheduler, settings, store


def _cfg(**schedule):
    cfg = settings.load_config()
    cfg["schedule"] = {**cfg["schedule"], **schedule}
    return cfg


def test_default_slot_is_around_20():
    slots = scheduler.slots_for_day(date(2026, 10, 6), _cfg(), random.Random(1))
    assert len(slots) == 1
    s = slots[0]
    assert s.tzinfo is not None
    target = s.replace(hour=20, minute=0)
    assert abs((s - target).total_seconds()) <= 15 * 60


def test_random_slots_stay_in_window():
    cfg = _cfg(posts_per_day=3, fixed_times=[], jitter_minutes=0)
    for seed in range(20):
        slots = scheduler.slots_for_day(date(2026, 10, 6), cfg, random.Random(seed))
        assert len(slots) == 3
        assert all(10 <= s.hour <= 22 for s in slots)
        assert slots == sorted(slots)


def test_fixed_slot_clamped_to_window():
    cfg = _cfg(fixed_times=["23:30"], jitter_minutes=0)
    (s,) = scheduler.slots_for_day(date(2026, 10, 6), cfg, random.Random(0))
    assert (s.hour, s.minute) == (22, 0)


def test_quiet_hours():
    t = datetime(2026, 10, 6, 3, 0)
    assert scheduler.is_quiet_hour(t, [2, 7])
    assert not scheduler.is_quiet_hour(t.replace(hour=8), [2, 7])
    assert scheduler.is_quiet_hour(t.replace(hour=23), [22, 6])


def test_store_draft_lifecycle():
    st = store.Store()
    d = st.add_draft({"kind": "post", "text": "hi"})
    assert st.get_draft(d["id"])["status"] == store.PENDING
    st.update_draft(d["id"], status=store.PUBLISHED)
    assert st.get_draft(d["id"])["status"] == store.PUBLISHED


def test_store_prune_keeps_open_drafts():
    st = store.Store()
    old = store.iso(store.now_utc() - timedelta(days=30))
    st.save_drafts(
        [
            {"id": "a", "status": store.PUBLISHED, "created_at": old},
            {"id": "b", "status": store.PENDING, "created_at": old},
        ]
    )
    assert st.prune_drafts() == 1
    assert [d["id"] for d in st.drafts()] == ["b"]


def test_handled_comments_roundtrip():
    st = store.Store()
    st.mark_comment_handled("c1")
    st.mark_comment_handled("c1")
    assert st.handled_comment_ids() == {"c1"}


def test_review_mode_inherit():
    assert settings.review_mode("reply") == settings.config()["review"]["mode"]
