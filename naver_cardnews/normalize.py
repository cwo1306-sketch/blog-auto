"""URL·제목·본문 정규화. 중복 제거의 모든 단계가 이 함수들에 의존한다."""

from __future__ import annotations

import html
import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_TAG_RE = re.compile(r"<[^>]+>")
# [속보], (종합), 【단독】 같은 머리말 꼬리말
_BRACKET_RE = re.compile(r"[\[\(【<][^\]\)】>]{1,12}[\]\)】>]")
# "…ㅣ뉴스1", " - 연합뉴스", " | 조선일보" 같은 매체명 꼬리
_SOURCE_SUFFIX_RE = re.compile(r"\s*[\|ㅣ\-–—]\s*[\w가-힣\s]{2,15}$")
_NON_WORD_RE = re.compile(r"[^0-9a-z가-힣]+")

# 광고·추적 파라미터. 기사 식별에 쓰이는 파라미터(oid/aid/sid 등)는 남긴다.
_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "igshid", "ref", "from", "source", "cds", "trackingcode",
}


def strip_html(text: str) -> str:
    """HTML 태그 제거 + 엔티티 복원 (네이버 API는 <b> 태그와 &quot;를 섞어 준다)."""
    return html.unescape(_TAG_RE.sub("", text or "")).strip()


def normalize_url(url: str) -> str:
    """스킴 통일, 호스트 소문자화, 추적 파라미터 제거, 쿼리 정렬, 말단 슬래시 제거."""
    if not url:
        return ""
    parts = urlsplit(url.strip())
    scheme = "https"  # http/https 차이는 같은 기사로 본다
    host = parts.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    if host.startswith("m."):  # 모바일 도메인을 데스크톱과 합친다
        host = host[2:]
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=False)
             if k.lower() not in _TRACKING_PARAMS]
    query.sort()
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((scheme, host, path, urlencode(query), ""))


def normalize_title(title: str) -> str:
    """제목 비교용 키. 대괄호 머리말, 매체명 꼬리, 기호, 공백을 모두 제거한다."""
    text = strip_html(title)
    text = unicodedata.normalize("NFKC", text)
    text = _BRACKET_RE.sub(" ", text)
    text = _SOURCE_SUFFIX_RE.sub("", text)
    text = text.lower()
    return _NON_WORD_RE.sub("", text)


def tokenize(text: str) -> list[str]:
    """유사도 계산용 토큰. 한글은 2-gram, 영문/숫자는 단어 단위."""
    text = unicodedata.normalize("NFKC", strip_html(text)).lower()
    tokens: list[str] = []
    for chunk in re.findall(r"[a-z0-9]+|[가-힣]+", text):
        if chunk[0].isascii():
            tokens.append(chunk)
        elif len(chunk) == 1:
            tokens.append(chunk)
        else:
            tokens.extend(chunk[i:i + 2] for i in range(len(chunk) - 1))
    return tokens
