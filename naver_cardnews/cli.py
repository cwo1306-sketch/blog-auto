"""사용법:
    python -m naver_cardnews run        # import(엑셀→DB) → collect(API+섹션) → draft(상위 N 원고) → export (평소엔 이것만)
    python -m naver_cardnews draft --top 10   # 대기 상위 N건 본문 크롤링 + 원고·캡션 생성 → '원고' 시트
    python -m naver_cardnews collect    # 수집 + 중복 제거 → SQLite
    python -m naver_cardnews export     # SQLite → 엑셀 재생성
    python -m naver_cardnews import     # 엑셀의 상태/메모 → SQLite
    python -m naver_cardnews stats
    python -m naver_cardnews pick-image --article 015_1 --slide 1 --headline "…" --concept "…" -q "abstract lens" -q "server room"
    python -m naver_cardnews stat-card --value 55 --unit % --label "AI 토큰 비용 절감률" --quote "…" --out data/stat.png
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .collect import collect
from .config import load_settings
from .db import Database
from .queue import ExcelLocked, export_queue, import_drafts, import_queue


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="naver_cardnews", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["run", "collect", "draft", "export", "import", "stats", "pick-image", "stat-card"])
    p.add_argument("--top", type=int, help="draft: 원고를 만들 상위 건수 (기본 NAVER_CARDNEWS_DRAFT_TOP=10, run 에서는 0이면 생략)")
    p.add_argument("--no-sections", action="store_true", help="섹션 페이지 크롤링 끄기")
    p.add_argument("--keywords", type=Path, help="키워드 YAML (기본 keywords.yaml)")
    p.add_argument("--db", type=Path)
    p.add_argument("--out", type=Path, help="엑셀 경로")
    p.add_argument("--per-keyword", type=int, help="키워드당 최대 건수 (≤1000)")
    p.add_argument("--days", type=int, help="수집 기간(일)")
    p.add_argument("--no-judge", action="store_true", help="Haiku 판정(같은 사건·니치 적합) 모두 끄기")
    p.add_argument("-v", "--verbose", action="store_true")
    g = p.add_argument_group("pick-image / stat-card")
    g.add_argument("--article", help="oid_aid (used_images 기록용)")
    g.add_argument("--slide", type=int, default=1)
    g.add_argument("--headline", default="")
    g.add_argument("--concept", default="", help="사진이 표현할 개념(한국어)")
    g.add_argument("-q", "--query", action="append", default=[], help="영어 검색어 (여러 번)")
    g.add_argument("--per-query", type=int, default=6)
    g.add_argument("--value"); g.add_argument("--unit", default=""); g.add_argument("--label", default="")
    g.add_argument("--quote", default=""); g.add_argument("--page", type=int, default=3)
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")
    if not args.verbose:  # anthropic SDK의 요청 로그 억제
        logging.getLogger("httpx2").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)
    if not args.verbose:  # anthropic SDK의 요청 로그 억제
        logging.getLogger("httpx2").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)
    s = load_settings(keywords_file=args.keywords)
    if args.db:
        s.db_path = args.db
    if args.out:
        s.output_path = args.out
    if args.per_keyword:
        s.per_keyword = args.per_keyword
    if args.days:
        s.max_age_days = args.days
    if args.no_judge:
        s.judge_enabled = s.niche_judge_enabled = False
    if args.no_sections:
        s.sections = []
    if args.top is not None:
        s.draft_top = args.top

    if args.command in ("run", "collect") and not (s.client_id and s.client_secret):
        print("NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 가 비어 있습니다. .env.example을 .env로 복사해 채우세요.",
              file=sys.stderr)
        return 2

    judge = None
    if args.command in ("run", "collect") and (s.judge_enabled or s.niche_judge_enabled) and s.anthropic_api_key:
        from .judge import HaikuJudge
        judge = HaikuJudge(s.anthropic_api_key)

    if args.command == "stat-card":
        return _stat_card(args, s)
    if args.command == "pick-image":
        return _pick_image(args, s)

    db = Database(s.db_path)
    try:
        if args.command in ("run", "import"):
            n = import_queue(db, s.output_path)
            m = import_drafts(db, s.output_path)
            print(f"엑셀 → DB 반영: 상태 {n}건, 원고 수정 {m}건")
        if args.command in ("run", "collect"):
            rep = collect(s, db, judge=judge, progress=lambda k: print("  수집:", k, file=sys.stderr))
            print(rep.summary())
            for e in rep.errors:
                print("  오류:", e, file=sys.stderr)
        if args.command == "draft" or (args.command == "run" and s.draft_top > 0):
            if not s.anthropic_api_key:
                print("원고 생성에 ANTHROPIC_API_KEY 가 필요합니다", file=sys.stderr)
            else:
                from . import writer
                from .draft import draft_top
                writer.configure(s.anthropic_api_key)
                rep = draft_top(db, s.draft_top, progress=lambda t: print("  원고:", t, file=sys.stderr))
                print(rep.summary())
        if args.command in ("run", "export"):
            n = export_queue(db, s.output_path)
            print(f"DB → 엑셀 {n}행 → {s.output_path}")
        if args.command == "stats":
            for k, v in db.stats().items():
                print(f"{k:>8}: {v}")
    except ExcelLocked as exc:
        print(exc, file=sys.stderr)
        return 3
    finally:
        db.close()
    return 0


def _stat_card(args, s) -> int:
    from .stat_card import Stat, StatError, render_png, validate_stat
    if not args.value:
        print("--value 가 필요합니다", file=sys.stderr); return 2
    stat = Stat(args.value, args.unit, args.label, args.quote)
    try:
        validate_stat(stat)
    except StatError as exc:
        print("stat 규칙 위반:", exc, file=sys.stderr); return 2
    out = args.out or (s.images_dir / "stat_card.png")
    qa = render_png(stat, Path(out), args.page)
    print(f"숫자 카드 → {out}  QA={qa}")
    return 0 if qa["ok"] else 1


def _pick_image(args, s) -> int:
    import json
    from .stock import PexelsClient, UnsplashClient, download, search_candidates
    from .vision_pick import HaikuScorer, pick
    from .imagehash import dhash, to_hex
    if not args.query:
        print("-q 검색어가 하나 이상 필요합니다", file=sys.stderr); return 2
    clients = []
    if s.pexels_api_key:
        clients.append(PexelsClient(s.pexels_api_key))
    if s.unsplash_access_key:
        clients.append(UnsplashClient(s.unsplash_access_key))
    if not clients:
        print("PEXELS_API_KEY 또는 UNSPLASH_ACCESS_KEY 가 필요합니다", file=sys.stderr); return 2
    if not s.anthropic_api_key:
        print("비전 검수에 ANTHROPIC_API_KEY 가 필요합니다", file=sys.stderr); return 2

    cands = search_candidates(args.query, clients, per_query=args.per_query)
    print(f"후보 {len(cands)}장 (소스 {len(clients)}개, 검색어 {len(args.query)}개)", file=sys.stderr)
    for c in cands:
        try:
            c.image_bytes = download(c.thumb_url)
        except Exception as exc:
            print(f"  썸네일 실패 {c.key}: {exc}", file=sys.stderr)
    db = Database(s.db_path)
    try:
        scorer = HaikuScorer(s.anthropic_api_key)
        result = pick(cands, args.headline, args.concept, scorer, db)
        out_dir = Path(args.out) if args.out else s.images_dir / (args.article or "adhoc")
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / f"s{args.slide}_pick.json").write_text(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        for c, sc in result.scored:
            mark = "✗" if sc.hard_fail else f"{sc.total:.2f}"
            print(f"  {mark:>5} {c.source}:{c.external_id} {sc.reason[:60]}", file=sys.stderr)
        if result.chosen is None:
            print("적합한 후보 없음 → 재검색 또는 단색 카드로 강등", file=sys.stderr); return 1
        c = result.chosen
        full = download(c.full_url)
        path = out_dir / f"s{args.slide}_{c.source}_{c.external_id}.jpg"
        path.write_bytes(full)
        if args.article:
            db.record_image(args.article, args.slide, c.source, c.external_id, c.query,
                            to_hex(dhash(c.image_bytes)), str(path), c.photographer, c.page_url)
        print(f"선택 {c.source}:{c.external_id} ({c.photographer}) → {path}  비전 호출 {scorer.calls}회")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
