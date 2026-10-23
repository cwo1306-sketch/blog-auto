from naver_cardnews.db import Article, Database
from naver_cardnews.dedup import Deduplicator
from naver_cardnews.normalize import normalize_title

NOW = "2026-10-21T03:00:00+00:00"


def make(aid, title, desc="", press="a.com", pub=NOW, keyword="AI"):
    return Article(id=aid, keyword=keyword, title=title, press=press, pub_date=pub,
                   naver_link=f"https://n.news.naver.com/article/{aid.replace('_', '/')}",
                   originallink=f"https://{press}/{aid}", description=desc,
                   title_key=normalize_title(title))


def store(db, dedup, art):
    d = dedup.decide(art)
    if d.stage == 0:
        db.insert(art, db.next_cluster_id(), True, "대기")
    else:
        db.insert(art, d.cluster_id, False, "제외", d.reason)
    db.conn.commit()
    return d


def test_stage1_same_naver_id():
    db = Database(":memory:")
    dd = Deduplicator(db)
    store(db, dd, make("001_1", "엔비디아 신형 칩 공개"))
    d = dd.decide(make("001_1", "다른 제목", keyword="반도체"))
    assert d.stage == 1 and d.status == "제외"


def test_stage2_title_match_joins_cluster():
    db = Database(":memory:")
    dd = Deduplicator(db)
    d0 = store(db, dd, make("001_1", "엔비디아, 신형 AI 칩 공개"))
    d = store(db, dd, make("002_1", "[단독] 엔비디아 신형 AI 칩 공개 - 뉴스1", press="b.com"))
    assert d.stage == 2 and d.status == "제외"
    assert db.get("002_1")["cluster_id"] == db.get("001_1")["cluster_id"]
    assert db.get("002_1")["is_representative"] == 0


def test_stage3_near_duplicate_within_72h():
    db = Database(":memory:")
    dd = Deduplicator(db)
    desc = "오픈AI가 21일 차세대 모델 GPT-6를 공개했다. 추론 성능이 두 배로 향상됐다고 밝혔다."
    store(db, dd, make("001_1", "오픈AI, 차세대 모델 GPT-6 공개", desc))
    d = store(db, dd, make("002_1", "오픈AI GPT-6 공개…추론 성능 2배", desc + " 업계는 주목했다.",
                            press="b.com", pub="2026-10-21T20:00:00+00:00"))
    assert d.stage == 3 and d.status == "제외"
    # 창 밖(4일 뒤)이면 새 클러스터
    d2 = store(db, dd, make("003_1", "오픈AI GPT-6 공개…추론 성능 2배", desc, press="c.com",
                             pub="2026-10-25T20:00:00+00:00"))
    assert d2.stage == 0


def test_stage3_borderline_uses_judge():
    class YesJudge:
        def same_event(self, *a):
            return True

        def on_niche(self, *a):
            return True

    db = Database(":memory:")
    dd = Deduplicator(db, threshold=0.5, borderline=0.35, judge=YesJudge())
    store(db, dd, make("001_1", "삼성전자 HBM4 양산 시작", "삼성전자가 차세대 HBM4 양산을 시작했다고 밝혔다"))
    d = store(db, dd, make("002_1", "삼성전자, HBM4 양산 돌입", "삼성전자가 차세대 HBM4 양산에 들어갔다고 밝혔다. 수율이 관건",
                            press="b.com"))
    assert d.stage == 3 and "haiku=같음" in d.reason
    assert dd.judge_calls >= 1


def test_stage4_already_posted():
    db = Database(":memory:")
    dd = Deduplicator(db)
    desc = "테슬라가 서울에서 로보택시 시범 운행을 시작했다. 강남 일대에서 50대가 운행된다."
    store(db, dd, make("001_1", "테슬라 로보택시 서울 시범 운행", desc, pub="2026-10-15T00:00:00+00:00"))
    db.conn.execute("UPDATE articles SET status='게시완료', posted_at='2026-10-16T00:00:00+00:00'")
    db.conn.commit()
    d = store(db, dd, make("002_1", "테슬라 로보택시, 서울 강남 시범 운행 개시", desc, press="b.com"))
    assert d.stage == 4 and d.reason.startswith("기게시")
    assert db.get("002_1")["status"] == "제외"


def test_unrelated_is_new_cluster_and_score_counts_press():
    db = Database(":memory:")
    dd = Deduplicator(db)
    store(db, dd, make("001_1", "엔비디아 신형 칩 공개", "GPU 시장 점유율 확대"))
    d = store(db, dd, make("002_1", "AI 기본법 시행령 입법예고", "과기정통부가 AI 기본법 시행령을 입법예고했다", press="b.com"))
    assert d.stage == 0 and d.status == "대기"
    store(db, dd, make("003_1", "[속보] 엔비디아 신형 칩 공개", "GPU 시장 점유율 확대", press="c.com"))
    db.refresh_scores()
    assert db.get("001_1")["score"] == 2
    assert db.get("002_1")["score"] == 1
