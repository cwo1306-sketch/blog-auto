import io
from pathlib import Path

from PIL import Image

from naver_cardnews import compose as c
from naver_cardnews import palette as pal
from naver_cardnews.db import Database
from naver_cardnews.stock import Candidate
from naver_cardnews.vision_pick import VisionScore, pick

ROOT = Path(__file__).resolve().parents[1]
BODY = ("삼성전자는 3분기 매출 79조원, 영업이익 10조원을 기록했다. 점유율은 30%, 직원은 12만명이다. "
        "전문가들은 우려를 나타냈다. ‘HBM’ ‘CXL’ ‘PIM’ 같은 용어가 쏟아진다. 평택 공장 현장에서 시연했다.")


def solid(hex_color, size=(64, 64)):
    im = Image.new("RGB", size, hex_color)
    buf = io.BytesIO(); im.save(buf, "PNG"); return buf.getvalue()


def test_eligible_formats_from_body():
    ok = c.eligible_formats(BODY)
    assert {"explainer", "numbers", "debate", "glossary", "scene"} <= set(ok)
    assert c.eligible_formats("짧은 소식이다.") == {"explainer": "기본"}


def test_layout_files_exist_and_photo_slots():
    for name in c.LAYOUTS:
        assert (ROOT / "templates" / f"layout_{name}.css").exists(), name
    assert c.photo_slots("qa") == 0 and c.photo_slots("scene") >= 4
    assert "--overlay: 1" in (ROOT / "templates" / "layout_fullbleed.css").read_text(encoding="utf-8")


def test_compose_avoids_repeats_and_is_reproducible():
    recent = []
    for i in range(12):
        comp = c.compose(BODY, recent, seed=i)
        if recent:
            last = recent[0]
            assert comp.palette != last["palette"] and comp.layout != last["layout"] and comp.format != last["format"]
        pairs = {(r["palette"], r["layout"]) for r in recent[:c.RECENT_PAIRS]}
        assert (comp.palette, comp.layout) not in pairs
        assert comp.palette in pal.ROTATION and comp.layout in c.LAYOUTS
        recent.insert(0, comp.to_dict())
    assert c.compose(BODY, [], seed=7).to_dict() == c.compose(BODY, [], seed=7).to_dict()


def test_photo_heavy_layout_needs_photo_format():
    for seed in range(20):
        comp = c.compose(BODY, [], locked_format="qa", seed=seed)   # qa 는 사진 장이 없다
        assert comp.format == "qa" and not c.LAYOUTS[comp.layout]["photo_heavy"]


def test_draft_format_reused_unless_repeat_or_ineligible():
    comp = c.compose(BODY, [], draft_format="numbers", seed=1)
    assert comp.format == "numbers" and any("재사용" in r for r in comp.reasons)
    last = {"palette": "ocean", "layout": "frame", "format": "numbers"}
    assert c.compose(BODY, [last], draft_format="numbers", seed=1).format != "numbers"
    assert c.compose("짧은 소식이다.", [], draft_format="numbers", seed=1).format == "explainer"


def test_fixed_palette_and_layout():
    comp = c.compose(BODY, [], palettes=["sage"], layouts=["card"], seed=3)
    assert (comp.palette, comp.layout) == ("sage", "card")


def test_tone_harmony_prefers_neutral_or_analogous_and_dark_for_fullbleed():
    brand = pal.PALETTES["ocean"]["brand"]                      # 청록 계열
    assert c.tone_harmony(solid("#808080"), "ocean") > c.tone_harmony(solid("#2E8B57"), "ocean")   # 무채 > 어중간한 각도(약 97°)의 녹색
    assert c.tone_harmony(solid(brand), "ocean") > c.tone_harmony(solid("#2E8B57"), "ocean")
    assert c.tone_harmony(solid("#1A2630"), "ocean", "fullbleed") > c.tone_harmony(solid("#E8EEF2"), "ocean", "fullbleed")


def test_pick_bonus_breaks_ties_but_not_threshold():
    a = Candidate("pexels", "a", "t", "f", 1000, 1500, image_bytes=solid("#111111"))
    b = Candidate("pexels", "b", "t", "f", 1000, 1500, image_bytes=solid("#EEEEEE"))
    weak = Candidate("pexels", "w", "t", "f", 1000, 1500, image_bytes=solid("#777777"))

    class Scorer:
        def score(self, img, headline, concept):
            if img == weak.image_bytes:
                return VisionScore(relevance=2, lower_third_clear=2, style_match=2)
            return VisionScore(relevance=4, lower_third_clear=4, style_match=4)

    assert pick([a, b], "h", "c", Scorer(), None).chosen is a            # 동점이면 먼저 본 후보
    r = pick([a, b], "h", "c", Scorer(), None, bonus=lambda img: 1.0 if img == b.image_bytes else 0.0)
    assert r.chosen is b and r.to_dict()["candidates"][1]["tone"] == 1.0
    assert pick([weak], "h", "c", Scorer(), None, bonus=lambda img: 1.0).chosen is None   # 톤이 좋아도 합격선 미달


def test_db_compositions_roundtrip():
    db = Database(":memory:")
    db.record_composition("001_1", "ocean", "frame", "debate", "r1")
    db.record_composition("001_2", "clay", "split", "scene", "r2")
    rows = [dict(r) for r in db.recent_compositions(5)]
    assert [r["palette"] for r in rows] == ["clay", "ocean"]
    comp = c.compose(BODY, rows, seed=0)
    assert comp.palette != "clay" and comp.layout != "split"
