import base64

import pytest

from bot import images, settings, store


class FakeResp:
    def __init__(self, payload, status=200):
        self._p, self.status_code, self.text = payload, status, str(payload)

    def json(self):
        return self._p


def test_openai_provider_saves_png(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    png = b"\x89PNG fake"
    sent = {}

    def fake_post(url, headers, json, timeout):
        sent.update(json)
        return FakeResp({"data": [{"b64_json": base64.b64encode(png).decode()}]})

    monkeypatch.setattr(images.requests, "post", fake_post)
    path = images.generate(store.Store(), "robot drinks tea", "d1")
    assert path.read_bytes() == png
    assert "robot drinks tea" in sent["prompt"] and "小機器人" in sent["prompt"]


def test_gemini_provider_reads_inline_data(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    cfg = settings.config()
    monkeypatch.setitem(cfg["image"], "provider", "gemini")
    data = base64.b64encode(b"img").decode()
    payload = {"candidates": [{"content": {"parts": [{"text": "hi"}, {"inlineData": {"data": data}}]}}]}
    monkeypatch.setattr(images.requests, "post", lambda *a, **k: FakeResp(payload))
    assert images.generate(store.Store(), "x", "d2").read_bytes() == b"img"


def test_missing_key_raises():
    with pytest.raises(images.ImageError):
        images.generate(store.Store(), "x", "d3")


def test_public_url(monkeypatch, tmp_path):
    monkeypatch.setenv("GITHUB_REPOSITORY", "me/repo")
    assert images.public_url(tmp_path / "a.png") == "https://raw.githubusercontent.com/me/repo/state/media/a.png"
