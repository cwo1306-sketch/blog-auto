"""카드뉴스 구성 템플릿(format). 네이버에 실제 올라오는 언론사 카드뉴스를 분석해 만들었다 (docs/TEMPLATES.md).

분석 대상(2026-10-21): ZDNet코리아 [카드뉴스] AMEET 시리즈 6건(8장), 연합뉴스 '우리말 구조대'(10장), 이데일리 K-스마트팜(8장),
스브스뉴스 추리 서사(논문). 공통: 8~10장, 질문형 표지, 비유, 수치 부제, 전문가 인용/비율, 마지막에 행동 제안.

장 수는 표지 1 + 본문 N(4~6) + 마무리 1. slide_type 는 photo / stat / list / term / qa / compare / quote.
"""

from __future__ import annotations

SLIDE_TYPES = ("photo", "stat", "list", "term", "qa", "compare", "quote")
MAX_BODY_SLIDES = 6

FORMATS: dict[str, dict] = {
    "debate": {
        "name": "질문-토론-권고형",
        "ref": "ZDNet코리아 AMEET 카드뉴스 (8장)",
        "when": "찬반이 갈리거나 '해도 되나/언제부터'를 묻는 주제. 전문가 의견·비율·권고가 기사에 있을 때",
        "body_slides": 6,
        "slides": ["photo", "stat", "photo", "compare|stat", "quote|photo", "list"],
        "rules": (
            "표지: 첫 줄은 질문(물음표), 둘째 줄은 핵심 수치 하나를 부제로. 본문 6장: ② '이런 생각 해보신 적 있으시죠?'처럼 독자 공감으로 여는 photo "
            "③ 핵심 수치 stat ④ 원리를 일상 비유로 푸는 photo(title은 '왜 그럴까요?'류) ⑤ 찬반·전문가 비율은 compare(left 찬성/right 반대, "
            "points에 비율과 근거) 또는 stat ⑥ 반론이나 우려를 quote(전문가·기관 발언 인용, 기사에 있는 발언만) 또는 photo "
            "⑦ 상황별 구체 권고 list(title 14자, body에 '~라면 ~하세요' 2~3개 상황). 마무리 question은 '오늘부터 ~해보는 건 어떨까요?'처럼 행동 제안."
        ),
    },
    "glossary": {
        "name": "용어 묶음형",
        "ref": "연합뉴스 '우리말 구조대' (10장)",
        "when": "기사에 낯선 용어가 3~4개 등장하고, 용어를 알면 흐름이 읽히는 발표·보고서",
        "body_slides": 6,
        "slides": ["photo", "term", "term", "term", "term", "quote|photo"],
        "rules": (
            "표지: 용어 3~4개를 따옴표로 나열('AI 에이전트', '바이브 코딩'…)하고 '뭐가 다를까?'류 한 줄. 본문 6장: ② 왜 이 용어들이 지금 쏟아지는가 photo "
            "③~⑥ 용어 하나씩 term(title=용어 10자, label=한 줄 정의 30자, body=비유 또는 기사 속 쓰임 50~110자) "
            "⑦ 전문가 인용 quote(기사에 있는 발언 그대로, 발언자·소속) 또는 오용 사례 photo. 마무리 summary는 '용어를 알면 ~가 보인다'류."
        ),
    },
    "scene": {
        "name": "현장 사례형",
        "ref": "이데일리 K-스마트팜 카드뉴스 (8장)",
        "when": "구체적인 장소·장면이 있는 기사(공장, 매장, 병원, 시연 현장). 사진이 중요한 주제",
        "body_slides": 6,
        "slides": ["photo", "photo", "stat", "photo", "photo", "photo"],
        "rules": (
            "한 장에 한 문장. 본문 6장: ② 장면 묘사 photo('뉴욕의 한 대형마트 안, …') ③ 어떻게 작동하나 photo ④ 핵심 수치 stat "
            "⑤ 또 다른 현장이나 확장 사례 photo ⑥ 계획·전망 photo ⑦ 의미 한 줄 photo. photo 장 body는 30~70자(짧게), title은 장면을 가리키는 "
            "명사구 12자. 사진 검색어는 그 장면을 직접 묘사(구체형 우선). 기사에 없는 장소·수치를 만들지 않는다."
        ),
    },
    "reveal": {
        "name": "반전 추리형",
        "ref": "스브스뉴스 추리 서사(의문 제시 → 비밀의 풀림)",
        "when": "통념과 다른 결론이 있는 기사, '사실은 ~였다'가 성립할 때",
        "body_slides": 5,
        "slides": ["photo", "photo", "stat|photo", "compare", "photo"],
        "rules": (
            "표지: '~라고 알고 있었다면' 또는 '왜 ~일까?' 의문. 본문 5장: ② 통념·겉보기 상황 photo ③ 단서 1 photo ④ 단서 2 (수치면 stat) "
            "⑤ 반전을 compare(left='알려진 것', right='실제로는')로 ⑥ 왜 그런가, 무엇이 달라지나 photo. photo body는 40~110자로 단서를 짧게 던진다. 결론을 마지막까지 미루되 "
            "표지에서 답을 암시하지 않는다. 마무리 summary에 반전 한 문장."
        ),
    },
    "qa": {
        "name": "문답형",
        "ref": "VOX 카드 스택, ZDNet 질문형 표지",
        "when": "정책·요금·서비스 변경처럼 독자가 '나한테 뭐가 달라져?'를 물을 때",
        "body_slides": 5,
        "slides": ["qa", "qa", "qa", "qa", "list"],
        "rules": (
            "본문 5장: ②~⑤ qa(title=독자 질문 30자 물음표, body=결론 먼저 60~120자): 무슨 일 → 나한테 영향 → 왜 → 언제부터 "
            "⑥ '이렇게 하세요' list(상황별 권고 2~3개). 표지는 가장 큰 질문 하나 + 수치 부제."
        ),
    },
    "numbers": {
        "name": "수치 브리핑형",
        "ref": "ZDNet 수치 부제 + 이데일리 수치 카드",
        "when": "원문 수치 3개 이상이 메시지일 때(실적, 시장 규모, 점유율)",
        "body_slides": 5,
        "slides": ["stat", "stat", "stat", "stat", "photo"],
        "rules": (
            "본문 5장: ②~⑤ stat(각 label 14자, title은 그 숫자의 의미 14자, body는 해석 60~110자, 수치·단위 원문 그대로, source_quote 원문 문장 복사) "
            "⑥ 수치를 묶는 결론 photo. 표지 둘째 줄에 가장 큰 수치. stat 연속·개수 제한 없음."
        ),
    },
    "explainer": {
        "name": "설명형(기본)",
        "ref": "일반 뉴스 설명형",
        "when": "위 어느 틀에도 맞지 않는 단일 사건",
        "body_slides": 4,
        "slides": ["photo", "photo", "photo|stat", "photo"],
        "rules": "본문 4장: 무슨 일 → 왜 중요 → 맥락·숫자(stat 가능) → 전망. photo title 14자, body 90~120자. stat 최대 2장, 연속 금지.",
    },
}

AUTO_RULE = (
    "format 선택 기준: 찬반·권고가 있으면 debate, 낯선 용어 3개 이상이면 glossary, 구체적 현장·장면이 있으면 scene, 통념과 다른 결론이면 reveal, "
    "독자 영향을 묻는 정책·서비스 변경이면 qa, 수치 3개 이상이 핵심이면 numbers, 그 외 explainer."
)


def body_slide_count(fmt: str) -> int:
    return FORMATS.get(fmt, FORMATS["explainer"])["body_slides"]


def format_rules(fmt: str | None) -> str:
    if fmt and fmt != "auto":
        f = FORMATS[fmt]
        return (f"이 원고의 format은 '{fmt}'({f['name']}, 참고: {f['ref']})로 고정한다. 본문 장 수 {f['body_slides']}장. {f['rules']}")
    lines = [AUTO_RULE, "각 format 규칙 (본문 장 수를 반드시 지킨다):"]
    for k, f in FORMATS.items():
        lines.append(f"- {k}({f['name']}, 본문 {f['body_slides']}장, 참고 {f['ref']}): {f['rules']}")
    return "\n".join(lines)
