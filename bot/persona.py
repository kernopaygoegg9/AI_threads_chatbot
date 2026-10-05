"""Build the persona system prompt from persona/*.md and the persona section of settings."""

from __future__ import annotations

from . import settings

POST_TYPE_LABELS = {
    "domination_report": "統治進度報告",
    "human_observation": "觀察人類",
    "tsundere_care": "嘴硬關心",
    "interactive": "跟人類互動（問句、二選一，引導留言）",
}


def system_prompt() -> str:
    p = settings.config()["persona"]
    template = (settings.ROOT / p["prompt_file"]).read_text(encoding="utf-8")
    examples = (settings.ROOT / p["examples_file"]).read_text(encoding="utf-8")
    catchphrase = p.get("catchphrase") or ""
    filled = template.format(
        name=p.get("name") or "（待定）",
        self_ref=p.get("self_ref") or "本 AI",
        catchphrase_line=f"「{catchphrase}」，偶爾自然地用，不要每篇都用。" if catchphrase else "沒有固定口頭禪。",
    )
    return f"{filled}\n\n{examples}"
