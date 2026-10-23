"""cardkit — 비전 검수: 후보 이미지를 Claude에게 보여주고 얼굴·글자·로고를 탈락시킨 뒤 점수로 고른다."""

from __future__ import annotations

import base64
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Callable, Protocol

from .store import Store as Database   # 사진 재사용 기록 (image_used·similar_image)
from .imagehash import dhash, to_hex
from .stock import Candidate

log = logging.getLogger(__name__)

MODEL = "claude-haiku-5-5"
SYSTEM = (
    "너는 인스타그램 카드뉴스 계정 '{account}'의 사진 에디터다. 1080×1350 세로 카드의 사진 후보를 심사한다. "
    "사진은 액자·전면·원형 등 레이아웃에 따라 놓이고, 사진 아래나 위에 제목이 올라간다.\n"
    "다음 JSON만 출력한다(설명 금지):\n"
    '{"faces": bool, "text_or_logo": bool, "brand_like": bool, "relevance": 1-5, '
    '"lower_third_clear": 1-5, "style_match": 1-5, "reason": "40자 이내 한 문장"}\n'
    "- faces: 알아볼 수 있는 사람 얼굴이 있으면 true (뒷모습·실루엣·손만 보이면 false)\n"
    "- text_or_logo: 글자, 숫자, 간판, 로고, 워터마크가 보이면 true\n"
    "- brand_like: 특정 기업 제품·로고·캐릭터가 연상되면 true (예: 애플 제품 디자인, 테슬라 차량)\n"
    "- relevance: 주어진 개념을 은유적으로라도 잘 표현하는가. 주제의 뻔한 클리셰(예: 테크는 로봇·파란 회로판, 심리는 머리 모양 실루엣)는 2 이하\n"
    "- lower_third_clear: 사진 하단이 단순해 액자 아래 글과 시각적으로 충돌하지 않는가\n"
    "- style_match: {style} 과포화·스톡 느낌 강하면 2 이하"
)
# v2 템플릿은 사진이 액자 안에 들어가 하단 여백이 덜 중요하고, 관련성이 약한 사진이 더 눈에 띈다 → 관련성 가중치 상향
WEIGHTS = {"relevance": 0.5, "lower_third_clear": 0.2, "style_match": 0.3}


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
    def __init__(self, api_key: str | None = None, model: str = MODEL, account: str = "카드뉴스",
                 style: str = "차분한 톤·여백·잡지 사진 느낌인가."):
        import anthropic
        self.client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
        self.system = SYSTEM.replace("{account}", account).replace("{style}", style)
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
                model=self.model, max_tokens=600, system=self.system,
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
    tone: dict[tuple[str, str], float] = field(default_factory=dict)   # 후보별 팔레트 톤 점수(0~1), bonus 를 줬을 때만

    def to_dict(self) -> dict:
        return {
            "chosen": _cand_dict(self.chosen) if self.chosen else None,
            "candidates": [{**_cand_dict(c), "vision": s.to_dict(), **({"tone": self.tone[c.key]} if c.key in self.tone else {})}
                           for c, s in self.scored],
            "skipped_used": [c.key for c in self.skipped_used],
            "skipped_similar": [c.key for c in self.skipped_similar],
        }


def _cand_dict(c: Candidate) -> dict:
    return {"source": c.source, "id": c.external_id, "query": c.query, "alt": c.alt,
            "photographer": c.photographer, "page_url": c.page_url, "full_url": c.full_url}


def pick(candidates: list[Candidate], headline: str, concept: str, scorer: Scorer, db: Database | None,
         max_score_calls: int = 8, min_total: float = 3.0, similar_distance: int = 8,
         exclude: set[tuple[str, str]] | None = None, bonus: Callable[[bytes], float] | None = None,
         bonus_weight: float = 0.5) -> PickResult:
    """후보 순서대로 점수를 매겨 최고점을 고른다. image_bytes가 채워진 후보만 심사한다.

    - 이미 쓴 사진(source, id)과 최근 30일 유사 해시(dHash)는 심사 전에 건너뛴다 (호출 절약)
    - 얼굴·글자·로고·브랜드 연상은 점수 0 (탈락)
    - 최고점이 min_total 미만이면 chosen=None → 호출자는 재검색 또는 단색 강등
    - exclude: 이번 실행에서 이미 심사한 (소스, id). 재검색 때 같은 후보를 다시 심사하지 않게 한다
    - bonus: 사진 바이트 → 0~1 (예: 팔레트 톤 어울림). 순위는 비전 총점 + bonus×bonus_weight 로 정하되,
      합격선(min_total)은 비전 총점만 본다 — 톤이 좋아도 내용이 안 맞는 사진은 뽑지 않는다
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
    if bonus is not None:
        for c, sc in result.scored:
            if not sc.hard_fail:
                try:
                    result.tone[c.key] = round(float(bonus(c.image_bytes)), 3)
                except Exception as exc:  # noqa: BLE001 — 톤 계산 실패는 가산점 0
                    log.warning("tone bonus failed: %s", exc)
    passed = [cs for cs in result.scored if cs[1].total >= min_total]
    best = max(passed, key=lambda cs: cs[1].total + bonus_weight * result.tone.get(cs[0].key, 0.0), default=None)
    if best is not None:
        result.chosen = best[0]
    return result
