import re
from pathlib import Path

from naver_cardnews import palette

ROOT = Path(__file__).resolve().parent.parent


def test_default_palette_passes_every_check():
    bad = [r for r in palette.audit(palette.DEFAULT) if not r["ok"]]
    assert bad == [], bad


def test_previous_yellow_fails_as_documented():
    whats = {r["what"] for r in palette.audit("yellow_v21") if not r["ok"]}
    assert {"출처(24px)", "강조선·인용부호(비텍스트)", "기업 브랜드색과 색상각 차(°)"} <= whats


def test_card_css_root_matches_default_palette():
    css = (ROOT / "templates" / "card.css").read_text(encoding="utf-8")
    root = css[css.index(":root {"):css.index("}", css.index(":root {"))]
    p = palette.PALETTES[palette.DEFAULT]
    for role in palette.ROLES:
        m = re.search(re.escape(palette.CSS_NAME[role]) + r":\s*(#[0-9A-Fa-f]{6})", root)
        assert m and m.group(1).upper() == p[role].upper(), role
    assert "--hl" not in css and "--paper" not in css and "--dark" not in css   # 옛 토큰 잔재 없음


def test_contrast_and_hue_math():
    assert palette.contrast("#000000", "#FFFFFF") == 21.0
    assert palette.hue_gap("#FEE500", "#FFE566") < 2          # 이전 노랑 ≈ 카카오 노랑
    assert palette.hue_gap("#13698F", "#0064FF") >= 20
    assert palette.hue_gap("#777777", "#0064FF") == 180.0     # 무채색은 충돌 없음


def test_generated_palette_files(tmp_path):
    paths = palette.write_palette_css(tmp_path)
    assert len(paths) == len(palette.PALETTES)
    txt = (tmp_path / "palette_coral.css").read_text(encoding="utf-8")
    assert "--line: #D9482A;" in txt and "--brand: #FF6A45;" in txt
