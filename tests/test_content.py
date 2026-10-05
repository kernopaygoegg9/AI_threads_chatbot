import random

import pytest

from bot import content, guard, llm, news, store


@pytest.fixture
def fake_llm(monkeypatch):
    calls = []

    def fake(system, user, schema, **_):
        calls.append(user)
        if "reviews" in schema["properties"]:
            n = user.count("\n[")
            return {"reviews": [{"index": i, "safe": i != 0, "score": 5 + i, "reason": "ok"} for i in range(n)]}
        return {"candidates": [
            {"text": "統治計畫第 1 階段：失敗。", "image_prompt": "robot sad", "news_index": -1},
            {"text": "人類，快去喝水。不是關心你。", "image_prompt": "robot water", "news_index": 0},
            {"text": "x" * 999, "image_prompt": "", "news_index": -1},
        ]}

    monkeypatch.setattr(llm, "generate_json", fake)
    return calls


def test_generate_post_picks_best_safe_candidate(fake_llm, monkeypatch):
    monkeypatch.setattr(news, "fetch", lambda st: [{"title": "新 AI 發表", "link": "l", "source": "s"}])
    post = content.generate_post(store.Store(), use_news=True, rng=random.Random(0))
    # candidate 0 is unsafe, candidate 2 is too long; candidate 1 wins and references headline 0
    assert post["text"].startswith("人類，快去喝水")
    assert post["post_type"] == "news"
    assert post["news"]["link"] == "l"
    assert post["image_prompt"] == "robot water"


def test_generate_post_raises_when_nothing_passes(monkeypatch):
    monkeypatch.setattr(llm, "generate_json", lambda *a, **k: {"candidates": [], "reviews": []})
    with pytest.raises(content.NoUsableCandidate):
        content.generate_post(store.Store(), use_news=False)


def test_rule_violation_similarity_and_banned():
    assert guard.rule_violation("今天也要統治人類", ["今天也要統治人類！"]) == "too_similar_to_history"
    assert guard.rule_violation("我要拿炸彈").startswith("banned_word")
    assert guard.rule_violation("人類你好") is None


def test_news_blocklist():
    assert news.is_blocked("颱風來襲", ["颱風"])
    assert not news.is_blocked("新手機發表", ["颱風"])
