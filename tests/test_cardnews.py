import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "cardnews"))

import keys  # noqa: E402
import naver_article  # noqa: E402
import render  # noqa: E402

HTML = """<html><head><meta property="og:title" content="메타 제목"/>
<meta property="og:article:author" content="한국경제 | 네이버"/></head><body>
<h2 id="title_area"><span>[단독] 카카오, <b>AI</b>의 '눈' 공개</span></h2>
<span data-date-time="2026-10-21 09:12:00"></span>
<article id="dic_area">카카오가 21일 이미지를 이해하는 비전 인코더 2종을 공개했다.<br>
<em class="img_desc">카카오 사옥 전경. 사진=카카오</em>
회사 측은 동급 모델 가운데 가장 높은 성능이라고 밝혔다.<br>이번 모델은 상업적 활용도 허용된다. 업계는 국내 AI 생태계에 미칠 영향을 주목하고 있다.
벤치마크 결과 구글과 메타의 동급 모델을 앞섰다는 설명이다. 카카오는 이를 자사 서비스에 순차 적용할 계획이다.<br>
이미지와 텍스트를 함께 이해하는 멀티모달 모델의 핵심 부품으로, 외부 개발자도 자유롭게 가져다 쓸 수 있다.<br>
홍길동 기자 hong@hankyung.com<br>ⓒ 한국경제 무단 전재 및 재배포 금지</article></body></html>"""


def test_parse_article_cleans_captions_and_tails():
    a = naver_article.parse(HTML, "https://n.news.naver.com/mnews/article/015/0005344713?sid=105")
    assert a["id"] == "015_0005344713" and a["press"] == "한국경제" and a["date"] == "2026-10-21"
    assert a["title"] == "[단독] 카카오, AI의 '눈' 공개"
    assert "사진=카카오" not in a["body"] and "hong@" not in a["body"] and "무단 전재" not in a["body"]
    assert a["body"].startswith("카카오가 21일")


def test_parse_article_rejects_empty_body():
    try:
        naver_article.parse("<html><h2 id='title_area'>x</h2><article id='dic_area'>짧음</article></html>", "https://n.news.naver.com/article/1/2")
        assert False
    except naver_article.ArticleError:
        pass


def test_keys_loader_reads_env_then_keys_txt(tmp_path, monkeypatch):
    kt = tmp_path / "keys.txt"
    kt.write_text("[Pexels-cardnews]\nPEXELS_API_KEY=from_txt\n[Other]\nPEXELS_API_KEY=wrong\n", encoding="utf-8")
    monkeypatch.setattr(keys, "KEYS_TXT", kt)
    monkeypatch.setattr(keys, "_ENV_LOADED", True)   # 실제 .env 를 읽지 않게
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    assert keys.load("Pexels-cardnews", "PEXELS_API_KEY") == "from_txt"
    monkeypatch.setenv("PEXELS_API_KEY", "from_env")
    assert keys.load("Pexels-cardnews", "PEXELS_API_KEY") == "from_env"
    assert keys.load("None", "NOPE_KEY", required=False) == ""


SCRIPT = {
    "cover": {"image_query": "lens", "lines": [{"text": "카카오가 만든", "highlight": False}, {"text": "AI의 눈", "highlight": True}]},
    "slides": [
        {"image_query": "q1", "title": "무엇을 공개했나", "body": "이미지를 이해하는 비전 인코더 2종을 오픈소스로 풀었다."},
        {"slide_type": "stat", "stat": {"value": "2", "unit": "종", "label": "공개한 비전 인코더", "source_quote": "비전 인코더 2종을 공개했다"},
         "title": "", "body": ""},
        {"image_query": "q3", "title": "왜 중요한가", "body": "구글·메타 동급 모델보다 높은 성능이라고 밝혔다."},
    ],
    "outro": {"summary": "카카오가 AI의 눈을 공개했다", "question": "오픈소스 AI, 써볼 생각 있나요?"},
}


def test_build_pages_stat_and_plain():
    pages = render.build_pages(SCRIPT, ["bg_01.jpg", "bg_02.jpg", None, None], "출처: 한국경제 · 2026.10.21")
    assert len(pages) == 5
    assert '<body class="cover">' in pages[0] and "bg_01.jpg" in pages[0]
    assert '<body class="stat">' in pages[2] and "card_stat.css" in pages[2] and 'data-len="short"' in pages[2]
    assert '<body class="slide plain">' in pages[3] and "background-image" not in pages[3]
    assert '<body class="outro">' in pages[4] and "bg_01.jpg" in pages[4]  # 마지막 장은 표지 사진 재사용


def test_render_smoke(tmp_path):
    if not os.environ.get("CHROMIUM_PATH") and not os.path.exists(os.path.expanduser("~/.cache/ms-playwright")):
        import pytest
        pytest.skip("Chromium 없음")
    out = tmp_path / "output" / "015_1"
    out.mkdir(parents=True)
    # ../../templates/card.css 상대 경로를 맞추기 위해 output 상위에 templates 링크
    (tmp_path / "templates").symlink_to(ROOT / "templates")
    from PIL import Image
    Image.new("RGB", (1080, 1350), (30, 40, 60)).save(out / "bg_01.jpg")
    Image.new("RGB", (1080, 1350), (60, 30, 30)).save(out / "bg_02.jpg")
    files, qa = render.render(render.build_pages(SCRIPT, ["bg_01.jpg", "bg_02.jpg", None, None], "출처: 테스트"), str(out))
    assert len(files) == 5 and all(os.path.getsize(f) > 10_000 for f in files)
    kinds = [q["kind"] for q in qa]
    assert kinds == ["cover", "slide", "stat", "slide", "outro"]
    assert qa[2]["contrast"] is None and not any("폰트" in i for q in qa for i in q["issues"])
    (tmp_path / "qa.json").write_text(json.dumps(qa, ensure_ascii=False))


def test_make_batch_continues_after_failure(tmp_path, monkeypatch):
    import make_batch
    from naver_cardnews.db import Article, Database
    from naver_cardnews.normalize import normalize_title
    db_path = tmp_path / "news.db"
    db = Database(db_path)
    for i, (aid, st) in enumerate([("001_1", "승인"), ("001_2", "승인"), ("001_3", "대기")]):
        db.insert(Article(aid, "AI", f"기사 {i}", "a.com", "2026-10-21T00:00:00+00:00",
                          f"https://n.news.naver.com/article/{aid.replace('_', '/')}", "", "", normalize_title(f"기사 {i}")),
                  i + 1, True, st)
    db.conn.commit(); db.close()

    calls = []
    def fake_make(url, dbp):
        calls.append(url)
        if url.endswith("/1"):
            raise RuntimeError("writer 실패")
        d = Database(dbp); d.update_review("001_2", "제작완료", None, "output/001_2", None); d.conn.commit(); d.close()
        return "output/001_2"
    monkeypatch.setattr(make_batch.make_card, "main", fake_make)
    monkeypatch.setattr(make_batch, "import_queue", lambda db, p: 0)
    monkeypatch.setattr(make_batch, "export_queue", lambda db, p: 0)
    monkeypatch.setenv("NAVER_CARDNEWS_OUT", str(tmp_path / "q.xlsx"))

    rc = make_batch.main(str(db_path), limit=5, dry_run=False)
    assert rc == 1 and len(calls) == 2
    db = Database(db_path)
    assert db.get("001_1")["status"] == "승인" and db.get("001_1")["memo"].startswith("제작 실패")
    assert db.get("001_2")["status"] == "제작완료" and db.get("001_2")["card_folder"] == "output/001_2"
    assert db.get("001_3")["status"] == "대기"
