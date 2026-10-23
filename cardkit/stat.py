"""숫자 장(stat): 원문 대조 규칙과 글자 크기 단계."""

from __future__ import annotations

import re
from dataclasses import dataclass

MAX_LABEL_CHARS = 14


@dataclass
class Stat:
    value: str          # "55", "1,000", "34.7"
    unit: str           # "%", "조원", "억달러"
    label: str          # 한 줄 설명 (≤14자)
    source_quote: str   # 원문에서 수치가 든 문장 그대로


class StatError(ValueError):
    pass


def validate_stat(stat: Stat, article_text: str | None = None) -> None:
    """작성 규칙 검사. article_text를 주면 원문 대조까지 한다 (validate.py의 수치 대조 보완)."""
    # 숫자(쉼표·소수점 둘째 자리)에 한국식 자릿수 단위(억·만·천·조)가 섞인 형태 허용: 55 / 34.7 / 1,000 / 4억2600만
    if not re.fullmatch(r"[0-9][0-9,]*(\.[0-9]{1,2})?(?:[만억조천][0-9][0-9,]*)*[만억조천]?", stat.value):
        raise StatError(f"value는 숫자만(쉼표·소수점 둘째 자리, 억·만 자릿수 허용): {stat.value!r}")
    if not stat.unit.strip():
        raise StatError("단위가 없는 숫자는 쓰지 않는다")
    if len(stat.label) > MAX_LABEL_CHARS:
        raise StatError(f"label은 {MAX_LABEL_CHARS}자 이하: {stat.label!r}")
    quote_norm = stat.source_quote.replace(" ", "")
    if (stat.value + stat.unit).replace(" ", "") not in quote_norm:
        raise StatError("value+unit 이 source_quote 안에 그대로 없다")
    if article_text is not None and quote_norm not in article_text.replace(" ", ""):
        raise StatError("source_quote 가 원문에 없다")


def len_class(value: str, unit: str) -> str:
    """숫자 글자 수 + 단위 폭(한글 단위는 숫자 1자 폭, 기호는 반 자)으로 크기 단계를 정한다.
    렌더 때 그래도 넘치면 render_png가 글자 크기를 더 줄인다."""
    n = sum(ch.isdigit() for ch in value) + (0.5 if "." in value else 0)
    u = unit.strip()
    n += 0 if len(u) >= 3 else sum(1.0 if ord(ch) > 0x2E80 else 0.5 for ch in u)   # 3자 이상 단위는 아래 줄로 내려가 폭에 안 들어감
    if n <= 3.5:
        return "short"
    if n <= 5.5:
        return "medium"
    return "long"
