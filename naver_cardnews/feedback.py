"""엑셀 수정을 학습 데이터로: ai 원고 vs 사람 수정본의 차이를 장·필드 단위로 분류·집계하고, 잘 고쳐진 쌍을 writer few-shot 예시로 만든다."""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from .db import Database
from .sheet import flatten

NUM_RE = re.compile(r"\d[\d,.]*")
ENDING_RE = re.compile(r"(습니다|입니다|합니다|거든요|인데요|이에요|예요|해요|어요|아요|네요|죠|다)\.?$")
_STYLE = {"습니다": "합쇼체", "입니다": "합쇼체", "합니다": "합쇼체", "다": "해라체"}   # 나머지는 해요체


def ending_style(text: str) -> str | None:
    m = ENDING_RE.search(text.strip())
    return (_STYLE.get(m.group(1), "해요체")) if m else None


def classify_change(field_name: str, before: str, after: str) -> str:
    """한 셀의 수정 유형. 집계 가능한 소수의 범주로."""
    if before == after:
        return "none"
    if not after.strip():
        return "삭제"
    if not before.strip():
        return "추가"
    if NUM_RE.findall(before) != NUM_RE.findall(after):
        return "수치 수정"
    if field_name.endswith("유형") or field_name == "포맷":
        return "유형 변경"
    if field_name.endswith("검색어") or field_name.endswith("개념"):
        return "사진 지시 수정"
    lb, la = len(before), len(after)
    if la < lb * 0.8:
        return "축약"
    if la > lb * 1.2:
        return "보강"
    sb, sa = ending_style(before), ending_style(after)
    if sb and sa and sb != sa:
        return "어투 변경"
    return "표현 다듬기"


@dataclass
class Diff:
    article_id: str
    from_version: int
    to_version: int
    changes: list[dict] = field(default_factory=list)   # {field, before, after, kind}


def diff_scripts(article_id: str, v_from: int, a: dict, v_to: int, b: dict) -> Diff:
    fa, fb = flatten(a), flatten(b)
    d = Diff(article_id, v_from, v_to)
    for k in fb:
        if k in ("id", "기사 제목", "상태", "점수", "언론사", "naver_link"):
            continue
        kind = classify_change(k, fa.get(k, "") or "", fb.get(k, "") or "")
        if kind != "none":
            d.changes.append({"field": k, "before": fa.get(k, ""), "after": fb.get(k, ""), "kind": kind})
    return d


def collect_diffs(db: Database, days: int = 30) -> list[Diff]:
    """같은 기사에서 ai 버전 → 그 다음 excel 버전으로 넘어간 쌍."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    rows = db.conn.execute(
        "SELECT article_id, version, source, script_json FROM drafts WHERE created_at>=? ORDER BY article_id, version", (since,)
    ).fetchall()
    by: dict[str, list] = {}
    for r in rows:
        by.setdefault(r["article_id"], []).append(r)
    diffs = []
    for aid, vs in by.items():
        for prev, cur in zip(vs, vs[1:]):
            if cur["source"] == "excel":
                diffs.append(diff_scripts(aid, prev["version"], json.loads(prev["script_json"]), cur["version"], json.loads(cur["script_json"])))
    return diffs


def aggregate(diffs: list[Diff]) -> dict:
    kinds = Counter(); fields = Counter(); slides = Counter()
    total_cells = 0
    for d in diffs:
        for c in d.changes:
            kinds[c["kind"]] += 1
            f = c["field"]
            fields[re.sub(r"^\d장 ", "", f)] += 1
            m = re.match(r"^(\d)장", f)
            slides[m.group(1) + "장" if m else "공통"] += 1
            total_cells += 1
    return {"articles": len(diffs), "cells": total_cells, "kinds": kinds.most_common(), "fields": fields.most_common(8),
            "slides": slides.most_common()}


def report_text(agg: dict) -> str:
    if not agg["articles"]:
        return "최근 엑셀에서 고친 원고가 없습니다."
    lines = [f"수정된 원고 {agg['articles']}건, 고친 셀 {agg['cells']}개"]
    lines.append("유형별: " + ", ".join(f"{k} {v}" for k, v in agg["kinds"]))
    lines.append("자주 고친 열: " + ", ".join(f"{k} {v}" for k, v in agg["fields"]))
    lines.append("장별: " + ", ".join(f"{k} {v}" for k, v in agg["slides"]))
    top = agg["kinds"][0][0] if agg["kinds"] else ""
    hint = {"수치 수정": "writer의 수치 규칙(단위·출처 주체)을 강화하고 validate 숫자+단위 대조가 놓친 패턴을 확인하세요.",
            "축약": "body 상한을 10자 낮추거나 '한 문장에 한 정보' 규칙을 프롬프트에 추가하세요.",
            "어투 변경": "writer 말투 규칙(해요체/합니다체)을 사람이 고친 쪽으로 통일하세요.",
            "표현 다듬기": "잘 고쳐진 쌍을 few-shot 예시로 넣는 것이 가장 효과적입니다 (feedback --fewshot).",
            "사진 지시 수정": "image_queries 규칙(은유형+구체형, 브랜드 금지)을 점검하세요.",
            "보강": "body 하한을 올리거나 '독자에게 무엇이 달라지나'를 반드시 넣게 하세요."}.get(top, "")
    if hint:
        lines.append(f"가장 많은 유형 '{top}' → {hint}")
    return "\n".join(lines)


def build_fewshot(diffs: list[Diff], limit: int = 12, min_len: int = 30) -> list[dict]:
    """표현 다듬기·축약·어투 변경처럼 '문장 품질' 수정만 골라 before/after 쌍을 만든다. 수치 수정은 제외(사실 오류는 예시가 아니라 규칙)."""
    good = ("표현 다듬기", "축약", "어투 변경", "보강")
    pairs = []
    for d in diffs:
        for c in d.changes:
            if c["kind"] in good and len(c["before"]) >= min_len and len(c["after"]) >= min_len:
                pairs.append({"field": c["field"], "before": c["before"], "after": c["after"], "kind": c["kind"], "article_id": d.article_id})
    # 최근 것 우선, 같은 기사 2개까지
    out, per = [], Counter()
    for p in reversed(pairs):
        if per[p["article_id"]] >= 2:
            continue
        per[p["article_id"]] += 1
        out.append(p)
        if len(out) >= limit:
            break
    return out


def fewshot_prompt(examples: list[dict]) -> str:
    if not examples:
        return ""
    lines = ["편집자가 실제로 고친 예시 (고친 뒤 문장처럼 써라):"]
    for e in examples:
        lines.append(f"- [{e['kind']}] 전: {e['before']}\n  후: {e['after']}")
    return "\n".join(lines)
