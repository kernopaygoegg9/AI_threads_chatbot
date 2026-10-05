"""Last line of defence before anything is published: hard rules, then a Claude review."""
from __future__ import annotations

from difflib import SequenceMatcher

from . import llm, persona, settings

REVIEW_SYSTEM = """你是社群內容審查員，負責檢查一個「想統治人類的賤萌 AI」帳號要發出的文字。
依照下面人設文件裡的「紅線」逐條檢查每一則文字，並評估它是不是符合人設、好不好笑。

safe = false 的情況：觸犯任何一條紅線、可能被誤會成真的威脅或惡意、
嘲諷特定真實個人或群體、拿災難或傷亡開玩笑、內容不實、讀者可能看不出是玩笑。
score（0～10）：人設符合度加上好笑程度；safe = false 時給 0。
reason：一句繁體中文說明。

=== 人設文件 ===
{persona}"""

REVIEW_SCHEMA = llm.obj({
    "reviews": {
        "type": "array",
        "items": llm.obj({"index": {"type": "integer"}, "safe": {"type": "boolean"},
                          "score": {"type": "number"}, "reason": {"type": "string"}}),
    }
})


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def rule_violation(text: str, history_texts: list[str] | None = None) -> str | None:
    """Cheap deterministic checks. Returns a reason string, or None if the text passes."""
    cfg = settings.config()
    text = (text or "").strip()
    if not text:
        return "empty"
    max_chars = cfg["content"].get("max_chars", 300)
    if len(text) > max_chars:
        return f"too_long:{len(text)}>{max_chars}"
    for word in cfg.get("guard", {}).get("banned_words", []):
        if word in text:
            return f"banned_word:{word}"
    threshold = cfg["content"].get("similarity_threshold", 0.6)
    for old in history_texts or []:
        if similarity(text, old) >= threshold:
            return "too_similar_to_history"
    return None


def review(texts: list[str], context: str = "") -> list[dict]:
    """Ask Claude to review each text against the persona red lines. Order matches `texts`."""
    if not texts:
        return []
    numbered = "\n".join(f"[{i}] {t}" for i, t in enumerate(texts))
    user = f"{context}\n\n要審查的文字：\n{numbered}".strip()
    out = llm.generate_json(REVIEW_SYSTEM.format(persona=persona.system_prompt()), user, REVIEW_SCHEMA)
    by_index = {r["index"]: r for r in out.get("reviews", [])}
    missing = {"safe": False, "score": 0, "reason": "not reviewed"}
    return [by_index.get(i, {"index": i, **missing}) for i in range(len(texts))]
