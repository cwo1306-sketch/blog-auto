"""경계 구간(유사도 0.35~0.5) 기사 쌍에 "같은 사건인가?"를 Claude Haiku에게 묻는다."""

from __future__ import annotations

import logging
from typing import Protocol

log = logging.getLogger(__name__)

MODEL = "claude-haiku-5-5"
SYSTEM = (
    "너는 뉴스 데스크의 중복 판정기다. 두 뉴스 기사의 제목과 요약을 보고 "
    "같은 사건(같은 발표·같은 발언·같은 사고·같은 발표 자료)을 다루는지 판정한다. "
    "같은 회사나 같은 주제라도 다른 사건이면 '다름'이다. "
    "반드시 '같음' 또는 '다름' 한 단어로만 답한다."
)


class Judge(Protocol):
    def same_event(self, a_title: str, a_desc: str, b_title: str, b_desc: str) -> bool | None: ...


class HaikuJudge:
    """반환값: True(같은 사건) / False(다름) / None(판정 실패 → 호출자는 '다름'으로 처리)."""

    def __init__(self, api_key: str | None = None):
        import anthropic  # 선택 의존성: 판정을 켠 경우에만 필요

        self.client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
        self.calls = 0

    def same_event(self, a_title: str, a_desc: str, b_title: str, b_desc: str) -> bool | None:
        import anthropic

        prompt = (f"기사 A\n제목: {a_title}\n요약: {a_desc}\n\n"
                  f"기사 B\n제목: {b_title}\n요약: {b_desc}\n\n같은 사건인가?")
        try:
            resp = self.client.messages.create(
                model=MODEL, max_tokens=16, system=SYSTEM,
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
        if text.startswith("같"):
            return True
        if text.startswith("다"):
            return False
        return None
