"""카드뉴스 색 체계: 역할(role) 토큰 + WCAG 대비 검증 + CSS 생성.

원칙
- 60·30·10: 배경 중립(bg) 60% · 잉크(ink) 30% · 퍼스널 컬러(brand) 10%. 브랜드색은 '어디에나'가 아니라 정해진 자리에만.
- 한 색상(hue)에서 파생: brand(서명색) · deep(숫자·비교 카드 배경) · mark(형광펜) · pop(어두운 배경 위 숫자)을 같은 계열로 만들어
  계정 그리드가 한 브랜드로 읽히게 한다.
- 대비는 수치로 검증: 본문 글씨 4.5:1(WCAG 2.x AA), 큰 글씨·비텍스트 요소 3:1(1.4.3 / 1.4.11). 이 기준을 못 넘는 팔레트는 쓰지 않는다.
- 다루는 기업의 브랜드색과 겹치지 않게: 카카오 #FEE500, 네이버 #03C75A, 배민 #2AC1BC, 토스 #0064FF 와 색차(ΔE)가 충분해야 한다.
"""

from __future__ import annotations

ROLES = ("bg", "bg2", "ink", "ink2", "muted", "brand", "on_brand", "line", "deep", "on_deep", "pop", "mark")
CSS_NAME = {"bg": "--bg", "bg2": "--bg-2", "ink": "--ink", "ink2": "--ink-2", "muted": "--muted", "brand": "--brand",
            "on_brand": "--on-brand", "line": "--line", "deep": "--deep", "on_deep": "--on-deep", "pop": "--pop", "mark": "--mark"}
ROLE_KO = {"bg": "배경(종이)", "bg2": "보조 배경(카드·사진 틀)", "ink": "글씨(제목)", "ink2": "글씨(본문)", "muted": "출처·보조 글씨",
           "brand": "퍼스널 컬러(마무리 배경·강조선·인용부호)", "on_brand": "퍼스널 컬러 위 글씨", "line": "밝은 배경 위 강조선·인용부호·번호 밑줄", "deep": "숫자·비교 카드 배경",
           "on_deep": "어두운 배경 위 글씨", "pop": "어두운 배경 위 큰 숫자", "mark": "형광펜(강조 줄 배경)"}

PALETTES: dict[str, dict] = {
    "ocean": {
        "name": "오션 블루 + 살구 (추천)",
        "why": "차분한 딥 시안은 뉴스의 신뢰감, 보색인 살구 형광펜은 '쉬운 말' 계정의 친근함을 맡는다. 다루는 기업 브랜드색(카카오 노랑·"
               "네이버 초록·배민 민트·토스 파랑) 모두와 색상각 30° 이상 떨어져 있다. 웜톤 종이·사진과 쿨톤 브랜드가 대비를 이룬다.",
        "bg": "#F6F5F1", "bg2": "#EAE8E2", "ink": "#1C2A33", "ink2": "#46545E", "muted": "#66727B",
        "brand": "#13698F", "on_brand": "#FFFFFF", "line": "#13698F",
        "deep": "#0E2C3C", "on_deep": "#F6F5F1", "pop": "#8ED3F2", "mark": "#FFD9A8",
    },
    "violet": {
        "name": "바이올렛 (참고)",
        "why": "AI 제품들이 많이 쓰는 보라라 'AI 뉴스' 연상이 가장 강하다. 다만 토스 파랑과 색상각 15.6°로 기준(20°) 미달이고, 흔한 'AI 보라'라 개성이 약하다.",
        "bg": "#F6F5F2", "bg2": "#EBE8E3", "ink": "#211C30", "ink2": "#4D4760", "muted": "#6C677B",
        "brand": "#7A3CE0", "on_brand": "#FFFFFF", "line": "#7A3CE0",
        "deep": "#21173F", "on_deep": "#F6F5F2", "pop": "#C9B6FF", "mark": "#E7DDFF",
    },
    "coral": {
        "name": "코랄",
        "why": "따뜻하고 활기찬 주황빨강. 피드에서 가장 눈에 띄지만 '속보·경고' 느낌이 섞이고, 밝은 배경 위 강조선은 더 진한 색으로 분리해야 한다.",
        "bg": "#F8F5F1", "bg2": "#EFE9E2", "ink": "#2B2320", "ink2": "#5A4F4A", "muted": "#776B65",
        "brand": "#FF6A45", "on_brand": "#241310", "line": "#D9482A",
        "deep": "#33201A", "on_deep": "#F8F5F1", "pop": "#FFA48A", "mark": "#FFDCD0",
    },
    "lime": {
        "name": "라임",
        "why": "테크 브랜드에서 유행하는 형광 연두. 흰 글씨를 못 얹어 마무리 장 글씨가 어두워야 하고, 강조선은 올리브로 분리해야 한다.",
        "bg": "#F5F6F0", "bg2": "#E9ECDF", "ink": "#1F231A", "ink2": "#4C5243", "muted": "#6A7060",
        "brand": "#C3EC3A", "on_brand": "#1A1F10", "line": "#557000",
        "deep": "#1F2716", "on_deep": "#F5F6F0", "pop": "#D4FA4E", "mark": "#E6F7A6",
    },
    "yellow_v21": {   # 비교용: 직전 v2.1
        "name": "노랑 (이전 v2.1)",
        "why": "직전 팔레트. 출처 글씨 대비 2.98:1, 강조선 대비 1.17:1, 마무리 노랑이 카카오 노랑과 색상각 0.9°.",
        "bg": "#F8F6F1", "bg2": "#EEEAE2", "ink": "#2A2926", "ink2": "#5E5B55", "muted": "#948F86",
        "brand": "#FFE566", "on_brand": "#2A2926", "line": "#FFE566",
        "deep": "#35332F", "on_deep": "#F8F6F1", "pop": "#FFEF8A", "mark": "#FFEF8A",
    },
}
DEFAULT = "ocean"

# (전경, 배경, 최소 대비, 설명)
CHECKS = [
    ("ink", "bg", 7.0, "제목 글씨"), ("ink2", "bg", 4.5, "본문 글씨"), ("ink2", "bg2", 4.5, "답 카드 본문"),
    ("muted", "bg", 4.5, "출처(24px)"), ("ink", "mark", 4.5, "형광펜 위 제목"), ("on_brand", "brand", 4.5, "마무리 장 글씨"),
    ("on_deep", "deep", 7.0, "숫자 카드 라벨"), ("pop", "deep", 4.5, "숫자 카드 큰 숫자"), ("line", "bg", 3.0, "강조선·인용부호(비텍스트)"),
]
MIN_HUE_GAP = 20.0   # 다루는 기업 브랜드색과 색상각(LCh hue)이 이보다 가까우면 같은 색 계열로 연상된다
COMPETITORS = {"카카오": "#FEE500", "네이버": "#03C75A", "배민": "#2AC1BC", "토스": "#0064FF"}


def _rgb(h: str) -> tuple[float, float, float]:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def luminance(h: str) -> float:
    def ch(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = _rgb(h)
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return round((la + 0.05) / (lb + 0.05), 2)


def _lab(h: str) -> tuple[float, float, float]:
    def lin(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(c) for c in _rgb(h))
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883
    f = lambda t: t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116  # noqa: E731
    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def delta_e(a: str, b: str) -> float:
    """CIE76 색차. 10 미만이면 '거의 같은 색'으로 인식된다."""
    la, lb = _lab(a), _lab(b)
    return round(sum((x - y) ** 2 for x, y in zip(la, lb)) ** 0.5, 1)


def audit(name: str) -> list[dict]:
    p = PALETTES[name]
    out = []
    for fg, bg, need, what in CHECKS:
        if not need:
            continue
        r = contrast(p[fg], p[bg])
        out.append({"pair": f"{fg}/{bg}", "what": what, "ratio": r, "need": need, "ok": r >= need})
    for comp, hexv in COMPETITORS.items():
        d = hue_gap(p["brand"], hexv)
        out.append({"pair": f"brand vs {comp}", "what": "기업 브랜드색과 색상각 차(°)", "ratio": d, "need": MIN_HUE_GAP, "ok": d >= MIN_HUE_GAP})
    return out


def lch(h: str) -> tuple[float, float, float]:
    import math
    L, a, b = _lab(h)
    return round(L, 1), round(math.hypot(a, b), 1), round(math.degrees(math.atan2(b, a)) % 360, 1)


def hue_gap(a: str, b: str) -> float:
    """두 색의 LCh 색상각 차(0~180°). 한쪽이라도 채도가 낮으면(무채색) 180 으로 본다."""
    _, ca, ha = lch(a)
    _, cb, hb = lch(b)
    if ca < 20 or cb < 20:
        return 180.0
    d = abs(ha - hb) % 360
    return round(min(d, 360 - d), 1)


def css_vars(name: str) -> str:
    p = PALETTES[name]
    lines = [f"  {CSS_NAME[r]}: {p[r]};   /* {ROLE_KO[r]} */" for r in ROLES]
    return ":root {\n" + "\n".join(lines) + "\n}\n"


def write_palette_css(dirpath) -> list[str]:
    """templates/palette_<name>.css 생성 (CARDNEWS_PALETTE=<name> 으로 덧씌운다)."""
    from pathlib import Path
    paths = []
    for name in PALETTES:
        path = Path(dirpath) / f"palette_{name}.css"
        path.write_text(f"/* 자동 생성: naver_cardnews/palette.py — {PALETTES[name]['name']} */\n" + css_vars(name), encoding="utf-8")
        paths.append(str(path))
    return paths
