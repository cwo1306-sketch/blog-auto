import json
import os
import sys
from pathlib import Path

import pytest

from naver_cardnews import sheet, validate
from naver_cardnews.chart import Chart, ChartError, draw_script, validate_chart
from naver_cardnews.formats import SLIDE_TYPES

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cardnews"))
import render  # noqa: E402

BODY = ("국내 라이브 커머스 방송 시장 규모는 지난 2021년 2.8조 원에서 2022년 6.2조 원, 2023년 10조 원을 기록했다. "
        "점유율은 A사 52%, B사 31%, 기타 17%로 집계됐다. 매출은 100억 원이다.")
BAR = {"type": "bar", "unit": "조 원", "labels": ["2021", "2022", "2023"], "values": ["2.8", "6.2", "10"],
       "source_quote": "2021년 2.8조 원에서 2022년 6.2조 원, 2023년 10조 원을 기록했다"}


def test_valid_bar_and_donut():
    validate_chart(Chart.from_dict(BAR), BODY)
    donut = {"type": "donut", "unit": "%", "labels": ["A사", "B사", "기타"], "values": ["52", "31", "17"],
             "source_quote": "점유율은 A사 52%, B사 31%, 기타 17%로 집계됐다"}
    validate_chart(Chart.from_dict(donut), BODY)
    assert Chart.from_dict(donut).highlight_index() == 0          # 도넛은 최댓값
    assert Chart.from_dict(BAR).highlight_index() == 2            # 막대는 마지막


@pytest.mark.parametrize("patch, msg", [
    ({"type": "pie"}, "type"),
    ({"values": ["2.8"], "labels": ["2021"]}, "값 2~6개"),
    ({"labels": ["2021", "2022"]}, "labels"),
    ({"labels": ["2021년 상반기 매출", "2022", "2023"]}, "라벨"),
    ({"unit": ""}, "단위"),
    ({"values": ["2.8", "6.2", "10.123"]}, "숫자만"),
    ({"values": ["2.8", "6.2", "11"]}, "source_quote 안에"),          # 원문에 없는 값
    ({"values": ["2.8", "6.2", "1"]}, "source_quote 안에"),           # '10' 안의 '1' 은 인정하지 않는다
    ({"source_quote": "2021년 2.8조 원, 2022년 6.2조 원, 2023년 10조 원"}, "원문에 없다"),
])
def test_invalid_charts(patch, msg):
    with pytest.raises(ChartError, match=msg):
        validate_chart(Chart.from_dict({**BAR, **patch}), BODY)


def test_donut_needs_percent_and_sum():
    bad = {"type": "donut", "unit": "%", "labels": ["A사", "B사"], "values": ["52", "31"],
           "source_quote": "점유율은 A사 52%, B사 31%, 기타 17%로 집계됐다"}
    with pytest.raises(ChartError, match="합"):
        validate_chart(Chart.from_dict(bad), BODY)


def test_slide_type_registered_and_draw_script():
    assert "chart" in SLIDE_TYPES
    js = draw_script(Chart.from_dict(BAR))
    assert "__chartDone" in js and '"values": ["2.8", "6.2", "10"]' in js and "__DATA__" not in js


def test_sheet_roundtrip_keeps_chart():
    script = {"format": "numbers", "cover": {"lines": [{"text": "숫자로", "highlight": True}], "image_queries": [], "image_concept": ""},
              "slides": [{"slide_type": "chart", "title": "3년 새 3.6배", "body": "", "evidence": [],
                          "chart": {**BAR, "highlight": 1}, "image_queries": [], "image_concept": ""}],
              "outro": {"summary": "s", "question": "q"}, "caption": "c", "hashtags": ["#AI"]}
    row = sheet.flatten(script)
    assert row["2장 유형"] == "chart:bar" and row["2장 수치"] == "2.8 ; *6.2 ; 10" and row["2장 라벨"] == "2021 ; 2022 ; 2023"
    back = sheet.unflatten(row)["slides"][0]
    assert back["slide_type"] == "chart"
    assert back["chart"]["values"] == BAR["values"] and back["chart"]["labels"] == BAR["labels"]
    assert back["chart"]["highlight"] == 1 and back["chart"]["unit"] == "조 원" and back["chart"]["type"] == "bar"


def test_validate_flags_bad_chart_and_counts():
    def script(slides):
        return {"format": "explainer", "cover": {"lines": [{"text": "표지", "highlight": True}]},
                "slides": slides, "outro": {"summary": "요약 문장은 스무 자를 넘겨야 합니다 꼭요", "question": "q?"},
                "caption": "c\n출처: 테스트", "hashtags": ["#a"] * 8}
    good = {"slide_type": "chart", "title": "3년 새 3.6배", "body": "", "chart": BAR}
    bad = {"slide_type": "chart", "title": "x", "body": "", "chart": {**BAR, "values": ["2.8", "6.2", "11"]}}
    errs = validate.check(script([good]), BODY)
    assert not any("chart" in e for e in errs), errs
    errs = validate.check(script([bad]), BODY)
    assert any("chart: 값" in e for e in errs)
    errs = validate.check(script([good, dict(good)]), BODY)
    assert any("chart 장 1장 초과" in e for e in errs)


def test_build_pages_chart_page():
    s = {"format": "numbers", "cover": {"lines": [{"text": "표지", "highlight": True}]},
         "slides": [{"slide_type": "chart", "title": "3년 새 3.6배", "body": "해석", "chart": BAR}],
         "outro": {"summary": "s", "question": "q"}}
    pages = render.build_pages(s, [None, None], "출처: 테스트", palette="sage", layout="card")
    p = pages[1]
    assert '<body class="chart">' in p and 'id="chart"' in p and "vendor/echarts.min.js" in p
    assert "layout_card.css" in p and "palette_sage.css" in p
    assert (ROOT / "templates" / "vendor" / "echarts.min.js").exists()
    assert (ROOT / "templates" / "vendor" / "ECHARTS_LICENSE").exists()


def test_render_chart(tmp_path):
    if not os.environ.get("CHROMIUM_PATH"):
        pytest.skip("Chromium 없음")
    out = tmp_path / "output" / "015_1"
    out.mkdir(parents=True)
    (tmp_path / "templates").symlink_to(ROOT / "templates")
    s = {"format": "numbers", "cover": {"lines": [{"text": "표지", "highlight": True}]},
         "slides": [{"slide_type": "chart", "title": "3년 새 3.6배", "body": "해석", "chart": BAR}],
         "outro": {"summary": "s", "question": "q"}}
    files, qa = render.render(render.build_pages(s, [None, None], "출처: 테스트"), str(out))
    assert qa[1]["kind"] == "chart" and not qa[1]["issues"]
    html = (out / "card_02.html").read_text(encoding="utf-8")
    assert json.dumps("3년 새 3.6배", ensure_ascii=False).strip('"') in html
