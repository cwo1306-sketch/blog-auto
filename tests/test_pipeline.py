from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path

from openpyxl import load_workbook

from naver_cardnews.collector import collect
from naver_cardnews.config import Settings
from naver_cardnews.db import Database
from naver_cardnews.export import export_review_queue


def rfc(dt):
    return format_datetime(dt)


class FakeClient:
    def __init__(self, data):
        self.data = data

    def iter_items(self, query, limit, sort="date"):
        return iter(self.data.get(query, [])[:limit])


def test_collect_and_export(tmp_path: Path):
    now = datetime.now(timezone.utc)
    old = now - timedelta(days=10)
    data = {
        "엔비디아": [
            {"title": "<b>엔비디아</b>, 신형 AI 칩 공개", "description": "블랙웰 후속작",
             "link": "https://n.naver.com/1", "originallink": "https://a.com/1?utm_source=x", "pubDate": rfc(now)},
            {"title": "[속보] 엔비디아 신형 AI 칩 공개 | 연합", "description": "블랙웰 후속작",
             "link": "https://n.naver.com/2", "originallink": "https://b.com/2", "pubDate": rfc(now)},
            {"title": "오래된 기사", "description": "", "link": "https://n.naver.com/9",
             "originallink": "https://c.com/9", "pubDate": rfc(old)},
        ],
        "AI 반도체": [
            {"title": "엔비디아, 신형 AI 칩 공개", "description": "블랙웰 후속작",
             "link": "https://n.naver.com/1", "originallink": "https://www.a.com/1/", "pubDate": rfc(now)},
            {"title": "SK하이닉스 HBM4 공급 계약", "description": "내년 상반기 양산",
             "link": "https://n.naver.com/3", "originallink": "https://d.com/3", "pubDate": rfc(now)},
        ],
    }
    settings = Settings(client_id="x", client_secret="y", db_path=tmp_path / "t.db",
                        output_path=tmp_path / "q.xlsx", per_keyword=50, max_age_days=3,
                        keyword_groups={"AI 반도체": ["엔비디아", "AI 반도체"]})
    db = Database(settings.db_path)
    report = collect(settings, db, client=FakeClient(data))

    assert report.fetched == 5
    assert report.inserted == 2
    assert report.skipped_old == 1
    assert report.by_stage == {1: 1, 2: 1}

    n = export_review_queue(db, settings.output_path, mark_exported=True)
    assert n == 2
    ws = load_workbook(settings.output_path)["검토 큐"]
    rows = list(ws.iter_rows(min_row=2, values_only=True))
    titles = {r[6] for r in rows}
    assert titles == {"엔비디아, 신형 AI 칩 공개", "SK하이닉스 HBM4 공급 계약"}
    dup_counts = {r[6]: r[8] for r in rows}
    assert dup_counts["엔비디아, 신형 AI 칩 공개"] == 1   # 2단계 중복 1건이 묶임

    assert db.stats()["pending"] == 0                     # mark_exported 반영
    assert export_review_queue(db, tmp_path / "q2.xlsx") == 0
