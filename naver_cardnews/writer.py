"""Claude Sonnet 5.5 원고 생성 (패키지 본체. cardnews/writer.py 는 keys 로더를 붙인 래퍼).

원본 대비 개선:
- 스키마 확장: 장마다 slide_type(photo|stat), stat{value,unit,label,source_quote}, image_queries[은유형, 구체형],
  image_concept(한국어 한 줄, 비전 검수 입력). 기존 image_query는 호환용으로 함께 유지
- 응답 파싱: ```json 펜스·앞뒤 설명 허용, 실패 시 원문 일부를 담은 명확한 예외 (원본은 AttributeError)
- 구조 검증(필수 키·장 수)을 writer 안에서 먼저 해 validate 전에 깨진 JSON을 걸러낸다
- usage(입출력 토큰)를 script["_usage"]에 기록 → meta.json 비용 실측·월 상한 가드(HANDOFF 6장)
- effort=medium: 원고 품질은 유지하면서 사고 토큰을 줄인다 (원본: 기본값 high, max_tokens 16000 유지)
- pick_photo는 비전 검수(naver_cardnews.vision_pick)로 대체. 호환용으로 남기되 호출 시 경고
"""

from __future__ import annotations

import json
import logging
import re
import warnings

import anthropic

from .formats import FORMATS, MAX_BODY_SLIDES, body_slide_count, format_rules

log = logging.getLogger(__name__)

MODEL = "claude-sonnet-5-5"
PICK_MODEL = "claude-haiku-5-5"
SLIDES = 4
MAX_STAT = 2

SYSTEM = """너는 10년 차 뉴스 에디터이자 인스타그램 카드뉴스 기획자다. 계정 'AI 뉴스 3분 브리핑'은
AI·테크 뉴스를 쉬운 말로 풀어 준다. 기사 원문을 읽고 1080x1350 카드뉴스 6장(표지 1 + 본문 4 + 마무리 1) 원고를 만든다.

규칙
- 기사에 없는 사실·수치를 만들지 않는다. 수치는 원문 표기 그대로 쓴다(단위 환산·반올림 금지). 수치 뒤에는 원문과 같은 단위를 붙인다.
- 원문 문장을 그대로 베끼지 말고 쉬운 말로 재구성한다. 전문 용어는 한 번은 풀어 쓴다.
- 한자 약어(中·美·日·韓 등)를 쓰지 말고 한글로 쓴다.
- 누가 주장한 수치인지(회사 자료인지, 공식 통계인지) 출처 주체를 본문에 밝힌다.
- 표지: 2~3줄, 줄당 공백 포함 12자 이내. 가장 강한 훅 1~2줄은 highlight=true.
- 본문 장 수는 format이 정한다(4~6장). 장 구성도 format을 따른다. 말투는 친근한 해요체('~해요/~인데요/~거든요')를 기본으로 하되
  stat·compare·quote 장은 간결체. 네이버 언론사 카드뉴스처럼 수치 하나를 표지 부제로 쓰고, 어려운 원리는 반드시 일상 비유로 한 번 풀어 준다.
  · photo 장: title(공백 포함 14자 이내), body(공백 포함 90~120자). 사진 지시 필요.
  · stat 장: 핵심이 숫자 하나일 때. stat = {value: 숫자만(쉼표 허용, 소수점 둘째 자리까지), unit: 원문 단위, label: 14자 이내 설명,
    source_quote: 그 수치가 든 원문 문장을 토씨 하나 바꾸지 말고 그대로 복사}. title·body도 채운다. explainer에서는 최대 2장, 연속 금지, 2장은 photo.
  · list 장: title(14자, 명사형) + body(60~110자). 번호는 코드가 붙인다. 사진 없음.
  · term 장: title=용어(10자) + label=한 줄 정의(30자) + body=비유 설명(60~110자). 사진 없음.
  · qa 장: title=질문(30자, 물음표로 끝) + body=답(60~120자, 결론 먼저). 사진 없음.
  · compare 장: title=비교 축(14자) + compare={left:{label(8자), points[2~3, 각 22자]}, right:{label, points}}. 사진 없음.
  · quote 장: 기사에 실제로 있는 발언만. title=발언 요지(14자), body=인용문 그대로(따옴표 없이, 40~110자), label='이름 소속/직함'(20자). 사진 없음.
  · 사진 없는 장(list/term/qa/compare)은 image_queries를 빈 배열로, image_concept은 빈 문자열로 둔다.
- 사진 지시(photo 장과 표지): image_queries는 영어 검색어 2개. 첫째는 은유형(abstract light, glass lens, data stream 같은 추상 장면),
  둘째는 구체형(server room corridor, circuit macro, city at night 같은 실제 장면). 각 2~5단어.
  실존 인물·기업명·제품명·로고·국기·글자가 보이는 장면은 넣지 않는다 (예: 'nvidia chip' 대신 'glowing processor macro').
  image_concept: 그 장의 사진이 표현해야 할 개념을 한국어 한 문장(20자 안팎)으로. 사진 심사 기준으로 쓰인다.
- outro: summary는 기사 전체를 한 문장으로(공백 포함 25~45자, 수치 1개 이하), question은 독자 의견을 묻는 댓글 유도 질문
  (공백 포함 30자 이내, 정치적 편가르기 금지).
- caption: 인스타 캡션. 줄 구조를 지킨다 → 1줄: 훅(표지와 다른 표현, 이모지 0~1개) / 빈 줄 / 2~4줄: 핵심 3가지를 각 한 문장으로
  ("•"로 시작) / 빈 줄 / 1줄: 댓글 유도(outro.question과 같거나 변형) / 1줄: "출처: {언론사}". 전체 공백 포함 350자 이내.
- hashtags: 8~10개, '#' 포함. 앞 3개는 고정(#AI뉴스 #AI #테크뉴스), 나머지는 기사 고유 키워드(기업·기술·제품명 가능).

JSON만 출력한다. 스키마:
{"format":"debate"|"glossary"|"scene"|"reveal"|"qa"|"numbers"|"explainer",
 "cover":{"lines":[{"text":str,"highlight":bool}],"image_queries":[str,str],"image_concept":str},
 "slides":[{"slide_type":"photo"|"stat"|"list"|"term"|"qa"|"compare"|"quote","title":str,"body":str,"label":str,
            "image_queries":[str,str],"image_concept":str,
            "stat":{"value":str,"unit":str,"label":str,"source_quote":str} | null,
            "compare":{"left":{"label":str,"points":[str]},"right":{"label":str,"points":[str]}} | null}],
 "outro":{"summary":str,"question":str},
 "caption":str,"hashtags":[str]}

구성 템플릿
{FORMAT_RULES}"""

PICK_SYSTEM = """카드뉴스 배경 사진을 고른다. 후보 사진 설명(alt) 목록과 카드 문구가 주어진다.
문구의 주제를 가장 직접적으로 떠올리게 하는 사진 1장을 고른다.
피할 것: 주제와 무관한 일상 장면, 얼굴이 알아보이는 사람, 화면 속 글자가 많은 사진, 브랜드·앱 이름이나 로고가 설명에 나오는 사진.
번호만 출력한다."""

_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.S)


class WriterError(RuntimeError):
    pass


_API_KEY: str | None = None


def configure(api_key: str | None) -> None:
    """모듈 전역 키 설정. 없으면 SDK 기본 경로(ANTHROPIC_API_KEY 환경 변수)를 쓴다."""
    global _API_KEY
    _API_KEY = api_key or None


def _client():
    return anthropic.Anthropic(api_key=_API_KEY) if _API_KEY else anthropic.Anthropic()


def _text(msg) -> str:
    return "".join(b.text for b in msg.content if b.type == "text")


def parse_script(text: str) -> dict:
    """모델 출력에서 JSON 객체를 꺼낸다. 펜스 안 → 가장 바깥 중괄호 순으로 시도."""
    m = _FENCE.search(text)
    candidates = [m.group(1)] if m else []
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start:end + 1])
    for cand in candidates:
        try:
            return json.loads(cand)
        except json.JSONDecodeError:
            continue
    raise WriterError(f"원고 JSON 파싱 실패: {text[:200]!r}")


def normalize_script(script: dict) -> dict:
    """구 스키마(image_query 하나)와 신 스키마를 같은 모양으로 맞추고 필수 키를 검사한다."""
    for key in ("cover", "slides", "outro", "caption", "hashtags"):
        if key not in script:
            raise WriterError(f"원고에 '{key}' 가 없습니다")
    fmt = script.get("format") if script.get("format") in FORMATS else "explainer"
    n = len(script["slides"]) if isinstance(script["slides"], list) else 0
    if not 4 <= n <= MAX_BODY_SLIDES:
        raise WriterError(f"본문 장은 4~{MAX_BODY_SLIDES}장이어야 합니다 (받음: {n})")
    if n != body_slide_count(fmt):
        raise WriterError(f"format '{fmt}'의 본문 장 수는 {body_slide_count(fmt)}장인데 {n}장을 받았습니다")

    def fix_image(item: dict) -> None:
        q = item.get("image_queries") or ([item["image_query"]] if item.get("image_query") else [])
        q = [str(x).strip() for x in q if str(x).strip()][:2]
        item["image_queries"] = q
        item["image_query"] = q[0] if q else ""          # 구 코드 호환
        item.setdefault("image_concept", "")

    fix_image(script["cover"])
    script["format"] = script.get("format") if script.get("format") in FORMATS else "explainer"
    for s in script["slides"]:
        kind = s.get("slide_type") or "photo"
        if kind == "stat" and not s.get("stat"):
            kind = "photo"
        if kind == "compare" and not s.get("compare"):
            kind = "photo"
        if kind not in ("photo", "stat", "list", "term", "qa", "compare", "quote"):
            kind = "photo"
        s["slide_type"] = kind
        if kind != "stat":
            s["stat"] = None
        if kind != "compare":
            s["compare"] = None
        s.setdefault("title", ""); s.setdefault("body", ""); s.setdefault("label", "")
        fix_image(s)
    return script


def system_prompt(fmt: str | None = None) -> str:
    return SYSTEM.replace("{FORMAT_RULES}", format_rules(fmt))


def write(article: dict, previous: dict | None = None, errors: list[str] | None = None,
          fmt: str | None = None) -> dict:
    """fmt: FORMATS 키 또는 None/'auto'(모델이 고른다)."""
    user = (f"언론사: {article['press']}\n날짜: {article['date']}\n"
            f"제목: {article['title']}\n\n본문:\n{article['body']}")
    if previous:
        prev = {k: v for k, v in previous.items() if not k.startswith("_")}
        user += ("\n\n---\n이전 원고:\n" + json.dumps(prev, ensure_ascii=False)
                 + "\n\n검수에서 아래 문제가 나왔다. 해당 부분만 고쳐 전체 JSON을 다시 출력해라.\n- "
                 + "\n- ".join(errors or []))
    msg = _client().messages.create(
        model=MODEL, max_tokens=16000, system=system_prompt(fmt),
        output_config={"effort": "medium"},
        messages=[{"role": "user", "content": user}],
    )
    if msg.stop_reason == "max_tokens":
        raise WriterError("원고가 max_tokens에서 잘렸습니다 (max_tokens 상향 또는 effort 조정)")
    if msg.stop_reason == "refusal":
        raise WriterError("모델이 원고 생성을 거부했습니다")
    script = normalize_script(parse_script(_text(msg)))
    u = msg.usage
    script["_usage"] = {"model": MODEL, "input_tokens": u.input_tokens, "output_tokens": u.output_tokens,
                        "rewrite": bool(previous), "format": script["format"]}
    return script


def pick_photo(card_text: str, candidates: list[dict]) -> int:
    """(호환용) alt 텍스트만 보고 고른다. 새 파이프라인은 naver_cardnews.vision_pick 을 쓴다."""
    warnings.warn("writer.pick_photo 는 비전 검수(vision_pick)로 대체되었습니다", DeprecationWarning, stacklevel=2)
    listing = "\n".join(f"{i}. {c.get('alt') or '(설명 없음)'}" for i, c in enumerate(candidates))
    msg = _client().messages.create(model=PICK_MODEL, max_tokens=64, system=PICK_SYSTEM,
                                    output_config={"effort": "low"},
                                    messages=[{"role": "user",
                                               "content": f"카드 문구:\n{card_text}\n\n후보:\n{listing}"}])
    m = re.search(r"\d+", _text(msg))
    i = int(m.group(0)) if m else 0
    return i if 0 <= i < len(candidates) else 0
