"""n.news.naver.com 기사 본문 파서 (cardnews/naver_article.py 의 본체. 1단계 DB에 본문을 저장할 때도 쓴다)."""

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
MIN_BODY = 200


class ArticleError(RuntimeError):
    pass


def article_id(url: str) -> str:
    m = _ID_RE.search(url)
    if not m:
        raise ArticleError(f"네이버 뉴스 기사 URL이 아닙니다: {url}")
    return f"{m.group(1)}_{m.group(2)}"


def clean_html(s: str) -> str:
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


def http_get(url: str, retries: int = 1, timeout: int = 15) -> str:
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ko"})
            return urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "ignore")
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(1.5 * (attempt + 1))
    raise ArticleError(f"요청 실패 {url}: {last}")


def parse(raw: str, url: str = "") -> dict:
    def find(pattern: str, flags: int = re.S) -> str:
        m = re.search(pattern, raw, flags)
        return m.group(1) if m else ""

    title = clean_html(find(r'id="title_area"[^>]*>(.*?)</h2>')) or clean_html(find(r'<meta property="og:title" content="([^"]*)"'))
    body = clean_html(find(r'id="dic_area"[^>]*>(.*?)</article>')) or clean_html(find(r'id="newsct_article"[^>]*>(.*?)</article>'))
    press = find(r'<meta property="og:article:author" content="([^"|]+)').strip() \
        or clean_html(find(r'class="media_end_head_top_logo"[^>]*>.*?alt="([^"]+)"'))
    date = find(r'data-date-time="([^"]+)"')[:10] or find(r'<meta property="article:published_time" content="(\d{4}-\d{2}-\d{2})')
    if not title or len(body) < MIN_BODY:
        raise ArticleError(f"제목/본문 추출 실패 (title={title[:30]!r}, body_len={len(body)}): {url}")
    return {"url": url, "id": article_id(url) if url else "", "title": title, "press": press,
            "date": date, "body": body}


def fetch(url: str) -> dict:
    return parse(http_get(url), url)
