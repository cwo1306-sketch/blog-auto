"""로드맵 2단계: 엑셀에서 '승인'으로 바꾼 기사를 일괄 제작한다.

Usage: .venv/bin/python make_batch.py [--db data/news.db] [--limit 3] [--dry-run]

흐름: queue.import(엑셀 → DB) → status='승인' 행 조회 → make_card.main(naver_link) → 성공 시 '제작완료'+card_folder,
      실패 시 status는 '승인' 유지하고 memo에 사유 → queue.export(DB → 엑셀)
한 건이 실패해도 다음 건을 계속한다. --limit 으로 하루 제작 수를 제한한다(HANDOFF 8장 미결: 하루 게시 수).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback

import make_card
from naver_cardnews.config import load_settings
from naver_cardnews.db import Database
from naver_cardnews.queue import ExcelLocked, export_queue, import_queue

ROOT = os.path.dirname(os.path.abspath(__file__))


def approved(db: Database, limit: int) -> list:
    return db.conn.execute(
        "SELECT id, title, naver_link, score FROM articles WHERE status='승인' "
        "ORDER BY score DESC, pub_date DESC LIMIT ?", (limit,)
    ).fetchall()


def main(db_path: str, limit: int, dry_run: bool) -> int:
    s = load_settings()
    s.db_path = db_path
    db = Database(db_path)
    results = []
    try:
        try:
            n = import_queue(db, s.output_path)
            print(f"엑셀 → DB 반영 {n}건", file=sys.stderr)
        except ExcelLocked as exc:
            print(exc, file=sys.stderr)
            return 3
        rows = approved(db, limit)
        print(f"승인 {len(rows)}건 (limit {limit})", file=sys.stderr)
        for row in rows:
            print(f"→ {row['id']} {row['title'][:50]}", file=sys.stderr)
            if dry_run:
                continue
            t0 = time.time()
            try:
                out = make_card.main(row["naver_link"], db_path)
                results.append({"id": row["id"], "ok": True, "folder": out, "seconds": round(time.time() - t0, 1)})
            except Exception as exc:  # noqa: BLE001 — 한 건 실패가 배치를 멈추지 않게
                traceback.print_exc()
                db.update_review(row["id"], None, f"제작 실패: {str(exc)[:120]}", None, None)
                db.conn.commit()
                results.append({"id": row["id"], "ok": False, "error": str(exc)[:200]})
        if not dry_run:
            try:
                export_queue(db, s.output_path)
            except ExcelLocked as exc:
                print(f"엑셀이 열려 있어 재생성하지 못했습니다: {exc}", file=sys.stderr)
    finally:
        db.close()
    print(json.dumps(results, ensure_ascii=False, indent=1))
    return 0 if all(r["ok"] for r in results) else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=os.path.join(ROOT, "data", "news.db"))
    ap.add_argument("--limit", type=int, default=3)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    sys.exit(main(a.db, a.limit, a.dry_run))
