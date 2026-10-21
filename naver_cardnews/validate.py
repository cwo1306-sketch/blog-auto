"""원고 검수 (패키지 본체. cardnews/validate.py 는 재수출).

원본 대비 개선:
- 수치 대조를 '숫자+단위' 단위로: 원본은 숫자가 원문 어딘가 있으면 통과해 '5'가 '55%'에 묻혔다(HANDOFF 6장).
  이제 '55%'·'1,000조'·'3분기'처럼 숫자 바로 뒤 단위까지 붙여 원문(공백·쉼표 제거)에 있어야 한다. 연도(4자리)는 숫자만 본다
- stat 장 검증: value+unit ⊂ source_quote ⊂ 원문, 최대 2장, 연속 금지, 2장(표지 다음)은 photo
- 사진 검색어 검증: 2개, 영어, 실존 기업·제품·인물·로고·국기 단어 금지
- caption 끝줄 '출처:' 확인, hashtags 8~10개·'#' 접두
- stat 장은 본문 길이 하한을 적용하지 않는다(엑셀·캡션용 보조 텍스트)
"""

from __future__ import annotations

import re

from .formats import FORMATS, body_slide_count
from .stat_card import Stat, StatError, validate_stat

LIMITS = {"cover_line": 12, "title": 14, "body": (80, 125), "summary": (20, 45), "question": 30,
          "hashtags": (8, 10), "image_concept": 40, "caption": 400}
# slide_type 별 제목·본문 한도 (writer 프롬프트와 약간 여유를 둔다)
TYPE_LIMITS = {
    "photo":   {"title": 14, "body": (80, 125)},
    "stat":    {"title": 14, "body": (0, 125)},
    "list":    {"title": 14, "body": (50, 115)},
    "term":    {"title": 10, "body": (50, 115), "label": 32},
    "qa":      {"title": 32, "body": (50, 125)},
    "compare": {"title": 14, "body": (0, 125), "cmp_label": 8, "points": (2, 3), "point": 24},
    "quote":   {"title": 14, "body": (30, 115), "label": 22},
}
# 포맷별 photo 본문 길이 예외 (현장 사례형은 한 장 한 문장)
FORMAT_PHOTO_BODY = {"scene": (25, 75), "reveal": (40, 110)}   # 반전형은 단서를 짧게 던진다
NO_PHOTO_TYPES = {"list", "term", "qa", "compare", "stat"}
NUM_UNIT = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*([가-힣%a-zA-Z]{0,3})")
HANJA = re.compile(r"[一-鿿]")
YEAR = re.compile(r"^(19|20)\d{2}$")
PARTICLES = set("을를이가은는의에로도와과만")   # 단위 뒤에 붙은 조사는 뗀다 ('2개을' → '2개')
BANNED_QUERY_WORDS = {
    "nvidia", "apple", "iphone", "tesla", "samsung", "google", "openai", "chatgpt", "meta", "facebook", "instagram",
    "microsoft", "amazon", "kakao", "naver", "sk", "lg", "hyundai", "musk", "altman", "huang", "trump", "logo",
    "brand", "flag", "text", "sign", "billboard", "celebrity", "politician", "president",
}
MAX_STAT = 2


def _norm(s: str) -> str:
    return s.replace(" ", "").replace(",", "")


def _texts(script: dict):
    for l in script["cover"]["lines"]:
        yield "표지", l["text"]
    for i, s in enumerate(script["slides"], start=2):
        yield f"{i}장 제목", s.get("title", "")
        yield f"{i}장 본문", s.get("body", "")
        if s.get("label"):
            yield f"{i}장 정의", s["label"]
        if s.get("slide_type") == "stat" and s.get("stat"):
            yield f"{i}장 stat label", s["stat"].get("label", "")
        if s.get("slide_type") == "compare" and s.get("compare"):
            for side in ("left", "right"):
                for p in (s["compare"].get(side) or {}).get("points", []):
                    yield f"{i}장 비교({side})", p
    yield "마무리 요약", script["outro"]["summary"]
    yield "마무리 질문", script["outro"]["question"]
    yield "캡션", script.get("caption", "")


def check_numbers(where: str, text: str, body_norm: str) -> list[str]:
    errors = []
    for num, unit in NUM_UNIT.findall(text):
        n = num.replace(",", "")
        while unit and unit[-1] in PARTICLES:
            unit = unit[:-1]
        if YEAR.match(n) or unit in ("자", "장"):      # 연도, '3장' 같은 서술은 숫자만 확인
            unit = ""
        # 가장 긴 '숫자+단위'부터 짧은 쪽으로 찾는다 ('3분기' → '3분' → '3')
        matched = next((k for k in range(len(unit), -1, -1) if n + unit[:k] in body_norm), None)
        if matched is None or (unit and matched == 0):
            if matched is None:
                errors.append(f"{where}: 원문에 없는 수치 '{num}{unit}'")
            else:
                errors.append(f"{where}: 수치 '{num}{unit}'의 단위가 원문과 다름")
    return errors


def check_queries(where: str, item: dict) -> list[str]:
    errors = []
    queries = item.get("image_queries") or []
    if len(queries) < 2:
        errors.append(f"{where}: image_queries 2개 필요 (은유형 + 구체형)")
    for q in queries:
        if not re.fullmatch(r"[A-Za-z][A-Za-z\s\-]{2,60}", q or ""):
            errors.append(f"{where}: 검색어는 영어 단어 2~5개: '{q}'")
            continue
        bad = {w for w in q.lower().split() if w in BANNED_QUERY_WORDS}
        if bad:
            errors.append(f"{where}: 검색어에 브랜드·인물·로고 단어 {sorted(bad)} → 추상 장면으로")
    if len(item.get("image_concept", "")) > LIMITS["image_concept"]:
        errors.append(f"{where}: image_concept {len(item['image_concept'])}자 > {LIMITS['image_concept']}자")
    return errors


def check(script: dict, article_body: str) -> list[str]:
    errors: list[str] = []
    body_norm = _norm(article_body)
    for where, text in _texts(script):
        errors += check_numbers(where, text, body_norm)
        if HANJA.search(text):
            errors.append(f"{where}: 한자 사용 '{''.join(HANJA.findall(text))}' → 한글로")

    for l in script["cover"]["lines"]:
        if len(l["text"]) > LIMITS["cover_line"]:
            errors.append(f"표지 '{l['text']}' {len(l['text'])}자 > {LIMITS['cover_line']}자")
    if not any(l.get("highlight") for l in script["cover"]["lines"]):
        errors.append("표지에 강조(highlight) 줄 없음")
    errors += check_queries("표지", script["cover"])

    fmt = script.get("format", "explainer")
    if fmt not in FORMATS:
        errors.append(f"알 수 없는 format '{fmt}'")
        fmt = "explainer"
    if len(script["slides"]) != body_slide_count(fmt):
        errors.append(f"format '{fmt}'은 본문 {body_slide_count(fmt)}장인데 {len(script['slides'])}장")
    stat_count, prev_stat = 0, False
    for i, s in enumerate(script["slides"], start=2):
        kind = s.get("slide_type", "photo")
        is_stat = kind == "stat" and bool(s.get("stat"))
        tl = TYPE_LIMITS.get(kind, TYPE_LIMITS["photo"])
        if len(s.get("title", "")) > tl["title"]:
            errors.append(f"{i}장 제목 {len(s['title'])}자 > {tl['title']}자 ({kind})")
        lo, hi = tl["body"]
        if kind == "photo" and fmt in FORMAT_PHOTO_BODY:
            lo, hi = FORMAT_PHOTO_BODY[fmt]
        blen = len(s.get("body", ""))
        if not lo <= blen <= hi:
            errors.append(f"{i}장 본문 {blen}자 (허용 {lo}~{hi}자, {kind})")
        if kind == "term":
            if not s.get("label"):
                errors.append(f"{i}장 term: 한 줄 정의(label) 필요")
            elif len(s["label"]) > tl["label"]:
                errors.append(f"{i}장 정의 {len(s['label'])}자 > {tl['label']}자")
        if kind == "quote":
            if not s.get("label"):
                errors.append(f"{i}장 quote: 발언자(label) 필요")
            elif len(s["label"]) > tl["label"]:
                errors.append(f"{i}장 발언자 {len(s['label'])}자 > {tl['label']}자")
            if s.get("body") and s["body"].replace(" ", "") not in article_body.replace(" ", "").replace("\n", ""):
                errors.append(f"{i}장 quote: 인용문이 원문에 그대로 없음")
        if kind == "qa" and not s.get("title", "").rstrip().endswith("?"):
            errors.append(f"{i}장 qa: 질문은 물음표로 끝나야 함")
        if kind == "compare":
            cmp = s.get("compare") or {}
            for side in ("left", "right"):
                side_d = cmp.get(side) or {}
                if len(side_d.get("label", "")) > tl["cmp_label"] or not side_d.get("label"):
                    errors.append(f"{i}장 비교 {side} 라벨 1~{tl['cmp_label']}자 필요")
                pts = side_d.get("points") or []
                if not tl["points"][0] <= len(pts) <= tl["points"][1]:
                    errors.append(f"{i}장 비교 {side} 포인트 {len(pts)}개 (허용 {tl['points'][0]}~{tl['points'][1]})")
                for p in pts:
                    if len(p) > tl["point"]:
                        errors.append(f"{i}장 비교 포인트 '{p[:12]}…' {len(p)}자 > {tl['point']}자")
        if is_stat:
            st = s["stat"]
            try:
                validate_stat(Stat(str(st.get("value", "")), str(st.get("unit", "")), st.get("label", ""),
                                   st.get("source_quote", "")), article_text=article_body)
            except StatError as exc:
                errors.append(f"{i}장 stat: {exc}")
            if fmt == "explainer":
                if i == 2:
                    errors.append("2장(표지 다음)은 photo 여야 함")
                if prev_stat:
                    errors.append(f"{i}장: stat 연속 금지")
                stat_count += 1
                if stat_count > MAX_STAT:
                    errors.append(f"{i}장: stat 장 {MAX_STAT}장 초과")
        elif kind == "photo":
            errors += check_queries(f"{i}장", s)
        prev_stat = is_stat

    lo, hi = LIMITS["summary"]
    if not lo <= len(script["outro"]["summary"]) <= hi:
        errors.append(f"마무리 요약 {len(script['outro']['summary'])}자 (허용 {lo}~{hi}자)")
    if len(script["outro"]["question"]) > LIMITS["question"]:
        errors.append(f"마무리 질문 {len(script['outro']['question'])}자 > {LIMITS['question']}자")

    caption = script.get("caption", "")
    if "출처:" not in caption.strip().splitlines()[-1] if caption.strip() else True:
        errors.append("캡션 마지막 줄에 '출처: {언론사}' 필요")
    if len(caption) > LIMITS["caption"]:
        errors.append(f"캡션 {len(caption)}자 > {LIMITS['caption']}자")
    tags = script.get("hashtags") or []
    lo, hi = LIMITS["hashtags"]
    if not lo <= len(tags) <= hi or not all(str(t).startswith("#") for t in tags):
        errors.append(f"hashtags {len(tags)}개 (허용 {lo}~{hi}개, '#' 접두)")
    return errors
