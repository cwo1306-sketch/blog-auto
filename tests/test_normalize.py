from naver_cardnews.normalize import normalize_title, normalize_url, strip_html, tokenize


def test_strip_html_unescapes_entities():
    assert strip_html("<b>엔비디아</b> &quot;AI&quot; 칩") == '엔비디아 "AI" 칩'


def test_normalize_url_drops_tracking_and_mobile_prefix():
    a = normalize_url("https://m.news.example.com/view/123?utm_source=naver&aid=9")
    b = normalize_url("http://www.news.example.com/view/123/?aid=9&fbclid=xyz")
    assert a == b == "https://news.example.com/view/123?aid=9"


def test_normalize_title_removes_prefix_suffix_symbols():
    a = normalize_title("[속보] 엔비디아, 차세대 AI 칩 공개… 주가 급등 | 연합뉴스")
    b = normalize_title("엔비디아 차세대 AI 칩 공개 주가 급등")
    assert a == b


def test_tokenize_korean_bigrams_and_ascii_words():
    assert tokenize("AI 반도체") == ["ai", "반도", "도체"]
