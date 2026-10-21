"""네이버 뉴스 검색 API 수집기."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable, Iterable
from urllib.parse import urlsplit

import requests

from .config import Settings
from .db import Article, Database
from .dedup import SIMHASH_MIN_TOKENS, Deduplicator, simhash
from .normalize import normalize_title, normalize_url, strip_html

log = logging.getLogger(__name__)

API_URL = "https://openapi.naver.com/v1/search/news.json"
MAX_DISPLAY = 100
MAX_START = 1000


class NaverNewsClient:
    def __init__(self, client_id: str, client_secret: str, session: requests.Session | None = None,
                 interval: float = 0.2):
        if not client_id or not client_secret:
            raise ValueError("NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 가 비어 있습니다. .env를 확인하세요.")
        self.session = session or requests.Session()
        self.session.headers.update({
            "X-Naver-Client-Id": client_id,
            "X-Naver-Client-Secret": client_secret,
        })
        self.interval = interval

    def search(self, query: str, display: int = MAX_DISPLAY, start: int = 1, sort: str = "date") -> dict[str, Any]:
        params = {"query": query, "display": min(display, MAX_DISPLAY), "start": min(start, MAX_START), "sort": sort}
        for attempt in range(3):
            resp = self.session.get(API_URL, params=params, timeout=10)
            if resp.status_code == 429 or resp.status_code >= 500:
                wait = 2 ** attempt
                log.warning("naver api %s for %r, retry in %ss", resp.status_code, query, wait)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            if self.interval:
                time.sleep(self.interval)
            return resp.json()
        resp.raise_for_status()
        return resp.json()

    def iter_items(self, query: str, limit: int, sort: str = "date") -> Iterable[dict[str, Any]]:
        fetched = 0
        start = 1
        while fetched < limit and start <= MAX_START:
            page = self.search(query, display=min(MAX_DISPLAY, limit - fetched), start=start, sort=sort)
            items = page.get("items") or []
            if not items:
                return
            for item in items:
                yield item
                fetched += 1
                if fetched >= limit:
                    return
            start += len(items)
            if len(items) < MAX_DISPLAY:
                return


def parse_pub_date(value: str) -> datetime:
    """'Mon, 20 Oct 2026 09:12:00 +0900' → aware UTC datetime."""
    dt = parsedate_to_datetime(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def item_to_article(item: dict[str, Any], keyword: str, group: str) -> Article:
    title = strip_html(item.get("title", ""))
    description = strip_html(item.get("description", ""))
    original = item.get("originallink") or item.get("link") or ""
    link = item.get("link") or original
    url_key = normalize_url(original)
    return Article(
        url_key=url_key,
        title_key=normalize_title(title),
        simhash=simhash(description, min_tokens=SIMHASH_MIN_TOKENS),
        title=title,
        description=description,
        link=link,
        original_link=original,
        source=urlsplit(url_key).netloc,
        pub_date=parse_pub_date(item["pubDate"]).isoformat(),
        keyword=keyword,
        keyword_group=group,
    )


@dataclass
class CollectReport:
    run_id: int
    fetched: int = 0
    inserted: int = 0
    duplicates: int = 0
    skipped_old: int = 0
    by_stage: dict[int, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        stages = ", ".join(f"{k}단계 {v}" for k, v in sorted(self.by_stage.items()))
        return (f"수집 {self.fetched}건 → 신규 {self.inserted}건, 중복 {self.duplicates}건"
                f"{' (' + stages + ')' if stages else ''}, 기간 초과 {self.skipped_old}건"
                f"{', 오류 ' + str(len(self.errors)) + '건' if self.errors else ''}")


def collect(settings: Settings, db: Database, client: NaverNewsClient | None = None,
            progress: Callable[[str], None] | None = None) -> CollectReport:
    client = client or NaverNewsClient(settings.client_id, settings.client_secret,
                                       interval=settings.request_interval)
    dedup = Deduplicator(db, window_days=max(settings.max_age_days, 1))
    keywords = settings.keywords
    report = CollectReport(run_id=db.start_run(len(keywords)))
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.max_age_days)

    for group, keyword in keywords:
        if progress:
            progress(f"[{group}] {keyword}")
        try:
            items = list(client.iter_items(keyword, settings.per_keyword))
        except Exception as exc:  # 한 키워드 실패가 전체 수집을 막지 않게 한다
            msg = f"{keyword}: {exc}"
            log.error(msg)
            report.errors.append(msg)
            continue

        with db.transaction():
            for item in items:
                report.fetched += 1
                try:
                    article = item_to_article(item, keyword, group)
                except Exception as exc:
                    report.errors.append(f"{keyword}: 파싱 실패 {exc}")
                    continue
                if datetime.fromisoformat(article.pub_date) < cutoff:
                    report.skipped_old += 1
                    continue
                result = dedup.check(article.url_key, article.title_key, article.title, article.simhash)
                if result.stage == 1:
                    # 같은 URL은 이미 저장돼 있으므로 다시 넣지 않는다.
                    report.duplicates += 1
                    report.by_stage[1] = report.by_stage.get(1, 0) + 1
                    continue
                new_id = db.insert(article, dedup_stage=result.stage, duplicate_of=result.duplicate_of)
                if result.stage == 0:
                    report.inserted += 1
                    dedup.remember(new_id, article.title, article.simhash)
                else:
                    report.duplicates += 1
                    report.by_stage[result.stage] = report.by_stage.get(result.stage, 0) + 1

    db.finish_run(report.run_id, report.fetched, report.inserted, report.duplicates, report.errors)
    return report
