import copy
import os
from pathlib import Path

import pytest

from cardkit import compose, formats, palette, profile, render, samples, validate, writer
from cardkit.store import Store

ROOT = Path(__file__).resolve().parents[1]
PSY = ROOT / "cardkit" / "profiles" / "psychology.yaml"
NEWS = ROOT / "cardkit" / "profiles" / "ai_news.yaml"


def test_cardkit_is_independent_of_news_pipeline():
    for f in (ROOT / "cardkit").glob("*.py"):
        text = f.read_text(encoding="utf-8")
        assert "naver_cardnews" not in text.replace("blog-auto", "") or f.name == "__init__.py", f.name


def test_profiles_load_and_palettes_pass_audit():
    for path in (PSY, NEWS):
        p = profile.load(path)
        assert p.audit_palettes() == {}, (path.name, p.audit_palettes())
    psy = profile.load(PSY)
    assert "lavender" in palette.PALETTES and psy.hashtags_fixed[0] == "#심리학" and psy.disclaimer


def test_profile_rejects_unknown_values(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("palettes: [nope]\n", encoding="utf-8")
    with pytest.raises(ValueError, match="팔레트"):
        profile.load(bad)
    bad.write_text("formats: [explainer]\nunknown_key: 1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="알 수 없는"):
        profile.load(bad)


def test_every_format_has_valid_slides():
    for key, f in formats.FORMATS.items():
        for slot in f["slides"]:
            assert all(t in formats.SLIDE_TYPES for t in slot.split("|")), (key, slot)


def test_compose_respects_profile_lists_and_rules():
    p = profile.load(PSY)
    recent = []
    for i in range(10):
        c = compose.compose(samples.SOURCE["body"], recent, seed=i, palettes=p.palettes, layouts=p.layouts, formats=p.formats)
        assert c.palette in p.palettes and c.layout in p.layouts and c.format in p.formats
        if recent:
            assert (c.palette, c.layout, c.format) != (recent[0]["palette"], recent[0]["layout"], recent[0]["format"])
            assert c.palette != recent[0]["palette"] and c.layout != recent[0]["layout"]
        recent.insert(0, c.to_dict())
    ok = compose.eligible_formats(samples.SOURCE["body"], p.formats)
    assert "study" in ok and "myth" in ok and "checklist" in ok


def test_samples_pass_validation_for_psychology_profile():
    p = profile.load(PSY)
    for fmt, script in samples.SCRIPTS.items():
        errs = validate.check(copy.deepcopy(script), samples.SOURCE["body"], p.formats, p.hashtags_fixed)
        assert errs == [], (fmt, errs)


def test_validate_catches_myth_and_checklist_problems_and_fixed_tags():
    p = profile.load(PSY)
    s = copy.deepcopy(samples.SCRIPTS["checklist"])
    s["slides"][1]["items"] = ["하나", "둘"]                        # 3개 미만
    s["hashtags"] = ["#a"] * 8                                     # 고정 태그 없음
    errs = validate.check(s, samples.SOURCE["body"], p.formats, p.hashtags_fixed)
    assert any("checklist 항목 2개" in e for e in errs) and any("고정 태그" in e for e in errs)
    s = copy.deepcopy(samples.SCRIPTS["myth"])
    s["slides"][3]["body"] = "참가자의 90%가 효과를 봤다고 답했어요. 그러니 어색해도 꼭 해 보세요. 연구가 증명했어요."
    errs = validate.check(s, samples.SOURCE["body"], p.formats, p.hashtags_fixed)
    assert any("90" in e for e in errs)


def test_caption_source_year_not_checked():
    p = profile.load(PSY)
    s = copy.deepcopy(samples.SCRIPTS["traits"])
    s["caption"] = s["caption"].replace("출처: 예시 연구 (가상) · 2026", "출처: Kim et al. (2024), Psychological Science 35(2)")
    assert validate.check(s, samples.SOURCE["body"], p.formats, p.hashtags_fixed) == []


def test_writer_prompt_uses_profile():
    p = profile.load(PSY)
    sp = writer.system_prompt(p, samples.SOURCE, "study")
    assert "논문으로 읽는 마음" in sp and "#심리학" in sp and p.disclaimer in sp and "연구 요약형" in sp
    assert "AI 뉴스" not in sp
    script = writer.normalize_script({"format": "myth", "cover": {"lines": []}, "outro": {},
                                      "slides": [{"slide_type": "myth"}, {"slide_type": "checklist"}, {"slide_type": "x"},
                                                 {"slide_type": "chart"}, {}]})
    assert [s["slide_type"] for s in script["slides"]] == ["myth", "photo", "photo", "photo", "photo"]


def test_build_pages_injects_profile_and_palette():
    p = profile.load(PSY)
    sc = samples.SCRIPTS["study"]
    pages = render.build_pages(sc, [None] * 7, "출처: 예시", p, "lavender", "card")
    assert "논문을 쉽게 풀었어요" in pages[0] and "--brand: #7B5B8A" in pages[0] and "layout_card.css" in pages[0]
    assert "file://" in pages[0]                                   # 절대 경로라 출력 폴더 위치와 무관
    assert p.disclaimer in pages[-1] and '<body class="chart">' in pages[3]
    myth = render.build_pages(samples.SCRIPTS["myth"], [None] * 6, "출처: 예시", p, "sage", "frame")
    assert '<body class="myth">' in myth[2] and "tag-fact" in myth[2]


def test_store_roundtrip():
    st = Store()
    st.record_composition("a", "sage", "card", "study")
    assert st.recent_compositions()[0]["layout"] == "card"
    st.record_image("a", 1, "pexels", "9", "q", "00ff00ff00ff00ff")
    assert st.image_used("pexels", "9") and st.similar_image("00ff00ff00ff00ff") is not None


def test_preview_renders(tmp_path):
    if not os.environ.get("CHROMIUM_PATH"):
        pytest.skip("Chromium 없음")
    from cardkit.__main__ import main
    assert main(["preview", "--profile", str(PSY), "--out", str(tmp_path)]) == 0
    assert len(list(tmp_path.glob("*/card_*.jpg"))) >= 28
