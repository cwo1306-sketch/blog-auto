"""네이버 뉴스 검색 API 수집 → 4단계 중복 제거 → SQLite."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable, Iterable

import requests

from .config import Settings
from .db import Article, Database
from .dedup import Deduplicator
from .judge import Judge
from .normalize import (naver_article_id, normalize_title, off_niche_reason, press_from_url,
                        strip_html)
from .section import crawl_sections

log = logging.getLogger(__name__)

API_URL = "https://openapi.naver.com/v1/search/news.json"
MAX_DISPLAY = 100
MAX_START = 1000


class NaverNewsClient:
    def __init__(self, client_id: str, client_secret: str, interval: float = 0.2,
                 session: requests.Session | None = None):
        if not client_id or not client_secret:
            raise ValueError("NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 가 비어 있습니다.")
        self.session = session or requests.Session()
        self.session.headers.update({"X-Naver-Client-Id": client_id,
                                     "X-Naver-Client-Secret": client_secret})
        self.interval = interval

    def search(self, query: str, display: int = MAX_DISPLAY, start: int = 1) -> dict[str, Any]:
        params = {"query": query, "display": min(display, MAX_DISPLAY),
                  "start": min(start, MAX_START), "sort": "date"}
        resp = None
        for attempt in range(3):
            resp = self.session.get(API_URL, params=params, timeout=10)
            if resp.status_code == 429 or resp.status_code >= 500:
                time.sleep(2 ** attempt)
                continue
            resp.raise_for_status()
            if self.interval:
                time.sleep(self.interval)
            return resp.json()
        assert resp is not None
        resp.raise_for_status()
        return resp.json()

    def iter_items(self, query: str, limit: int) -> Iterable[dict[str, Any]]:
        fetched, start = 0, 1
        while fetched < limit and start <= MAX_START:
            page = self.search(query, display=min(MAX_DISPLAY, limit - fetched), start=start)
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
    dt = parsedate_to_datetime(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def item_to_article(item: dict[str, Any], keyword: str) -> Article | None:
    """네이버 뉴스(n.news.naver.com) 링크가 아니면 None (본문 파서가 동작하지 않음)."""
    link = item.get("link") or ""
    article_id = naver_article_id(link)
    if article_id is None:
        return None
    title = strip_html(item.get("title", ""))
    original = item.get("originallink") or ""
    return Article(
        id=article_id, keyword=keyword, title=title,
        press=item.get("press") or press_from_url(original or link),
        pub_date=parse_pub_date(item["pubDate"]).isoformat(),
        naver_link=link, originallink=original,
        description=strip_html(item.get("description", "")),
        title_key=normalize_title(title),
    )


@dataclass
class Report:
    fetched: int = 0
    non_naver: int = 0
    too_old: int = 0
    off_niche: int = 0
    off_niche_ai: int = 0
    new_clusters: int = 0
    by_stage: dict[int, int] = field(default_factory=dict)
    judge_calls: int = 0
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        names = {1: "URL", 2: "제목", 3: "근접", 4: "기게시"}
        stages = ", ".join(f"{names[k]} {v}" for k, v in sorted(self.by_stage.items()))
        parts = [f"API {self.fetched}건", f"네이버뉴스 아님 {self.non_naver}건",
                 f"기간 초과 {self.too_old}건",
                 f"니치 외 {self.off_niche}건" + (f" (+Haiku {self.off_niche_ai}건)" if self.off_niche_ai else ""),
                 f"신규 대기 {self.new_clusters}건",
                 f"중복 {sum(self.by_stage.values())}건" + (f" ({stages})" if stages else "")]
        if self.judge_calls:
            parts.append(f"Haiku 판정 {self.judge_calls}회")
        if self.errors:
            parts.append(f"오류 {len(self.errors)}건")
        return " · ".join(parts)


def collect(settings: Settings, db: Database, client: NaverNewsClient | None = None,
            judge: Judge | None = None, progress: Callable[[str], None] | None = None) -> Report:
    client = client or NaverNewsClient(settings.client_id, settings.client_secret,
                                       interval=settings.request_interval)
    dedup = Deduplicator(db, threshold=settings.sim_threshold, borderline=settings.sim_borderline,
                         window_hours=settings.cluster_window_hours,
                         posted_days=settings.posted_window_days,
                         judge=judge if settings.judge_enabled else None)
    niche_judge = judge if (judge is not None and settings.niche_judge_enabled) else None
    report = Report()
    run_id = db.start_run()
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.max_age_days)

    sources: list[tuple[str, Callable[[], list[dict]]]] = [
        (kw, (lambda kw=kw: list(client.iter_items(kw, settings.per_keyword)))) for kw in settings.keywords
    ]
    if settings.sections:
        sources.append(("섹션:IT/과학", lambda: crawl_sections(settings.sections)))

    for keyword, load in sources:
        if progress:
            progress(keyword)
        try:
            items = load()
        except Exception as exc:
            report.errors.append(f"{keyword}: {exc}")
            log.error("%s", report.errors[-1])
            continue

        with db.transaction():
            for item in items:
                report.fetched += 1
                try:
                    article = item_to_article(item, keyword)
                except Exception as exc:
                    report.errors.append(f"{keyword}: 파싱 실패 {exc}")
                    continue
                if article is None:
                    report.non_naver += 1
                    continue
                if datetime.fromisoformat(article.pub_date) < cutoff:
                    report.too_old += 1
                    continue

                if db.get(article.id) is not None:          # 1단계: 같은 네이버 기사
                    db.add_keyword_hit(article.id, keyword)
                    report.by_stage[1] = report.by_stage.get(1, 0) + 1
                    continue
                why = off_niche_reason(article.title, settings.topic_terms, settings.exclude_terms)
                if why:                                      # 니치 밖: 대표가 되지 않게 저장만
                    db.insert(article, None, False, "제외", why)
                    report.off_niche += 1
                    continue

                d = dedup.decide(article)
                if d.stage == 0 and niche_judge is not None:
                    # 새 클러스터 대표가 될 기사만 Haiku에게 묻는다 (중복은 대표 판정을 따라간다)
                    verdict = niche_judge.on_niche(article.title, article.description)
                    if verdict is False:
                        db.insert(article, None, False, "제외", "니치 외(Haiku 판정)")
                        report.off_niche_ai += 1
                        continue
                if d.stage == 0:
                    db.insert(article, db.next_cluster_id(), True, "대기")
                    report.new_clusters += 1
                else:
                    # 2·3단계는 기존 클러스터에 합류, 4단계(기게시)·니치 외 재송고는 클러스터 없이 제외
                    db.insert(article, d.cluster_id, False, "제외", d.reason)
                    report.by_stage[d.stage] = report.by_stage.get(d.stage, 0) + 1

    report.judge_calls = getattr(judge, "calls", dedup.judge_calls)
    db.refresh_scores()
    db.finish_run(run_id, report.summary())
    return report
