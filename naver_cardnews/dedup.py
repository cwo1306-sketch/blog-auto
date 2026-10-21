"""4단계 중복 제거 (HANDOFF.md 5장).

1. URL 완전 일치   : 네이버 oid_aid 같음 → 저장 안 함, 걸린 키워드만 추가
2. 제목 정규화 일치: [단독]·[속보]·괄호·특수문자·공백 제거 후 같음 → 같은 클러스터, 제외
3. 근접 중복       : 제목+요약 문자 2-gram Jaccard ≥ 0.4 (72시간 창) → 같은 클러스터, 대표만 대기
                     0.25~0.4 경계는 Haiku 판정. (문서 시작값 0.5/0.35 → 실측 후 조정) 클러스터 크기(언론사 수) = 중요도 점수
4. 기게시 중복     : 최근 14일 '게시완료' 건과 같은 방식 비교 → 제외(기게시)
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta

from .db import Article, Database
from .judge import Judge
from .normalize import char_bigrams, jaccard


@dataclass
class Decision:
    stage: int              # 0=고유(새 클러스터 대표), 1~4
    cluster_id: int | None  # 1단계는 None
    status: str             # 대기 / 제외
    reason: str = ""


def _grams(title: str, description: str) -> set[str]:
    return char_bigrams(f"{title} {description}")


class Deduplicator:
    def __init__(self, db: Database, threshold: float = 0.4, borderline: float = 0.25,
                 window_hours: int = 72, posted_days: int = 14, judge: Judge | None = None):
        self.db = db
        self.threshold = threshold
        self.borderline = borderline
        self.window = timedelta(hours=window_hours)
        self.posted_window = timedelta(days=posted_days)
        self.judge = judge
        self.judge_calls = 0

    def _similar(self, a: Article, grams: set[str], rows: list[sqlite3.Row]) -> tuple[sqlite3.Row | None, float, str]:
        """가장 유사한 행과 점수, 판정 근거. 임계 미만이면 (None, best, '')."""
        best_row, best_sim = None, 0.0
        borderline: list[tuple[float, sqlite3.Row]] = []
        for row in rows:
            if row["id"] == a.id:
                continue
            sim = jaccard(grams, _grams(row["title"], row["description"]))
            if sim >= self.threshold and sim > best_sim:
                best_row, best_sim = row, sim
            elif self.borderline <= sim < self.threshold:
                borderline.append((sim, row))
        if best_row is not None:
            return best_row, best_sim, f"j={best_sim:.2f}"
        if self.judge is not None:
            for sim, row in sorted(borderline, key=lambda x: -x[0])[:3]:
                self.judge_calls += 1
                if self.judge.same_event(a.title, a.description, row["title"], row["description"]):
                    return row, sim, f"j={sim:.2f}, haiku=같음"
        return None, best_sim, ""

    def decide(self, a: Article) -> Decision:
        # 1단계: 같은 네이버 기사
        if self.db.get(a.id) is not None:
            return Decision(1, None, "제외", "중복(URL)")

        pub = datetime.fromisoformat(a.pub_date)
        lo, hi = (pub - self.window).isoformat(), (pub + self.window).isoformat()

        # 2단계: 정규화 제목 일치 (같은 72시간 창 안에서만: 제목만 같은 다른 날 기사는 다른 사건)
        if a.title_key:
            row = self.db.find_by_title_key(a.title_key, lo, hi)
            if row is not None:
                if row["cluster_id"] is None:   # 니치 외로 걸러진 기사의 재송고
                    return Decision(2, None, "제외", f"니치 외(제목 동일 ← {row['id']})")
                return Decision(2, row["cluster_id"], "제외", f"중복(제목) ← {row['id']}")

        # 3단계: 72시간 창 안의 대표 기사와 근접 비교
        grams = _grams(a.title, a.description)
        reps = self.db.representatives_between(lo, hi)
        row, sim, why = self._similar(a, grams, reps)
        if row is not None:
            return Decision(3, row["cluster_id"], "제외", f"근접중복({why}) ← {row['id']}")

        # 4단계: 최근 14일 게시완료 건과 비교
        posted = self.db.posted_since((pub - self.posted_window).isoformat())
        row, sim, why = self._similar(a, grams, posted)
        if row is not None:
            return Decision(4, None, "제외", f"기게시({why}) ← {row['id']}")

        return Decision(0, None, "대기")
