"""포맷(구성) 정의. 계정은 profile.formats 로 이 중에서 고른다.

장 수는 표지 1 + 본문 N + 마무리 1. slide_type:
photo · stat(큰 숫자) · chart(ECharts 그래프) · list(번호 항목) · term(용어) · qa(문답) · compare(2열 비교) · quote(인용)
· checklist(체크 항목 3~5개) · myth(오해 → 사실).

뉴스 7종은 네이버 언론사 카드뉴스 분석(blog-auto docs/TEMPLATES.md), 논문·심리 4종(study·traits·checklist·myth)은
카드뉴스 포맷 자료집(노션: 연구 요약, 특징 N가지 공감형, 체크리스트·자가진단, 오해와 진실)을 바탕으로 했다.
cues: 원문에 이 단어가 있으면 이 포맷을 후보로 올린다(compose.eligible_formats). numbers 는 수치 개수로 판단.
"""

from __future__ import annotations

SLIDE_TYPES = ("photo", "stat", "chart", "list", "term", "qa", "compare", "quote", "checklist", "myth")
NO_PHOTO_TYPES = {"stat", "chart", "list", "term", "qa", "compare", "quote", "checklist", "myth"}

FORMATS: dict[str, dict] = {
    # ---------------- 뉴스·해설 ----------------
    "debate": {
        "name": "질문-토론-권고형", "ref": "ZDNet코리아 AMEET (8장)",
        "when": "찬반이 갈리거나 '해도 되나/언제부터'를 묻는 주제. 전문가 의견·비율·권고가 원문에 있을 때",
        "cues": ("찬성", "반대", "우려", "논란", "전문가", "갈린", "해야", "권고", "비판", "반발"),
        "slides": ["photo", "stat", "photo", "compare|stat", "quote|photo", "list"],
        "rules": ("표지: 첫 줄은 질문, 둘째 줄은 핵심 수치. ② 독자 공감으로 여는 photo ③ 핵심 수치 stat ④ 원리를 일상 비유로 푸는 photo "
                  "⑤ 찬반·의견 비율 compare(left 찬성/right 반대) 또는 stat ⑥ 반론·우려 quote(원문에 있는 발언만) 또는 photo "
                  "⑦ 상황별 권고 list(body에 '~라면 ~하세요' 2~3개). 마무리 question 은 행동 제안."),
    },
    "glossary": {
        "name": "용어 묶음형", "ref": "연합뉴스 '우리말 구조대' (10장)",
        "when": "낯선 용어가 3~4개 나오고, 용어를 알면 흐름이 읽힐 때",
        "cues": (), "terms": 3,
        "slides": ["photo", "term", "term", "term", "term", "quote|photo"],
        "rules": ("표지: 용어 3~4개를 따옴표로 나열하고 '뭐가 다를까?'류 한 줄. ② 왜 이 용어들이 지금 쏟아지는가 photo "
                  "③~⑥ term(title=용어 10자, label=한 줄 정의 30자, body=비유 또는 원문 속 쓰임 50~110자) ⑦ 전문가 인용 quote 또는 photo."),
    },
    "scene": {
        "name": "현장 사례형", "ref": "이데일리 K-스마트팜 (8장)",
        "when": "구체적인 장소·장면이 있는 원문. 사진이 중요한 주제",
        "cues": ("현장", "매장", "공장", "병원", "시연", "전시", "부스", "거리", "마트", "캠퍼스", "연구실", "센터"),
        "slides": ["photo", "photo", "stat", "photo", "photo", "photo"],
        "rules": ("한 장에 한 문장. ② 장면 묘사 ③ 작동 방식 ④ 핵심 수치 stat ⑤ 또 다른 현장 ⑥ 계획·전망 ⑦ 의미 한 줄. "
                  "photo body 30~70자, title 은 장면을 가리키는 명사구 12자. 원문에 없는 장소·수치를 만들지 않는다."),
        "photo_body": (25, 75),
    },
    "reveal": {
        "name": "반전 추리형", "ref": "스브스뉴스 추리 서사(의문 제시 → 비밀의 풀림)",
        "when": "통념과 다른 결론이 있을 때, '사실은 ~였다'가 성립할 때",
        "cues": ("오히려", "사실은", "알고 보니", "통념", "예상과 달리", "반면", "착각", "반대로"),
        "slides": ["photo", "photo", "stat|photo", "compare", "photo"],
        "rules": ("표지: '~라고 알고 있었다면' 또는 '왜 ~일까?'. ② 통념 ③ 단서 1 ④ 단서 2(수치면 stat) "
                  "⑤ compare(left='알려진 것', right='실제로는') ⑥ 왜 그런가. 결론은 표지에서 암시하지 않는다."),
        "photo_body": (40, 110),
    },
    "qa": {
        "name": "문답형", "ref": "VOX 카드 스택, 정책브리핑 Q&A",
        "when": "독자가 '나한테 뭐가 달라져?', '그래서 어떻게 해?'를 물을 때",
        "cues": ("요금", "시행", "적용", "변경", "신청", "부터", "서비스", "정책", "규제", "이용자", "방법"),
        "slides": ["qa", "qa", "qa", "qa", "list"],
        "rules": ("②~⑤ qa(title=독자 질문 30자 물음표, body=결론 먼저 60~120자): 무슨 일 → 나한테 영향 → 왜 → 언제부터/어떻게 "
                  "⑥ '이렇게 하세요' list. 표지는 가장 큰 질문 하나."),
    },
    "numbers": {
        "name": "수치 브리핑형", "ref": "ZDNet 수치 부제 + 이데일리 수치 카드",
        "when": "원문 수치 3개 이상이 메시지일 때",
        "cues": (), "min_numbers": 4,
        "slides": ["stat", "chart|stat", "stat", "stat", "photo"],
        "rules": ("본문은 정확히 5장. ③ 한 장만 chart 또는 stat: 같은 단위 값이 2개 이상 나란히 있으면 chart, 아니면 stat. "
                  "②④⑤ stat(label 14자, title 은 숫자의 의미 14자, body 해석 60~110자) ⑥ 수치를 묶는 결론 photo."),
    },
    "explainer": {
        "name": "설명형(기본)", "ref": "일반 해설",
        "when": "위 어느 틀에도 맞지 않을 때",
        "cues": (), "always": True,
        "slides": ["photo", "photo", "photo|stat|chart", "photo"],
        "rules": "본문 4장: 무슨 일 → 왜 중요 → 맥락·숫자(stat 또는 chart 가능) → 전망. photo title 14자, body 90~120자.",
    },
    # ---------------- 논문·심리·정보 ----------------
    "study": {
        "name": "연구 요약형", "ref": "논문 카드뉴스(질문 → 방법 → 결과 → 해석 → 한계 → 적용)",
        "when": "연구·실험·조사 결과가 원문일 때 (논문 기반 계정의 기본)",
        "cues": ("연구", "실험", "참가자", "조사", "논문", "연구진", "분석", "표본", "대상자", "응답자", "study", "participants"),
        "slides": ["photo", "photo", "chart|stat", "photo", "photo", "list"],
        "rules": ("표지: 연구가 던진 질문을 독자 말로(예 '혼잣말, 정말 도움이 될까?') + 핵심 결과 한 줄. "
                  "② 왜 이 질문이 중요한가(일상 장면) photo ③ 누구를 어떻게 연구했나 photo(참가자 수·방법·기간은 원문 그대로) "
                  "④ 핵심 결과 chart 또는 stat ⑤ 결과를 쉬운 비유로 해석 photo ⑥ 한계(표본·인과관계·일반화)를 솔직하게 photo "
                  "⑦ 일상에 적용하는 법 list(2~3개, 연구가 뒷받침하는 범위 안에서). 상관관계를 인과로 쓰지 않는다."),
    },
    "traits": {
        "name": "특징 N가지 공감형", "ref": "한경매거진 '오래된 연인들의 7가지 특징' 등",
        "when": "원문이 특징·신호·유형을 여러 개 제시할 때",
        "cues": ("특징", "유형", "신호", "징후", "성향", "패턴", "습관", "공통점"),
        "slides": ["photo", "list", "list", "list", "list", "photo"],
        "rules": ("표지: '~하는 사람들의 N가지 특징'처럼 숫자를 넣은 질문·공감형. ② 도입 공감 photo ③~⑥ 특징 하나씩 list"
                  "(title=특징 14자, body=원문 근거로 설명 50~110자) ⑦ 마무리 photo('몇 개 해당하나요?'). 근거 없는 일반화 금지."),
    },
    "checklist": {
        "name": "체크리스트·자가점검형", "ref": "번아웃 자가진단, 가입 전 체크리스트",
        "when": "원문이 점검 항목·기준·증상을 제시할 때",
        "cues": ("체크", "점검", "증상", "기준", "자가", "척도", "문항", "진단", "해당"),
        "slides": ["photo", "checklist", "checklist", "photo", "list"],
        "rules": ("표지: '나도 혹시?'류 질문. ② 왜 점검해야 하나 photo ③④ checklist(title 14자, items 3~5개 각 22자, 원문 항목 그대로 쉬운 말로) "
                  "⑤ 결과 해석 photo(원문 기준이 있을 때만 '몇 개 이상이면'을 쓴다) ⑥ 대처법 list. 진단이 아니라 점검임을 분명히 한다."),
    },
    "myth": {
        "name": "오해와 진실형", "ref": "Myth vs Fact 캐러셀, 정책브리핑 OX",
        "when": "흔한 통념을 연구·자료로 바로잡을 수 있을 때",
        "cues": ("오해", "통념", "속설", "잘못 알려", "사실은", "근거 없", "믿음", "착각"),
        "slides": ["photo", "myth", "myth", "myth", "photo"],
        "rules": ("표지: 통념 하나를 따옴표로 + '정말일까?'. ② 왜 이런 오해가 퍼졌나 photo ③~⑤ myth(title=통념 문장 30자, "
                  "body=사실 50~120자, 원문 근거) ⑥ 정리 photo. 통념 문장도 원문에 나온 것만 쓴다."),
    },
}

AUTO_RULE = ("format 선택 기준: 찬반·권고 → debate, 낯선 용어 3개 이상 → glossary, 현장 → scene, 통념과 다른 결론 → reveal, "
             "독자 영향·방법 질문 → qa, 수치 3개 이상 → numbers, 연구 결과 → study, 특징 여러 개 → traits, 점검 항목 → checklist, "
             "통념 바로잡기 → myth, 그 외 explainer.")


def body_slide_count(fmt: str) -> int:
    return len(FORMATS[fmt]["slides"])


def photo_slots(fmt: str) -> int:
    return sum(1 for s in FORMATS[fmt]["slides"] if "photo" in s.split("|"))


def format_rules(fmt: str | None, allowed: list[str] | None = None) -> str:
    if fmt and fmt != "auto":
        f = FORMATS[fmt]
        return f"이 원고의 format은 '{fmt}'({f['name']})로 고정한다. 본문 장 수 정확히 {body_slide_count(fmt)}장. {f['rules']}"
    keys = allowed or list(FORMATS)
    lines = [AUTO_RULE, f"이 계정이 쓰는 format: {', '.join(keys)}. 각 규칙(본문 장 수를 반드시 지킨다):"]
    for k in keys:
        f = FORMATS[k]
        lines.append(f"- {k}({f['name']}, 본문 {body_slide_count(k)}장): {f['rules']}")
    return "\n".join(lines)
