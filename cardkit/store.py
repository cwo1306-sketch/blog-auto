"""작은 SQLite 저장소: 사진 재사용 금지(used_images)와 구성 기록(compositions).

계정마다 파일 하나(profile.store_path)를 쓴다. 다른 파이프라인의 DB 와 섞지 않는다.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .imagehash import from_hex, hamming

SCHEMA = """
CREATE TABLE IF NOT EXISTS used_images (
    id INTEGER PRIMARY KEY AUTOINCREMENT, item_id TEXT NOT NULL, slide_no INTEGER NOT NULL,
    source TEXT NOT NULL, external_id TEXT, query TEXT NOT NULL DEFAULT '', dhash TEXT NOT NULL,
    file_path TEXT NOT NULL DEFAULT '', photographer TEXT NOT NULL DEFAULT '', page_url TEXT NOT NULL DEFAULT '',
    used_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_used_ext ON used_images(source, external_id);
CREATE TABLE IF NOT EXISTS compositions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, item_id TEXT NOT NULL, palette TEXT NOT NULL, layout TEXT NOT NULL,
    format TEXT NOT NULL, reasons TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL);
"""


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class Store:
    def __init__(self, path: str | Path = ":memory:"):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    # 사진
    def image_used(self, source: str, external_id: str) -> bool:
        return self.conn.execute("SELECT 1 FROM used_images WHERE source=? AND external_id=? LIMIT 1",
                                 (source, external_id)).fetchone() is not None

    def similar_image(self, dhash_hex: str, max_distance: int = 8, days: int = 30):
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        target = from_hex(dhash_hex)
        for row in self.conn.execute("SELECT * FROM used_images WHERE used_at>=?", (since,)):
            if hamming(target, from_hex(row["dhash"])) <= max_distance:
                return row
        return None

    def record_image(self, item_id: str, slide_no: int, source: str, external_id: str | None, query: str,
                     dhash_hex: str, file_path: str = "", photographer: str = "", page_url: str = "") -> None:
        self.conn.execute("INSERT INTO used_images (item_id, slide_no, source, external_id, query, dhash, file_path, "
                          "photographer, page_url, used_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                          (item_id, slide_no, source, external_id, query, dhash_hex, file_path, photographer, page_url, _now()))
        self.conn.commit()

    # 구성
    def record_composition(self, item_id: str, palette: str, layout: str, fmt: str, reasons: str = "") -> None:
        self.conn.execute("INSERT INTO compositions (item_id, palette, layout, format, reasons, created_at) VALUES (?,?,?,?,?,?)",
                          (item_id, palette, layout, fmt, reasons, _now()))
        self.conn.commit()

    def recent_compositions(self, n: int = 6) -> list[dict]:
        return [dict(r) for r in self.conn.execute("SELECT * FROM compositions ORDER BY id DESC LIMIT ?", (n,))]
