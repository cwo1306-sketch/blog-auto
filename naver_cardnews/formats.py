"""카드뉴스 구성 템플릿(format) 정의. 모두 표지 1 + 본문 4 + 마무리 1 = 6장.

리서치(docs/TEMPLATES.md) 기준 6가지:
  explainer  설명형     무슨 일 → 왜 중요 → 맥락·숫자 → 전망            (기본, 사진 카드 중심)
  listicle   나열형     01~04 한 장에 하나씩                              (발표에 항목이 여럿일 때)
  numbers    수치형     큰 숫자 4개와 한 줄 해석                          (수치가 3개 이상 핵심일 때)
  term       용어해설   단어 → 한 줄 정의 → 비유 → 뉴스와의 연결 → 쓰임    (낯선 기술 용어가 핵심일 때)
  qa         문답형     독자가 물을 법한 질문 4개와 답                     (논란·정책·'그래서 나한테?'형)
  compare    비교형     A vs B / 오해 vs 사실 / 이전 vs 이후 2열 비교        (경쟁·변화·오해가 핵심일 때)

본문 장의 slide_type 는 format 과 독립적으로 섞일 수 있다(예: explainer 안의 stat 장). 렌더는 slide_type 만 본다.
"""

from __future__ import annotations

SLIDE_TYPES = ("photo", "stat", "list", "term", "qa", "compare")

FORMATS: dict[str, dict] = {
    "explainer": {
        "name": "설명형",
        "when": "하나의 사건을 처음 접하는 독자에게 맥락까지 설명해야 할 때 (기본값)",
        "slides": ["photo", "photo", "photo|stat", "photo"],
        "rules": (
            "본문 4장 흐름: ① 무슨 일이 있었나 ② 왜 중요한가(독자에게 무엇이 달라지나) ③ 맥락·숫자(핵심 수치가 있으면 stat) "
            "④ 의미·전망. 각 장은 photo(title 14자, body 90~120자) 또는 stat."
        ),
    },
    "listicle": {
        "name": "나열형",
        "when": "발표·보고서에 항목이 여럿이거나 '알아야 할 N가지'로 묶일 때",
        "slides": ["list", "list", "list", "list"],
        "rules": (
            "본문 4장은 모두 list: 번호는 코드가 붙이므로 쓰지 말고 title(14자 이내, 명사형)과 body(60~110자, 한 항목의 핵심과 "
            "독자에게 의미)만. 중요도 순이 아니라 읽는 흐름 순으로. 표지 둘째 줄에 'N가지' 같은 개수 예고를 넣는다."
        ),
    },
    "numbers": {
        "name": "수치형",
        "when": "기사에 원문 그대로 인용 가능한 수치가 3개 이상이고 수치가 곧 메시지일 때",
        "slides": ["stat", "stat", "stat", "stat|photo"],
        "rules": (
            "본문 4장 중 3~4장을 stat으로. 각 stat의 label은 '무엇의 수치인지' 14자, 그리고 title은 그 숫자가 뜻하는 바 한 줄(14자), "
            "body는 해석 한두 문장(60~110자). 수치는 반드시 원문 표기 그대로, source_quote는 원문 문장 그대로 복사. "
            "stat 연속 금지 규칙은 이 포맷에서는 적용하지 않는다."
        ),
    },
    "term": {
        "name": "용어해설",
        "when": "기사의 핵심이 낯선 기술 용어 하나로 모이고, 그 용어를 알면 뉴스가 이해될 때",
        "slides": ["term", "photo", "photo", "photo"],
        "rules": (
            "2장은 term: title=용어(10자 이내, 영문 약어면 괄호 없이), label=한 줄 정의(30자 이내), body=일상 비유로 풀어 쓴 설명(60~110자). "
            "3장: 이 뉴스에서 그 용어가 왜 등장했나. 4장: 실제로 어디에 쓰이나(독자 생활과 연결). 5장: 앞으로 무엇이 달라지나. "
            "표지 첫 줄은 '○○이 뭐길래' 같은 질문형."
        ),
    },
    "qa": {
        "name": "문답형",
        "when": "독자가 '그래서 나한테 뭐가 달라지는데?'를 물을 만한 정책·논란·서비스 변경",
        "slides": ["qa", "qa", "qa", "qa"],
        "rules": (
            "본문 4장은 모두 qa: title=독자가 실제로 물을 법한 질문(30자 이내, 구어체, 물음표), body=답(60~120자, 첫 문장에 결론, "
            "근거는 기사에 있는 것만). 질문 순서: 무슨 일 → 나한테 영향 → 왜 그런가 → 언제부터/앞으로. 표지는 가장 큰 질문 하나."
        ),
    },
    "compare": {
        "name": "비교형",
        "when": "두 대상(기업·제품·이전/이후·오해/사실)의 차이가 메시지일 때",
        "slides": ["compare", "compare", "compare", "photo|stat"],
        "rules": (
            "2~4장은 compare: title=비교 축(14자, 예: '성능', '가격', '공개 범위'), compare={left:{label(8자), points[2~3개, 각 22자 이내]}, "
            "right:{label, points}}. 좌우 라벨은 전 장에서 같은 두 대상을 유지한다. 오해 vs 사실이면 left='오해', right='사실'. "
            "5장은 비교의 결론(photo 또는 stat). 기사에 없는 대상의 수치를 추측하지 않는다."
        ),
    },
}

AUTO_RULE = (
    "format 선택 기준: 수치 3개 이상이 핵심이면 numbers, 낯선 용어가 핵심이면 term, 두 대상의 차이가 핵심이면 compare, "
    "정책·논란·서비스 변경으로 독자가 영향을 물을 만하면 qa, 항목이 여럿인 발표면 listicle, 그 외는 explainer."
)


def format_rules(fmt: str | None) -> str:
    if fmt and fmt != "auto":
        f = FORMATS[fmt]
        return f"이 원고의 format은 '{fmt}'({f['name']})로 고정한다. {f['rules']}"
    lines = [AUTO_RULE, "각 format 규칙:"]
    for k, f in FORMATS.items():
        lines.append(f"- {k}({f['name']}): {f['rules']}")
    return "\n".join(lines)
