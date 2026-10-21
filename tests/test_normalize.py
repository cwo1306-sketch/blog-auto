from naver_cardnews.normalize import (char_bigrams, jaccard, naver_article_id, normalize_title, off_niche_reason,
                                      press_from_url, strip_html)


def test_strip_html_unescapes_entities():
    assert strip_html("<b>엔비디아</b> &quot;AI&quot; 칩") == '엔비디아 "AI" 칩'


def test_naver_article_id():
    assert naver_article_id("https://n.news.naver.com/mnews/article/015/0005344713?sid=101") == "015_0005344713"
    assert naver_article_id("https://n.news.naver.com/article/001/0001234567") == "001_0001234567"
    assert naver_article_id("https://www.hankyung.com/article/2026102112345") is None


def test_press_from_url():
    assert press_from_url("https://www.hankyung.com/article/1") == "hankyung.com"
    assert press_from_url("http://news.mt.co.kr/x") == "mt.co.kr"


def test_normalize_title_removes_prefix_suffix_symbols():
    a = normalize_title("[속보] 엔비디아, 차세대 AI 칩 공개… 주가 급등 | 연합뉴스")
    b = normalize_title("엔비디아 차세대 AI 칩 공개 (종합) 주가 급등")
    assert a == b == "엔비디아차세대ai칩공개주가급등"


def test_bigram_jaccard():
    a, b = char_bigrams("AI 반도체 수출"), char_bigrams("AI 반도체 수입")
    assert 0.5 < jaccard(a, b) < 1.0
    assert jaccard(a, set()) == 0.0


def test_off_niche_reason():
    topic, excl = ["AI", "반도체", "엔비디아"], ["코스피", "시황"]
    assert off_niche_reason("엔비디아, 신형 ai 칩 공개", topic, excl) is None
    assert off_niche_reason("코스피 3% 반등…삼전·닉스 급등 반도체주 강세", topic, excl).startswith("니치 외(배제어")
    assert off_niche_reason("전북도, 4조8119억 규모 신규사업 발굴", topic, excl) == "니치 외(제목에 AI·테크 용어 없음)"
    assert off_niche_reason("전북도, 신규사업 발굴", [], excl) is None  # topic_terms 비면 필터 끔
