import io
import json

from PIL import Image, ImageFilter

from naver_cardnews.db import Database
from naver_cardnews.imagehash import dhash, hamming, to_hex
from naver_cardnews.stat_card import Stat, StatError, len_class, render_html, validate_stat
from naver_cardnews.stock import Candidate, PexelsClient, UnsplashClient, search_candidates
from naver_cardnews.vision_pick import VisionScore, parse_score, pick


def img_bytes(color, size=(80, 100), fmt="JPEG"):
    """색을 시드로 쓴 결정적 노이즈 이미지. 색이 다르면 구조도 달라 dHash가 멀어진다."""
    import random
    rnd = random.Random(sum(color))
    im = Image.new("RGB", size, color)
    px = im.load()
    for x in range(size[0]):
        for y in range(size[1]):
            v = rnd.randint(0, 255)
            px[x, y] = (v, (v + color[1]) % 256, (v * 3 + color[2]) % 256)
    im = im.filter(ImageFilter.GaussianBlur(6))  # 저주파 구조만 남겨 리사이즈에 안정적이게
    buf = io.BytesIO(); im.save(buf, fmt, quality=95); return buf.getvalue()


class FakeResp:
    def __init__(self, data): self.data = data
    def raise_for_status(self): pass
    def json(self): return self.data


class FakeSession:
    def __init__(self, data): self.data, self.headers, self.calls = data, {}, []
    def get(self, url, params=None, timeout=None, headers=None):
        self.calls.append((url, params)); return FakeResp(self.data)


def test_pexels_and_unsplash_parse_and_dedup():
    pex = FakeSession({"photos": [
        {"id": 1, "width": 1000, "height": 1500, "url": "https://pexels.com/p/1", "photographer": "A", "alt": "lens",
         "src": {"medium": "m1", "portrait": "p1", "original": "o1"}},
        {"id": 2, "width": 1500, "height": 1000, "src": {"medium": "m2", "portrait": "p2"}},  # 가로 → 제외
        {"id": 3, "width": 800, "height": 1200, "src": {"medium": "m3", "portrait": "p3"}},   # 높이 부족 → 제외
    ]})
    uns = FakeSession({"results": [
        {"id": "u1", "width": 1000, "height": 1600, "alt_description": "glass", "user": {"name": "B"},
         "urls": {"small": "s", "raw": "https://img/u1?ixid=1"}, "links": {"html": "https://unsplash.com/u1"}},
    ]})
    pc, uc = PexelsClient("k", session=pex), UnsplashClient("k", session=uns)
    assert pex.headers["User-Agent"] and pex.headers["Authorization"] == "k"
    cands = search_candidates(["abstract lens", "server room"], [pc, uc], per_query=5)
    assert [c.key for c in cands] == [("pexels", "1"), ("unsplash", "u1")]  # 두 번째 검색어 결과는 중복으로 제거
    assert cands[1].full_url.endswith("w=1080&h=1350&fit=crop")
    assert pex.calls[0][1]["orientation"] == "portrait"


def test_dhash_detects_resized_copy():
    a = img_bytes((40, 60, 90))
    b_img = Image.open(io.BytesIO(a)).resize((160, 200)); buf = io.BytesIO(); b_img.save(buf, "PNG")
    other = img_bytes((200, 30, 30))
    assert hamming(dhash(a), dhash(buf.getvalue())) <= 4
    assert hamming(dhash(a), dhash(other)) > 8


def test_parse_score_tolerates_fences():
    s = parse_score('```json\n{"faces": false, "text_or_logo": true, "relevance": 4, "lower_third_clear": 5, "style_match": 3, "reason": "x"}\n```')
    assert s.text_or_logo and s.hard_fail and s.total == 0.0
    s2 = parse_score('{"faces": false, "text_or_logo": false, "brand_like": false, "relevance": 4, "lower_third_clear": 5, "style_match": 3}')
    assert s2.total == round(4*.4 + 5*.35 + 3*.25, 2)
    assert parse_score("no json here").error


def test_pick_skips_used_and_similar_and_hard_fails():
    db = Database(":memory:")
    used = Candidate("pexels", "9", "t", "f", 1000, 1500, image_bytes=img_bytes((10, 10, 10)))
    db.record_image("015_1", 1, "pexels", "9", "q", to_hex(dhash(used.image_bytes)))
    similar = Candidate("unsplash", "s", "t", "f", 1000, 1500, image_bytes=used.image_bytes)  # 같은 그림 다른 소스
    face = Candidate("pexels", "f", "t", "f", 1000, 1500, image_bytes=img_bytes((90, 90, 200)))
    good = Candidate("pexels", "g", "t", "f", 1000, 1500, image_bytes=img_bytes((200, 120, 20)))
    weak = Candidate("pexels", "w", "t", "f", 1000, 1500, image_bytes=img_bytes((20, 200, 120)))

    class Scorer:
        def score(self, b, headline, concept):
            if b == face.image_bytes: return VisionScore(faces=True, relevance=5, lower_third_clear=5, style_match=5)
            if b == good.image_bytes: return VisionScore(relevance=4, lower_third_clear=4, style_match=4)
            return VisionScore(relevance=2, lower_third_clear=2, style_match=2)

    r = pick([used, similar, face, weak, good], "헤드라인", "개념", Scorer(), db)
    assert r.chosen is good
    assert [c.external_id for c in r.skipped_used] == ["9"]
    assert [c.external_id for c in r.skipped_similar] == ["s"]
    assert [c.external_id for c, _ in r.scored] == ["f", "w", "g"]
    d = r.to_dict(); assert d["chosen"]["id"] == "g" and d["candidates"][0]["vision"]["hard_fail"]
    # 전부 약하면 chosen 없음
    assert pick([weak], "h", "c", Scorer(), None).chosen is None


def test_stat_validation_and_html():
    ok = Stat("55", "%", "AI 토큰 비용 절감률", "토큰 비용을 55% 줄였다고 밝혔다")
    validate_stat(ok, article_text="…회사는 토큰 비용을 55% 줄였다고 밝혔다. …")
    for bad in [Stat("55.123", "%", "x", "55.123%"), Stat("55", "", "x", "55"),
                Stat("55", "%", "열네자를넘는아주아주긴라벨입니다", "55%"), Stat("55", "%", "x", "원문엔 60%만 있다")]:
        try:
            validate_stat(bad); assert False, bad
        except StatError:
            pass
    try:
        validate_stat(ok, article_text="전혀 다른 본문"); assert False
    except StatError:
        pass
    assert (len_class("55", "%"), len_class("34.7", "조원"), len_class("1,000", "조원")) == ("short", "medium", "long")
    assert len_class("107", "조원") == "medium" and len_class("8.9", "억개") == "medium"
    h = render_html(ok, 3)
    assert 'data-len="short"' in h and ">55<span class=\"unit\">%</span>" in h and "3/6" in h and "<script" not in h
