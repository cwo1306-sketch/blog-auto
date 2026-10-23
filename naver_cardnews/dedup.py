"""4단계 중복 제거 (HANDOFF.md 5장).

1. URL 완전 일치   : 네이버 oid_aid 같음 → 저장 안 함, 걸린 키워드만 추가
2. 제목 정규화 일치: [단독]·[속보]·괄호·특수문자·공백 제거 후 같음 → 같은 클러스터, 제외
3. 근접 중복       : 제목+요약 문자 2-gram Jaccard ≥ 0.4 (72시간 창) → 같은 클러스터, 대표만 대기
                     0.2~0.4 경계(제목 단독 유사도 포함)는 Haiku 판정. (문서 시작값 0.5/0.35 → 실측 후 조정) 클러스터 크기(언론사 수) = 중요도 점수
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
    def __init__(self, db: Database, threshold: float = 0.4, borderline: float = 0.2,
                 window_hours: int = 72, posted_days: int = 14, judge: Judge | None = None):
        self.db = db
        self.threshold = threshold
        self.borderline = borderline
        self.window = timedelta(hours=window_hours)
        self.posted_window = timedelta(days=posted_days)
        self.judge = judge
        self.judge_calls = 0

    def _similar(self, a: Article, grams: set[str], rows: list[sqlite3.Row]) -> tuple[sqlite3.Row | None, float, str]:
        """가장 유사한 행과 점수, 판정 근거. 임계 미만이면 (None, best, '').

        자동 판정은 제목+요약 유사도만 쓴다. 경계 후보 선별에는 제목 단독 유사도도 함께 본다:
        매체마다 요약문이 달라 같은 사건도 합산 유사도는 0.15 안팎까지 떨어지는데(실측: 카카오 비전 인코더
        4건), 제목끼리는 0.2~0.45로 남기 때문이다. 후보는 점수 순 상위 5개까지 Haiku에 묻는다."""
        best_row, best_sim = None, 0.0
        title_grams = char_bigrams(a.title)
        borderline: list[tuple[float, sqlite3.Row]] = []
        for row in rows:
            if row["id"] == a.id:
                continue
            sim = jaccard(grams, _grams(row["title"], row["description"]))
            if sim >= self.threshold and sim > best_sim:
                best_row, best_sim = row, sim
                continue
            score = max(sim, jaccard(title_grams, char_bigrams(row["title"])))
            if score >= self.borderline:   # 제목만 비슷해 임계를 넘어도 자동 판정은 않고 Haiku에 묻는다
                borderline.append((score, row))
        if best_row is not None:
            return best_row, best_sim, f"j={best_sim:.2f}"
        if self.judge is not None:
            for score, row in sorted(borderline, key=lambda x: -x[0])[:5]:
                self.judge_calls += 1
                if self.judge.same_event(a.title, a.description, row["title"], row["description"]):
                    return row, score, f"j={score:.2f}, haiku=같음"
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
