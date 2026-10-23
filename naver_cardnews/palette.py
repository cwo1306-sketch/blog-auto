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
    # ---- 순환 사용(rotation) 템플릿: 모두 대비·눈 편안함·기업 색 회피 검사를 통과해야 한다 ----
    "ocean": {"name": "오션", "rotation": True, "mode": "light",
              "why": "차분한 딥 시안 + 복숭아빛 형광펜. 신뢰감 있는 기본 톤.",
              "bg": "#F6F5F1", "bg2": "#EAE8E2", "ink": "#1C2A33", "ink2": "#46545E", "muted": "#66727B",
              "brand": "#13698F", "on_brand": "#FFFFFF", "line": "#13698F",
              "deep": "#0E2C3C", "on_deep": "#F6F5F1", "pop": "#8ED3F2", "mark": "#F8D3C6"},
    "clay": {"name": "클레이", "rotation": True, "mode": "light",
             "why": "흙빛 테라코타 + 옅은 하늘 형광펜(보색). 따뜻하고 부드러운 생활·서비스 소식에 맞다.",
             "bg": "#F7F3EE", "bg2": "#ECE4DA", "ink": "#2E2420", "ink2": "#584A43", "muted": "#76665E",
             "brand": "#A0563B", "on_brand": "#FFFFFF", "line": "#A0563B",
             "deep": "#3A2620", "on_deep": "#F7F3EE", "pop": "#F0B89E", "mark": "#D3E3EE"},
    "sage": {"name": "세이지", "rotation": True, "mode": "light",
             "why": "채도를 뺀 세이지 그린 + 라일락 형광펜. 가장 눈이 편한 저채도 조합, 정책·연구 기사에 맞다.",
             "bg": "#F3F5F0", "bg2": "#E4E9E1", "ink": "#22302A", "ink2": "#495A52", "muted": "#5E6C64",
             "brand": "#4C6D60", "on_brand": "#FFFFFF", "line": "#4C6D60",
             "deep": "#1F332B", "on_deep": "#F3F5F0", "pop": "#A9D4C0", "mark": "#E2DAF0"},
    "plum": {"name": "플럼", "rotation": True, "mode": "light",
             "why": "먼지 낀 자두색 + 옅은 민트 형광펜. 사람·사회 영향 기사에 부드럽게 어울린다.",
             "bg": "#F7F3F4", "bg2": "#EDE5E8", "ink": "#2C2228", "ink2": "#584852", "muted": "#76656F",
             "brand": "#8A4E6A", "on_brand": "#FFFFFF", "line": "#8A4E6A",
             "deep": "#33202A", "on_deep": "#F7F3F4", "pop": "#EFB6CC", "mark": "#D6EADD"},
    "mono": {"name": "뉴스프린트", "rotation": True, "mode": "light",
             "why": "신문지 회백색 + 차콜, 모래빛 형광펜. 색을 거의 쓰지 않아 숫자·사실 중심 기사에 맞다.",
             "bg": "#F4F2EE", "bg2": "#E6E3DD", "ink": "#232323", "ink2": "#4C4C4C", "muted": "#6D6D6D",
             "brand": "#343A44", "on_brand": "#F4F2EE", "line": "#343A44",
             "deep": "#2A2E35", "on_deep": "#F4F2EE", "pop": "#E8D2B6", "mark": "#E2D6C6"},
    "slate": {"name": "슬레이트(다크)", "rotation": True, "mode": "dark",
              "why": "어두운 청회색 바탕 + 순백이 아닌 미색 글씨. 밤 시간대 피드에서 눈부심이 가장 적다.",
              "bg": "#1D232B", "bg2": "#29313B", "ink": "#E6E2DA", "ink2": "#C2BFB7", "muted": "#9B9B97",
              "brand": "#7CAFD3", "on_brand": "#132029", "line": "#7CAFD3",
              "deep": "#12171D", "on_deep": "#E6E2DA", "pop": "#9DCDEB", "mark": "#3A5165"},
    # ---- 참고용(순환 제외) ----
    "violet": {"name": "바이올렛 (참고)", "rotation": False, "mode": "light",
               "why": "AI 연상 최강이지만 토스 파랑과 색상각 15.6°.",
               "bg": "#F6F5F2", "bg2": "#EBE8E3", "ink": "#211C30", "ink2": "#4D4760", "muted": "#6C677B",
               "brand": "#7A3CE0", "on_brand": "#FFFFFF", "line": "#7A3CE0",
               "deep": "#21173F", "on_deep": "#F6F5F2", "pop": "#C9B6FF", "mark": "#E7DDFF"},
    "coral": {"name": "코랄 (참고)", "rotation": False, "mode": "light",
              "why": "눈에 띄지만 채도가 높아 마무리 전면 배경으로는 눈이 피로하다.",
              "bg": "#F8F5F1", "bg2": "#EFE9E2", "ink": "#2B2320", "ink2": "#5A4F4A", "muted": "#776B65",
              "brand": "#FF6A45", "on_brand": "#241310", "line": "#D9482A",
              "deep": "#33201A", "on_deep": "#F8F5F1", "pop": "#FFA48A", "mark": "#FFDCD0"},
    "yellow_v21": {"name": "노랑 (이전 v2.1)", "rotation": False, "mode": "light",
                   "why": "직전 팔레트. 출처 대비 2.98:1, 강조선 1.17:1, 카카오 노랑과 색상각 0.9°.",
                   "bg": "#F8F6F1", "bg2": "#EEEAE2", "ink": "#2A2926", "ink2": "#5E5B55", "muted": "#948F86",
                   "brand": "#FFE566", "on_brand": "#2A2926", "line": "#FFE566",
                   "deep": "#35332F", "on_deep": "#F8F6F1", "pop": "#FFEF8A", "mark": "#FFEF8A"},
}
ROTATION = [k for k, v in PALETTES.items() if v.get("rotation")]
DEFAULT = "ocean"


def pick_rotation(made: int, override: str = "") -> str:
    """돌려 쓰기: 지금까지 만든 카드 수(made)로 순번을 정해 피드에서 같은 색이 연달아 나오지 않게 한다.
    override(CARDNEWS_PALETTE)가 있으면 그대로 쓴다."""
    override = (override or "").strip()
    if override:
        if override not in PALETTES:
            raise ValueError(f"알 수 없는 팔레트: {override} (가능: {', '.join(PALETTES)})")
        return override
    return ROTATION[made % len(ROTATION)]

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


# 눈 편안함 기준 (가독성 하한 + 눈부심·피로 상한)
COMFORT = {
    "ink_max": 16.0,          # 제목 대비 상한: 순백·순흑(21:1)은 눈부심(헐레이션)
    "bg_chroma_max": 8.0,     # 배경 채도 상한 (LCh C): 넓은 면적은 거의 무채색
    "light_bg_L": (91.0, 97.5),
    "dark_bg_L": (10.0, 22.0),
    "brand_chroma_max": 50.0, # 마무리 장 전면 배경 채도 상한
    "mark_chroma_max": 30.0,  # 형광펜은 부드럽게
    "mark_visible_de": 8.0,   # 형광펜이 배경과 구분되는 최소 색차(ΔE)
    "yellow_hue": (80.0, 105.0),   # 형광펜 노랑 계열 제외 (사용자 요청)
}


def audit(name: str) -> list[dict]:
    p = PALETTES[name]
    out = []
    c = COMFORT
    L_bg, C_bg, _ = lch(p["bg"])
    lo, hi = c["dark_bg_L"] if p.get("mode") == "dark" else c["light_bg_L"]
    r = contrast(p["ink"], p["bg"])
    out.append({"pair": "ink/bg", "what": "눈부심 상한(제목 대비 ≤16)", "ratio": r, "need": c["ink_max"], "ok": r <= c["ink_max"]})
    out.append({"pair": "bg", "what": "배경 채도(LCh C ≤8)", "ratio": C_bg, "need": c["bg_chroma_max"], "ok": C_bg <= c["bg_chroma_max"]})
    out.append({"pair": "bg", "what": f"배경 밝기 L {lo}~{hi}", "ratio": L_bg, "need": lo, "ok": lo <= L_bg <= hi})
    Cb = lch(p["brand"])[1]
    out.append({"pair": "brand", "what": "마무리 전면 배경 채도(≤50)", "ratio": Cb, "need": c["brand_chroma_max"], "ok": Cb <= c["brand_chroma_max"]})
    Lm, Cm, Hm = lch(p["mark"])
    out.append({"pair": "mark", "what": "형광펜 채도(≤30)", "ratio": Cm, "need": c["mark_chroma_max"], "ok": Cm <= c["mark_chroma_max"]})
    de = delta_e(p["mark"], p["bg"])
    out.append({"pair": "mark/bg", "what": "형광펜이 배경과 구분(ΔE ≥8)", "ratio": de, "need": c["mark_visible_de"], "ok": de >= c["mark_visible_de"]})
    ylo, yhi = c["yellow_hue"]
    is_yellow = Cm >= 15 and ylo <= Hm <= yhi
    out.append({"pair": "mark", "what": "형광펜 노랑 계열 아님", "ratio": Hm, "need": ylo, "ok": not is_yellow})
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
