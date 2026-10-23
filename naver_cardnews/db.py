"""SQLite 저장소(원본). 엑셀은 이 DB를 보기/승인용으로 내보낸 사본이다."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

STATUSES = ("대기", "승인", "제작완료", "게시완료", "제외")

SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
    id              TEXT PRIMARY KEY,           -- 네이버 oid_aid
    collected_at    TEXT NOT NULL,
    keyword         TEXT NOT NULL,              -- 처음 발견한 검색어
    keywords_hit    TEXT NOT NULL DEFAULT '',   -- 걸린 검색어 전부 (쉼표 구분)
    title           TEXT NOT NULL,
    press           TEXT NOT NULL DEFAULT '',   -- 언론사 (원문 도메인)
    pub_date        TEXT NOT NULL,              -- ISO8601 UTC
    naver_link      TEXT NOT NULL,
    originallink    TEXT NOT NULL DEFAULT '',
    description     TEXT NOT NULL DEFAULT '',
    title_key       TEXT NOT NULL,              -- 정규화 제목
    cluster_id      INTEGER,
    is_representative INTEGER NOT NULL DEFAULT 1,
    dup_reason      TEXT NOT NULL DEFAULT '',
    score           INTEGER NOT NULL DEFAULT 1, -- 클러스터 내 언론사 수
    status          TEXT NOT NULL DEFAULT '대기',
    card_folder     TEXT NOT NULL DEFAULT '',
    post_url        TEXT NOT NULL DEFAULT '',
    memo            TEXT NOT NULL DEFAULT '',
    posted_at       TEXT,
    body            TEXT,                       -- 크롤링한 기사 본문 (원고 생성 대상만)
    body_fetched_at TEXT
);
CREATE TABLE IF NOT EXISTS drafts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id  TEXT NOT NULL REFERENCES articles(id),
    version     INTEGER NOT NULL,               -- 기사별 1부터
    source      TEXT NOT NULL,                  -- ai | excel
    script_json TEXT NOT NULL,
    errors_json TEXT NOT NULL DEFAULT '[]',     -- validate 결과
    usage_json  TEXT NOT NULL DEFAULT '{}',
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_drafts_article ON drafts(article_id, version);
CREATE TABLE IF NOT EXISTS evaluations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id  TEXT NOT NULL,
    version     INTEGER NOT NULL,               -- 채점한 원고 버전
    source      TEXT NOT NULL,                  -- judge | human
    scores_json TEXT NOT NULL,                  -- {fact, attribution, plain, structure, hook}
    total       REAL NOT NULL,
    detail_json TEXT NOT NULL DEFAULT '{}',     -- judge: issues/unsupported/summary, human: memo
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_eval_article ON evaluations(article_id, version, source);
CREATE INDEX IF NOT EXISTS idx_articles_title_key ON articles(title_key);
CREATE INDEX IF NOT EXISTS idx_articles_pub_date ON articles(pub_date);
CREATE INDEX IF NOT EXISTS idx_articles_cluster ON articles(cluster_id);
CREATE INDEX IF NOT EXISTS idx_articles_status ON articles(status);

CREATE TABLE IF NOT EXISTS used_images (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id  TEXT NOT NULL,              -- oid_aid
    slide_no    INTEGER NOT NULL,
    source      TEXT NOT NULL,              -- pexels | unsplash | generated
    external_id TEXT,                       -- 스톡 사진 id
    query       TEXT NOT NULL DEFAULT '',   -- 검색어 또는 프롬프트
    dhash       TEXT NOT NULL,              -- 16 hex = 64bit
    file_path   TEXT NOT NULL DEFAULT '',
    photographer TEXT NOT NULL DEFAULT '',
    page_url    TEXT NOT NULL DEFAULT '',
    used_at     TEXT NOT NULL,
    posted      INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_used_images_ext ON used_images(source, external_id);
CREATE INDEX IF NOT EXISTS idx_used_images_article ON used_images(article_id);

-- 무작위 구성 기록: 색 → 레이아웃 → 포맷. 직전과 같은 조합을 피하는 데 쓴다 (naver_cardnews/compose.py)
CREATE TABLE IF NOT EXISTS compositions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id  TEXT NOT NULL,
    palette     TEXT NOT NULL,
    layout      TEXT NOT NULL,
    format      TEXT NOT NULL,
    reasons     TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS collect_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    summary     TEXT NOT NULL DEFAULT ''
);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class Article:
    id: str
    keyword: str
    title: str
    press: str
    pub_date: str
    naver_link: str
    originallink: str
    description: str
    title_key: str


class Database:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(SCHEMA)
        self._migrate()

    def _migrate(self) -> None:
        """기존 DB에 새 열 추가 (CREATE TABLE IF NOT EXISTS 는 열을 더하지 않는다)."""
        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(articles)")}
        for col, ddl in (("body", "TEXT"), ("body_fetched_at", "TEXT")):
            if col not in cols:
                self.conn.execute(f"ALTER TABLE articles ADD COLUMN {col} {ddl}")
        self.conn.commit()

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
    def get(self, article_id: str) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM articles WHERE id=?", (article_id,)).fetchone()

    def find_by_title_key(self, title_key: str, start_iso: str, end_iso: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM articles WHERE title_key=? AND pub_date BETWEEN ? AND ? "
            "ORDER BY pub_date LIMIT 1", (title_key, start_iso, end_iso),
        ).fetchone()

    def representatives_between(self, start_iso: str, end_iso: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM articles WHERE is_representative=1 AND pub_date BETWEEN ? AND ? "
            "ORDER BY pub_date", (start_iso, end_iso),
        ).fetchall()

    def posted_since(self, since_iso: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM articles WHERE status='게시완료' AND COALESCE(posted_at, pub_date)>=?",
            (since_iso,),
        ).fetchall()

    def next_cluster_id(self) -> int:
        row = self.conn.execute("SELECT COALESCE(MAX(cluster_id), 0) + 1 FROM articles").fetchone()
        return int(row[0])

    def cluster_press_count(self, cluster_id: int) -> int:
        row = self.conn.execute(
            "SELECT COUNT(DISTINCT press) FROM articles WHERE cluster_id=?", (cluster_id,)
        ).fetchone()
        return int(row[0])

    def for_export(self) -> list[sqlite3.Row]:
        """엑셀에는 전부 내보낸다(제외 포함). 대표·대기 건이 위로 오도록 정렬."""
        return self.conn.execute(
            "SELECT * FROM articles ORDER BY "
            "CASE status WHEN '대기' THEN 0 WHEN '승인' THEN 1 WHEN '제작완료' THEN 2 "
            "WHEN '게시완료' THEN 3 ELSE 4 END, is_representative DESC, score DESC, pub_date DESC"
        ).fetchall()

    def stats(self) -> dict[str, int]:
        out = {r[0]: r[1] for r in self.conn.execute(
            "SELECT status, COUNT(*) FROM articles GROUP BY status")}
        out["전체"] = sum(out.values())
        out["클러스터"] = self.conn.execute(
            "SELECT COUNT(DISTINCT cluster_id) FROM articles").fetchone()[0]
        return out

    # --- 쓰기 -------------------------------------------------------------
    def insert(self, a: Article, cluster_id: int | None, is_representative: bool,
               status: str, dup_reason: str = "") -> None:
        self.conn.execute(
            "INSERT INTO articles (id, collected_at, keyword, keywords_hit, title, press, pub_date, "
            "naver_link, originallink, description, title_key, cluster_id, is_representative, "
            "dup_reason, status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (a.id, utcnow(), a.keyword, a.keyword, a.title, a.press, a.pub_date, a.naver_link,
             a.originallink, a.description, a.title_key, cluster_id, int(is_representative),
             dup_reason, status),
        )

    def add_keyword_hit(self, article_id: str, keyword: str) -> None:
        row = self.get(article_id)
        if row is None:
            return
        hits = [k for k in row["keywords_hit"].split(",") if k]
        if keyword not in hits:
            hits.append(keyword)
            self.conn.execute("UPDATE articles SET keywords_hit=? WHERE id=?",
                              (",".join(hits), article_id))

    def refresh_scores(self) -> None:
        """대표 기사의 score = 클러스터 내 언론사 수."""
        self.conn.execute(
            "UPDATE articles SET score=(SELECT COUNT(DISTINCT press) FROM articles b "
            "WHERE b.cluster_id=articles.cluster_id) WHERE cluster_id IS NOT NULL"
        )
        self.conn.commit()

    def update_review(self, article_id: str, status: str | None, memo: str | None,
                      card_folder: str | None, post_url: str | None) -> bool:
        row = self.get(article_id)
        if row is None:
            return False
        fields, values = [], []
        if status and status in STATUSES and status != row["status"]:
            fields.append("status=?"); values.append(status)
            if status == "게시완료":
                fields.append("posted_at=?"); values.append(utcnow())
        for col, val in (("memo", memo), ("card_folder", card_folder), ("post_url", post_url)):
            if val is not None and val != row[col]:
                fields.append(f"{col}=?"); values.append(val)
        if not fields:
            return False
        values.append(article_id)
        self.conn.execute(f"UPDATE articles SET {', '.join(fields)} WHERE id=?", values)
        return True

    # --- 본문·원고 ---------------------------------------------------------
    def set_body(self, article_id: str, body: str, press: str | None = None) -> None:
        self.conn.execute("UPDATE articles SET body=?, body_fetched_at=?, press=COALESCE(NULLIF(?, ''), press) WHERE id=?",
                          (body, utcnow(), press or "", article_id))
        self.conn.commit()

    def draft_candidates(self, limit: int) -> list[sqlite3.Row]:
        """원고가 아직 없는 '대기' 대표 기사를 점수(여러 매체가 다룬 이슈) 순으로."""
        return self.conn.execute(
            "SELECT a.* FROM articles a WHERE a.status IN ('대기', '승인') AND a.is_representative=1 "
            "AND NOT EXISTS (SELECT 1 FROM drafts d WHERE d.article_id=a.id) "
            "ORDER BY a.score DESC, a.pub_date DESC LIMIT ?", (limit,)
        ).fetchall()

    def latest_draft(self, article_id: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM drafts WHERE article_id=? ORDER BY version DESC LIMIT 1", (article_id,)
        ).fetchone()

    def drafts_for_export(self) -> list[sqlite3.Row]:
        """기사별 최신 원고 + 기사 메타. 상태 우선순위 → 점수 순."""
        return self.conn.execute(
            "SELECT d.*, a.title AS article_title, a.status, a.score, a.press, a.naver_link, a.memo FROM drafts d "
            "JOIN articles a ON a.id=d.article_id "
            "WHERE d.version=(SELECT MAX(version) FROM drafts x WHERE x.article_id=d.article_id) "
            "ORDER BY CASE a.status WHEN '승인' THEN 0 WHEN '대기' THEN 1 WHEN '제작완료' THEN 2 ELSE 3 END, a.score DESC"
        ).fetchall()

    def bodies_for_export(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT id, title, press, pub_date, naver_link, body, body_fetched_at FROM articles WHERE body IS NOT NULL "
            "ORDER BY body_fetched_at DESC"
        ).fetchall()

    def save_draft(self, article_id: str, script: dict, errors: list[str], source: str, usage: dict | None = None) -> int:
        import json
        row = self.conn.execute("SELECT COALESCE(MAX(version), 0) FROM drafts WHERE article_id=?", (article_id,)).fetchone()
        version = int(row[0]) + 1
        self.conn.execute(
            "INSERT INTO drafts (article_id, version, source, script_json, errors_json, usage_json, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (article_id, version, source, json.dumps(script, ensure_ascii=False),
             json.dumps(errors, ensure_ascii=False), json.dumps(usage or {}, ensure_ascii=False), utcnow()),
        )
        self.conn.commit()
        return version

    # --- 채점 ---------------------------------------------------------------
    def save_evaluation(self, article_id: str, version: int, source: str, scores: dict, total: float, detail: dict) -> None:
        import json
        if source == "human":   # 사람 점수는 같은 버전에 하나만 (덮어쓰기)
            self.conn.execute("DELETE FROM evaluations WHERE article_id=? AND version=? AND source='human'", (article_id, version))
        self.conn.execute(
            "INSERT INTO evaluations (article_id, version, source, scores_json, total, detail_json, created_at) VALUES (?,?,?,?,?,?,?)",
            (article_id, version, source, json.dumps(scores, ensure_ascii=False), total, json.dumps(detail, ensure_ascii=False), utcnow()),
        )
        self.conn.commit()

    def evaluation(self, article_id: str, version: int, source: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM evaluations WHERE article_id=? AND version=? AND source=? ORDER BY id DESC LIMIT 1",
            (article_id, version, source),
        ).fetchone()

    def clear_judgements(self, source: str = "judge") -> int:
        cur = self.conn.execute("DELETE FROM evaluations WHERE source=?", (source,))
        self.conn.commit()
        return cur.rowcount

    def unjudged_drafts(self, limit: int = 50, source: str = "judge") -> list[sqlite3.Row]:
        """최신 버전인데 해당 판정기(source) 점수가 없는 원고."""
        return self.conn.execute(
            "SELECT d.*, a.body, a.press, a.title AS article_title, a.pub_date FROM drafts d JOIN articles a ON a.id=d.article_id "
            "WHERE d.version=(SELECT MAX(version) FROM drafts x WHERE x.article_id=d.article_id) "
            "AND NOT EXISTS (SELECT 1 FROM evaluations e WHERE e.article_id=d.article_id AND e.version=d.version AND e.source=?) "
            "ORDER BY d.created_at DESC LIMIT ?", (source, limit)
        ).fetchall()

    def judge_human_totals(self, source: str = "judge") -> list[tuple[str, float, float]]:
        """(article_id, 판정 총점, 사람 총점) — 사람이 총점만 매긴 경우도 포함."""
        rows = self.conn.execute(
            "SELECT j.article_id, j.total AS jt, h.total AS ht FROM evaluations j JOIN evaluations h "
            "ON h.article_id=j.article_id AND h.version=j.version AND h.source='human' WHERE j.source=? "
            "AND j.id=(SELECT MAX(id) FROM evaluations x WHERE x.article_id=j.article_id AND x.version=j.version AND x.source=?)",
            (source, source),
        ).fetchall()
        return [(r["article_id"], float(r["jt"]), float(r["ht"])) for r in rows]

    def judge_agreement_counts(self) -> dict[str, int]:
        import json
        out: dict[str, int] = {}
        for r in self.conn.execute("SELECT detail_json FROM evaluations WHERE source='human'"):
            a = json.loads(r["detail_json"]).get("judge_agree", "")
            if a:
                out[a] = out.get(a, 0) + 1
        return out

    def judge_human_pairs(self, source: str = "judge") -> list[tuple[dict, dict]]:
        import json
        rows = self.conn.execute(
            "SELECT j.scores_json AS j, h.scores_json AS h FROM evaluations j JOIN evaluations h "
            "ON h.article_id=j.article_id AND h.version=j.version AND h.source='human' WHERE j.source=?", (source,)
        ).fetchall()
        return [(json.loads(r["j"]), json.loads(r["h"])) for r in rows if json.loads(r["h"])]   # 총점만 매긴 행은 축별 보정에서 제외

    # --- 사용 이미지 기록 --------------------------------------------------
    def image_used(self, source: str, external_id: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM used_images WHERE source=? AND external_id=? LIMIT 1", (source, external_id)
        ).fetchone()
        return row is not None

    def similar_image(self, dhash_hex: str, max_distance: int = 8, days: int = 30) -> sqlite3.Row | None:
        """최근 N일 안에 dHash 해밍 거리가 max_distance 이하인 기록이 있으면 돌려준다."""
        from .imagehash import from_hex, hamming  # 순환 import 방지
        since = (datetime.now(timezone.utc) - __import__("datetime").timedelta(days=days)).isoformat()
        target = from_hex(dhash_hex)
        for row in self.conn.execute("SELECT * FROM used_images WHERE used_at>=?", (since,)):
            if hamming(target, from_hex(row["dhash"])) <= max_distance:
                return row
        return None

    def record_image(self, article_id: str, slide_no: int, source: str, external_id: str | None,
                     query: str, dhash_hex: str, file_path: str = "", photographer: str = "",
                     page_url: str = "") -> int:
        cur = self.conn.execute(
            "INSERT INTO used_images (article_id, slide_no, source, external_id, query, dhash, file_path, "
            "photographer, page_url, used_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (article_id, slide_no, source, external_id, query, dhash_hex, file_path, photographer,
             page_url, utcnow()),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def record_composition(self, article_id: str, palette: str, layout: str, fmt: str, reasons: str = "") -> int:
        cur = self.conn.execute(
            "INSERT INTO compositions (article_id, palette, layout, format, reasons, created_at) VALUES (?,?,?,?,?,?)",
            (article_id, palette, layout, fmt, reasons, utcnow()))
        self.conn.commit()
        return int(cur.lastrowid)

    def recent_compositions(self, n: int = 6) -> list[sqlite3.Row]:
        """최근 구성 n개 (최신이 앞)."""
        return list(self.conn.execute("SELECT * FROM compositions ORDER BY id DESC LIMIT ?", (n,)))

    def start_run(self) -> int:
        cur = self.conn.execute("INSERT INTO collect_runs (started_at) VALUES (?)", (utcnow(),))
        self.conn.commit()
        return int(cur.lastrowid)

    def finish_run(self, run_id: int, summary: str) -> None:
        self.conn.execute("UPDATE collect_runs SET finished_at=?, summary=? WHERE id=?",
                          (utcnow(), summary, run_id))
        self.conn.commit()
