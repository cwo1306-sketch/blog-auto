"""원고 생성: 대기 중 점수 상위 N건 → 본문 크롤링 → writer(Sonnet) → validate → drafts 저장.

엑셀 '원고' 시트에 펼쳐져 사람이 점검·수정하고, 수정본(source='excel')이 제작에 쓰인다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable

from . import validate, writer
from .article import ArticleError, fetch
from .db import Database

log = logging.getLogger(__name__)
MAX_REWRITES = 2


@dataclass
class DraftReport:
    drafted: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0

    def summary(self) -> str:
        return (f"원고 {len(self.drafted)}건 생성, 실패 {len(self.failed)}건, "
                f"토큰 입력 {self.input_tokens:,} / 출력 {self.output_tokens:,}")


def ensure_body(db: Database, row, fetcher: Callable[[str], dict] = fetch) -> dict:
    """DB에 본문이 있으면 그걸, 없으면 크롤링해 저장한다. writer 입력 dict 를 돌려준다."""
    if row["body"]:
        return {"url": row["naver_link"], "id": row["id"], "title": row["title"], "press": row["press"],
                "date": row["pub_date"][:10], "body": row["body"]}
    art = fetcher(row["naver_link"])
    db.set_body(row["id"], art["body"], art.get("press"))
    art.setdefault("date", row["pub_date"][:10])
    return art


def draft_one(db: Database, row, fetcher: Callable[[str], dict] = fetch,
              write: Callable = writer.write, fmt: str | None = None) -> tuple[dict, list[str], dict]:
    article = ensure_body(db, row, fetcher)
    script = write(article, fmt=fmt) if fmt else write(article)
    usage = dict(script.get("_usage") or {})
    errors = validate.check(script, article["body"])
    usage["first_pass_errors"] = list(errors)   # 재작성을 부른 1차 오류 (프롬프트 튜닝 근거)
    for _ in range(MAX_REWRITES):
        if not errors:
            break
        script = write(article, script, errors, fmt=fmt) if fmt else write(article, script, errors)
        u = script.get("_usage") or {}
        usage["input_tokens"] = usage.get("input_tokens", 0) + u.get("input_tokens", 0)
        usage["output_tokens"] = usage.get("output_tokens", 0) + u.get("output_tokens", 0)
        usage["rewrites"] = usage.get("rewrites", 0) + 1
        errors = validate.check(script, article["body"])
    script.pop("_usage", None)
    return script, errors, usage


def draft_top(db: Database, top: int, fetcher: Callable[[str], dict] = fetch, write: Callable = writer.write,
              progress: Callable[[str], None] | None = None, fmt: str | None = None) -> DraftReport:
    report = DraftReport()
    for row in db.draft_candidates(top):
        if progress:
            progress(f"{row['id']} {row['title'][:40]}")
        try:
            script, errors, usage = draft_one(db, row, fetcher, write, fmt=fmt)
        except (ArticleError, writer.WriterError) as exc:
            log.error("%s 원고 실패: %s", row["id"], exc)
            db.update_review(row["id"], None, f"원고 실패: {str(exc)[:100]}", None, None)
            db.conn.commit()
            report.failed.append(row["id"])
            continue
        db.save_draft(row["id"], script, errors, "ai", usage)
        report.drafted.append(row["id"])
        report.input_tokens += usage.get("input_tokens", 0)
        report.output_tokens += usage.get("output_tokens", 0)
    return report
