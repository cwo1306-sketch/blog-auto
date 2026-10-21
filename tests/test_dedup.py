from naver_cardnews.db import Article, Database
from naver_cardnews.dedup import SIMHASH_MIN_TOKENS, Deduplicator, hamming, simhash
from naver_cardnews.normalize import normalize_title, normalize_url


def make(title, url, desc="", keyword="AI"):
    return Article(
        url_key=normalize_url(url), title_key=normalize_title(title),
        simhash=simhash(desc, min_tokens=SIMHASH_MIN_TOKENS), title=title, description=desc,
        link=url, original_link=url, source="example.com",
        pub_date="2099-01-01T00:00:00+00:00", keyword=keyword, keyword_group="g",
    )


def insert_unique(db, dedup, art):
    new_id = db.insert(art)
    dedup.remember(new_id, art.title, art.simhash)
    return new_id


def test_stage1_url():
    db = Database(":memory:")
    d = Deduplicator(db)
    base = make("엔비디아 신형 칩 공개", "https://a.com/1?utm_source=x")
    oid = insert_unique(db, d, base)
    r = d.check(normalize_url("https://www.a.com/1/"), "다른제목", "다른 제목", 123)
    assert (r.stage, r.duplicate_of) == (1, oid)


def test_stage2_title():
    db = Database(":memory:")
    d = Deduplicator(db)
    oid = insert_unique(db, d, make("엔비디아, 신형 AI 칩 공개", "https://a.com/1"))
    dup = make("[단독] 엔비디아 신형 AI 칩 공개 - 뉴스1", "https://b.com/2")
    r = d.check(dup.url_key, dup.title_key, dup.title, dup.simhash)
    assert (r.stage, r.duplicate_of) == (2, oid)


def test_stage3_similar_title():
    db = Database(":memory:")
    d = Deduplicator(db)
    oid = insert_unique(db, d, make("오픈AI, 차세대 모델 GPT 공개하며 경쟁 본격화", "https://a.com/1"))
    dup = make("오픈AI, 차세대 모델 GPT 공개하며 경쟁 본격화한다", "https://b.com/2")
    r = d.check(dup.url_key, dup.title_key, dup.title, dup.simhash)
    assert (r.stage, r.duplicate_of) == (3, oid)


def test_stage4_simhash_body():
    db = Database(":memory:")
    d = Deduplicator(db)
    body = ("삼성전자가 차세대 고대역폭메모리 HBM4 양산을 시작했다고 21일 밝혔다. 엔비디아 등 주요 고객사에 "
            "공급될 예정이며 수율 안정화로 하반기 실적 개선이 기대된다고 회사 측은 설명했다.")
    oid = insert_unique(db, d, make("삼성 HBM4 양산 돌입", "https://a.com/1", body))
    dup = make("삼성전자 실적 개선 기대", "https://b.com/2", body + " 업계는 환영했다.")
    assert hamming(simhash(body), dup.simhash) <= 6
    r = d.check(dup.url_key, dup.title_key, dup.title, dup.simhash)
    assert (r.stage, r.duplicate_of) == (4, oid)


def test_stage4_skipped_for_short_description():
    db = Database(":memory:")
    d = Deduplicator(db)
    insert_unique(db, d, make("엔비디아 신형 칩", "https://a.com/1", "블랙웰 후속작"))
    other = make("SK하이닉스 HBM4 계약", "https://b.com/2", "내년 상반기 양산")
    assert other.simhash == 0
    assert d.check(other.url_key, other.title_key, other.title, other.simhash).stage == 0


def test_unrelated_is_unique():
    db = Database(":memory:")
    d = Deduplicator(db)
    insert_unique(db, d, make("엔비디아 신형 칩 공개", "https://a.com/1", "GPU 시장 점유율 확대"))
    other = make("테슬라 로보택시 서울 시범 운행", "https://b.com/2", "자율주행 택시가 강남에서 운행을 시작한다")
    r = d.check(other.url_key, other.title_key, other.title, other.simhash)
    assert r.stage == 0
