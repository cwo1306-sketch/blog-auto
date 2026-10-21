# naver-cardnews — 1단계: 뉴스 수집 → SQLite → 엑셀 검토 큐

네이버 뉴스 검색 API로 AI·테크 키워드 기사를 모아 SQLite에 쌓고, 4단계 중복 제거를 거친 고유 기사만
사람이 검토할 엑셀 큐로 내보냅니다. (카드뉴스 자동화 로드맵 1단계)

## 설치 / 실행

```bash
pip install -r requirements.txt
cp .env.example .env          # NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 입력
python -m naver_cardnews run  # 수집 + 엑셀 출력 (data/news.db, data/review_queue.xlsx)
```

| 명령 | 역할 |
|---|---|
| `collect` | keywords.yaml의 모든 키워드를 검색해 SQLite에 저장 (중복 판정 포함) |
| `export` | 검토 대기(`pending`) 고유 기사를 엑셀로 출력. `--mark-exported`를 주면 다음 큐에서 제외 |
| `run` | collect + export |
| `stats` | 단계별 중복 수, 검토 대기 수 |

옵션: `--keywords 파일`, `--db 경로`, `--out 경로`, `--per-keyword N`(키워드당 최대 1000), `--days N`(수집 기간, 기본 3일).

## 키워드

`keywords.yaml`의 `groups:` 아래에 그룹명 → 키워드 목록으로 적습니다. 그룹명은 엑셀의 "키워드 그룹" 열에
들어가 필터용으로 씁니다. 현재 파일은 AI·테크 초안입니다.

## 4단계 중복 제거 (`naver_cardnews/dedup.py`)

| 단계 | 기준 | 잡아내는 경우 |
|---|---|---|
| 1 | 정규화 URL 일치 (추적 파라미터·모바일 도메인·http/https 통일) | 같은 기사를 다른 키워드로 다시 받음 → 저장하지 않음 |
| 2 | 정규화 제목 일치 (`[속보]` 머리말, 매체명 꼬리, 기호 제거) | 재송고, 포털 재게시 |
| 3 | 제목 2-gram 자카드 유사도 ≥ 0.80 | 통신사 기사 받아쓰기, 어미만 바꾼 제목 |
| 4 | 요약문 SimHash(63비트) 해밍 거리 ≤ 6 | 제목은 달라도 내용이 같은 기사. 요약이 짧으면(토큰 < 15) 건너뜀 |

2~4단계 중복은 버리지 않고 `dedup_stage`, `duplicate_of`로 원본에 묶어 저장합니다. 엑셀의 "중복 수" 열이
이 묶음 크기이며, 여러 매체가 다룬 기사일수록 커지므로 화제성 신호로 씁니다. 3·4단계 비교는 최근 N일의
고유 기사하고만 합니다.

## 엑셀 검토 큐

시트 "검토 큐": ID · 선택(O/X/보류 드롭다운) · 키워드 그룹 · 키워드 · 발행 시각(KST) · 매체 · 제목 · 요약 ·
중복 수 · 원문 링크 · 네이버 링크 · 메모. 시트 "요약": 생성 시각과 단계별 중복 통계.
"선택" 열은 2단계(검토 결과 반영 → 카드뉴스 생성) 입력으로 쓰도록 비워 둡니다.

## DB 스키마 (`naver_cardnews/db.py`)

`articles`: 기사 본문 메타 + `dedup_stage`(0=고유) + `duplicate_of` + `review_status`
(`pending`/`approved`/`rejected`/`exported`). `collect_runs`: 실행 로그.

## 테스트

```bash
python -m pytest -q
```

## 1단계 구현 시 가정 (HANDOFF.md 미확인)

이 구현은 HANDOFF.md 원문을 읽지 못한 상태에서 작성했습니다. 아래는 문서와 다를 수 있는 가정입니다.

- 수집 소스는 네이버 **뉴스 검색 API**(`openapi.naver.com/v1/search/news.json`), 크롤링이 아님.
- "4단계 중복 제거"는 위 표의 URL → 제목 일치 → 제목 유사 → 본문 지문 순서로 정의.
- 키워드 초안은 `keywords.yaml`의 AI·테크 목록. 문서의 초안이 있으면 이 파일만 교체하면 됨.
- 수집 기간 기본 3일, 키워드당 최대 100건.
