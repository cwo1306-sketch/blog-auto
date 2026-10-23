"""무료 스톡 사진 검색: Pexels(기본) + Unsplash(선택). 세로(portrait) 사진 후보를 돌려준다."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

import requests

log = logging.getLogger(__name__)

USER_AGENT = "cardkit/0.1 (+instagram card news pipeline)"  # Pexels는 UA 없으면 403


@dataclass
class Candidate:
    source: str            # pexels | unsplash
    external_id: str
    thumb_url: str         # 비전 검수용 (가로 350~400px)
    full_url: str          # 렌더용 (세로 1350px 이상)
    width: int
    height: int
    alt: str = ""
    photographer: str = ""
    page_url: str = ""
    query: str = ""
    image_bytes: bytes | None = field(default=None, repr=False)

    @property
    def key(self) -> tuple[str, str]:
        return (self.source, self.external_id)


class StockClient(Protocol):
    source: str
    def search(self, query: str, per_page: int = 10) -> list[Candidate]: ...


class PexelsClient:
    source = "pexels"
    API = "https://api.pexels.com/v1/search"

    def __init__(self, api_key: str, session: requests.Session | None = None):
        if not api_key:
            raise ValueError("PEXELS_API_KEY 가 비어 있습니다.")
        self.session = session or requests.Session()
        self.session.headers.update({"Authorization": api_key, "User-Agent": USER_AGENT})

    def search(self, query: str, per_page: int = 10) -> list[Candidate]:
        resp = self.session.get(self.API, params={"query": query, "orientation": "portrait",
                                                  "per_page": per_page}, timeout=15)
        resp.raise_for_status()
        return [self._parse(p, query) for p in resp.json().get("photos", [])]

    @staticmethod
    def _parse(p: dict[str, Any], query: str) -> Candidate:
        src = p.get("src", {})
        return Candidate(
            source="pexels", external_id=str(p["id"]),
            thumb_url=src.get("medium") or src.get("small") or src.get("original", ""),
            # portrait(800×1200)·large2x는 1350px에 못 미친다 → 원본을 받아 render에서 cover-fit
            full_url=src.get("original") or src.get("large2x") or src.get("portrait", ""),
            width=int(p.get("width", 0)), height=int(p.get("height", 0)),
            alt=p.get("alt") or "", photographer=p.get("photographer") or "",
            page_url=p.get("url") or "", query=query,
        )


class UnsplashClient:
    source = "unsplash"
    API = "https://api.unsplash.com/search/photos"

    def __init__(self, access_key: str, session: requests.Session | None = None):
        if not access_key:
            raise ValueError("UNSPLASH_ACCESS_KEY 가 비어 있습니다.")
        self.session = session or requests.Session()
        self.session.headers.update({"Authorization": f"Client-ID {access_key}",
                                     "Accept-Version": "v1", "User-Agent": USER_AGENT})

    def search(self, query: str, per_page: int = 10) -> list[Candidate]:
        resp = self.session.get(self.API, params={"query": query, "orientation": "portrait",
                                                  "per_page": per_page, "content_filter": "high"}, timeout=15)
        resp.raise_for_status()
        return [self._parse(p, query) for p in resp.json().get("results", [])]

    @staticmethod
    def _parse(p: dict[str, Any], query: str) -> Candidate:
        urls = p.get("urls", {})
        return Candidate(
            source="unsplash", external_id=str(p["id"]),
            thumb_url=urls.get("small") or urls.get("thumb", ""),
            full_url=(urls.get("raw") + "&w=1080&h=1350&fit=crop") if urls.get("raw") else urls.get("full", ""),
            width=int(p.get("width", 0)), height=int(p.get("height", 0)),
            alt=p.get("alt_description") or p.get("description") or "",
            photographer=(p.get("user") or {}).get("name", ""),
            page_url=(p.get("links") or {}).get("html", ""), query=query,
        )


def search_candidates(queries: list[str], clients: list[StockClient], per_query: int = 6,
                      min_height: int = 1350, max_per_photographer: int = 2) -> list[Candidate]:
    """여러 검색어 × 여러 소스에서 후보를 모아 (소스, id) 기준으로 중복을 없앤다. 검색어 순서를 유지한다.
    같은 작가의 연작이 후보를 독점하지 않게 작가당 max_per_photographer장까지만 남긴다."""
    seen: set[tuple[str, str]] = set()
    per_author: dict[str, int] = {}
    out: list[Candidate] = []
    for query in queries:
        for client in clients:
            try:
                found = client.search(query, per_page=per_query)
            except Exception as exc:
                log.warning("%s 검색 실패 (%r): %s", client.source, query, exc)
                continue
            for c in found:
                if c.key in seen or c.height < min_height or c.height <= c.width:
                    continue
                author = f"{c.source}:{c.photographer}"
                if c.photographer and per_author.get(author, 0) >= max_per_photographer:
                    continue
                per_author[author] = per_author.get(author, 0) + 1
                seen.add(c.key)
                out.append(c)
    return out


def download(url: str, session: requests.Session | None = None, timeout: int = 20) -> bytes:
    s = session or requests.Session()
    resp = s.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    resp.raise_for_status()
    return resp.content
