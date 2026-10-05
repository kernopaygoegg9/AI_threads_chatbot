import shutil

import pytest
from fastapi.testclient import TestClient

from bot import settings, ui
from bot.store import Store


@pytest.fixture
def client(tmp_path, monkeypatch):
    cfg = tmp_path / "settings.yaml"
    shutil.copy(settings.CONFIG_PATH, cfg)
    monkeypatch.setattr(settings, "CONFIG_PATH", cfg)
    monkeypatch.setitem(ui.FILES, "settings", str(cfg))
    settings.reload()
    return TestClient(ui.create_app())


def test_index_and_overview(client):
    assert "Overlord" in client.get("/").text
    o = client.get("/api/overview").json()
    assert o["dry_run"] is True and o["review_mode"] == "discord"


def test_draft_actions(client):
    st = Store()
    d = st.add_draft({"kind": "post", "text": "人類你好"})
    assert client.patch(f"/api/drafts/{d['id']}", json={"text": "人類晚安"}).json()["text"] == "人類晚安"
    assert client.patch(f"/api/drafts/{d['id']}", json={"text": "我有炸彈"}).status_code == 400
    assert client.post(f"/api/drafts/{d['id']}/approve").json()["status"] == "approved"
    assert client.post(f"/api/drafts/{d['id']}/publish").json()["status"] == "published"
    assert [x["id"] for x in client.get("/api/drafts?scope=all").json()] == [d["id"]]
    assert client.get("/api/drafts").json() == []


def test_settings_roundtrip_keeps_comments(client):
    fields = {f["path"]: f for f in client.get("/api/settings").json()}
    assert fields["review.mode"]["value"] == "discord"
    r = client.put(
        "/api/settings",
        json={
            "review.mode": "auto",
            "schedule.fixed_times": "12:00, 20:00",
            "replies.quiet_hours": "1, 6",
            "news.ratio": "0.3",
            "image.enabled": False,
        },
    )
    assert r.status_code == 200
    cfg = settings.config()
    assert cfg["review"]["mode"] == "auto"
    assert cfg["schedule"]["fixed_times"] == ["12:00", "20:00"]
    assert cfg["replies"]["quiet_hours"] == [1, 6]
    assert cfg["news"]["ratio"] == 0.3 and cfg["image"]["enabled"] is False
    assert "# 草稿超過這個時數沒核准就丟棄" in settings.CONFIG_PATH.read_text(encoding="utf-8")
    assert client.put("/api/settings", json={"nope": 1}).status_code == 400


def test_raw_settings_rejects_bad_yaml(client):
    assert client.put("/api/files/settings", json={"content": "a: [unclosed"}).status_code == 400
