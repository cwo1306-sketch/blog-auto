"""n.news.naver.com 기사 파서.

원본 대비 개선:
- 제목·본문이 비면 예외 (빈 원고가 writer로 흘러가는 것을 막는다)
- 사진 설명(<em class="img_desc">), 기자 이메일·'무단 전재' 꼬리, 광고 문구 제거
- og: 메타 폴백(title/press/date), 네트워크 재시도 1회, 모바일(m.)·데스크톱 URL 모두 허용
- 결과에 oid_aid 포함 → 1단계 DB(articles.id)와 바로 조인
"""

from __future__ import annotations

import html
import re
import time
import urllib.request

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0 Safari/537.36")
_ID_RE = re.compile(r"article/(?:comment/)?(\d+)/(\d+)")
_TAIL_PATTERNS = [
    r"[\w.+-]+@[\w-]+\.[\w.]+",                       # 기자 이메일
    r"(?m)^\s*\S*\s*기자\s*$",                          # '홍길동 기자' 단독 줄
    r"(?m)^.*(무단\s*전재|재배포\s*금지|AI\s*학습\s*이용\s*금지).*$",
    r"(?m)^\s*\[.{1,12}\]\s*$",                        # [사진=…] 류 단독 줄
]


class ArticleError(RuntimeError):
    pass


def article_id(url: str) -> str:
    m = _ID_RE.search(url)
    if not m:
        raise ArticleError(f"네이버 뉴스 기사 URL이 아닙니다: {url}")
    return f"{m.group(1)}_{m.group(2)}"


def _clean(s: str) -> str:
    s = re.sub(r"<em class=\"img_desc\"[^>]*>.*?</em>", " ", s, flags=re.S)   # 사진 설명
    s = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", s, flags=re.S)
    s = re.sub(r"<br\s*/?>", "\n", s)
    s = re.sub(r"</(p|div|li|h\d)>", "\n", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s)
    for pat in _TAIL_PATTERNS:
        s = re.sub(pat, "", s)
    s = re.sub(r"[ \t ]+", " ", s)
    return re.sub(r"\n\s*\n+", "\n", s).strip()


def _get(url: str, retries: int = 1) -> str:
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ko"})
            return urllib.request.urlopen(req, timeout=15).read().decode("utf-8", "ignore")
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(1.5 * (attempt + 1))
    raise ArticleError(f"기사 요청 실패: {last}")


def parse(raw: str, url: str = "") -> dict:
    def find(pattern: str, flags: int = re.S) -> str:
        m = re.search(pattern, raw, flags)
        return m.group(1) if m else ""

    title = _clean(find(r'id="title_area"[^>]*>(.*?)</h2>')) or _clean(find(r'<meta property="og:title" content="([^"]*)"'))
    body = _clean(find(r'id="dic_area"[^>]*>(.*?)</article>')) or _clean(find(r'id="newsct_article"[^>]*>(.*?)</article>'))
    press = find(r'<meta property="og:article:author" content="([^"|]+)').strip() \
        or _clean(find(r'class="media_end_head_top_logo"[^>]*>.*?alt="([^"]+)"'))
    date = find(r'data-date-time="([^"]+)"')[:10] or find(r'<meta property="article:published_time" content="(\d{4}-\d{2}-\d{2})')
    if not title or len(body) < 200:
        raise ArticleError(f"제목/본문 추출 실패 (title={title[:30]!r}, body_len={len(body)}): {url}")
    return {"url": url, "id": article_id(url) if url else "", "title": title, "press": press,
            "date": date, "body": body}


def fetch(url: str) -> dict:
    return parse(_get(url), url)
