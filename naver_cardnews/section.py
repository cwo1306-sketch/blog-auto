"""네이버 뉴스 섹션 페이지 크롤러 (IT/과학 = 105). 키워드 검색에 안 걸리는 기사를 큐에 보탠다.

n.news.naver.com/section/{sid} 의 첫 화면(헤드라인+최신, 40~50건)만 읽는다. 약관·부하를 고려해 호출은 수집 1회당
섹션당 1페이지, 요청 간 1초. 결과는 검색 API item 과 같은 모양으로 돌려줘 collect 파이프라인(니치 필터·중복 제거·Haiku 판정)을
그대로 탄다. 제목·리드문·언론사·상대 시각만 있고 originallink 는 없다.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

from .article import clean_html, http_get

log = logging.getLogger(__name__)

SECTION_URL = "https://n.news.naver.com/section/{sid}"
SECTIONS = {"105": "IT/과학"}
_ITEM_RE = re.compile(r'<div class="sa_text">(.*?)</div>\s*</div>\s*</div>\s*</li>', re.S)
_ITEM_FALLBACK_RE = re.compile(r'<div class="sa_text">(.*?)(?=<div class="sa_text">|</ul>)', re.S)
_TITLE_RE = re.compile(r'<a[^>]+href="(https://n\.news\.naver\.com/mnews/article/\d+/\d+)[^"]*"[^>]*class="sa_text_title[^"]*"[^>]*>(.*?)</a>', re.S)
_LEDE_RE = re.compile(r'class="sa_text_lede">(.*?)</div>', re.S)
_PRESS_RE = re.compile(r'class="sa_text_press">([^<]+)<')
_TIME_RE = re.compile(r'class="sa_text_datetime[^"]*"[^>]*>\s*<b>([^<]+)</b>')
_REL_RE = re.compile(r"(\d+)\s*(분|시간|일)전")


def parse_relative_time(text: str, now: datetime | None = None) -> datetime:
    """'1시간전' → 대략적인 UTC 시각. 절대 날짜(YYYY.MM.DD.)면 그 날 0시(KST)."""
    now = now or datetime.now(timezone.utc)
    m = _REL_RE.search(text or "")
    if m:
        n, unit = int(m.group(1)), m.group(2)
        delta = {"분": timedelta(minutes=n), "시간": timedelta(hours=n), "일": timedelta(days=n)}[unit]
        return (now - delta).replace(microsecond=0)
    m = re.search(r"(\d{4})\.(\d{2})\.(\d{2})", text or "")
    if m:
        kst = timezone(timedelta(hours=9))
        return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=kst).astimezone(timezone.utc)
    return now.replace(microsecond=0)


def parse_section(raw: str, sid: str = "105", now: datetime | None = None) -> list[dict]:
    """섹션 HTML → 검색 API item 모양의 dict 목록 (title, description, link, originallink, pubDate, press)."""
    items, seen = [], set()
    blocks = _ITEM_FALLBACK_RE.findall(raw)
    for block in blocks:
        m = _TITLE_RE.search(block)
        if not m:
            continue
        link, title = m.group(1), clean_html(m.group(2))
        if not title or link in seen:
            continue
        seen.add(link)
        lede = _LEDE_RE.search(block)
        press = _PRESS_RE.search(block)
        when = _TIME_RE.search(block)
        items.append({
            "title": title,
            "description": clean_html(lede.group(1)) if lede else "",
            "link": link, "originallink": "",
            "pubDate": format_datetime(parse_relative_time(when.group(1) if when else "", now)),
            "press": press.group(1).strip() if press else "",
            "section": SECTIONS.get(sid, sid),
        })
    return items


def crawl_sections(sids: list[str], interval: float = 1.0) -> list[dict]:
    out: list[dict] = []
    for i, sid in enumerate(sids):
        if i:
            time.sleep(interval)
        try:
            out += parse_section(http_get(SECTION_URL.format(sid=sid)), sid)
        except Exception as exc:  # noqa: BLE001
            log.error("섹션 %s 크롤링 실패: %s", sid, exc)
    return out
