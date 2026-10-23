"""구성 템플릿 샘플 원고 (구조 확인용, 카카오 비전 인코더 기사 기준). `python samples.py <out_root> <사진 폴더>` 로 전부 렌더.

인용(quote) 장의 문장은 실제 기사 발언이 아니라 구조 확인용 예시다. 실제 제작에서는 validate 가 원문 대조를 한다.
"""

from __future__ import annotations

import os
import shutil
import sys


def _cover(lines, concept="AI가 이미지를 보는 눈"):
    return {"lines": [{"text": t.lstrip("*"), "highlight": t.startswith("*")} for t in lines],
            "image_queries": ["abstract glass lens light", "camera aperture macro dark"], "image_concept": concept}


def _s(kind, title, body="", label="", stat=None, compare=None, q=("abstract light", "server room dark"), concept=""):
    return {"slide_type": kind, "title": title, "body": body, "label": label, "stat": stat, "compare": compare,
            "image_queries": list(q) if kind == "photo" else [], "image_concept": concept if kind == "photo" else ""}


def _stat(title, value, unit, label, quote, body=""):
    return _s("stat", title, body, stat={"value": value, "unit": unit, "label": label, "source_quote": quote})


def _chart(title, ctype, unit, labels, values, quote, body="", highlight=None):
    s = _s("chart", title, body)
    s["chart"] = {"type": ctype, "unit": unit, "labels": labels, "values": values, "highlight": highlight, "source_quote": quote}
    return s


OUTRO = {"summary": "카카오가 AI의 눈 2종을 상업 이용까지 가능하게 공개했어요", "question": "AI의 눈, 어디에 가장 쓰이면 좋을까요?"}
TAIL = {"outro": OUTRO, "caption": "…\n출처: 조선비즈", "hashtags": ["#AI뉴스", "#AI", "#테크뉴스", "#카카오", "#비전인코더", "#오픈소스", "#멀티모달", "#온디바이스AI"]}
QUOTE = "작은 모델이 큰 모델을 이기는 일은 흔치 않다. 한국어 문서에서는 격차가 더 벌어진다"

SAMPLES = {
    # ZDNet AMEET형: 질문 표지(수치 부제) → 공감 훅 → 핵심 수치 → 비유 → 찬반 비율 → 인용/반론 → 상황별 권고
    "debate": {"format": "debate", "cover": _cover(["*AI의 눈, 국내서도", "*만들어도 될까?", "42개 평가 1위"]), "slides": [
        _s("photo", "이런 생각 해보셨죠?", "'어차피 구글·메타가 다 만드는데 국내 기업이 굳이?' 이런 생각, 한 번쯤 해보셨을 거예요. 카카오가 이미지를 이해하는 AI 부품을 직접 만들어 공개하면서 이 질문이 다시 나왔어요.", concept="의문, 선택의 갈림길"),
        _stat("평가 42개에서 1위", "42", "개", "성능 평가 벤치마크", "총 42개 벤치마크에서 카나나 비전 인코더의 성능을 평가했다."),
        _s("photo", "왜 작은 게 이길까요?", "같은 연필을 줘도 그림 실력은 제각각이죠. 모델도 크기보다 어떤 데이터로 배웠느냐가 성능을 가르는데요, 카카오는 한국어 문서와 사진을 집중적으로 학습시켰다고 해요.", concept="비유, 연필과 그림"),
        _s("compare", "전문가들은 어떻게 볼까", compare={"left": {"label": "기대", "points": ["한국어 문서 인식 강점", "상업 이용 허용으로 확산", "온디바이스 적용 가능"]},
                                               "right": {"label": "우려", "points": ["자체 평가라 검증 필요", "글로벌 모델 갱신 속도", "생태계 유지 비용"]}}),
        _s("quote", "작은 모델의 역설", QUOTE, label="업계 관계자 (기사 인용)"),
        _s("list", "그래서 이렇게 보세요", "개발자라면 허깅페이스에서 내려받아 한국어 문서로 먼저 테스트해 보세요. 일반 사용자라면 앱의 사진 검색·영수증 인식이 좋아지는지 지켜보면 돼요."),
    ], **TAIL},
    # 연합 우리말 구조대형: 용어 묶음
    "glossary": {"format": "glossary", "cover": _cover(["비전 인코더부터", "*벤치마크까지", "AI 용어 4개 풀이"]), "slides": [
        _s("photo", "왜 이런 말이 쏟아질까", "카카오가 AI 부품을 공개한 기사 한 편에 낯선 용어가 네 개나 나와요. 용어만 알아도 기사가 절반은 읽히는데요, 오늘은 그 네 개를 하나씩 풀어 볼게요.", concept="낯선 단어들"),
        _s("term", "비전 인코더", "사람으로 치면 눈과 시신경이에요. 사진을 보고 '빨간 사과가 접시 위에 있다'는 정보를 뇌(언어 모델)에 넘겨 줘요.", label="이미지를 AI가 읽을 수 있는 숫자로 바꾸는 부품"),
        _s("term", "파라미터", "모델 안의 조절 손잡이 수예요. 손잡이가 많을수록 똑똑하지만 무겁고 비싸져요. 미디엄은 4억2600만 개, 티니는 9800만 개예요.", label="AI 모델의 크기를 나타내는 숫자"),
        _s("term", "온디바이스 AI", "인터넷 서버 대신 스마트폰 안에서 바로 계산하는 AI예요. 인터넷이 없어도 되고 사진이 밖으로 나가지 않아요.", label="기기 안에서 직접 돌아가는 AI"),
        _s("term", "벤치마크", "모델끼리 같은 시험지를 풀게 해 점수를 매기는 거예요. 카카오는 42개 시험에서 1위였다고 해요.", label="AI 성능을 비교하는 표준 시험"),
        _s("quote", "용어를 알면 보이는 것", QUOTE, label="업계 관계자 (기사 인용)"),
    ], **TAIL},
    # 이데일리형: 현장 사례, 한 장 한 문장
    "scene": {"format": "scene", "cover": _cover(["판교 사무실 한켠,", "*AI가 사진을 읽기", "시작했다"]), "slides": [
        _s("photo", "판교의 어느 모니터", "카카오 연구실 모니터 위, 영수증 사진 한 장이 글자와 숫자로 바뀌고 있어요.", q=("office monitor dark room", "receipt paper macro"), concept="연구실 장면"),
        _s("photo", "어떻게 읽나", "사진을 숫자로 바꾸는 부품 '비전 인코더'가 글자·위치·형태를 먼저 읽어요.", q=("abstract data flow", "glass lens light"), concept="작동 원리"),
        _stat("평가 범위", "42", "개", "성능 평가 벤치마크", "총 42개 벤치마크에서 카나나 비전 인코더의 성능을 평가했다."),
        _s("photo", "또 다른 현장", "스마트폰 안에서도 돌아가는 작은 모델 '티니'가 인터넷 없이 사진을 읽어요.", q=("hand holding phone dark", "small glowing light"), concept="손안의 기기"),
        _s("photo", "다음 계획", "카카오는 이 부품을 자사 서비스에 순차 적용할 계획이라고 밝혔어요.", q=("city skyline night minimal", "abstract timeline light"), concept="계획, 확장"),
        _s("photo", "그래서", "국내 서비스가 바로 가져다 쓸 수 있는 '한국어에 강한 눈'이 생긴 거예요.", q=("open door light", "network nodes glowing"), concept="결론"),
    ], **TAIL},
    # 스브스뉴스형: 반전 추리
    "reveal": {"format": "reveal", "cover": _cover(["AI는 클수록", "*똑똑하다고", "알고 있었다면"]), "slides": [
        _s("photo", "다들 그렇게 알았죠", "파라미터가 많을수록, 서버가 클수록 AI는 똑똑하다. 지난 몇 년 AI 뉴스는 대부분 '더 크게'의 경쟁이었어요.", concept="거대한 서버"),
        _s("photo", "그런데 이상한 숫자", "카카오가 공개한 '티니'는 파라미터가 1억 개도 안 돼요. 그런데 4억 개 넘는 글로벌 모델보다 성능이 좋았다고 해요.", concept="작은 것과 큰 것"),
        _stat("1억 개도 안 되는 크기", "9800만", "파라미터", "티니 모델 크기", "9800만 파라미터의 티니"),
        _s("compare", "알려진 것 vs 실제로는", compare={"left": {"label": "알려진 것", "points": ["클수록 똑똑하다", "서버 없인 못 쓴다", "한국어는 덤이다"]},
                                              "right": {"label": "실제로는", "points": ["학습 데이터가 가른다", "폰 안에서 돌아간다", "한국어 특화가 강점"]}}),
        _s("photo", "왜 이런 일이", "크기보다 '무엇을 배웠나'가 중요했던 거예요. 한국어 문서와 사진을 집중 학습한 작은 모델이 범용 큰 모델을 특정 시험에서 앞선 거죠.", concept="반전의 이유"),
    ], **TAIL},
    "qa": {"format": "qa", "cover": _cover(["카카오 AI의 눈,", "*그래서 나한테", "*뭐가 달라져?"]), "slides": [
        _s("qa", "무슨 일이 있었나요?", "카카오가 이미지를 이해하는 AI 부품 '비전 인코더' 2종을 오픈소스로 공개했어요. 누구나 내려받아 쓸 수 있고 상업적 이용도 허용돼요."),
        _s("qa", "내가 쓰는 앱도 바뀌나요?", "바로는 아니에요. 다만 개발사들이 이 부품을 가져다 쓰면 사진 검색, 영수증 인식 같은 기능이 더 많은 앱에 들어올 수 있어요."),
        _s("qa", "성능은 믿을 만한가요?", "카카오 자체 평가 기준으로는 42개 벤치마크에서 구글·메타 동급 모델을 앞섰다고 해요. 외부 검증 결과는 아직 나오지 않았어요."),
        _s("qa", "언제부터 체감할 수 있나요?", "카카오는 자사 서비스에 순차 적용할 계획이라고 밝혔어요. 구체적인 시점은 기사에 나오지 않았어요."),
        _s("list", "이렇게 해보세요", "개발자라면 허깅페이스에서 내려받아 테스트해 보세요. 일반 사용자라면 자주 쓰는 앱의 사진 기능 업데이트 소식을 지켜보면 돼요."),
    ], **TAIL},
    "numbers": {"format": "numbers", "cover": _cover(["숫자로 보는", "*카카오 AI의 눈", "4억·9800만·42"]), "slides": [
        _stat("큰 모델의 크기", "4억2600만", "파라미터", "미디엄 모델 크기", "4억2600만 파라미터의 미디엄"),
        _chart("9개 영역, 42개 시험", "compare", "개", ["평가 영역", "벤치마크"], ["9", "42"], "9개 영역, 총 42개 벤치마크",
               "카카오는 9개 영역에 걸친 42개 벤치마크로 성능을 쟀다고 밝혔어요."),
        _stat("공개한 모델 수", "2", "종", "오픈소스 비전 인코더", "비전 인코더 2종"),
        _stat("작은 모델의 크기", "9800만", "파라미터", "티니 모델 크기", "9800만 파라미터의 티니"),
        _s("photo", "숫자가 말하는 것", "작은 모델도 한국어 문서처럼 특정 영역을 집중 학습하면 큰 모델을 앞설 수 있다는 게 이번 숫자들의 공통 메시지예요. 다만 평가는 카카오 자체 기준이에요.", concept="결론"),
    ], **TAIL},
    "explainer": {"format": "explainer", "cover": _cover(["카카오가 만든", "*AI의 '눈' 공개", "*누구나 쓸 수 있다"]), "slides": [
        _s("photo", "카카오, AI의 눈 공개", "카카오가 이미지를 이해하도록 돕는 '카나나-2-비전 인코더' 2종을 허깅페이스에 오픈소스로 공개했습니다. 4억2600만 파라미터의 '미디엄'과 9800만 파라미터의 '티니'입니다."),
        _s("photo", "비전 인코더란?", "비전 인코더는 AI의 '눈'입니다. 사진 속 사물, 글자, 위치, 형태를 읽어 언어 모델에 전달하고, 언어 모델은 이를 질문과 함께 해석해 답합니다. 메뉴판의 가격을 읽는 일도 이 기술로 가능합니다."),
        _stat("42개 평가에서 최고 성능", "42", "개", "성능 평가 벤치마크", "총 42개 벤치마크에서 카나나 비전 인코더의 성능을 평가했다."),
        _s("photo", "작지만 강한 티니", "티니 모델은 파라미터가 1억개 미만인 경량 모델인데도 4억개가 넘는 글로벌 모델보다 뛰어난 성능을 보였다고 카카오는 밝혔습니다. 스마트폰 등 기기 안에서 돌리는 온디바이스 AI를 염두에 두고 개발됐습니다."),
    ], **TAIL},
}


def main(out_root: str, source_dir: str) -> None:
    import render
    photos = sorted(f for f in os.listdir(source_dir) if f.startswith("bg_") and f.endswith(".jpg"))
    for fmt, script in SAMPLES.items():
        out = os.path.join(out_root, f"sample_{fmt}")   # output/ 바로 아래여야 ../../templates/card.css 경로가 맞는다
        os.makedirs(out, exist_ok=True)
        shutil.copy(os.path.join(source_dir, "bg_01.jpg"), os.path.join(out, "bg_01.jpg"))
        images: list[str | None] = ["bg_01.jpg"]
        k = 1
        for i, s in enumerate(script["slides"], start=2):
            if s["slide_type"] == "photo":
                src = os.path.join(source_dir, photos[k % len(photos)]); k += 1
                shutil.copy(src, os.path.join(out, f"bg_{i:02d}.jpg"))
                images.append(f"bg_{i:02d}.jpg")
            else:
                images.append(None)
        files, qa = render.render(render.build_pages(script, images, "출처: 조선비즈 · 2026.10.21"), out)
        print(fmt, len(files), "장", [(q["card"], q["kind"], q["issues"]) for q in qa if q["issues"]] or "QA 이슈 없음")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
