"""호환용 얇은 래퍼. 실제 검색은 naver_cardnews.stock (Pexels+Unsplash, 세로·크기 필터, 작가당 상한) 이 한다.

원본 대비 개선: urllib 직접 호출 → requests 세션·타임아웃, large2x(세로 1300px 미만) 대신 원본 다운로드,
가로 사진·1350px 미만 제외, Unsplash 키가 있으면 후보 풀 2배.
"""

from __future__ import annotations

from naver_cardnews.stock import Candidate, PexelsClient, UnsplashClient, download, search_candidates

import keys

_clients = None


def clients():
    global _clients
    if _clients is None:
        _clients = [PexelsClient(keys.load("Pexels-cardnews", "PEXELS_API_KEY"))]
        unsplash = keys.load("Unsplash-cardnews", "UNSPLASH_ACCESS_KEY", required=False)
        if unsplash:
            _clients.append(UnsplashClient(unsplash))
    return _clients


def search(query: str | list[str], n: int = 6) -> list[Candidate]:
    queries = [query] if isinstance(query, str) else list(query)
    return search_candidates(queries, clients(), per_query=n)


def save(photo: Candidate, dest: str) -> None:
    with open(dest, "wb") as f:
        f.write(download(photo.full_url))
