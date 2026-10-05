"""Generate one post: pick a type, optionally a headline, draft candidates, keep the best safe one."""

from __future__ import annotations

import random

from . import guard, llm, news, persona, settings
from .store import Store

CANDIDATE_SCHEMA = llm.obj(
    {
        "candidates": {
            "type": "array",
            "items": llm.obj(
                {
                    "text": {"type": "string"},
                    "image_prompt": {"type": "string"},
                    "news_index": {"type": "integer"},
                }
            ),
        }
    }
)


class NoUsableCandidate(RuntimeError):
    pass


def pick_post_type(rng: random.Random) -> str:
    weights = settings.config()["content"]["post_types"]
    types = [t for t, w in weights.items() if w > 0]
    return rng.choices(types, weights=[weights[t] for t in types])[0]


def _user_prompt(post_type: str, n: int, headlines: list[dict], recent: list[str], with_image: bool) -> str:
    max_chars = settings.config()["content"].get("max_chars", 300)
    parts = []
    if headlines:
        listed = "\n".join(f"[{i}] {h['title']}（{h['source']}）" for i, h in enumerate(headlines))
        parts.append(
            "今天的新聞標題如下。挑一則最適合用霸主角度吐槽、又完全不碰紅線的新聞來寫，"
            "news_index 填那則新聞的編號；只根據標題寫，不要編造細節；"
            f"如果每一則都不適合，就改寫「{persona.POST_TYPE_LABELS[post_type]}」類型，news_index 填 -1。\n{listed}"
        )
    else:
        parts.append(f"這次的貼文類型：{persona.POST_TYPE_LABELS[post_type]}。news_index 一律填 -1。")
    parts.append(f"寫 {n} 個彼此不同的候選貼文，每篇不超過 {max_chars} 字。")
    if with_image:
        parts.append(
            "image_prompt：用英文描述一張搭配這篇貼文的插圖畫面（主角是固定的小機器人，"
            "畫出貼文的情境或笑點），圖中不要有任何文字。"
        )
    else:
        parts.append("image_prompt 填空字串。")
    if recent:
        parts.append("最近已經發過的貼文（不要重複同樣的梗或句型）：\n" + "\n".join(f"- {t}" for t in recent))
    return "\n\n".join(parts)


def generate_post(st: Store, *, use_news: bool | None = None, rng: random.Random | None = None) -> dict:
    """Return {text, image_prompt, post_type, news, score, review_reason}; raise if nothing passes."""
    rng = rng or random.Random()
    cfg = settings.config()
    news_cfg = cfg["news"]
    if use_news is None:
        use_news = news_cfg.get("enabled", False) and rng.random() < news_cfg.get("ratio", 0)
    headlines = news.fetch(st)[:12] if use_news else []
    post_type = pick_post_type(rng)
    history = [h["text"] for h in st.history() if h.get("kind") == "post"][-cfg["content"].get("history_size", 60) :]
    with_image = cfg["image"].get("enabled", False) and cfg["image"].get("provider") != "none"

    out = llm.generate_json(
        persona.system_prompt(),
        _user_prompt(post_type, cfg["llm"].get("candidates", 4), headlines, history[-15:], with_image),
        CANDIDATE_SCHEMA,
    )
    candidates = [c for c in out.get("candidates", []) if not guard.rule_violation(c["text"], history)]
    if not candidates:
        raise NoUsableCandidate("all candidates failed rule checks")

    reviews = guard.review([c["text"] for c in candidates])
    min_score = cfg.get("guard", {}).get("min_score", 6)
    scored = [(r["score"], c, r) for c, r in zip(candidates, reviews, strict=True) if r["safe"] and r["score"] >= min_score]
    if not scored:
        raise NoUsableCandidate("no candidate passed review: " + "; ".join(r["reason"] for r in reviews))
    score, best, review = max(scored, key=lambda x: x[0])

    idx = best.get("news_index", -1)
    item = headlines[idx] if 0 <= idx < len(headlines) else None
    return {
        "text": best["text"].strip(),
        "image_prompt": best["image_prompt"].strip() if with_image else "",
        "post_type": "news" if item else post_type,
        "news": item,
        "score": score,
        "review_reason": review["reason"],
    }
