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
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and value and key not in os.environ:
            os.environ[key] = value


@dataclass
class Settings:
    client_id: str
    client_secret: str
    db_path: Path
    output_path: Path
    keywords: list[str] = field(default_factory=list)
    topic_terms: list[str] = field(default_factory=list)    # 제목에 하나는 있어야 함 (비면 필터 끔)
    exclude_terms: list[str] = field(default_factory=list)  # 제목에 있으면 제외
    keywords_file: Path = DEFAULT_KEYWORDS_FILE
    per_keyword: int = 100          # 네이버 API display 최대 100
    max_age_days: int = 3           # 이보다 오래된 기사는 저장하지 않는다
    request_interval: float = 0.2
    # 3단계 근접 중복: 제목+요약 문자 2-gram Jaccard
    # 2026-10-21 실측(700건): 0.5는 "우리금융 34.7조" 같은 명백한 동일 사건(0.42~0.49)을 놓쳐 0.4로 조정.
    # 0.2~0.4에도 같은 사건이 섞여 있어(코스피 반등, 화성시 추진단) 경계 구간은 Haiku에 묻는다.
    sim_threshold: float = 0.4      # 이상이면 같은 사건
    sim_borderline: float = 0.2     # 이상~threshold 미만이면 Haiku 판정 (제목 단독 유사도도 봄)
    cluster_window_hours: int = 72
    # 4단계 기게시 비교 기간(일)
    posted_window_days: int = 14
    judge_enabled: bool = True          # 경계 구간 같은 사건 판정 (Haiku)
    niche_judge_enabled: bool = True    # 규칙 필터 통과 기사의 니치 적합 판정 (Haiku)
    anthropic_api_key: str = ""
    pexels_api_key: str = ""
    unsplash_access_key: str = ""
    images_dir: Path = PROJECT_ROOT / "data" / "images"
    sections: list[str] = field(default_factory=lambda: ["105"])   # 크롤링할 네이버 뉴스 섹션 (105=IT/과학). 비우면 끔
    draft_top: int = 10            # 수집 후 원고를 미리 만들 상위 건수


def _clean_list(words) -> list[str]:
    out: list[str] = []
    for w in words or []:
        w = str(w).strip()
        if w and w not in out:
            out.append(w)
    return out


def load_keyword_file(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_keywords(path: Path) -> list[str]:
    data = load_keyword_file(path)
    words = data.get("keywords")
    if isinstance(words, dict):  # 그룹 형태도 허용
        words = [w for group in words.values() for w in (group or [])]
    if not isinstance(words, list):
        raise ValueError(f"{path}: 'keywords'는 목록이어야 합니다.")
    return _clean_list(words)


def load_settings(env_file: Path | None = None, keywords_file: Path | None = None) -> Settings:
    _load_dotenv(env_file or PROJECT_ROOT / ".env")
    env = os.environ.get
    kw_file = keywords_file or Path(env("NAVER_CARDNEWS_KEYWORDS", DEFAULT_KEYWORDS_FILE))
    kw_data = load_keyword_file(kw_file)
    return Settings(
        client_id=env("NAVER_CLIENT_ID", ""),
        client_secret=env("NAVER_CLIENT_SECRET", ""),
        db_path=Path(env("NAVER_CARDNEWS_DB", PROJECT_ROOT / "data" / "news.db")),
        output_path=Path(env("NAVER_CARDNEWS_OUT", PROJECT_ROOT / "data" / "news_queue.xlsx")),
        keywords=load_keywords(kw_file),
        topic_terms=_clean_list(kw_data.get("topic_terms")),
        exclude_terms=_clean_list(kw_data.get("exclude_terms")),
        keywords_file=kw_file,
        per_keyword=int(env("NAVER_CARDNEWS_PER_KEYWORD", "100")),
        max_age_days=int(env("NAVER_CARDNEWS_MAX_AGE_DAYS", "3")),
        sim_threshold=float(env("NAVER_CARDNEWS_SIM_THRESHOLD", "0.4")),
        sim_borderline=float(env("NAVER_CARDNEWS_SIM_BORDERLINE", "0.2")),
        judge_enabled=env("NAVER_CARDNEWS_JUDGE", "on").lower() not in ("off", "0", "false", "no"),
        niche_judge_enabled=env("NAVER_CARDNEWS_NICHE_JUDGE", "on").lower() not in ("off", "0", "false", "no"),
        anthropic_api_key=env("ANTHROPIC_API_KEY", ""),
        pexels_api_key=env("PEXELS_API_KEY", ""),
        unsplash_access_key=env("UNSPLASH_ACCESS_KEY", ""),
        sections=[s for s in env("NAVER_CARDNEWS_SECTIONS", "105").split(",") if s.strip()],
        draft_top=int(env("NAVER_CARDNEWS_DRAFT_TOP", "10")),
    )
