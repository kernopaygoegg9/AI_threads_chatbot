"""Local web dashboard (127.0.0.1 only): review drafts, preview posts, tune settings and persona.

Run with `uv run python -m bot ui`. It works on the local STATE_DIR; use the sync buttons to
pull the bot's state from the `state` branch and push your review decisions back.
"""

from __future__ import annotations

import subprocess
from datetime import timedelta
from pathlib import Path
from typing import Annotated, Any

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse
from ruamel.yaml import YAML

from . import content, discord, jobs, settings
from .store import OPEN_STATUSES, Store, now_utc, parse_iso

STATIC = Path(__file__).parent / "static"
JsonBody = Annotated[dict, Body()]

# Editable text files (key -> path relative to repo root)
FILES = {
    "settings": "config/settings.yaml",
    "persona": "persona/persona.md",
    "examples": "persona/examples.md",
}

# Structured settings form: (dotted path, label, type, options, help)
FIELDS: list[tuple[str, str, str, list | None, str]] = [
    ("persona.name", "人設名字", "text", None, "待定項目，見 PLAN.md 第 10 節"),
    ("persona.self_ref", "自稱", "text", None, "例如：本 AI、本霸主、本喵"),
    ("persona.catchphrase", "口頭禪", "text", None, "留空表示不固定"),
    ("review.mode", "發文審核模式", "select", ["discord", "auto"], "discord：送 Discord 審核；auto：全自動"),
    ("review.timeout_hours", "審核逾時（小時）", "number", None, "超過沒核准就丟棄"),
    ("schedule.posts_per_day", "每天發文篇數", "number", None, ""),
    ("schedule.fixed_times", "指定時段", "list", None, "以逗號分隔，例如 12:00, 20:00；不足的篇數會在區間內隨機"),
    ("schedule.window", "發文區間", "list", None, "開始, 結束，例如 10:00, 22:00"),
    ("schedule.jitter_minutes", "指定時段隨機偏移（分鐘）", "number", None, ""),
    ("schedule.generate_at", "每天產生草稿的時間", "text", None, "HH:MM，要早於第一個時段"),
    ("llm.model", "Claude 模型", "select", ["claude-opus-5-5", "claude-sonnet-5-5", "claude-fable-5-1"], ""),
    ("llm.effort", "思考強度", "select", ["low", "medium", "high", "xhigh", "max"], ""),
    ("llm.candidates", "每篇候選數", "number", None, "越多越好挑，但越貴"),
    ("llm.refusal_fallback", "被拒絕時自動換模型", "bool", None, ""),
    ("content.max_chars", "貼文字數上限", "number", None, ""),
    ("content.similarity_threshold", "與舊貼文相似度上限", "number", None, "0～1，超過就淘汰"),
    ("guard.min_score", "審查最低分", "number", None, "0～10"),
    ("news.enabled", "使用時事", "bool", None, ""),
    ("news.ratio", "時事比例", "number", None, "0～1"),
    ("news.max_age_hours", "新聞最舊（小時）", "number", None, ""),
    ("image.enabled", "配圖", "bool", None, ""),
    ("image.required", "配圖失敗就不發", "bool", None, "關閉時會改發純文字"),
    ("image.provider", "圖片供應商", "select", ["openai", "gemini", "none"], ""),
    ("image.openai_model", "OpenAI 圖片模型", "text", None, ""),
    ("image.openai_quality", "OpenAI 圖片品質", "select", ["low", "medium", "high"], "影響價格很大"),
    ("image.gemini_model", "Gemini 圖片模型", "text", None, ""),
    ("image.style", "固定畫風／角色", "textarea", None, "每張圖都會加上這段描述"),
    ("replies.enabled", "自動回覆留言", "bool", None, ""),
    ("replies.review_mode", "回覆審核模式", "select", ["inherit", "discord", "auto"], "inherit：跟發文一樣"),
    ("replies.max_per_run", "每次最多回覆", "number", None, ""),
    ("replies.max_per_day", "每天最多回覆", "number", None, ""),
    ("replies.quiet_hours", "不回覆時段", "list", None, "開始小時, 結束小時，例如 2, 7"),
    ("replies.llm_review", "回覆送出前再審查", "bool", None, ""),
    ("token.refresh_after_days", "Token 更新間隔（天）", "number", None, ""),
]


def _roundtrip() -> YAML:
    y = YAML()
    y.preserve_quotes = True
    y.width = 4096
    return y


def _get(data: dict, dotted: str) -> Any:
    for key in dotted.split("."):
        data = (data or {}).get(key)
    return data


def _coerce(kind: str, value: Any, current: Any) -> Any:
    if kind == "bool":
        return bool(value)
    if kind == "number":
        num = float(value)
        return int(num) if isinstance(current, int) and num.is_integer() else num
    if kind == "list":
        items = [x.strip() for x in str(value).split(",") if x.strip()] if isinstance(value, str) else list(value)
        return [int(x) if str(x).lstrip("-").isdigit() else x for x in items]
    return value


def _run(cmd: list[str]) -> dict:
    proc = subprocess.run(cmd, cwd=settings.ROOT, capture_output=True, text=True, encoding="utf-8")
    return {"ok": proc.returncode == 0, "output": (proc.stdout + proc.stderr).strip()[-2000:]}


def create_app() -> FastAPI:
    app = FastAPI(title="Threads Bot Dashboard")

    def store() -> Store:
        return Store()

    def need_draft(st: Store, draft_id: str) -> dict:
        d = st.get_draft(draft_id)
        if not d:
            raise HTTPException(404, "draft not found")
        return d

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/media/{name}")
    def media(name: str):
        path = store().media_path(Path(name).name)
        if not path.exists():
            raise HTTPException(404)
        return FileResponse(path)

    @app.get("/api/overview")
    def overview():
        st = store()
        cfg = settings.config()
        now = now_utc()
        drafts = st.drafts()
        last_token = parse_iso(st.meta().get("token_refreshed_at"))
        return {
            "dry_run": settings.dry_run(),
            "review_mode": settings.review_mode("post"),
            "reply_review_mode": settings.review_mode("reply"),
            "persona": cfg["persona"],
            "discord_configured": discord.configured(),
            "upcoming": sorted(d["scheduled_at"] for d in drafts if d["status"] in OPEN_STATUSES and d.get("scheduled_at")),
            "schedule": cfg["schedule"],
            "counts": {s: sum(1 for d in drafts if d["status"] == s) for s in {d["status"] for d in drafts}},
            "published_24h": sum(1 for h in st.history() if parse_iso(h["ts"]) > now - timedelta(hours=24)),
            "meta": {k: v for k, v in st.meta().items() if k != "used_news"},
            "token_age_days": (now - last_token).days if last_token else None,
        }

    @app.get("/api/drafts")
    def drafts(scope: str = "open"):
        items = store().drafts()
        if scope == "open":
            items = [d for d in items if d["status"] in OPEN_STATUSES]
        return sorted(items, key=lambda d: d.get("created_at", ""), reverse=True)

    @app.post("/api/drafts/{draft_id}/{action}")
    def draft_action(draft_id: str, action: str):
        st = store()
        d = need_draft(st, draft_id)
        if action == "approve":
            return jobs.approve(st, draft_id)
        if action == "reject":
            return jobs.reject(st, draft_id)
        if action == "publish":
            return jobs.publish_draft(st, d)
        raise HTTPException(400, f"unknown action {action}")

    @app.patch("/api/drafts/{draft_id}")
    def draft_edit(draft_id: str, body: JsonBody):
        st = store()
        need_draft(st, draft_id)
        try:
            return jobs.edit_text(st, draft_id, body.get("text", ""))
        except ValueError as e:
            raise HTTPException(400, str(e)) from e

    @app.post("/api/generate/{mode}")
    def generate(mode: str, body: Annotated[dict | None, Body()] = None):
        use_news = {"on": True, "off": False}.get((body or {}).get("news", "auto"))
        st = store()
        try:
            if mode == "preview":
                return content.generate_post(st, use_news=use_news)
            if mode == "draft":
                return jobs.create_post_draft(st, now_utc(), use_news=use_news)
        except Exception as e:
            raise HTTPException(500, str(e)) from e
        raise HTTPException(400, f"unknown mode {mode}")

    @app.get("/api/history")
    def history():
        return list(reversed(store().history()))

    @app.get("/api/log")
    def log(n: int = 200):
        return list(reversed(store().recent_log(n)))

    @app.get("/api/settings")
    def get_settings():
        cfg = settings.load_config()
        return [
            {"path": p, "label": label, "type": t, "options": opts, "help": h, "value": _get(cfg, p)}
            for p, label, t, opts, h in FIELDS
        ]

    @app.put("/api/settings")
    def put_settings(body: JsonBody):
        kinds = {p: t for p, _, t, _, _ in FIELDS}
        unknown = set(body) - set(kinds)
        if unknown:
            raise HTTPException(400, f"unknown fields: {sorted(unknown)}")
        y = _roundtrip()
        path = settings.CONFIG_PATH
        data = y.load(path.read_text(encoding="utf-8"))
        try:
            for dotted, value in body.items():
                *parents, leaf = dotted.split(".")
                node = data
                for key in parents:
                    node = node.setdefault(key, {})
                node[leaf] = _coerce(kinds[dotted], value, node.get(leaf))
        except (TypeError, ValueError) as e:
            raise HTTPException(400, f"invalid value: {e}") from e
        with path.open("w", encoding="utf-8", newline="\n") as f:
            y.dump(data, f)
        settings.reload()
        return get_settings()

    @app.get("/api/files/{key}")
    def get_file(key: str):
        if key not in FILES:
            raise HTTPException(404)
        return {"key": key, "path": FILES[key], "content": (settings.ROOT / FILES[key]).read_text(encoding="utf-8")}

    @app.put("/api/files/{key}")
    def put_file(key: str, body: JsonBody):
        if key not in FILES:
            raise HTTPException(404)
        text = body.get("content", "")
        if key == "settings":
            try:
                YAML(typ="safe").load(text)
            except Exception as e:
                raise HTTPException(400, f"YAML 格式錯誤：{e}") from e
        (settings.ROOT / FILES[key]).write_text(text, encoding="utf-8", newline="\n")
        settings.reload()
        return get_file(key)

    @app.post("/api/git/{action}")
    def git(action: str):
        if action == "state-pull":
            return _run(["bash", "scripts/state.sh", "pull"])
        if action == "state-push":
            return _run(["bash", "scripts/state.sh", "push", "dashboard: review decisions"])
        if action == "config-commit":
            paths = sorted(set(FILES.values()))
            res = _run(["git", "add", *paths])
            if res["ok"]:
                res = _run(["git", "commit", "-m", "Update bot settings from dashboard", "--", *paths])
            if res["ok"]:
                res = _run(["git", "push", "-q"])
            return res
        raise HTTPException(400, f"unknown action {action}")

    return app
