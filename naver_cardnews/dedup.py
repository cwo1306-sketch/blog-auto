"""4단계 중복 제거.

1단계  URL 일치      : 정규화한 원문 URL이 같다 (같은 기사를 다른 키워드로 다시 받은 경우).
2단계  제목 일치     : 머리말·매체명·기호를 뺀 제목이 완전히 같다 (같은 기사의 재송고, 포털 재게시).
3단계  제목 유사     : 2-gram 자카드 유사도가 임계값 이상 (통신사 기사 받아쓰기, 어미만 바꾼 제목).
4단계  본문 지문     : 요약문 SimHash 해밍 거리가 임계값 이하 (제목은 달라도 내용이 같은 기사).
                     요약이 짧으면(토큰 < SIMHASH_MIN_TOKENS) 지문이 불안정하므로 건너뛴다.

3·4단계는 최근 N일의 고유 기사하고만 비교해 비용을 묶어 둔다.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .db import Database
from .normalize import tokenize

TITLE_SIMILARITY_THRESHOLD = 0.80   # 3단계
SIMHASH_MAX_DISTANCE = 6            # 4단계 (63비트 기준, 요약문 기준 측정값: 문장 하나 추가 ≈ 6, 재서술 ≈ 15, 무관 ≈ 30)
SIMHASH_MIN_TOKENS = 15             # 요약이 이보다 짧으면 4단계는 건너뛴다 (짧은 글은 지문 신뢰도가 낮다)
NEAR_DUP_WINDOW_DAYS = 3


def simhash(text: str, bits: int = 63, min_tokens: int = 0) -> int:
    """토큰 빈도 가중 SimHash. SQLite INTEGER(부호 있는 64비트)에 맞춰 63비트를 쓴다.
    토큰이 min_tokens보다 적으면 0(지문 없음)을 돌려준다."""
    tokens = tokenize(text)
    counts = Counter(tokens)
    if not counts or len(tokens) < min_tokens:
        return 0
    vec = [0] * bits
    for token, weight in counts.items():
        h = int.from_bytes(hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest(), "big")
        for i in range(bits):
            vec[i] += weight if (h >> i) & 1 else -weight
    out = 0
    for i, v in enumerate(vec):
        if v > 0:
            out |= 1 << i
    return out


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def jaccard(a: list[str], b: list[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


@dataclass
class DedupResult:
    stage: int                 # 0이면 고유
    duplicate_of: int | None   # 원본 article id
    reason: str = ""


class Deduplicator:
    def __init__(
        self,
        db: Database,
        title_threshold: float = TITLE_SIMILARITY_THRESHOLD,
        simhash_distance: int = SIMHASH_MAX_DISTANCE,
        window_days: int = NEAR_DUP_WINDOW_DAYS,
    ):
        self.db = db
        self.title_threshold = title_threshold
        self.simhash_distance = simhash_distance
        self.window_days = window_days
        self._cache: list[tuple[int, list[str], int]] | None = None
        self._cache_since: str | None = None

    # 수집 한 번 도는 동안 최근 고유 기사 목록을 메모리에 들고 있는다.
    def _recent(self) -> list[tuple[int, list[str], int]]:
        since = (datetime.now(timezone.utc) - timedelta(days=self.window_days)).isoformat()
        if self._cache is None or self._cache_since != since[:13]:
            rows = self.db.unique_since(since)
            self._cache = [(r["id"], tokenize(r["title"]), r["simhash"]) for r in rows]
            self._cache_since = since[:13]
        return self._cache

    def remember(self, article_id: int, title: str, sh: int) -> None:
        if self._cache is not None:
            self._cache.append((article_id, tokenize(title), sh))

    def check(self, url_key: str, title_key: str, title: str, sh: int) -> DedupResult:
        # 1단계: URL
        row = self.db.find_by_url(url_key)
        if row is not None:
            origin = row["duplicate_of"] or row["id"]
            return DedupResult(1, origin, "same url")

        # 2단계: 정규화 제목
        if title_key:
            row = self.db.find_by_title_key(title_key)
            if row is not None:
                return DedupResult(2, row["id"], "same normalized title")

        # 3·4단계: 최근 고유 기사와 근사 비교
        tokens = tokenize(title)
        best_stage, best_id, best_reason = 0, None, ""
        for other_id, other_tokens, other_hash in self._recent():
            sim = jaccard(tokens, other_tokens)
            if sim >= self.title_threshold:
                return DedupResult(3, other_id, f"title jaccard={sim:.2f}")
            if sh and other_hash:
                dist = hamming(sh, other_hash)
                if dist <= self.simhash_distance and best_id is None:
                    best_stage, best_id, best_reason = 4, other_id, f"simhash distance={dist}"
        if best_id is not None:
            return DedupResult(best_stage, best_id, best_reason)
        return DedupResult(0, None)
