"""계정(채널) 설정. YAML 한 파일로 계정마다 다른 것만 적는다 (예: profiles/psychology.yaml).

계정마다 달라지는 것(사용자 결정 2026-10-23): 색(팔레트 목록·전용 팔레트), 폰트, 레이아웃 목록, 포맷 목록.
그 밖의 브랜드 표기·말투·해시태그·면책 문구도 적을 수 있지만, 비워 두면 공통 기본값을 쓴다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import palette as pal
from .formats import FORMATS

LAYOUTS = ("frame", "fullbleed", "split", "card", "band", "type")
BODY_FONT = '"Pretendard", "Pretendard Variable", "Noto Sans CJK KR", "Noto Sans KR", "Apple SD Gothic Neo", sans-serif'
DISPLAY_FONT = '"BM JUA_OTF", "BM JUA_TTF", "BMJUA", "배달의민족 주아", "Jua", var(--font)'


@dataclass
class Profile:
    id: str = "default"
    name: str = "카드뉴스"                       # 계정 이름 (원고 작성·사진 심사 프롬프트에 들어간다)
    # 디자인 (계정별)
    palettes: list[str] = field(default_factory=lambda: list(pal.ROTATION))
    palettes_custom: dict[str, dict] = field(default_factory=dict)
    layouts: list[str] = field(default_factory=lambda: list(LAYOUTS))
    font_body: str = BODY_FONT
    font_display: str = DISPLAY_FONT
    font_mode: str = "mixed"                     # mixed(표지·마무리만 display) | all(제목·숫자까지) | none(display 안 씀)
    # 구성 (계정별)
    formats: list[str] = field(default_factory=lambda: list(FORMATS))
    # 공통 기본값이 있는 것
    label_top: str = "AI로 재가공한 콘텐츠"       # 좌상단 라벨
    handle: str = "@your_handle"
    source_kind: str = "기사"                     # 원문 종류: 기사 | 논문 | 보고서 …
    persona: str = "10년 차 에디터이자 인스타그램 카드뉴스 기획자"
    audience: str = "전문 지식이 없는 일반 독자"
    tone: str = "친근한 해요체('~해요/~인데요/~거든요'), stat·compare·quote 장은 간결체"
    hashtags_fixed: list[str] = field(default_factory=list)
    disclaimer: str = ""                         # 마무리 장 하단 작은 글씨 + 캡션 끝 (건강·심리·금융)
    cta: list[str] = field(default_factory=lambda: ["저장", "공유", "팔로우"])
    photo_style: str = "차분한 톤·여백·잡지 사진 느낌인가."
    avoid_colors: dict[str, str] = field(default_factory=lambda: dict(pal.COMPETITORS))
    store_path: str = "cardkit_data/store.db"

    def __post_init__(self):
        for name, spec in self.palettes_custom.items():
            pal.register(name, spec)
        bad = [p for p in self.palettes if p not in pal.PALETTES]
        if bad:
            raise ValueError(f"없는 팔레트: {bad} (가능: {', '.join(pal.PALETTES)})")
        bad = [l for l in self.layouts if l not in LAYOUTS]
        if bad:
            raise ValueError(f"없는 레이아웃: {bad} (가능: {', '.join(LAYOUTS)})")
        bad = [f for f in self.formats if f not in FORMATS]
        if bad:
            raise ValueError(f"없는 포맷: {bad} (가능: {', '.join(FORMATS)})")
        if self.font_mode not in ("mixed", "all", "none"):
            raise ValueError("font_mode 는 mixed | all | none")
        if not self.palettes or not self.layouts or not self.formats:
            raise ValueError("palettes·layouts·formats 는 하나 이상")

    def audit_palettes(self) -> dict[str, list[str]]:
        """계정 팔레트 중 대비·눈 편안함·피할 색 검사에 걸린 항목 (비어 있으면 통과)."""
        out = {}
        for p in self.palettes:
            bad = [r["what"] for r in pal.audit(p, self.avoid_colors) if not r["ok"]]
            if bad:
                out[p] = bad
        return out


def load(path: str | Path) -> Profile:
    import yaml
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    fonts = data.pop("fonts", {}) or {}
    for k_src, k_dst in (("body", "font_body"), ("display", "font_display"), ("mode", "font_mode")):
        if k_src in fonts:
            data[k_dst] = fonts[k_src]
    known = set(Profile.__dataclass_fields__)
    extra = set(data) - known
    if extra:
        raise ValueError(f"알 수 없는 설정: {sorted(extra)}")
    return Profile(**data)
