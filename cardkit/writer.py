"""원고 작성(Claude). 프롬프트는 계정 설정(profile)에서 만든다: 계정 이름·독자·말투·고정 해시태그·면책 문구·쓰는 포맷.

원문(source)은 dict: {id, title, body, credit(출처 표기: '한국경제 · 2026.10.21' 또는 'Kim et al. (2024), Psychological Science'),
date, kind(기사|논문|보고서 …, 비우면 profile.source_kind)}.
"""

from __future__ import annotations

import json
import re

from .formats import FORMATS, SLIDE_TYPES, body_slide_count, format_rules
from .profile import Profile

MODEL = "claude-sonnet-5-5"

SYSTEM = """너는 {persona}다. 인스타그램 카드뉴스 계정 '{account}'은(는) {source_kind}을(를) 읽고 {audience}에게 쉬운 말로 풀어 준다.
원문을 읽고 1080x1350 카드뉴스(표지 1 + 본문 N + 마무리 1) 원고를 만든다.

규칙
- 원문에 없는 사실·수치를 만들지 않는다. 수치는 원문 표기 그대로(환산·반올림 금지), 원문과 같은 단위를 붙인다.
- 원문 문장을 베끼지 말고 쉬운 말로 재구성한다. 전문 용어는 한 번은 풀어 쓴다. 한자 약어를 쓰지 않는다.
- 누가 주장한 내용인지(연구진·기관·회사) 주체를 밝힌다. 상관관계를 인과관계로 바꿔 쓰지 않는다.
- 말투: {tone}.
- 표지: 2~3줄, 줄당 공백 포함 12자 이내. 가장 강한 훅 1~2줄은 highlight=true.
- 본문 장 수와 구성은 format 이 정한다.
  · photo: title 14자, body 90~120자, 사진 지시 필요.
  · stat: 숫자 하나가 핵심. stat={value: 숫자만, unit: 원문 단위, label: 14자, source_quote: 그 수치가 든 원문 문장 그대로}.
  · chart: 같은 단위 값 2개 이상(연도별·집단별·전후·비중). chart={type: bar|line|donut|compare, unit, labels(각 8자), values(숫자만, 원문 그대로),
    highlight: 강조할 값의 위치(0부터), source_quote: 모든 값이 든 원문 문장 그대로(여러 문장은 ' / ')}. title 은 그래프의 결론 14자. 최대 1장.
    차트에 쓴 값은 stat 장에 다시 쓰지 않는다.
  · list: title 14자(명사형) + body 60~110자. term: title=용어 10자, label=한 줄 정의 30자, body 60~110자.
  · qa: title=질문 30자(물음표), body=답 60~120자(결론 먼저). quote: 원문에 실제로 있는 발언만, body=인용문 그대로, label='이름 소속' 20자.
  · compare: compare={left:{label 8자, points 2~3개 각 22자}, right:{같은 형식} }.
  · checklist: title 14자 + items 3~5개(각 22자, 독자가 스스로 체크할 수 있는 문장) + body 0~80자(안내).
  · myth: title=흔한 통념 문장 30자, body=원문 근거로 바로잡는 사실 50~120자.
  · 사진 없는 장(stat/chart/list/term/qa/compare/quote/checklist/myth)은 image_queries 를 빈 배열, image_concept 를 빈 문자열로.
- 근거(evidence): 본문 모든 장에 그 장이 기대는 원문 문장 1~2개를 토씨 그대로(20자 이상) 단다. 장의 모든 수치는 그 장의 evidence 안에 있어야 한다.
- 사진 지시(photo 장과 표지): image_queries 는 영어 검색어 2개(은유형 1, 구체형 1, 각 2~5단어). 실존 인물·기업·제품·로고·글자·얼굴이 보이는 장면 금지.
  image_concept: 사진이 표현할 개념을 한국어 한 문장(20자 안팎).
- outro: summary 는 전체를 한 문장으로(25~45자, 수치 1개 이하), question 은 댓글 유도 질문(30자 이내).
- caption: 1줄 훅 / 빈 줄 / 핵심 3가지('•'로 시작) / 빈 줄 / 댓글 유도 1줄{disclaimer_rule} / 마지막 줄 "출처: {credit}". 전체 350자 이내.
- hashtags: 8~10개, '#' 포함.{hashtag_rule}

JSON만 출력한다. 스키마:
{{"format": {format_enum},
 "cover":{{"lines":[{{"text":str,"highlight":bool}}],"image_queries":[str,str],"image_concept":str}},
 "slides":[{{"slide_type": {type_enum},"title":str,"body":str,"label":str,"items":[str],
            "image_queries":[str],"image_concept":str,"evidence":[str],
            "stat":{{"value":str,"unit":str,"label":str,"source_quote":str}} | null,
            "chart":{{"type":str,"unit":str,"labels":[str],"values":[str],"highlight":int,"source_quote":str}} | null,
            "compare":{{"left":{{"label":str,"points":[str]}},"right":{{"label":str,"points":[str]}}}} | null}}],
 "outro":{{"summary":str,"question":str}},
 "caption":str,"hashtags":[str]}}

구성 템플릿
{format_rules}"""


class WriterError(RuntimeError):
    pass


def system_prompt(profile: Profile, source: dict, fmt: str | None = None) -> str:
    fixed = profile.hashtags_fixed
    values = dict(
        persona=profile.persona, account=profile.name, source_kind=source.get("kind") or profile.source_kind,
        audience=profile.audience, tone=profile.tone, credit=source.get("credit", ""),
        disclaimer_rule=(f" / 면책 1줄: \"{profile.disclaimer}\"" if profile.disclaimer else ""),
        hashtag_rule=(f" 앞 {len(fixed)}개는 고정({' '.join(fixed)}), 나머지는 원문 고유 키워드." if fixed else " 원문 고유 키워드 위주."),
        format_enum="|".join(f'"{k}"' for k in profile.formats), type_enum="|".join(f'"{t}"' for t in SLIDE_TYPES),
        format_rules=format_rules(fmt, profile.formats))
    text = SYSTEM   # str.format 대신 치환: 규칙 문장 안의 {value: …} 같은 중괄호를 건드리지 않는다
    for k, v in values.items():
        text = text.replace("{" + k + "}", v)
    return text.replace("{{", "{").replace("}}", "}")


def parse_script(text: str) -> dict:
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    cands = [m.group(1)] if m else []
    a, b = text.find("{"), text.rfind("}")
    if a != -1 and b > a:
        cands.append(text[a:b + 1])
    for c in cands:
        try:
            return json.loads(c)
        except json.JSONDecodeError:
            continue
    raise WriterError(f"원고 JSON 파싱 실패: {text[:200]!r}")


def normalize_script(script: dict, fmt: str | None = None) -> dict:
    for k in ("cover", "slides", "outro"):
        if k not in script:
            raise WriterError(f"원고에 '{k}' 없음")
    script["format"] = script.get("format") if script.get("format") in FORMATS else (fmt or "explainer")
    n, want = len(script["slides"]), body_slide_count(script["format"])
    if n != want:
        raise WriterError(f"format '{script['format']}'의 본문 장 수는 {want}장인데 {n}장을 받았습니다")

    def fix_image(item: dict) -> None:
        q = [str(x).strip() for x in (item.get("image_queries") or []) if str(x).strip()][:2]
        item["image_queries"] = q
        item.setdefault("image_concept", "")

    fix_image(script["cover"])
    for s in script["slides"]:
        kind = s.get("slide_type") or "photo"
        need = {"stat": "stat", "chart": "chart", "compare": "compare", "checklist": "items"}
        if kind in need and not s.get(need[kind]):
            kind = "photo"
        if kind not in SLIDE_TYPES:
            kind = "photo"
        s["slide_type"] = kind
        for key, owner in (("stat", "stat"), ("chart", "chart"), ("compare", "compare")):
            if kind != owner:
                s[key] = None
        if kind != "checklist":
            s["items"] = []
        for key in ("title", "body", "label"):
            s.setdefault(key, "")
        ev = s.get("evidence") or []
        s["evidence"] = [str(x).strip() for x in (ev if isinstance(ev, list) else [ev]) if str(x).strip()][:3]
        fix_image(s)
    return script


def write(source: dict, profile: Profile, fmt: str | None = None, previous: dict | None = None,
          errors: list[str] | None = None, api_key: str | None = None, model: str = MODEL) -> dict:
    import anthropic
    client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
    user = f"원문 종류: {source.get('kind') or profile.source_kind}\n출처: {source.get('credit', '')}\n제목: {source.get('title', '')}\n\n본문:\n{source['body']}"
    if previous:
        user += ("\n\n---\n이전 원고:\n" + json.dumps({k: v for k, v in previous.items() if not k.startswith("_")}, ensure_ascii=False)
                 + "\n\n검수에서 아래 문제가 나왔다. 해당 부분만 고쳐 전체 JSON을 다시 출력해라.\n- " + "\n- ".join(errors or []))
    msg = client.messages.create(model=model, max_tokens=16000, system=system_prompt(profile, source, fmt),
                                 output_config={"effort": "medium"}, messages=[{"role": "user", "content": user}])
    if msg.stop_reason in ("max_tokens", "refusal"):
        raise WriterError(f"원고 생성 중단: {msg.stop_reason}")
    script = normalize_script(parse_script("".join(b.text for b in msg.content if b.type == "text")), fmt)
    script["_usage"] = {"model": model, "input_tokens": msg.usage.input_tokens, "output_tokens": msg.usage.output_tokens}
    return script
