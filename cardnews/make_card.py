"""Usage: .venv/bin/python make_card.py <naver news url> [--db data/news.db] [--force]

원고 우선순위: DB drafts 의 최신 버전(엑셀에서 고친 source='excel' 포함) → 없으면 writer 로 새로 생성.
엑셀 수정본이 최종이므로 drafts 가 있으면 writer 를 다시 부르지 않는다. 검수 오류가 남아 있으면 중단하고
memo 에 남긴다(--force 로 무시하고 렌더 가능).

원본 대비 개선:
- 장 유형 분기: writer가 slide_type="stat" + stat{} 을 내면 숫자 카드(사진 없음). 검증 실패 시 photo로 강등
- 사진 선택: alt 텍스트 기반 writer.pick_photo → 비전 검수(naver_cardnews.vision_pick, 얼굴·글자·로고 탈락)
- 검색어 2개(image_queries, 없으면 image_query 1개) × Pexels(+Unsplash) 후보 → 작가당 상한 → 중복 제거
- 게시물 간 사진 재사용 금지: SQLite used_images(id 일치, 30일 내 dHash 유사) — 원본은 같은 게시물 안에서만 막았음
- 후보 전부 탈락 → 재검색 1회 → 그래도 없으면 단색(plain) 강등, meta에 사유 기록 (원본은 IndexError로 중단)
- validate 재작성 2회 후에도 오류가 남으면 렌더하지 않고 중단 (원본은 오류를 안고 렌더)
- meta.json에 비전 판정·호출 수·사진 출처 기록, articles.status='제작완료'·card_folder 갱신(1단계 DB와 연결)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

import naver_article
import pexels
import render

import keys
from naver_cardnews import palette
from naver_cardnews.db import Database
from naver_cardnews.imagehash import dhash, to_hex
from naver_cardnews.stat_card import Stat, StatError, validate_stat
from naver_cardnews.stock import download
from naver_cardnews.rubric import Judge, ensure_judged, gate
from naver_cardnews.vision_pick import HaikuScorer, pick

ROOT = os.path.dirname(os.path.abspath(__file__))
MAX_REWRITES = 2
MAX_STAT_SLIDES = 2


def _queries(item: dict) -> list[str]:
    q = item.get("image_queries") or [item.get("image_query", "")]
    return [s for s in q if s][:2]


def _normalize_slide_types(script: dict, body: str, log: list[str]) -> None:
    """stat 장은 검증을 통과해야 하고 최대 2장, 연속 금지. 아니면 photo로 강등."""
    prev_stat = False
    count = 0
    for s in script["slides"]:
        if s.get("slide_type") != "stat":
            prev_stat = False
            continue
        st = s.get("stat") or {}
        reason = None
        try:
            validate_stat(Stat(str(st.get("value", "")), st.get("unit", ""), st.get("label", ""),
                               st.get("source_quote", "")), article_text=body)
        except StatError as exc:
            reason = str(exc)
        if reason is None and prev_stat:
            reason = "stat 연속"
        if reason is None and count >= MAX_STAT_SLIDES:
            reason = f"stat {MAX_STAT_SLIDES}장 초과"
        if reason:
            log.append(f"slide {s.get('title', '')!r}: stat → photo 강등 ({reason})")
            s["slide_type"] = "photo"
            prev_stat = False
        else:
            count += 1
            prev_stat = True


def _pick_image(db: Database, scorer: HaikuScorer, article_id: str, slide_no: int, queries: list[str],
                headline: str, concept: str, out: str) -> tuple[str | None, dict]:
    """검색 → 썸네일 → 비전 선택 → used_images 기록 → 원본 저장. 실패하면 (None, 사유)."""
    log: dict = {"queries": queries, "attempts": []}
    seen: set[tuple[str, str]] = set()
    for attempt in range(2):
        cands = [c for c in pexels.search(queries, n=6 if attempt == 0 else 10) if c.key not in seen]
        for c in cands:
            try:
                c.image_bytes = download(c.thumb_url)
            except Exception as exc:  # noqa: BLE001
                log.setdefault("thumb_errors", []).append(f"{c.key}: {exc}")
        result = pick(cands, headline, concept, scorer, db, exclude=seen)
        seen.update(c.key for c, _ in result.scored)
        seen.update(c.key for c in cands)   # 심사 한도에 걸려 못 본 후보도 재검색 때 새 후보에 자리를 양보
        log["attempts"].append(result.to_dict())
        if result.chosen is not None:
            c = result.chosen
            name = f"bg_{slide_no:02d}.jpg"
            with open(os.path.join(out, name), "wb") as f:
                f.write(download(c.full_url))
            db.record_image(article_id, slide_no, c.source, c.external_id, c.query,
                            to_hex(dhash(c.image_bytes)), os.path.join(out, name), c.photographer, c.page_url)
            log["chosen"] = {"file": name, "source": c.source, "id": c.external_id,
                             "photographer": c.photographer, "url": c.page_url, "alt": c.alt}
            return name, log
        # 재검색: 1차 질의는 이미 봤으므로 더 추상적인 질의로 바꾼다 (실측: 같은 질의 재검색은 같은 후보 8장을 다시 심사했다)
        queries = ["abstract dark minimal light texture", "bokeh lights dark background", queries[0]]
    log["fallback"] = "plain"
    return None, log


def main(url: str, db_path: str, force: bool = False) -> str:
    import validate
    import writer

    t0 = time.time()
    aid = naver_article.article_id(url)
    out = os.path.join(ROOT, "output", aid)
    os.makedirs(out, exist_ok=True)
    notes: list[str] = []

    db = Database(db_path)
    row = db.get(aid)
    draft = db.latest_draft(aid)
    if row is not None and row["body"]:
        article = {"url": url, "id": aid, "title": row["title"], "press": row["press"],
                   "date": row["pub_date"][:10], "body": row["body"]}
    else:
        article = naver_article.fetch(url)
        if row is not None:
            db.set_body(aid, article["body"], article.get("press"))

    if draft is not None:
        script = json.loads(draft["script_json"])
        errors = validate.check(script, article["body"])
        notes.append(f"원고: drafts v{draft['version']} ({draft['source']})")
    else:
        script = writer.write(article)
        errors = validate.check(script, article["body"])
        for _ in range(MAX_REWRITES):
            if not errors:
                break
            script = writer.write(article, script, errors)
            errors = validate.check(script, article["body"])
        db.save_draft(aid, {k: v for k, v in script.items() if k != "_usage"}, errors, "ai", script.get("_usage") or {})
        notes.append("원고: writer 신규 생성")
    if errors and not force:
        db.update_review(aid, None, f"검수 오류 {len(errors)}건 — 원고 시트 확인", None, None)
        db.conn.commit()
        db.close()
        raise SystemExit(f"원고 검수 오류 {len(errors)}건 (엑셀 '원고' 시트에서 수정 후 재실행, 또는 --force): {errors}")
    # LLM 판정 게이트: 사실 일치 2점 이하(수치 오류·근거 없는 귀속)는 사람이 놓치기 쉬워 제작 전에 멈춘다 (docs/EVAL.md)
    # 판정이 없는 버전(엑셀에서 막 고친 원고 등)은 여기서 채점한다.
    if not force:
        version = draft["version"] if draft is not None else db.latest_draft(aid)["version"]
        key = keys.load("Anthropic-jachi", "ANTHROPIC_API_KEY", required=False)
        ev = ensure_judged(db, aid, version, script, article["body"],
                           {"press": article.get("press", ""), "title": article.get("title", ""), "date": article.get("date", "")},
                           Judge(key) if key else None)
        ok, why = gate(ev)
        if not ok:
            db.update_review(aid, None, f"제작 보류: {why[:120]}", None, None)
            db.conn.commit()
            db.close()
            raise SystemExit(f"제작 보류 — {why}\n엑셀 '원고' 시트에서 고친 뒤 다시 실행하세요 (무시하려면 --force)")
    _normalize_slide_types(script, article["body"], notes)

    scorer = HaikuScorer(keys.load("Anthropic-jachi", "ANTHROPIC_API_KEY"))
    images: list[str | None] = []
    image_log: list[dict] = []
    try:
        cover = script["cover"]
        name, log = _pick_image(db, scorer, aid, 1, _queries(cover),
                                " ".join(l["text"] for l in cover["lines"]),
                                cover.get("image_concept", ""), out)
        images.append(name); image_log.append({"slide": 1, **log})
        for n, s in enumerate(script["slides"], start=2):
            if s.get("slide_type") == "stat":
                images.append(None); image_log.append({"slide": n, "stat": True})
                continue
            name, log = _pick_image(db, scorer, aid, n, _queries(s), s["title"],
                                    s.get("image_concept", s["body"][:80]), out)
            images.append(name); image_log.append({"slide": n, **log})

        source = f"출처: {article['press']} · {article['date'].replace('-', '.')}"
        made = db.conn.execute("SELECT COUNT(*) FROM articles WHERE status IN ('제작완료','게시완료')").fetchone()[0]
        pal = palette.pick_rotation(made, os.environ.get("CARDNEWS_PALETTE", ""))
        files, qa = render.render(render.build_pages(script, images, source, palette=pal), out)

        meta = {
            "palette": pal,
            "article": {k: article[k] for k in ("id", "url", "title", "press", "date")},
            "script": script, "images": image_log, "cards": files,
            "qa": {"script_errors": errors, "notes": notes, "render": qa,
                   "vision_calls": scorer.calls, "seconds": round(time.time() - t0, 1)},
            "usage": {"writer": script.pop("_usage", None), "vision_calls": scorer.calls},
        }
        with open(os.path.join(out, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        if db.get(aid) is not None:
            db.update_review(aid, "제작완료", None, out, None)
            db.conn.commit()
    finally:
        db.close()

    print(json.dumps({"notes": notes, "render": qa, "vision_calls": scorer.calls}, ensure_ascii=False, indent=1))
    print(out)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--db", default=os.path.join(ROOT, "data", "news.db"))
    ap.add_argument("--force", action="store_true", help="검수 오류가 있어도 렌더")
    a = ap.parse_args()
    main(a.url, a.db, a.force)
