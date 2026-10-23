import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cardnews"))

from naver_cardnews import sheet, validate, writer  # noqa: E402
from naver_cardnews.formats import FORMATS, SLIDE_TYPES, format_rules  # noqa: E402
from samples import SAMPLES  # noqa: E402

from samples import QUOTE  # noqa: E402

BODY = ("카카오가 21일 이미지를 이해하는 비전 인코더 2종을 허깅페이스에 오픈소스로 공개했다. 4억2600만 파라미터의 미디엄과 "
        "9800만 파라미터의 티니다. 카카오는 일반 시각 질의응답 등 9개 영역, 총 42개 벤치마크에서 카나나 비전 인코더의 성능을 평가했다. "
        f"티니는 1억개 미만 경량 모델이다. 상업적 활용도 허용된다. 업계 관계자는 \"{QUOTE}\"고 말했다.")


def test_all_sample_formats_pass_validation():
    for fmt, script in SAMPLES.items():
        s = writer.normalize_script(copy.deepcopy(script))
        # 샘플은 구조 확인용이라 원문 대조(수치·근거)는 제외한다
        errs = [e for e in validate.check(s, BODY) if "원문에 없는 수치" not in e and "단위가 원문" not in e and "근거" not in e]
        assert errs == [], (fmt, errs)
        assert s["format"] == fmt and all(sl["slide_type"] in SLIDE_TYPES for sl in s["slides"])
        assert len(s["slides"]) == FORMATS[fmt]["body_slides"]


def test_format_specific_rules():
    qa = copy.deepcopy(SAMPLES["qa"]); qa["slides"][0]["title"] = "물음표 없는 질문"
    assert any("물음표" in e for e in validate.check(qa, BODY))
    gl = copy.deepcopy(SAMPLES["glossary"]); gl["slides"][1]["label"] = ""
    assert any("정의" in e for e in validate.check(gl, BODY))
    db = copy.deepcopy(SAMPLES["debate"]); db["slides"][3]["compare"]["left"]["points"] = ["하나뿐"]
    assert any("포인트 1개" in e for e in validate.check(db, BODY))
    db2 = copy.deepcopy(SAMPLES["debate"]); db2["slides"][4]["body"] = "기사에 없는 발언입니다 정말로 없는 문장이에요 그렇죠"
    assert any("인용문이 원문에" in e for e in validate.check(db2, BODY))
    nums = copy.deepcopy(SAMPLES["numbers"])
    assert not any("연속 금지" in e or "초과" in e for e in validate.check(nums, BODY))   # numbers 포맷은 stat 제한 없음
    short = copy.deepcopy(SAMPLES["debate"]); short["slides"] = short["slides"][:4]
    assert any("본문 6장인데 4장" in e for e in validate.check(short, BODY))
    scene = copy.deepcopy(SAMPLES["scene"]); scene["slides"][0]["body"] = "너무 긴 문장 " * 12
    assert any("25~75자" in e for e in validate.check(scene, BODY))


def test_sheet_roundtrip_for_new_types():
    for fmt in ("debate", "glossary", "scene", "reveal", "qa", "numbers"):
        s = writer.normalize_script(copy.deepcopy(SAMPLES[fmt]))
        back = sheet.unflatten(sheet.flatten(s))
        assert back["format"] == fmt
        assert [x["slide_type"] for x in back["slides"]] == [x["slide_type"] for x in s["slides"]]
        assert not sheet.changed(s, back), fmt
    s = writer.normalize_script(copy.deepcopy(SAMPLES["reveal"]))
    flat = sheet.flatten(s)
    assert flat["5장 라벨"] == "알려진 것 | 실제로는" and flat["5장 본문"].startswith("클수록 똑똑하다 ; ")
    assert flat["7장 유형"] == "" and sheet.unflatten(flat)["slides"].__len__() == 5   # 빈 장은 건너뜀


def test_writer_prompt_mentions_formats():
    p = writer.system_prompt()
    assert all(k in p for k in FORMATS) and "format 선택 기준" in p
    assert "고정한다" in writer.system_prompt("qa") and "glossary" not in format_rules("qa")
