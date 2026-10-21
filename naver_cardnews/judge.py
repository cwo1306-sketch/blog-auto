"""Claude Haiku 판정기 두 가지.

- same_event : 경계 구간(유사도 0.25~0.4) 기사 쌍이 같은 사건인지
- on_niche   : 규칙 필터를 통과한 기사가 실제로 'AI·테크를 쉬운 말로' 니치에 맞는지
둘 다 한 단어로만 답하게 하고, 실패하면 None을 돌려줘 호출자가 보수적으로 처리한다.
"""

from __future__ import annotations

import logging
from typing import Protocol

log = logging.getLogger(__name__)

MODEL = "claude-haiku-5-5"

SAME_EVENT_SYSTEM = (
    "너는 뉴스 데스크의 중복 판정기다. 두 뉴스 기사의 제목과 요약을 보고 "
    "같은 사건(같은 발표·같은 발언·같은 사고·같은 발표 자료)을 다루는지 판정한다. "
    "같은 회사나 같은 주제라도 다른 사건이면 '다름'이다. "
    "반드시 '같음' 또는 '다름' 한 단어로만 답한다."
)

NICHE_SYSTEM = (
    "너는 인스타그램 카드뉴스 계정 'AI 뉴스 3분 브리핑'의 편집장이다. 니치는 'AI·테크를 쉬운 말로'다.\n"
    "기사 제목과 요약을 보고 이 계정의 카드뉴스 소재로 적합한지 판정한다.\n"
    "적합: 기사의 핵심이 AI·반도체·빅테크·로봇·자율주행·클라우드 같은 기술 자체, 그 제품·서비스·연구·"
    "기업 전략·투자·규제·정책·사회적 영향인 경우. 일반 독자가 '그래서 뭐가 달라지는데?'를 느낄 수 있어야 한다.\n"
    "부적합: AI가 곁다리로만 언급되는 기사(정치인 발언 속 AI, 주가·시황, 지자체 행사·수상·인사, 채용·교육 프로그램 "
    "홍보, 기업 보도자료식 MOU·행사 알림, 특정 지역 소식), 기술과 무관한 금융·부동산·스포츠·연예.\n"
    "반드시 '적합' 또는 '부적합' 한 단어로만 답한다."
)


class Judge(Protocol):
    def same_event(self, a_title: str, a_desc: str, b_title: str, b_desc: str) -> bool | None: ...
    def on_niche(self, title: str, desc: str) -> bool | None: ...


class HaikuJudge:
    def __init__(self, api_key: str | None = None):
        import anthropic  # 선택 의존성: 판정을 켠 경우에만 필요

        self.client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
        self.calls = 0

    def _ask(self, system: str, prompt: str, yes: str, no: str) -> bool | None:
        import anthropic

        try:
            resp = self.client.messages.create(
                model=MODEL, max_tokens=16, system=system,
                output_config={"effort": "low"},
                messages=[{"role": "user", "content": prompt}],
            )
        except anthropic.APIError as exc:
            log.warning("haiku judge failed: %s", exc)
            return None
        self.calls += 1
        if resp.stop_reason == "refusal":
            return None
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        if text.startswith(yes):
            return True
        if text.startswith(no):
            return False
        log.warning("haiku judge unexpected answer: %r", text)
        return None

    def same_event(self, a_title: str, a_desc: str, b_title: str, b_desc: str) -> bool | None:
        prompt = (f"기사 A\n제목: {a_title}\n요약: {a_desc}\n\n"
                  f"기사 B\n제목: {b_title}\n요약: {b_desc}\n\n같은 사건인가?")
        return self._ask(SAME_EVENT_SYSTEM, prompt, "같", "다")

    def on_niche(self, title: str, desc: str) -> bool | None:
        prompt = f"제목: {title}\n요약: {desc}\n\n이 계정의 카드뉴스 소재로 적합한가?"
        # '부적합'이 '적합'을 포함하므로 부정을 먼저 본다
        result = self._ask(NICHE_SYSTEM, prompt, "적합", "부적합")
        return result
