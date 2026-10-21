"""구성 템플릿 6종의 샘플 원고 (카카오 비전 인코더 기사 기준, 구조 확인용). `python samples.py <out_dir>` 로 전부 렌더."""

from __future__ import annotations

import os
import shutil
import sys

COVER_IMG = "bg_01.jpg"

def _cover(lines, concept="AI가 이미지를 보는 눈"):
    return {"lines": [{"text": t.lstrip("*"), "highlight": t.startswith("*")} for t in lines],
            "image_queries": ["abstract glass lens light", "camera aperture macro dark"], "image_concept": concept}

def _photo(title, body, q=("abstract light", "server room dark"), concept=""):
    return {"slide_type": "photo", "title": title, "body": body, "image_queries": list(q), "image_concept": concept,
            "stat": None, "compare": None, "label": ""}

OUTRO = {"summary": "카카오가 AI의 눈 2종을 상업 이용까지 가능하게 공개했습니다", "question": "AI의 눈, 어디에 가장 쓰이면 좋을까요?"}
TAIL = {"outro": OUTRO, "caption": "…\n출처: 조선비즈", "hashtags": ["#AI뉴스", "#AI", "#테크뉴스", "#카카오", "#비전인코더", "#오픈소스", "#멀티모달", "#온디바이스AI"]}

SAMPLES = {
    "explainer": {"format": "explainer", "cover": _cover(["카카오가 만든", "*AI의 '눈' 공개", "*누구나 쓸 수 있다"]), "slides": [
        _photo("카카오, AI의 눈 공개", "카카오가 이미지를 이해하도록 돕는 '카나나-2-비전 인코더' 2종을 허깅페이스에 오픈소스로 공개했습니다. 4억2600만 파라미터의 '미디엄'과 9800만 파라미터의 '티니'입니다."),
        _photo("비전 인코더란?", "비전 인코더는 AI의 '눈'입니다. 사진 속 사물, 글자, 위치, 형태를 읽어 언어 모델에 전달하고, 언어 모델은 이를 질문과 함께 해석해 답합니다. 메뉴판의 가격을 읽는 일도 이 기술로 가능합니다."),
        {"slide_type": "stat", "title": "42개 평가에서 최고 성능", "body": "", "label": "", "image_queries": [], "image_concept": "", "compare": None,
         "stat": {"value": "42", "unit": "개", "label": "성능 평가 벤치마크", "source_quote": "총 42개 벤치마크에서 카나나 비전 인코더의 성능을 평가했다."}},
        _photo("작지만 강한 티니", "티니 모델은 파라미터가 1억개 미만인 경량 모델인데도 4억개가 넘는 글로벌 모델보다 뛰어난 성능을 보였다고 카카오는 밝혔습니다. 스마트폰 등 기기 안에서 돌리는 온디바이스 AI를 염두에 두고 개발됐습니다."),
    ], **TAIL},
    "listicle": {"format": "listicle", "cover": _cover(["카카오 AI의 눈", "*알아야 할 4가지", "3분 정리"]), "slides": [
        {"slide_type": "list", "title": "두 가지 크기로 공개", "body": "4억2600만 파라미터 '미디엄'과 9800만 파라미터 '티니'. 큰 모델은 정확도, 작은 모델은 기기 탑재를 노립니다.", "label": "", "image_queries": [], "image_concept": "", "stat": None, "compare": None},
        {"slide_type": "list", "title": "상업적 이용 허용", "body": "허깅페이스에 오픈소스로 풀렸고 상업적 활용까지 허용됩니다. 스타트업도 가져다 자기 서비스에 붙일 수 있습니다.", "label": "", "image_queries": [], "image_concept": "", "stat": None, "compare": None},
        {"slide_type": "list", "title": "42개 벤치마크 평가", "body": "9개 영역 42개 벤치마크로 평가했고, 회사 측은 구글·메타·애플·알리바바의 동급 모델을 상회했다고 밝혔습니다.", "label": "", "image_queries": [], "image_concept": "", "stat": None, "compare": None},
        {"slide_type": "list", "title": "한국어 문서에 강점", "body": "한국어 문자 인식과 문서 이해 영역이 평가에 포함됐습니다. 영수증·메뉴판처럼 한글이 섞인 이미지에서 차이가 날 수 있습니다.", "label": "", "image_queries": [], "image_concept": "", "stat": None, "compare": None},
    ], **TAIL},
    "numbers": {"format": "numbers", "cover": _cover(["숫자로 보는", "*카카오 AI의 눈", "4억·9800만·42"]), "slides": [
        {"slide_type": "stat", "title": "미디엄 모델 크기", "body": "", "label": "", "image_queries": [], "image_concept": "", "compare": None,
         "stat": {"value": "4억2600만", "unit": "파라미터", "label": "미디엄 모델 크기", "source_quote": "4억2600만 파라미터의 미디엄"}},
        {"slide_type": "stat", "title": "티니 모델 크기", "body": "", "label": "", "image_queries": [], "image_concept": "", "compare": None,
         "stat": {"value": "9800만", "unit": "파라미터", "label": "티니 모델 크기", "source_quote": "9800만 파라미터의 티니"}},
        {"slide_type": "stat", "title": "평가 범위", "body": "", "label": "", "image_queries": [], "image_concept": "", "compare": None,
         "stat": {"value": "42", "unit": "개", "label": "성능 평가 벤치마크", "source_quote": "총 42개 벤치마크에서"}},
        {"slide_type": "stat", "title": "평가 영역", "body": "", "label": "", "image_queries": [], "image_concept": "", "compare": None,
         "stat": {"value": "9", "unit": "개 영역", "label": "평가 영역 수", "source_quote": "9개 영역, 총 42개 벤치마크"}},
    ], **TAIL},
    "term": {"format": "term", "cover": _cover(["*비전 인코더가", "뭐길래", "카카오가 공개했나"]), "slides": [
        {"slide_type": "term", "title": "비전 인코더", "label": "이미지를 AI가 읽을 수 있는 숫자로 바꾸는 부품", "body": "사람으로 치면 눈과 시신경입니다. 사진을 보고 '빨간 사과가 접시 위에 있다'는 정보를 뇌(언어 모델)에 전달하는 역할을 합니다.", "image_queries": [], "image_concept": "", "stat": None, "compare": None},
        _photo("왜 지금 등장했나", "카카오가 이 부품 2종을 오픈소스로 공개했기 때문입니다. 그동안 국내 기업은 해외 모델의 눈을 빌려 썼는데, 자체 개발한 눈을 누구나 쓰게 풀었습니다.", concept="공개, 개방"),
        _photo("어디에 쓰이나", "메뉴판 사진에서 가격 읽기, 영수증 정리, 사진 검색, 화면을 보고 안내하는 비서까지. 이미지를 이해해야 하는 모든 AI 서비스의 입구입니다.", concept="일상 속 카메라"),
        _photo("무엇이 달라지나", "작은 '티니' 모델은 스마트폰 안에서 돌릴 수 있게 설계됐습니다. 인터넷 없이도 사진을 이해하는 기능이 앱에 더 많이 들어올 수 있습니다.", concept="손안의 기기"),
    ], **TAIL},
    "qa": {"format": "qa", "cover": _cover(["카카오 AI의 눈,", "*그래서 나한테", "*뭐가 달라져?"]), "slides": [
        {"slide_type": "qa", "title": "무슨 일이 있었나요?", "body": "카카오가 이미지를 이해하는 AI 부품 '비전 인코더' 2종을 오픈소스로 공개했습니다. 누구나 내려받아 쓸 수 있고 상업적 이용도 허용됩니다.", "label": "", "image_queries": [], "image_concept": "", "stat": None, "compare": None},
        {"slide_type": "qa", "title": "내가 쓰는 앱도 바뀌나요?", "body": "바로는 아닙니다. 다만 개발사들이 이 부품을 가져다 쓰면 사진 검색, 영수증 인식 같은 기능이 더 많은 앱에 들어올 수 있습니다.", "label": "", "image_queries": [], "image_concept": "", "stat": None, "compare": None},
        {"slide_type": "qa", "title": "성능은 믿을 만한가요?", "body": "카카오 자체 평가 기준으로는 42개 벤치마크에서 구글·메타 동급 모델을 앞섰다고 합니다. 외부 검증 결과는 아직 나오지 않았습니다.", "label": "", "image_queries": [], "image_concept": "", "stat": None, "compare": None},
        {"slide_type": "qa", "title": "언제부터 체감할 수 있나요?", "body": "카카오는 자사 서비스에 순차 적용할 계획이라고 밝혔습니다. 구체적인 시점은 기사에 나오지 않았습니다.", "label": "", "image_queries": [], "image_concept": "", "stat": None, "compare": None},
    ], **TAIL},
    "compare": {"format": "compare", "cover": _cover(["카카오 vs 글로벌", "*AI의 눈,", "*뭐가 다른가"]), "slides": [
        {"slide_type": "compare", "title": "모델 크기", "body": "", "label": "", "image_queries": [], "image_concept": "", "stat": None,
         "compare": {"left": {"label": "카카오 티니", "points": ["9800만 파라미터", "스마트폰 탑재 겨냥", "1억개 미만 경량"]}, "right": {"label": "글로벌 동급", "points": ["4억개 이상", "서버에서 구동", "카카오 평가 기준 성능 열세"]}}},
        {"slide_type": "compare", "title": "공개 범위", "body": "", "label": "", "image_queries": [], "image_concept": "", "stat": None,
         "compare": {"left": {"label": "카카오", "points": ["허깅페이스 오픈소스", "상업적 이용 허용"]}, "right": {"label": "다수 빅테크", "points": ["API로만 제공", "가중치 비공개가 많음"]}}},
        {"slide_type": "compare", "title": "강점 영역", "body": "", "label": "", "image_queries": [], "image_concept": "", "stat": None,
         "compare": {"left": {"label": "카카오", "points": ["한국어 문자 인식", "한국어 문서 이해"]}, "right": {"label": "글로벌 동급", "points": ["영어 중심 학습", "한글 문서는 약점"]}}},
        _photo("결론", "국내 서비스에 바로 붙일 수 있는 '한국어에 강한 눈'이 공개됐다는 점이 핵심입니다. 성능 비교는 카카오 자체 평가라는 점은 감안해야 합니다.", concept="결론, 균형"),
    ], **TAIL},
}


def main(out_root: str, source_dir: str) -> None:
    import render
    for fmt, script in SAMPLES.items():
        out = os.path.join(out_root, f"sample_{fmt}")   # output/ 바로 아래여야 ../../templates/card.css 경로가 맞는다
        os.makedirs(out, exist_ok=True)
        shutil.copy(os.path.join(source_dir, "bg_01.jpg"), os.path.join(out, "bg_01.jpg"))
        images: list[str | None] = ["bg_01.jpg"]
        for i, s in enumerate(script["slides"], start=2):
            if s["slide_type"] == "photo":
                src = os.path.join(source_dir, f"bg_{min(i, 5):02d}.jpg")
                if not os.path.exists(src):
                    src = os.path.join(source_dir, "bg_02.jpg")
                shutil.copy(src, os.path.join(out, f"bg_{i:02d}.jpg"))
                images.append(f"bg_{i:02d}.jpg")
            else:
                images.append(None)
        files, qa = render.render(render.build_pages(script, images, "출처: 조선비즈 · 2026.10.21"), out)
        print(fmt, [(q["card"], q["kind"], q["issues"]) for q in qa])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
