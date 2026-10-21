"""환경 변수와 키워드 파일을 읽어 설정 객체를 만든다."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_KEYWORDS_FILE = PROJECT_ROOT / "keywords.yaml"


def _load_dotenv(path: Path) -> None:
    """의존성 없이 .env를 읽는다. 이미 설정된 환경 변수는 덮어쓰지 않는다."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


@dataclass
class Settings:
    client_id: str
    client_secret: str
    db_path: Path
    output_path: Path
    keywords_file: Path = DEFAULT_KEYWORDS_FILE
    # 키워드당 요청할 최대 기사 수 (네이버 API: display 최대 100, start 최대 1000)
    per_keyword: int = 100
    # 수집 대상 기간(일). 이보다 오래된 기사는 저장하지 않는다.
    max_age_days: int = 3
    # 요청 간 대기(초). 네이버 검색 API 일일 25,000건 제한을 고려한 완충.
    request_interval: float = 0.2
    keyword_groups: dict[str, list[str]] = field(default_factory=dict)

    @property
    def keywords(self) -> list[tuple[str, str]]:
        """(그룹, 키워드) 목록. 중복 키워드는 첫 그룹만 남긴다."""
        seen: set[str] = set()
        out: list[tuple[str, str]] = []
        for group, words in self.keyword_groups.items():
            for word in words:
                if word in seen:
                    continue
                seen.add(word)
                out.append((group, word))
        return out


def load_keywords(path: Path) -> dict[str, list[str]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    groups = data.get("groups") or {}
    if not isinstance(groups, dict):
        raise ValueError(f"{path}: 'groups'는 그룹명 → 키워드 목록 형태여야 합니다.")
    cleaned: dict[str, list[str]] = {}
    for group, words in groups.items():
        cleaned[str(group)] = [str(w).strip() for w in (words or []) if str(w).strip()]
    return cleaned


def load_settings(env_file: Path | None = None, keywords_file: Path | None = None) -> Settings:
    _load_dotenv(env_file or PROJECT_ROOT / ".env")
    kw_file = keywords_file or Path(os.environ.get("NAVER_CARDNEWS_KEYWORDS", DEFAULT_KEYWORDS_FILE))
    return Settings(
        client_id=os.environ.get("NAVER_CLIENT_ID", ""),
        client_secret=os.environ.get("NAVER_CLIENT_SECRET", ""),
        db_path=Path(os.environ.get("NAVER_CARDNEWS_DB", PROJECT_ROOT / "data" / "news.db")),
        output_path=Path(os.environ.get("NAVER_CARDNEWS_OUT", PROJECT_ROOT / "data" / "review_queue.xlsx")),
        keywords_file=kw_file,
        per_keyword=int(os.environ.get("NAVER_CARDNEWS_PER_KEYWORD", "100")),
        max_age_days=int(os.environ.get("NAVER_CARDNEWS_MAX_AGE_DAYS", "3")),
        keyword_groups=load_keywords(kw_file),
    )
