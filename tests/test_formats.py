import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cardnews"))

from naver_cardnews import sheet, validate, writer  # noqa: E402
from naver_cardnews.formats import FORMATS, format_rules  # noqa: E402
from samples import SAMPLES  # noqa: E402

BODY = ("카카오가 21일 이미지를 이해하는 비전 인코더 2종을 허깅페이스에 오픈소스로 공개했다. 4억2600만 파라미터의 미디엄과 "
        "9800만 파라미터의 티니다. 카카오는 일반 시각 질의응답 등 9개 영역, 총 42개 벤치마크에서 카나나 비전 인코더의 성능을 평가했다. "
        "티니는 1억개 미만 경량 모델이다. 상업적 활용도 허용된다.")


def test_all_sample_formats_pass_validation():
    for fmt, script in SAMPLES.items():
        s = writer.normalize_script(copy.deepcopy(script))
        errs = [e for e in validate.check(s, BODY) if "원문에 없는 수치" not in e and "단위가 원문" not in e]
        assert errs == [], (fmt, errs)
        assert s["format"] == fmt and all(sl["slide_type"] in ("photo", "stat", "list", "term", "qa", "compare") for sl in s["slides"])


def test_format_specific_rules():
    qa = copy.deepcopy(SAMPLES["qa"]); qa["slides"][0]["title"] = "물음표 없는 질문"
    assert any("물음표" in e for e in validate.check(qa, BODY))
    term = copy.deepcopy(SAMPLES["term"]); term["slides"][0]["label"] = ""
    assert any("정의" in e for e in validate.check(term, BODY))
    cmp = copy.deepcopy(SAMPLES["compare"]); cmp["slides"][0]["compare"]["left"]["points"] = ["하나뿐"]
    assert any("포인트 1개" in e for e in validate.check(cmp, BODY))
    nums = copy.deepcopy(SAMPLES["numbers"])
    assert not any("연속 금지" in e or "초과" in e for e in validate.check(nums, BODY))   # numbers 포맷은 stat 제한 없음
    nums["format"] = "explainer"
    assert any("연속 금지" in e for e in validate.check(nums, BODY))


def test_sheet_roundtrip_for_new_types():
    for fmt in ("listicle", "term", "qa", "compare"):
        s = writer.normalize_script(copy.deepcopy(SAMPLES[fmt]))
        back = sheet.unflatten(sheet.flatten(s))
        assert back["format"] == fmt
        assert [x["slide_type"] for x in back["slides"]] == [x["slide_type"] for x in s["slides"]]
        assert not sheet.changed(s, back), fmt
    s = writer.normalize_script(copy.deepcopy(SAMPLES["compare"]))
    flat = sheet.flatten(s)
    assert flat["2장 라벨"] == "카카오 티니 | 글로벌 동급" and flat["2장 본문"].startswith("9800만 파라미터 ; ")


def test_writer_prompt_mentions_formats():
    p = writer.system_prompt()
    assert all(k in p for k in FORMATS) and "format 선택 기준" in p
    assert "고정한다" in writer.system_prompt("qa") and "listicle" not in format_rules("qa")
