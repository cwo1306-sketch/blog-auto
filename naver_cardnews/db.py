"""SQLite 저장소. articles 한 테이블에 수집·중복·검토 상태를 모두 기록한다."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    url_key         TEXT NOT NULL UNIQUE,       -- 정규화된 원문 URL (1단계 중복 키)
    title_key       TEXT NOT NULL,              -- 정규화된 제목 (2단계 중복 키)
    simhash         INTEGER NOT NULL,           -- 제목+요약 SimHash (4단계 중복 키)
    title           TEXT NOT NULL,
    description     TEXT NOT NULL DEFAULT '',
    link            TEXT NOT NULL,              -- 네이버 뉴스 링크
    original_link   TEXT NOT NULL,              -- 언론사 원문 링크
    source          TEXT NOT NULL DEFAULT '',   -- 원문 도메인
    pub_date        TEXT NOT NULL,              -- ISO8601(UTC)
    keyword         TEXT NOT NULL,              -- 처음 발견한 검색어
    keyword_group   TEXT NOT NULL DEFAULT '',
    collected_at    TEXT NOT NULL,
    dedup_stage     INTEGER NOT NULL DEFAULT 0, -- 0=고유, 1~4=해당 단계에서 중복 판정
    duplicate_of    INTEGER REFERENCES articles(id),
    review_status   TEXT NOT NULL DEFAULT 'pending', -- pending / approved / rejected / exported
    exported_at     TEXT
);
CREATE INDEX IF NOT EXISTS idx_articles_title_key ON articles(title_key);
CREATE INDEX IF NOT EXISTS idx_articles_pub_date ON articles(pub_date);
CREATE INDEX IF NOT EXISTS idx_articles_status ON articles(review_status, dedup_stage);

CREATE TABLE IF NOT EXISTS collect_runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at    TEXT NOT NULL,
    finished_at   TEXT,
    keywords      INTEGER NOT NULL DEFAULT 0,
    fetched       INTEGER NOT NULL DEFAULT 0,
    inserted      INTEGER NOT NULL DEFAULT 0,
    duplicates    INTEGER NOT NULL DEFAULT 0,
    errors        TEXT NOT NULL DEFAULT ''
);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class Article:
    url_key: str
    title_key: str
    simhash: int
    title: str
    description: str
    link: str
    original_link: str
    source: str
    pub_date: str
    keyword: str
    keyword_group: str


class Database:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        try:
            yield self.conn
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    # --- 조회 -------------------------------------------------------------
    def find_by_url(self, url_key: str) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM articles WHERE url_key=?", (url_key,)).fetchone()

    def find_by_title_key(self, title_key: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM articles WHERE title_key=? AND dedup_stage=0 ORDER BY id LIMIT 1",
            (title_key,),
        ).fetchone()

    def unique_since(self, since_iso: str) -> list[sqlite3.Row]:
        """근사 중복 비교 대상: 지정 시각 이후의 고유 기사만."""
        return self.conn.execute(
            "SELECT id, title, title_key, simhash, pub_date FROM articles "
            "WHERE dedup_stage=0 AND pub_date>=? ORDER BY id",
            (since_iso,),
        ).fetchall()

    def pending_unique(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM articles WHERE dedup_stage=0 AND review_status='pending' "
            "ORDER BY pub_date DESC, id DESC"
        ).fetchall()

    def duplicate_count(self, article_id: int) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) FROM articles WHERE duplicate_of=?", (article_id,)
        ).fetchone()
        return int(row[0])

    def stats(self) -> dict[str, int]:
        rows = self.conn.execute(
            "SELECT dedup_stage, COUNT(*) FROM articles GROUP BY dedup_stage"
        ).fetchall()
        out = {f"stage_{r[0]}": r[1] for r in rows}
        out["total"] = sum(out.values())
        out["pending"] = self.conn.execute(
            "SELECT COUNT(*) FROM articles WHERE dedup_stage=0 AND review_status='pending'"
        ).fetchone()[0]
        return out

    # --- 쓰기 -------------------------------------------------------------
    def insert(self, a: Article, dedup_stage: int = 0, duplicate_of: int | None = None) -> int:
        cur = self.conn.execute(
            "INSERT INTO articles (url_key, title_key, simhash, title, description, link, "
            "original_link, source, pub_date, keyword, keyword_group, collected_at, "
            "dedup_stage, duplicate_of) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (a.url_key, a.title_key, a.simhash, a.title, a.description, a.link,
             a.original_link, a.source, a.pub_date, a.keyword, a.keyword_group,
             utcnow(), dedup_stage, duplicate_of),
        )
        return int(cur.lastrowid)

    def mark_exported(self, ids: list[int]) -> None:
        now = utcnow()
        self.conn.executemany(
            "UPDATE articles SET review_status='exported', exported_at=? WHERE id=?",
            [(now, i) for i in ids],
        )
        self.conn.commit()

    def start_run(self, keyword_count: int) -> int:
        cur = self.conn.execute(
            "INSERT INTO collect_runs (started_at, keywords) VALUES (?, ?)",
            (utcnow(), keyword_count),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def finish_run(self, run_id: int, fetched: int, inserted: int, duplicates: int, errors: list[str]) -> None:
        self.conn.execute(
            "UPDATE collect_runs SET finished_at=?, fetched=?, inserted=?, duplicates=?, errors=? WHERE id=?",
            (utcnow(), fetched, inserted, duplicates, "\n".join(errors), run_id),
        )
        self.conn.commit()
