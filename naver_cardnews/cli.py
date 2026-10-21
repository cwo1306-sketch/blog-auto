"""사용법:
    python -m naver_cardnews run        # import → collect → export (평소엔 이것만)
    python -m naver_cardnews collect    # 수집 + 중복 제거 → SQLite
    python -m naver_cardnews export     # SQLite → 엑셀 재생성
    python -m naver_cardnews import     # 엑셀의 상태/메모 → SQLite
    python -m naver_cardnews stats
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .collect import collect
from .config import load_settings
from .db import Database
from .queue import ExcelLocked, export_queue, import_queue


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="naver_cardnews", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["run", "collect", "export", "import", "stats"])
    p.add_argument("--keywords", type=Path, help="키워드 YAML (기본 keywords.yaml)")
    p.add_argument("--db", type=Path)
    p.add_argument("--out", type=Path, help="엑셀 경로")
    p.add_argument("--per-keyword", type=int, help="키워드당 최대 건수 (≤1000)")
    p.add_argument("--days", type=int, help="수집 기간(일)")
    p.add_argument("--no-judge", action="store_true", help="경계 구간 Haiku 판정 끄기")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")
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
        s.judge_enabled = False

    if args.command in ("run", "collect") and not (s.client_id and s.client_secret):
        print("NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 가 비어 있습니다. .env.example을 .env로 복사해 채우세요.",
              file=sys.stderr)
        return 2

    judge = None
    if args.command in ("run", "collect") and s.judge_enabled and s.anthropic_api_key:
        from .judge import HaikuJudge
        judge = HaikuJudge(s.anthropic_api_key)

    db = Database(s.db_path)
    try:
        if args.command in ("run", "import"):
            n = import_queue(db, s.output_path)
            print(f"엑셀 → DB 반영 {n}건")
        if args.command in ("run", "collect"):
            rep = collect(s, db, judge=judge, progress=lambda k: print("  수집:", k, file=sys.stderr))
            print(rep.summary())
            for e in rep.errors:
                print("  오류:", e, file=sys.stderr)
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


if __name__ == "__main__":
    sys.exit(main())
