# naver-cardnews — 로드맵 1단계: 뉴스 수집 → SQLite → 엑셀 큐 + 4단계 중복 제거

HANDOFF.md 5장 설계를 구현한 것이다. 네이버 뉴스 검색 API로 키워드별 기사를 받아 SQLite에 쌓고,
4단계 중복 제거로 같은 사건을 클러스터로 묶은 뒤, 대표 기사만 `대기` 상태로 엑셀 큐에 올린다.
사람은 엑셀에서 `상태`를 `승인`으로만 바꾸면 되고, 다음 실행 때 DB로 반영된다(로드맵 2단계가 승인 건만 제작).

## 설치 / 실행

```bash
pip install -r requirements.txt
cp .env.example .env         # keys.txt의 [Naver-cardnews] 값을 NAVER_CLIENT_ID / NAVER_CLIENT_SECRET에
python -m naver_cardnews run # import(엑셀→DB) → collect → export(DB→엑셀)
```

| 명령 | 역할 |
|---|---|
| `run` | 평소에 쓰는 명령. 엑셀의 승인 값을 DB로 읽고, 수집하고, 엑셀을 다시 만든다 |
| `collect` (`python collect.py`) | 수집 + 중복 제거 → `data/news.db` |
| `export` | DB → `data/news_queue.xlsx` 재생성 (이전 파일은 `data/backups/`에 보관) |
| `import` | 엑셀의 상태·카드폴더·게시URL·메모 → DB |
| `stats` | 상태별 건수, 클러스터 수 |

`python newsqueue.py`는 `run`과 같다(`queue.py`는 표준 라이브러리 이름이라 피했다).
옵션: `--keywords`, `--db`, `--out`, `--per-keyword N`(≤1000), `--days N`(기본 3), `--no-judge`.

## 수집 규칙 (`naver_cardnews/collect.py`)

- `news.json`, `sort=date`, `display=100`, 키워드별 호출. 키워드는 `keywords.yaml`.
- `link`가 `n.news.naver.com`인 것만 채택 (본문 파서 `naver_article.py`가 동작하는 범위). 나머지는 버린다.
- `title`/`description`의 `<b>` 태그·HTML 엔티티 제거.
- `id`는 네이버 `oid_aid`. 언론사는 `originallink` 도메인.

## 니치 필터 (`keywords.yaml`의 `topic_terms` / `exclude_terms`)

네이버 검색은 'AI'가 어디든 들어간 기사를 느슨하게 돌려줘, 필터 없이는 대기 건의 약 1/3이 지자체 예산·
정치·코스피 시황 같은 니치 밖 기사였다(2026-10-21 실측 200건 중 65건). 그래서 1단계(URL) 다음, 중복 제거 전에
제목 기준으로 거른다.

- `topic_terms` 중 하나가 제목에 있어야 한다(AI, 인공지능, 반도체, 엔비디아, 빅테크, 로봇 …). 비워 두면 필터가 꺼진다.
- `exclude_terms`가 제목에 있으면 제외한다(코스피, 시황, 특징주, 단신, 박람회, 채용 …).
- 걸러진 기사는 버리지 않고 상태 `제외`, 중복사유 `니치 외(...)`로 엑셀에 남겨 기준을 조정할 수 있게 했다.
  대표가 되지 않으므로 중복 클러스터에도 영향을 주지 않는다.

실측: 규칙 필터 적용 후 대기 200건 → 116건, 니치 외 86건.

규칙을 통과한 기사 중 **새 클러스터 대표가 되는 것**(중복은 대표를 따라감)에는 Claude Haiku(`claude-haiku-5-5`)에게
"'AI 뉴스 3분 브리핑' 카드뉴스 소재로 적합한가"를 한 번 더 묻는다(`naver_cardnews/judge.py`의 `on_niche`).
AI가 곁다리로 언급되는 정치 발언·시황·지자체 행사·채용 홍보를 걸러내는 용도다. 부적합이면 상태 `제외`,
사유 `니치 외(Haiku 판정)`. `ANTHROPIC_API_KEY`가 없거나 `NAVER_CARDNEWS_NICHE_JUDGE=off`면 건너뛴다.
호출은 대표 기사 수(실측 110건 안팎)만큼이며 Haiku 요금 기준 한 번 수집에 1원 미만이다.

## 4단계 중복 제거 (`naver_cardnews/dedup.py`)

| 단계 | 기준 | 결과 |
|---|---|---|
| 1 | `oid_aid` 완전 일치 | 저장하지 않음. 걸린 키워드만 `키워드` 열에 추가 (이 단계 뒤에 니치 필터) |
| 2 | 정규화 제목 일치 (`[단독]`·`[속보]`·괄호·특수문자·공백 제거, 72시간 창) | 같은 클러스터, `제외` |
| 3 | 제목+요약 문자 2-gram Jaccard ≥ **0.4**, 72시간 창 → `cluster_id` 부여, 대표 1건만 `대기` | 같은 클러스터, `제외`. 0.2~0.4 경계(제목 단독 유사도 포함)는 Claude Haiku(`claude-haiku-5-5`)에게 "같은 사건인가?" 판정 |
| 4 | 최근 14일 `게시완료` 건과 같은 방식 비교 | `제외`, 중복사유 `기게시(...)` |

`점수` = 클러스터 안의 언론사 수(여러 언론이 다룬 이슈 = 중요도). 임계값은 `.env`의
`NAVER_CARDNEWS_SIM_THRESHOLD` / `NAVER_CARDNEWS_SIM_BORDERLINE`로 조정한다.

2026-10-21 실측(키워드 7개, API 700건 → 네이버뉴스 258건): 문서 시작값 0.5에서는 "우리금융 34.7조 공급"(0.49),
"문샷AI 천재소년"(0.46), "반도체의 날 훈장"(0.42)처럼 명백한 같은 사건을 놓쳐 0.4로 내렸다. 0.2~0.4에는
같은 사건(코스피 5700 반등 0.30, 네이버 D2SF 투자 0.33)과 다른 사건이 섞여 있어 이 구간을 Haiku 판정에 맡긴다.
매체마다 요약문이 달라 같은 사건도 합산 유사도가 0.15까지 떨어지는 경우가 있어(카카오 비전 인코더 4건),
경계 후보를 고를 때는 제목 단독 유사도도 함께 본다(자동 판정에는 쓰지 않음). Haiku 실측: 0.26~0.33 쌍 7개를
모두 올바르게 같은 사건으로 묶었다.
주의: 네이버 `description`이 기사 본문이 아닌 페이지의 다른 블록(뉴스레터 등)을 담는 경우가 있어 엉뚱한 쌍이
0.5 이상으로 묶일 수 있다(서울경제 사례). 엑셀의 `중복사유`로 확인 가능.
Haiku 판정은 `ANTHROPIC_API_KEY`가 있을 때만 켜지고, 없으면 경계 구간은 '다름'으로 둔다. `--no-judge`로 두 판정을 모두 끈다.

## 엑셀 큐 (`naver_cardnews/queue.py`)

시트 `뉴스큐` 컬럼: `id(oid_aid)` · 수집일시 · 키워드 · 제목 · 언론사 · 발행일시 · naver_link · originallink ·
요약 · 정규화제목 · cluster_id · 대표여부 · 중복사유 · 점수 · 상태(대기/승인/제작완료/게시완료/제외) ·
카드폴더 · 게시URL · 메모. 노란 열(상태·카드폴더·게시URL·메모)만 사람이 편집한다.
제외 행도 회색으로 함께 내보내 클러스터를 확인할 수 있게 했다.

- 원본은 SQLite, 엑셀은 매 실행 때 재생성. 승인 값은 엑셀 → DB로 읽어온다.
- 엑셀이 열려 있으면(`~$news_queue.xlsx` 존재) 쓰지 않고 중단한다. 저장 전 `data/backups/`에 백업(최근 10개).

## 테스트

```bash
python -m pytest -q
```

## 다음 단계 (HANDOFF 로드맵)

2. 승인 건 일괄 제작: `status='승인'`인 행의 `naver_link`를 `make_card.py`에 넘기고 `카드폴더` 기록
3. 숫자 카드 템플릿 + `used_photos` + 비전 사진 선택
