"""무작위 구성: 색(팔레트) → 레이아웃 → 포맷(구성) 순서로 고르고, 사진은 고른 색과 어울리는 쪽에 가산점을 준다.

규칙 있는 무작위 (사용자 결정 2026-10-23):
- 직전 게시물과 같은 팔레트·레이아웃·포맷은 피한다(후보가 남아 있을 때).
- 최근 RECENT_PAIRS 개 안에 쓴 (팔레트, 레이아웃) 조합은 피한다.
- 기사에 안 맞는 조합은 뺀다: 포맷은 기사 본문 조건(수치 개수·찬반 어휘 등)을 통과해야 하고,
  사진 비중이 큰 레이아웃(fullbleed·split·band)은 사진 장이 2장 이상인 포맷에만 붙인다.
- 사람이 고친 원고는 포맷을 바꾸지 않는다(locked_format).
기록은 cardkit.store.Store 의 compositions 테이블. 같은 seed 면 같은 결과(테스트·재현용).
"""

from __future__ import annotations

import io
import random
import re
from dataclasses import dataclass, field

from . import palette as pal
from .formats import FORMATS, photo_slots

# 레이아웃: templates/layout_<name>.css. photo_heavy 는 사진이 화면 대부분을 차지하는 레이아웃
LAYOUTS: dict[str, dict] = {
    "frame":     {"name": "액자", "photo_heavy": False, "desc": "둥근 액자 사진 + 큰 번호 워터마크 (기본)"},
    "fullbleed": {"name": "풀블리드", "photo_heavy": True, "desc": "사진 전면 + 하단 딥 컬러 그라데이션 위 흰 글씨"},
    "split":     {"name": "매거진 분할", "photo_heavy": True, "desc": "위 절반 사진(모서리 없음) + 강조선 + 번호 배지"},
    "card":      {"name": "카드 스택", "photo_heavy": False, "desc": "옅은 퍼스널 컬러 바탕 위 종이 카드 한 장"},
    "band":      {"name": "사이드 밴드", "photo_heavy": True, "desc": "왼쪽 컬러 띠 + 오른쪽 세로 사진 + 큰 번호"},
    "type":      {"name": "타이포 우선", "photo_heavy": False, "desc": "원형 작은 사진, 글씨가 주도"},
}
DEFAULT_LAYOUT = "frame"
RECENT_PAIRS = 6
MIN_PHOTOS_FOR_HEAVY = 2

NUM_RE = re.compile(r"\d[\d,.]*\s?(?:%|퍼센트|원|달러|유로|엔|억|조|만|천|개|명|배|년|위|건|대|곳|GB|TB|MB|nm|W|㎡)")
TERM_RE = re.compile(r"[‘'\"“]([^’'\"”]{2,20})[’'\"”]|\b([A-Z][A-Za-z0-9]{2,}(?:\s[A-Z][A-Za-z0-9]+)?)\b")


def eligible_formats(body: str, allowed: list[str] | None = None) -> dict[str, str]:
    """원문으로 쓸 수 있는 포맷과 그 근거. 포맷 정의의 cues/min_numbers/terms/always 를 본다."""
    out: dict[str, str] = {}
    nums = len(NUM_RE.findall(body))
    terms = {(a or b).strip() for a, b in TERM_RE.findall(body)}
    for key in (allowed or list(FORMATS)):
        f = FORMATS[key]
        if f.get("always"):
            out[key] = "기본"
        elif f.get("min_numbers") and nums >= f["min_numbers"]:
            out[key] = f"수치 {nums}개"
        elif f.get("terms") and len(terms) >= f["terms"]:
            out[key] = f"용어 후보 {len(terms)}개"
        else:
            hit = [w for w in f.get("cues", ()) if w in body]
            if hit:
                out[key] = "단서: " + ", ".join(hit[:3])
    if not out:   # 계정 포맷 중 맞는 게 없으면 첫 포맷을 기본으로
        first = (allowed or list(FORMATS))[0]
        out[first] = "계정 기본 포맷"
    return out


@dataclass
class Composition:
    palette: str
    layout: str
    format: str
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"palette": self.palette, "layout": self.layout, "format": self.format, "reasons": self.reasons}


def _choose(rng: random.Random, options: list[str], avoid: set[str], what: str, reasons: list[str]) -> str:
    pool = [o for o in options if o not in avoid] or options
    pick = rng.choice(sorted(pool))
    dropped = sorted(set(options) - set(pool))
    reasons.append(f"{what}: {pick} (후보 {len(pool)}개" + (f", 제외 {','.join(dropped)}" if dropped else "") + ")")
    return pick


def compose(body: str, recent: list[dict] | None = None, locked_format: str | None = None,
            draft_format: str | None = None, seed: int | None = None, locked_why: str = "사람이 고친 원고",
            palettes: list[str] | None = None, layouts: list[str] | None = None,
            formats: list[str] | None = None) -> Composition:
    """색 → 레이아웃 → 포맷. recent 는 최근 구성(최신이 앞, dict 에 palette/layout/format).

    palettes/layouts/formats: 계정(profile)이 쓰는 목록. locked_format: 바꾸면 안 되는 포맷(사람이 고친 원고). draft_format: 이미 있는 AI 원고의 포맷 — 조건을 통과하고
    직전과 다르면 그대로 써서 원고를 다시 쓰는 비용을 아낀다.
    """
    rng = random.Random(seed)
    recent = recent or []
    last = recent[0] if recent else {}
    reasons: list[str] = []
    pairs = {(r["palette"], r["layout"]) for r in recent[:RECENT_PAIRS]}

    # 1) 색
    palette = _choose(rng, palettes or list(pal.ROTATION), {last.get("palette")} - {None}, "색", reasons)

    # 3) 포맷 후보를 먼저 계산해 둔다(레이아웃이 사진 장 수에 달려 있음)
    ok = eligible_formats(body, formats)
    if locked_format:
        fmt_pool = [locked_format]
        reasons.append(f"포맷 고정: {locked_format} ({locked_why})")
    elif draft_format and draft_format in ok and draft_format != last.get("format"):
        fmt_pool = [draft_format]
        reasons.append(f"포맷 재사용: {draft_format} (기존 원고, {ok[draft_format]})")
    else:
        fmt_pool = list(ok)

    # 2) 레이아웃: 직전과 다르고, 최근 (색, 레이아웃) 조합이 아니며, 사진형이면 사진 장이 충분한 포맷이 남아야 한다
    lay_opts = layouts or list(LAYOUTS)
    def lay_fits(lay: str) -> bool:
        if not LAYOUTS[lay]["photo_heavy"]:
            return True
        return any(photo_slots(f) >= MIN_PHOTOS_FOR_HEAVY for f in fmt_pool)
    fitting = [l for l in lay_opts if lay_fits(l)] or lay_opts
    avoid = {last.get("layout")} | {l for l in fitting if (palette, l) in pairs}
    layout = _choose(rng, fitting, avoid - {None}, "레이아웃", reasons)

    # 3) 포맷: 레이아웃에 맞고 직전과 다른 것
    fmt_fit = [f for f in fmt_pool if not LAYOUTS[layout]["photo_heavy"] or photo_slots(f) >= MIN_PHOTOS_FOR_HEAVY] or fmt_pool
    fmt = _choose(rng, fmt_fit, set() if len(fmt_pool) == 1 else {last.get("format")} - {None}, "포맷", reasons)
    if fmt in ok and not locked_format:
        reasons.append(f"포맷 근거: {ok[fmt]}")
    return Composition(palette, layout, fmt, reasons)


# ---------- 사진 톤: 고른 팔레트와 어울리는 사진에 가산점 ----------

def photo_tone(image_bytes: bytes) -> tuple[float, float, float]:
    """사진 평균색의 LCh (밝기 L, 채도 C, 색상각 h). 64px 로 줄여 평균."""
    from PIL import Image
    im = Image.open(io.BytesIO(image_bytes)).convert("RGB").resize((64, 64))
    data = im.tobytes()
    n = len(data) // 3
    r = sum(data[0::3]) / n
    g = sum(data[1::3]) / n
    b = sum(data[2::3]) / n
    return pal.lch("#%02X%02X%02X" % (round(r), round(g), round(b)))


def tone_harmony(image_bytes: bytes, palette: str, layout: str = DEFAULT_LAYOUT) -> float:
    """0~1. 무채색에 가까운 사진은 어떤 팔레트와도 맞는다(0.8). 유채색이면 퍼스널 컬러 색상각과 가까울수록(유사색)
    또는 정반대(보색, 150° 이상)일수록 높고, 어중간한 각도(95° 부근, 탁해 보이는 조합)는 낮다.
    풀블리드는 흰 글씨를 얹으므로 어두운 사진을, 그 외는 너무 어둡지 않은 사진을 조금 더 친다."""
    L, C, h = photo_tone(image_bytes)
    _, bc, bh = pal.lch(pal.PALETTES[palette]["brand"])
    if C < 12 or bc < 20:
        hue = 0.8
    else:
        d = abs(h - bh) % 360
        d = min(d, 360 - d)
        if d <= 40:
            hue = 1.0 - d / 200            # 유사색
        elif d >= 150:
            hue = 0.85                     # 보색
        else:
            hue = 0.3 + 0.3 * abs(d - 95) / 55   # 95° 부근(어중간한 각도)이 가장 낮다
    if layout == "fullbleed":
        light = 1.0 if L < 45 else max(0.2, 1 - (L - 45) / 50)
    else:
        light = 1.0 if L >= 25 else 0.6 + L / 62
    return round(0.7 * hue + 0.3 * light, 3)
