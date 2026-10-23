"""원고 검수(결정적 규칙). 사실 대조는 원문(source body) 기준: 수치·근거 문장·인용·차트 값이 원문에 그대로 있어야 한다.

LLM 채점과 별개로, 여기서 걸리면 원고 작성기가 고쳐 쓴다(pipeline.MAX_REWRITES).
"""

from __future__ import annotations

import re

from .chart import Chart, ChartError, validate_chart
from .formats import FORMATS, body_slide_count
from .stat import Stat, StatError, validate_stat

LIMITS = {"cover_line": 12, "summary": (20, 45), "question": 30, "hashtags": (8, 10), "caption": 400, "image_concept": 40}
TYPE_LIMITS = {
    "photo":     {"title": 14, "body": (80, 125)},
    "stat":      {"title": 14, "body": (0, 125)},
    "chart":     {"title": 14, "body": (0, 125)},
    "list":      {"title": 14, "body": (50, 115)},
    "term":      {"title": 10, "body": (50, 115), "label": 32},
    "qa":        {"title": 32, "body": (50, 125)},
    "compare":   {"title": 14, "body": (0, 125), "cmp_label": 8, "points": (2, 3), "point": 24},
    "quote":     {"title": 14, "body": (30, 115), "label": 22},
    "checklist": {"title": 14, "body": (0, 80), "items": (3, 5), "item": 22},
    "myth":      {"title": 30, "body": (50, 125)},
}
NUM_UNIT = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*([가-힣%a-zA-Z]{0,3})")
HANJA = re.compile(r"[一-鿿]")
YEAR = re.compile(r"^(19|20)\d{2}$")
PARTICLES = set("을를이가은는의에로도와과만")
BANNED_QUERY_WORDS = {
    "nvidia", "apple", "iphone", "tesla", "samsung", "google", "openai", "chatgpt", "meta", "facebook", "instagram",
    "microsoft", "amazon", "kakao", "naver", "logo", "brand", "flag", "text", "sign", "billboard", "celebrity",
    "politician", "president", "face", "portrait",
}
MAX_STAT, MAX_CHART, EVIDENCE_MIN = 2, 1, 20
_QUOTES = re.compile(r"[\s'\"‘’“”`]")


def _norm(s: str) -> str:
    return (s or "").replace(" ", "").replace(",", "")


def _ntext(s: str) -> str:
    return _QUOTES.sub("", s or "")


def slide_evidence(s: dict) -> list[str]:
    ev = list(s.get("evidence") or [])
    kind = s.get("slide_type")
    if not ev and kind == "stat" and s.get("stat"):
        ev = [s["stat"].get("source_quote", "")]
    if not ev and kind == "chart" and s.get("chart"):
        ev = s["chart"].get("source_quote", "").split(" / ")
    if not ev and kind == "quote" and s.get("body"):
        ev = [s["body"]]
    return [e for e in ev if e]


def _slide_texts(s: dict) -> list[str]:
    out = [s.get("title", ""), s.get("body", ""), s.get("label", "")]
    out += list(s.get("items") or [])
    if s.get("compare"):
        for side in ("left", "right"):
            out += (s["compare"].get(side) or {}).get("points", [])
    return [t for t in out if t]


def check_evidence(i: int, s: dict, body_ntext: str) -> list[str]:
    errors = []
    ev = slide_evidence(s)
    if not ev:
        if any(NUM_UNIT.search(t) for t in _slide_texts(s)):
            errors.append(f"{i}장: 수치가 있는데 근거(evidence) 없음")
        return errors
    for e in ev:
        if len(e) < EVIDENCE_MIN and s.get("slide_type") not in ("quote",):
            errors.append(f"{i}장 근거가 너무 짧음({len(e)}자 < {EVIDENCE_MIN}자)")
        if _ntext(e) not in body_ntext:
            errors.append(f"{i}장 근거가 원문에 그대로 없음: '{e[:24]}…'")
    ev_norm = _norm(" ".join(ev))
    for t in _slide_texts(s):
        for num, _unit in NUM_UNIT.findall(t):
            n = num.replace(",", "")
            if not YEAR.match(n) and n not in ev_norm:
                errors.append(f"{i}장: 수치 '{num}' 이 그 장의 근거 안에 없음")
    return errors


def check_numbers(where: str, text: str, body_norm: str) -> list[str]:
    errors = []
    for num, unit in NUM_UNIT.findall(text):
        n = num.replace(",", "")
        while unit and unit[-1] in PARTICLES:
            unit = unit[:-1]
        if YEAR.match(n) or unit in ("자", "장", "가지", "개월"):
            unit = ""
        matched = next((k for k in range(len(unit), -1, -1) if n + unit[:k] in body_norm), None)
        if matched is None:
            errors.append(f"{where}: 원문에 없는 수치 '{num}{unit}'")
        elif unit and matched == 0:
            errors.append(f"{where}: 수치 '{num}{unit}'의 단위가 원문과 다름")
    return errors


def check_queries(where: str, item: dict) -> list[str]:
    errors = []
    qs = item.get("image_queries") or []
    if len(qs) < 1:
        errors.append(f"{where}: 사진 검색어 없음")
    for q in qs:
        words = set(re.findall(r"[a-z]+", q.lower()))
        if words & BANNED_QUERY_WORDS:
            errors.append(f"{where}: 검색어에 금지어 {sorted(words & BANNED_QUERY_WORDS)}")
        if re.search(r"[가-힣]", q):
            errors.append(f"{where}: 검색어는 영어로")
    if len(item.get("image_concept", "")) > LIMITS["image_concept"]:
        errors.append(f"{where}: image_concept {len(item['image_concept'])}자 > {LIMITS['image_concept']}자")
    return errors


def _texts(script: dict):
    for l in script["cover"]["lines"]:
        yield "표지", l["text"]
    for i, s in enumerate(script["slides"], start=2):
        for t in _slide_texts(s):
            yield f"{i}장", t
        if s.get("slide_type") == "stat" and s.get("stat"):
            yield f"{i}장 stat label", s["stat"].get("label", "")
    yield "마무리 요약", script["outro"]["summary"]
    yield "마무리 질문", script["outro"]["question"]
    # 캡션의 '출처:' 줄은 출처 표기(논문 연도·학술지 권호 등)라 원문 대조에서 뺀다
    yield "캡션", "\n".join(l for l in script.get("caption", "").splitlines() if not l.strip().startswith("출처:"))


def check(script: dict, source_body: str, formats: list[str] | None = None,
          hashtags_fixed: list[str] | None = None) -> list[str]:
    """formats: 계정이 쓰는 포맷(없으면 전체). hashtags_fixed: 앞에 와야 하는 고정 해시태그."""
    errors: list[str] = []
    body_norm = _norm(source_body)
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
    if fmt not in FORMATS or (formats and fmt not in formats):
        errors.append(f"이 계정에서 쓰지 않는 format '{fmt}'")
        fmt = fmt if fmt in FORMATS else "explainer"
    if len(script["slides"]) != body_slide_count(fmt):
        errors.append(f"format '{fmt}'은 본문 {body_slide_count(fmt)}장인데 {len(script['slides'])}장")
    body_ntext = _ntext(source_body)
    stat_count, chart_count, prev_stat = 0, 0, False
    for i, s in enumerate(script["slides"], start=2):
        kind = s.get("slide_type", "photo")
        tl = TYPE_LIMITS.get(kind, TYPE_LIMITS["photo"])
        errors += check_evidence(i, s, body_ntext)
        if len(s.get("title", "")) > tl["title"]:
            errors.append(f"{i}장 제목 {len(s['title'])}자 > {tl['title']}자 ({kind})")
        lo, hi = FORMATS[fmt].get("photo_body", tl["body"]) if kind == "photo" else tl["body"]
        if not lo <= len(s.get("body", "")) <= hi:
            errors.append(f"{i}장 본문 {len(s.get('body', ''))}자 (허용 {lo}~{hi}자, {kind})")
        if kind in ("term", "quote"):
            if not s.get("label"):
                errors.append(f"{i}장 {kind}: label 필요")
            elif len(s["label"]) > tl["label"]:
                errors.append(f"{i}장 label {len(s['label'])}자 > {tl['label']}자")
        if kind == "quote" and s.get("body") and _ntext(s["body"]) not in body_ntext:
            errors.append(f"{i}장 quote: 인용문이 원문에 그대로 없음")
        if kind == "qa" and not s.get("title", "").rstrip().endswith("?"):
            errors.append(f"{i}장 qa: 질문은 물음표로 끝나야 함")
        if kind == "checklist":
            items = s.get("items") or []
            if not tl["items"][0] <= len(items) <= tl["items"][1]:
                errors.append(f"{i}장 checklist 항목 {len(items)}개 (허용 {tl['items'][0]}~{tl['items'][1]})")
            for it in items:
                if len(it) > tl["item"]:
                    errors.append(f"{i}장 checklist 항목 '{it[:10]}…' {len(it)}자 > {tl['item']}자")
        if kind == "compare":
            cmp = s.get("compare") or {}
            for side in ("left", "right"):
                d = cmp.get(side) or {}
                if not d.get("label") or len(d["label"]) > tl["cmp_label"]:
                    errors.append(f"{i}장 비교 {side} 라벨 1~{tl['cmp_label']}자 필요")
                pts = d.get("points") or []
                if not tl["points"][0] <= len(pts) <= tl["points"][1]:
                    errors.append(f"{i}장 비교 {side} 포인트 {len(pts)}개")
        if kind == "stat":
            st = s.get("stat") or {}
            try:
                validate_stat(Stat(str(st.get("value", "")), str(st.get("unit", "")), st.get("label", ""),
                                   st.get("source_quote", "")), article_text=source_body)
            except StatError as exc:
                errors.append(f"{i}장 stat: {exc}")
            if fmt != "numbers":
                stat_count += 1
                if prev_stat:
                    errors.append(f"{i}장: stat 연속 금지")
                if stat_count > MAX_STAT:
                    errors.append(f"{i}장: stat {MAX_STAT}장 초과")
        if kind == "chart":
            try:
                validate_chart(Chart.from_dict(s.get("chart") or {}), article_text=source_body)
            except ChartError as exc:
                errors.append(f"{i}장 chart: {exc}")
            chart_count += 1
            if chart_count > MAX_CHART:
                errors.append(f"{i}장: chart {MAX_CHART}장 초과")
        if kind == "photo":
            errors += check_queries(f"{i}장", s)
        prev_stat = kind == "stat"

    chart_vals = {(_norm(str(v)), _norm(c.get("unit", ""))) for s in script["slides"] if s.get("slide_type") == "chart"
                  for c in [s.get("chart") or {}] for v in c.get("values") or []}
    for i, s in enumerate(script["slides"], start=2):
        st = s.get("stat") or {}
        if s.get("slide_type") == "stat" and (_norm(str(st.get("value", ""))), _norm(st.get("unit", ""))) in chart_vals:
            errors.append(f"{i}장 stat: 차트에 이미 나온 값 '{st.get('value')}{st.get('unit')}' 반복")

    lo, hi = LIMITS["summary"]
    if not lo <= len(script["outro"]["summary"]) <= hi:
        errors.append(f"마무리 요약 {len(script['outro']['summary'])}자 (허용 {lo}~{hi}자)")
    if len(script["outro"]["question"]) > LIMITS["question"]:
        errors.append(f"마무리 질문 {len(script['outro']['question'])}자 > {LIMITS['question']}자")
    caption = script.get("caption", "").strip()
    if not caption or "출처:" not in caption.splitlines()[-1]:
        errors.append("캡션 마지막 줄에 '출처: …' 필요")
    if len(caption) > LIMITS["caption"]:
        errors.append(f"캡션 {len(caption)}자 > {LIMITS['caption']}자")
    tags = script.get("hashtags") or []
    lo, hi = LIMITS["hashtags"]
    if not lo <= len(tags) <= hi or not all(str(t).startswith("#") for t in tags):
        errors.append(f"hashtags {len(tags)}개 (허용 {lo}~{hi}개, '#' 접두)")
    if hashtags_fixed and tags[:len(hashtags_fixed)] != hashtags_fixed:
        errors.append(f"해시태그 앞에 고정 태그 {hashtags_fixed} 필요")
    return errors
