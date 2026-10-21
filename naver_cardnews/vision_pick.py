"""비전 검수: 후보 이미지를 Claude에게 보여주고 얼굴·글자·로고를 탈락시킨 뒤 점수로 고른다."""

from __future__ import annotations

import base64
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Protocol

from .db import Database
from .imagehash import dhash, to_hex
from .stock import Candidate

log = logging.getLogger(__name__)

MODEL = "claude-haiku-5-5"
SYSTEM = (
    "너는 인스타그램 카드뉴스 'AI 뉴스 3분 브리핑'의 사진 에디터다. 1080×1350 세로 카드의 배경 사진 후보를 심사한다. "
    "사진 위에는 하단 1/3에 흰색·노란색 헤드라인이 올라가고 좌상단에 작은 라벨이 붙는다.\n"
    "다음 JSON만 출력한다(설명 금지):\n"
    '{"faces": bool, "text_or_logo": bool, "brand_like": bool, "relevance": 1-5, '
    '"lower_third_clear": 1-5, "style_match": 1-5, "reason": "40자 이내 한 문장"}\n'
    "- faces: 알아볼 수 있는 사람 얼굴이 있으면 true (뒷모습·실루엣·손만 보이면 false)\n"
    "- text_or_logo: 글자, 숫자, 간판, 로고, 워터마크가 보이면 true\n"
    "- brand_like: 특정 기업 제품·로고·캐릭터가 연상되면 true (예: 애플 제품 디자인, 테슬라 차량)\n"
    "- relevance: 주어진 기사 개념을 은유적으로라도 잘 표현하는가. 뻔한 로봇·파란 회로판 클리셰는 2 이하\n"
    "- lower_third_clear: 하단 1/3이 단순·어두워 글자를 올려도 읽히는가\n"
    "- style_match: 차분한 어두운 톤·시네마틱·고급 테크 매거진 느낌인가. 과포화·스톡 느낌 강하면 2 이하"
)
WEIGHTS = {"relevance": 0.4, "lower_third_clear": 0.35, "style_match": 0.25}


@dataclass
class VisionScore:
    faces: bool = False
    text_or_logo: bool = False
    brand_like: bool = False
    relevance: int = 0
    lower_third_clear: int = 0
    style_match: int = 0
    reason: str = ""
    error: str = ""

    @property
    def hard_fail(self) -> bool:
        return self.faces or self.text_or_logo or self.brand_like or bool(self.error)

    @property
    def total(self) -> float:
        if self.hard_fail:
            return 0.0
        return round(sum(getattr(self, k) * w for k, w in WEIGHTS.items()), 2)

    def to_dict(self) -> dict:
        return {**self.__dict__, "total": self.total, "hard_fail": self.hard_fail}


class Scorer(Protocol):
    def score(self, image_bytes: bytes, headline: str, concept: str) -> VisionScore: ...


class HaikuScorer:
    def __init__(self, api_key: str | None = None, model: str = MODEL):
        import anthropic
        self.client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
        self.model = model
        self.calls = 0

    def score(self, image_bytes: bytes, headline: str, concept: str) -> VisionScore:
        import anthropic
        media = "image/png" if image_bytes[:8] == b"\x89PNG\r\n\x1a\n" else "image/jpeg"
        content = [
            {"type": "image", "source": {"type": "base64", "media_type": media,
                                         "data": base64.standard_b64encode(image_bytes).decode()}},
            {"type": "text", "text": f"카드 헤드라인: {headline}\n표현하려는 개념: {concept}\n이 사진을 심사하라."},
        ]
        try:
            resp = self.client.messages.create(
                model=self.model, max_tokens=600, system=SYSTEM,
                output_config={"effort": "low"},
                messages=[{"role": "user", "content": content}],
            )
        except anthropic.APIError as exc:
            log.warning("vision score failed: %s", exc)
            return VisionScore(error=str(exc)[:120])
        self.calls += 1
        if resp.stop_reason == "refusal":
            return VisionScore(error="refusal")
        text = "".join(b.text for b in resp.content if b.type == "text")
        return parse_score(text)


def parse_score(text: str) -> VisionScore:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return VisionScore(error=f"no json: {text[:80]}")
    try:
        d = json.loads(m.group(0))
    except json.JSONDecodeError as exc:
        return VisionScore(error=f"bad json: {exc}")
    def _int(k): 
        try: return max(1, min(5, int(d.get(k, 0))))
        except (TypeError, ValueError): return 1
    return VisionScore(
        faces=bool(d.get("faces")), text_or_logo=bool(d.get("text_or_logo")),
        brand_like=bool(d.get("brand_like")), relevance=_int("relevance"),
        lower_third_clear=_int("lower_third_clear"), style_match=_int("style_match"),
        reason=str(d.get("reason", ""))[:200],
    )


@dataclass
class PickResult:
    chosen: Candidate | None
    scored: list[tuple[Candidate, VisionScore]] = field(default_factory=list)
    skipped_used: list[Candidate] = field(default_factory=list)
    skipped_similar: list[Candidate] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "chosen": _cand_dict(self.chosen) if self.chosen else None,
            "candidates": [{**_cand_dict(c), "vision": s.to_dict()} for c, s in self.scored],
            "skipped_used": [c.key for c in self.skipped_used],
            "skipped_similar": [c.key for c in self.skipped_similar],
        }


def _cand_dict(c: Candidate) -> dict:
    return {"source": c.source, "id": c.external_id, "query": c.query, "alt": c.alt,
            "photographer": c.photographer, "page_url": c.page_url, "full_url": c.full_url}


def pick(candidates: list[Candidate], headline: str, concept: str, scorer: Scorer, db: Database | None,
         max_score_calls: int = 8, min_total: float = 3.0, similar_distance: int = 8,
         exclude: set[tuple[str, str]] | None = None) -> PickResult:
    """후보 순서대로 점수를 매겨 최고점을 고른다. image_bytes가 채워진 후보만 심사한다.

    - 이미 쓴 사진(source, id)과 최근 30일 유사 해시(dHash)는 심사 전에 건너뛴다 (호출 절약)
    - 얼굴·글자·로고·브랜드 연상은 점수 0 (탈락)
    - 최고점이 min_total 미만이면 chosen=None → 호출자는 재검색 또는 단색 강등
    - exclude: 이번 실행에서 이미 심사한 (소스, id). 재검색 때 같은 후보를 다시 심사하지 않게 한다
    """
    result = PickResult(chosen=None)
    calls = 0
    for c in candidates:
        if c.image_bytes is None or (exclude and c.key in exclude):
            continue
        if db is not None and db.image_used(c.source, c.external_id):
            result.skipped_used.append(c)
            continue
        if db is not None and db.similar_image(to_hex(dhash(c.image_bytes)), similar_distance) is not None:
            result.skipped_similar.append(c)
            continue
        if calls >= max_score_calls:
            break
        calls += 1
        result.scored.append((c, scorer.score(c.image_bytes, headline, concept)))
    best = max(result.scored, key=lambda cs: cs[1].total, default=None)
    if best is not None and best[1].total >= min_total:
        result.chosen = best[0]
    return result
