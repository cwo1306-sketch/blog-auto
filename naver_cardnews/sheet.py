"""원고(script) ↔ 엑셀 한 행 변환. 사람이 셀을 고치면 그대로 원고가 된다 (엑셀 수정본이 최종)."""

from __future__ import annotations

SLIDES = 6   # 본문 최대 장 수 (포맷에 따라 4~6장, 빈 장은 비워 둔다)
HL = "*"   # 표지 강조 줄 표시: 셀 값 앞에 '*'

COVER_COLS = ["표지1", "표지2", "표지3", "표지 검색어", "표지 개념"]
SLIDE_COLS = ["유형", "제목", "본문", "근거", "수치", "단위", "라벨", "인용", "검색어", "개념"]   # 근거: 원문 문장, 줄바꿈으로 여러 개
TAIL_COLS = ["마무리 요약", "마무리 질문", "캡션", "해시태그"]
META_COLS = ["id", "기사 제목", "상태", "점수", "언론사", "naver_link", "포맷"]
RESULT_COLS = ["검수오류", "원고출처", "버전", "생성일시", "메모"]


def slide_col(i: int, name: str) -> str:
    return f"{i}장 {name}"


def columns() -> list[str]:
    cols = META_COLS + COVER_COLS
    for i in range(2, 2 + SLIDES):
        cols += [slide_col(i, n) for n in SLIDE_COLS]
    return cols + TAIL_COLS + RESULT_COLS


EDITABLE = set(COVER_COLS + TAIL_COLS + ["메모", "포맷"] + [slide_col(i, n) for i in range(2, 2 + SLIDES) for n in SLIDE_COLS])
SEP = " ; "   # compare 포인트·chart 값 구분자
# chart 장: 유형 'chart:bar' 처럼 차트 종류를 붙이고, 수치='2.8 ; 6.2 ; *10'(강조할 값 앞에 '*'), 라벨='2021 ; 2022 ; 2023',
# 단위='조 원', 인용=source_quote


def flatten(script: dict) -> dict[str, str]:
    row: dict[str, str] = {"포맷": script.get("format", "explainer")}
    lines = script["cover"]["lines"]
    for k in range(3):
        if k < len(lines):
            l = lines[k]
            row[f"표지{k + 1}"] = (HL if l.get("highlight") else "") + l["text"]
        else:
            row[f"표지{k + 1}"] = ""
    row["표지 검색어"] = " | ".join(script["cover"].get("image_queries") or [])
    row["표지 개념"] = script["cover"].get("image_concept", "")
    for i in range(2, 2 + SLIDES):
        for n in SLIDE_COLS:
            row[slide_col(i, n)] = ""
    for i, s in enumerate(script["slides"][:SLIDES], start=2):
        st = s.get("stat") or {}
        row[slide_col(i, "유형")] = s.get("slide_type", "photo")
        row[slide_col(i, "제목")] = s.get("title", "")
        row[slide_col(i, "본문")] = s.get("body", "")
        row[slide_col(i, "근거")] = "\n".join(s.get("evidence") or [])
        row[slide_col(i, "수치")] = str(st.get("value", "")) if st else ""
        row[slide_col(i, "단위")] = st.get("unit", "") if st else ""
        cmp = s.get("compare") or {}
        ch = s.get("chart") or {}
        if s.get("slide_type") == "chart" and ch:
            hl = ch.get("highlight")
            row[slide_col(i, "유형")] = f"chart:{ch.get('type', 'bar')}"
            row[slide_col(i, "수치")] = SEP.join(("*" if k == hl else "") + str(v) for k, v in enumerate(ch.get("values") or []))
            row[slide_col(i, "단위")] = ch.get("unit", "")
            row[slide_col(i, "라벨")] = SEP.join(ch.get("labels") or [])
            row[slide_col(i, "인용")] = ch.get("source_quote", "")
        elif s.get("slide_type") == "compare" and cmp:
            row[slide_col(i, "라벨")] = f"{cmp['left'].get('label', '')} | {cmp['right'].get('label', '')}"
            row[slide_col(i, "본문")] = SEP.join(cmp["left"].get("points", []))
            row[slide_col(i, "인용")] = SEP.join(cmp["right"].get("points", []))
        else:
            row[slide_col(i, "라벨")] = st.get("label", "") if st else s.get("label", "")   # term 정의 / quote 발언자
            row[slide_col(i, "인용")] = st.get("source_quote", "") if st else ""
        row[slide_col(i, "검색어")] = " | ".join(s.get("image_queries") or [])
        row[slide_col(i, "개념")] = s.get("image_concept", "")
    row["마무리 요약"] = script["outro"]["summary"]
    row["마무리 질문"] = script["outro"]["question"]
    row["캡션"] = script.get("caption", "")
    row["해시태그"] = " ".join(script.get("hashtags") or [])
    return row


def _s(v) -> str:
    return "" if v is None else str(v).strip()


def _queries(v) -> list[str]:
    return [q.strip() for q in _s(v).replace("|", "\n").splitlines() if q.strip()][:2]


def unflatten(row: dict) -> dict:
    lines = []
    for k in range(1, 4):
        t = _s(row.get(f"표지{k}"))
        if t:
            lines.append({"text": t.lstrip(HL).strip(), "highlight": t.startswith(HL)})
    cover = {"lines": lines, "image_queries": _queries(row.get("표지 검색어")), "image_concept": _s(row.get("표지 개념"))}
    cover["image_query"] = cover["image_queries"][0] if cover["image_queries"] else ""
    slides = []
    for i in range(2, 2 + SLIDES):
        g = lambda n: _s(row.get(slide_col(i, n)))  # noqa: E731
        kind = g("유형").lower()
        if not kind and not g("제목") and not g("본문"):
            continue   # 비어 있는 장 (포맷 장 수가 6 미만)
        kind = kind or "photo"
        chart = None
        if kind.startswith("chart"):
            ctype = kind.split(":", 1)[1].strip() if ":" in kind else "bar"
            raw = [v.strip() for v in g("수치").split(";") if v.strip()]
            hl = next((k for k, v in enumerate(raw) if v.startswith("*")), None)
            chart = {"type": ctype or "bar", "unit": g("단위"), "values": [v.lstrip("*").strip() for v in raw],
                     "labels": [x.strip() for x in g("라벨").split(";") if x.strip()], "highlight": hl,
                     "source_quote": g("인용")}
            kind = "chart" if raw else "photo"
        value = g("수치")
        stat = ({"value": value, "unit": g("단위"), "label": g("라벨"), "source_quote": g("인용")}
                if kind == "stat" and value else None)
        compare = None
        body = g("본문")
        if kind == "compare":
            labels = [x.strip() for x in g("라벨").split("|")] + ["", ""]
            compare = {"left": {"label": labels[0], "points": [p.strip() for p in body.split(";") if p.strip()]},
                       "right": {"label": labels[1], "points": [p.strip() for p in g("인용").split(";") if p.strip()]}}
            body = ""
        if kind not in ("photo", "stat", "chart", "list", "term", "qa", "compare", "quote"):
            kind = "photo"
        if kind == "stat" and not stat:
            kind = "photo"
        qs = _queries(row.get(slide_col(i, "검색어")))
        evidence = [x.strip() for x in g("근거").splitlines() if x.strip()]
        slides.append({"slide_type": kind, "title": g("제목"), "body": body, "evidence": evidence,
                       "label": g("라벨") if kind in ("term", "quote") else "",
                       "stat": stat, "compare": compare, "chart": chart, "image_queries": qs, "image_query": qs[0] if qs else "",
                       "image_concept": g("개념")})
    tags = [t if t.startswith("#") else "#" + t for t in _s(row.get("해시태그")).replace(",", " ").split() if t.strip("#")]
    fmt = _s(row.get("포맷")) or "explainer"
    return {"format": fmt, "cover": cover, "slides": slides,
            "outro": {"summary": _s(row.get("마무리 요약")), "question": _s(row.get("마무리 질문"))},
            "caption": _s(row.get("캡션")), "hashtags": tags}


def changed(a: dict, b: dict) -> bool:
    """편집 가능한 열만 비교 (공백 차이는 무시)."""
    fa, fb = flatten(a), flatten(b)
    return any(fa.get(c, "").strip() != fb.get(c, "").strip() for c in EDITABLE if c != "메모")
