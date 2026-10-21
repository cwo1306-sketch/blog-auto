"""URL·제목·요약 정규화. 중복 제거의 모든 단계가 이 함수들에 의존한다."""

from __future__ import annotations

import html
import re
import unicodedata
from urllib.parse import urlsplit

_TAG_RE = re.compile(r"<[^>]+>")
# [속보], (종합), 【단독】 같은 머리말·꼬리말과 괄호 안 짧은 주석
_BRACKET_RE = re.compile(r"[\[\(【<][^\]\)】>]{1,15}[\]\)】>]")
# "…ㅣ뉴스1", " - 연합뉴스", " | 조선일보" 같은 매체명 꼬리
_SOURCE_SUFFIX_RE = re.compile(r"\s*[\|ㅣ\-–—]\s*[\w가-힣\s]{2,15}$")
_NON_WORD_RE = re.compile(r"[^0-9a-z가-힣]+")
_NAVER_ARTICLE_RE = re.compile(r"n\.news\.naver\.com/(?:mnews/)?(?:hotissue/)?article/(\d+)/(\d+)")


def strip_html(text: str) -> str:
    """HTML 태그 제거 + 엔티티 복원 (네이버 API는 <b> 태그와 &quot;를 섞어 준다)."""
    return html.unescape(_TAG_RE.sub("", text or "")).strip()


def naver_article_id(link: str) -> str | None:
    """n.news.naver.com 기사 링크 → 'oid_aid'. 네이버 뉴스가 아니면 None."""
    m = _NAVER_ARTICLE_RE.search(link or "")
    return f"{m.group(1)}_{m.group(2)}" if m else None


def press_from_url(url: str) -> str:
    host = urlsplit(url or "").netloc.lower()
    for prefix in ("www.", "m.", "news.", "biz."):
        if host.startswith(prefix):
            host = host[len(prefix):]
    return host


def normalize_title(title: str) -> str:
    """제목 비교용 키. 대괄호 머리말, 매체명 꼬리, 특수문자, 공백을 모두 제거한다."""
    text = unicodedata.normalize("NFKC", strip_html(title))
    text = _BRACKET_RE.sub(" ", text)
    text = _SOURCE_SUFFIX_RE.sub("", text)
    return _NON_WORD_RE.sub("", text.lower())


def char_bigrams(text: str) -> set[str]:
    """문자 2-gram 집합 (공백·기호 제거 후). 3·4단계 Jaccard 비교용."""
    t = _NON_WORD_RE.sub("", unicodedata.normalize("NFKC", strip_html(text)).lower())
    if len(t) < 2:
        return {t} if t else set()
    return {t[i:i + 2] for i in range(len(t) - 1)}


def off_niche_reason(title: str, topic_terms: list[str], exclude_terms: list[str]) -> str | None:
    """니치 필터. 제목에 exclude 용어가 있거나 topic 용어가 하나도 없으면 사유를 돌려준다.
    topic_terms가 비어 있으면 필터를 끈 것으로 본다. 비교는 대소문자를 무시한다."""
    t = unicodedata.normalize("NFKC", strip_html(title)).lower()
    for term in exclude_terms:
        if term.lower() in t:
            return f"니치 외(배제어 '{term}')"
    if topic_terms and not any(term.lower() in t for term in topic_terms):
        return "니치 외(제목에 AI·테크 용어 없음)"
    return None


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)
