"""사용법:
    python -m naver_cardnews collect            # 키워드별 뉴스 수집 + 중복 제거 → SQLite
    python -m naver_cardnews export             # 검토 대기 기사 → 엑셀
    python -m naver_cardnews run                # collect + export
    python -m naver_cardnews stats
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .collector import collect
from .config import load_settings
from .db import Database
from .export import export_review_queue


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="naver_cardnews", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["collect", "export", "run", "stats"])
    parser.add_argument("--keywords", type=Path, help="키워드 YAML 경로 (기본 keywords.yaml)")
    parser.add_argument("--db", type=Path, help="SQLite 경로")
    parser.add_argument("--out", type=Path, help="엑셀 출력 경로")
    parser.add_argument("--per-keyword", type=int, help="키워드당 최대 수집 건수 (≤1000)")
    parser.add_argument("--days", type=int, help="수집 대상 기간(일)")
    parser.add_argument("--mark-exported", action="store_true",
                        help="export 후 해당 기사를 'exported'로 표시해 다음 큐에서 제외")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")

    settings = load_settings(keywords_file=args.keywords)
    if args.db:
        settings.db_path = args.db
    if args.out:
        settings.output_path = args.out
    if args.per_keyword:
        settings.per_keyword = args.per_keyword
    if args.days:
        settings.max_age_days = args.days

    if args.command in ("collect", "run") and not (settings.client_id and settings.client_secret):
        print("NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 가 비어 있습니다. .env.example을 .env로 복사해 채우세요.",
              file=sys.stderr)
        return 2

    db = Database(settings.db_path)
    try:
        if args.command in ("collect", "run"):
            report = collect(settings, db, progress=lambda s: print("  수집:", s, file=sys.stderr))
            print(report.summary())
            for err in report.errors:
                print("  오류:", err, file=sys.stderr)
        if args.command in ("export", "run"):
            n = export_review_queue(db, settings.output_path, mark_exported=args.mark_exported)
            print(f"엑셀 검토 큐 {n}건 → {settings.output_path}")
        if args.command == "stats":
            for k, v in db.stats().items():
                print(f"{k:>10}: {v}")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
