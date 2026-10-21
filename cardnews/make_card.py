"""Usage: .venv/bin/python make_card.py <naver news url> [--db data/news.db]

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
from naver_cardnews.db import Database
from naver_cardnews.imagehash import dhash, to_hex
from naver_cardnews.stat_card import Stat, StatError, validate_stat
from naver_cardnews.stock import download
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
    for attempt in range(2):
        cands = pexels.search(queries, n=6 if attempt == 0 else 10)
        for c in cands:
            try:
                c.image_bytes = download(c.thumb_url)
            except Exception as exc:  # noqa: BLE001
                log.setdefault("thumb_errors", []).append(f"{c.key}: {exc}")
        result = pick(cands, headline, concept, scorer, db)
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
        # 재검색: 더 추상적인 질의로 넓힌다
        queries = queries + ["abstract dark minimal light texture"]
    log["fallback"] = "plain"
    return None, log


def main(url: str, db_path: str) -> str:
    import validate  # 로컬 프로젝트 모듈 (이 저장소에는 없음) — 호출 시점에 import 해 배치·테스트가 모듈 부재로 죽지 않게
    import writer

    t0 = time.time()
    article = naver_article.fetch(url)
    aid = article["id"]
    out = os.path.join(ROOT, "output", aid)
    os.makedirs(out, exist_ok=True)
    notes: list[str] = []

    script = writer.write(article)
    errors = validate.check(script, article["body"])
    for _ in range(MAX_REWRITES):
        if not errors:
            break
        script = writer.write(article, script, errors)
        errors = validate.check(script, article["body"])
    if errors:
        raise SystemExit(f"원고 검수 실패({MAX_REWRITES}회 재작성 후): {errors}")
    _normalize_slide_types(script, article["body"], notes)

    db = Database(db_path)
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
        files, qa = render.render(render.build_pages(script, images, source), out)

        meta = {
            "article": {k: article[k] for k in ("id", "url", "title", "press", "date")},
            "script": script, "images": image_log, "cards": files,
            "qa": {"script_errors": errors, "notes": notes, "render": qa,
                   "vision_calls": scorer.calls, "seconds": round(time.time() - t0, 1)},
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
    a = ap.parse_args()
    main(a.url, a.db)
