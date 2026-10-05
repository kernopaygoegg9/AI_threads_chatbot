"""JSON state kept in STATE_DIR (synced to the public `state` branch by GitHub Actions).

Only non-sensitive data lives here: drafts, published ids, timestamps. Never tokens.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import settings

# Draft statuses
PENDING = "pending"        # waiting for human review
APPROVED = "approved"      # ready to publish at scheduled_at
REJECTED = "rejected"
EXPIRED = "expired"
PUBLISHED = "published"
FAILED = "failed"
OPEN_STATUSES = {PENDING, APPROVED}


def now_utc() -> datetime:
    return datetime.now(UTC)


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).replace(microsecond=0).isoformat()


def parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


class Store:
    def __init__(self, root: Path | None = None):
        self.root = Path(root or settings.state_dir())
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "media").mkdir(exist_ok=True)

    # ---- low-level -------------------------------------------------------
    def _path(self, name: str) -> Path:
        return self.root / name

    def _read(self, name: str, default: Any) -> Any:
        p = self._path(name)
        if not p.exists():
            return default
        return json.loads(p.read_text(encoding="utf-8"))

    def _write(self, name: str, data: Any) -> None:
        p = self._path(name)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, p)

    # ---- drafts ----------------------------------------------------------
    def drafts(self) -> list[dict]:
        return self._read("drafts.json", [])

    def save_drafts(self, drafts: list[dict]) -> None:
        self._write("drafts.json", drafts)

    def add_draft(self, draft: dict) -> dict:
        draft = {
            "id": uuid.uuid4().hex[:10],
            "created_at": iso(now_utc()),
            "status": PENDING,
            **draft,
        }
        drafts = self.drafts()
        drafts.append(draft)
        self.save_drafts(drafts)
        return draft

    def get_draft(self, draft_id: str) -> dict | None:
        return next((d for d in self.drafts() if d["id"] == draft_id), None)

    def update_draft(self, draft_id: str, **changes: Any) -> dict | None:
        drafts = self.drafts()
        for d in drafts:
            if d["id"] == draft_id:
                d.update(changes)
                d["updated_at"] = iso(now_utc())
                self.save_drafts(drafts)
                return d
        return None

    def prune_drafts(self, keep_days: int = 14) -> int:
        """Drop closed drafts older than keep_days so the file stays small."""
        cutoff = now_utc().timestamp() - keep_days * 86400
        drafts = self.drafts()
        kept = [
            d for d in drafts
            if d["status"] in OPEN_STATUSES
            or (parse_iso(d.get("created_at")) or now_utc()).timestamp() >= cutoff
        ]
        if len(kept) != len(drafts):
            self.save_drafts(kept)
        return len(drafts) - len(kept)

    # ---- history ---------------------------------------------------------
    def history(self) -> list[dict]:
        return self._read("history.json", [])

    def add_history(self, entry: dict, limit: int = 200) -> None:
        hist = self.history()
        hist.append({"ts": iso(now_utc()), **entry})
        self._write("history.json", hist[-limit:])

    # ---- meta ------------------------------------------------------------
    def meta(self) -> dict:
        return self._read("meta.json", {})

    def set_meta(self, **changes: Any) -> dict:
        meta = self.meta()
        meta.update(changes)
        self._write("meta.json", meta)
        return meta

    # ---- replies bookkeeping --------------------------------------------
    def handled_comment_ids(self) -> set[str]:
        return set(self._read("handled_comments.json", []))

    def mark_comment_handled(self, comment_id: str, limit: int = 5000) -> None:
        ids = self._read("handled_comments.json", [])
        if comment_id not in ids:
            ids.append(comment_id)
        self._write("handled_comments.json", ids[-limit:])

    # ---- log -------------------------------------------------------------
    def log(self, event: str, **detail: Any) -> None:
        entry = {"ts": iso(now_utc()), "event": event, **detail}
        with self._path("log.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def recent_log(self, n: int = 100) -> list[dict]:
        p = self._path("log.jsonl")
        if not p.exists():
            return []
        lines = p.read_text(encoding="utf-8").splitlines()[-n:]
        return [json.loads(x) for x in lines if x.strip()]

    def media_path(self, name: str) -> Path:
        return self.root / "media" / name
