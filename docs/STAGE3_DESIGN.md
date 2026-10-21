# 3단계 설계: 무료 스톡 검색(Pexels+Unsplash) + 비전 선택 + used_images + 숫자 카드

로드맵 3단계(HANDOFF 7장). **이미지 소스는 무료 스톡 검색**으로 가고, 품질은 소스가 아니라 **고르는 방식**(검색어 2종,
비전 검수, 재사용 금지, 숫자 카드로 사진 수 자체를 줄임)으로 끌어올린다. 2026-10-21 결정: 생성(Gemini 3.1 Flash가
4개 모델 비교에서 최선)은 비용·키 발급 문제로 보류하고, 2주 테스트 지표에서 "사진이 뻔하다"가 문제로 확인되면 표지
1장에만 생성을 붙인다. 아래 4장은 그때를 위해 남겨 둔 생성 경로이며, 지금 구현하는 경로는 **4-S장(검색)**이다.
구현된 부품은 이 저장소 `naver_cardnews/stock.py`, `vision_pick.py`, `imagehash.py`, `db.py(used_images)`, `stat_card.py`. 대상 코드는 로컬 프로젝트(`make_card.py`, `writer.py`, `validate.py`, `pexels.py`, `render.py`,
`templates/card.css`)이고, 이 저장소의 `naver_cardnews/`(1단계)와는 SQLite(`data/news.db`)로 이어진다.

> 전제: 2단계(승인 건 일괄 제작)가 `status='승인'` 행을 `make_card.py`에 넘기는 배치 루프를 갖는다.
> 3단계는 그 루프 안에서 **한 장(slide)을 만드는 방식**을 바꾼다.

---

## 1. 목표와 범위

| 목표 | 왜 |
|---|---|
| 사진 카드의 이미지를 Pexels 검색 → **Gemini 생성**으로 바꾼다 | 스톡의 "로봇·파란 회로" 반복, 저작권·로고·실존 인물 위험 제거. 스타일 일관성 확보 |
| **숫자 카드(stat)** 템플릿 추가 | 수치가 핵심인 장은 사진 없이 큰 숫자가 더 읽히고 저장률에 유리. 이미지 비용도 절감 |
| **사용 이미지 기록**(`used_images`) | 생성 이미지도 비슷한 구도가 반복될 수 있다. 같은 프롬프트·유사 이미지 재사용 금지 |
| **비전 검수**로 후보 선택 | alt 텍스트만 보고 고르던 문제. 생성 결과도 얼굴·글자·로고·엉뚱한 장면이 섞이므로 실제로 보고 고른다 |

범위 밖: Instagram 게시(5단계), 스케줄(6단계). Pexels는 **폴백**으로만 남긴다.

---

## 2. 한 게시물(6장)의 장 구성 규칙

```
1 표지      photo   (생성 이미지 풀블리드 + 헤드라인)
2~5 본문    photo | stat   ← writer가 장마다 정한다. stat은 최대 2장, 연속 금지
6 마무리    photo | plain  (요약·댓글 질문·저장/공유/팔로우). 이미지 재사용 없이 단색 배경도 허용
```

- 사진 카드(photo)는 게시물당 **3~5장 생성**. 장당 후보 2장 → 비전 검수로 1장 선택.
- stat 카드는 **기사 원문에 그 수치가 그대로 있을 때만**(`validate.py` 수치 대조 통과) 허용. 없으면 photo로 강등.

---

## 3. Writer 스키마 변경 (`writer.py`)

기존 장 객체에 세 필드를 더한다. 하위 호환을 위해 없으면 `photo`로 본다.

```json
{
  "slide_no": 3,
  "slide_type": "stat",                      // "photo" | "stat" | "plain"
  "headline": "토큰 비용 55% 절감",
  "body": "…",
  "stat": { "value": "55", "unit": "%", "label": "AI 토큰 비용 절감률", "source_quote": "토큰 비용을 55% 줄였다" },
  "image": {                                 // slide_type == "photo"일 때
    "concept_ko": "데이터 입자가 유리 렌즈로 모여드는 장면",
    "prompt_en": "a translucent glass lens made of flowing light, particles of data converging into it",
    "mood": "calm" | "tense" | "bright"
  }
}
```

Writer 프롬프트에 추가할 규칙:
- `image.prompt_en`은 **장면만** 쓴다(스타일·금지어는 코드가 붙인다). 은유형 1개 + 구체형 1개를 섞어 2개 후보 프롬프트를 내게 해도 된다(`prompt_en_alt`).
- 실존 기업명·제품명·인물명을 프롬프트에 넣지 않는다("엔비디아 로고" 금지 → "AI 가속기 칩 추상화").
- `stat.source_quote`는 원문에서 수치가 포함된 문장을 **그대로** 복사한다(검수 입력).

---

## 4-S. 스톡 검색 모듈 `stock.py` (구현됨, 기본 경로)

- Pexels `search`(orientation=portrait, size=large) + Unsplash `search/photos`(orientation=portrait, content_filter=high).
  Pexels는 `User-Agent` 헤더 필수. 세로가 아니거나 높이 1350px 미만은 버린다.
- Writer가 장마다 **검색어 2개**(은유형 + 구체형, 영어)를 낸다: `image.queries: ["abstract glass lens light", "camera aperture macro dark"]`.
  검색어에 실존 기업·제품·인물명은 넣지 않는다.
- 검색어 2개 × 소스 2개 × 6장 = 최대 24후보 → (소스, id) 중복 제거 → 썸네일 다운로드 → 5장 비전 검수로.
- 비용 0. 한도: Pexels 시간당 200회, Unsplash 시간당 50회(데모 키). 게시물당 호출 ≤ 20회.
- 톤 통일은 사진이 아니라 템플릿에서: 기존 하단 스모크그레이 그라데이션에 더해 사진 전체에 약한 어두운 틴트(검정 25~35%)를 얹는다.
- 출처 표기: Pexels·Unsplash 라이선스상 필수는 아니지만 `used_images.photographer/page_url`을 기록해 두고 캡션에 쓸 수 있게 한다.

## 4. (보류) 이미지 생성 모듈 `imagegen.py`

### 4.1 호출
- 모델: `gemini-3.1-flash-image` (Google AI Studio, `google-genai` SDK). 비교 테스트는 Figma 경유였지만 운영은 Gemini API 직접 호출.
- 비율 `4:5`(1080×1350에 가장 가까움). 응답이 928×1152처럼 작게 오면 `render.py`에서 cover-fit으로 채운다(가로 1080 기준 업스케일 16%, 허용 범위).
- 장당 후보 **2장**(프롬프트 2개 × 1장, 또는 같은 프롬프트 2장). 재시도 1회.
- 키: `GEMINI_API_KEY` **신규 발급 필요**(`keys.txt`에 `[Gemini-cardnews]`로 추가). 현재 키 목록에 없음.

### 4.2 프롬프트 조립
```
{scene}  ← writer의 prompt_en
, vertical 4:5 editorial photograph, cinematic, shallow depth of field,
moody dark background in charcoal and smoke-grey (#848884 family), one warm yellow (#FFE500) highlight,
lower third darker and uncluttered for headline overlay.
No people, no faces, no hands, no logos, no brand marks, no text, no letters, no numbers, no robots, no flags.
Photorealistic, high-end tech magazine style.
```
- 스타일 꼬리는 상수(`STYLE_SUFFIX`)로 고정해 게시물 간 톤을 맞춘다. 표지만 `mood`에 따라 하이라이트 강도 문구를 바꾼다.
- 금지어 목록은 비전 검수 기준(5장)과 같은 상수에서 가져온다(한 곳에서 관리).

### 4.3 출력과 기록
- 파일: `output/<oid_aid>/img/s{slide_no}_c{candidate}.png`
- `meta.json`에 장별 `image: {source: "gemini", model, prompt, candidates: [...], chosen, usage}` 기록.
- 비용: 응답의 토큰 사용량을 `meta.json`에 쌓고, 월 누적이 **이미지 예산**(초기값 월 2만 원, 전체 5만 원 상한의 일부)을 넘으면 Pexels 폴백으로 자동 전환 + Discord 알림(4단계와 연결).

### 4.4 폴백
생성 실패(오류·안전 필터·예산 초과) → `pexels.py`로 후보 15장 검색 → 같은 비전 검수(5장)로 선택. 이 경우 `image.source = "pexels"`,
`used_images`에 Pexels ID 기록(재사용 금지).

---

## 5. 비전 검수·선택 `vision_pick.py` (구현됨)

후보 이미지(생성 2장 또는 Pexels 상위 6장 썸네일)를 **Claude에게 이미지로 보여주고** 점수를 매긴다.
모델은 `claude-haiku-5-5`(비전 지원, 저렴). 판정이 갈리는 표지만 `claude-sonnet-5-5`로 재확인(선택).

입력: 이미지 + 장의 `headline`, `concept_ko`.
출력(JSON 강제):
```json
{ "faces": false, "text_or_logo": false, "brand_like": false, "relevance": 4, "lower_third_clear": 4,
  "style_match": 5, "verdict": "pass" | "fail", "reason": "…" }
```
규칙:
- `faces`/`text_or_logo`/`brand_like` 중 하나라도 true → **즉시 탈락**(이미 규칙으로 금지된 항목의 실제 확인).
- 나머지는 1~5점, 가중합 `relevance*0.4 + lower_third_clear*0.35 + style_match*0.25` 최고점 선택.
- 후보 전부 탈락 → 프롬프트에 탈락 사유를 덧붙여 **1회 재생성**, 또 실패하면 Pexels 폴백, 그것도 실패하면 `plain`(단색 배경)으로 강등하고 meta에 기록.
- 모든 판정 결과는 `meta.json`의 `image.candidates[].vision`에 남긴다(나중에 프롬프트 튜닝 근거).

`render.py`의 기존 QA(텍스트 위치·대비·8MB)는 그대로 두고, 비전 검수는 **렌더 전** 단계로 들어간다.

---

## 6. 사용 이미지 기록 `used_images` (구현됨, SQLite `data/news.db`)

```sql
CREATE TABLE used_images (
  id          INTEGER PRIMARY KEY,
  article_id  TEXT NOT NULL,           -- oid_aid
  slide_no    INTEGER NOT NULL,
  source      TEXT NOT NULL,           -- gemini | pexels
  external_id TEXT,                    -- pexels photo id (gemini는 NULL)
  prompt      TEXT,                    -- gemini 프롬프트 전체
  phash       TEXT NOT NULL,           -- 64bit perceptual hash (imagehash)
  file_path   TEXT NOT NULL,
  used_at     TEXT NOT NULL,
  posted      INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_used_images_phash ON used_images(phash);
```
재사용 금지 규칙(선택 직전에 검사):
- Pexels: `external_id` 일치 → 탈락.
- Gemini: 최근 **30일** 기록과 pHash 해밍 거리 ≤ 8 → 탈락(같은 구도 반복 방지). 프롬프트 `scene` 문자열이 완전히 같아도 탈락.
- 1단계 `articles`와 `article_id`로 조인해 "어떤 기사·어떤 장에서 썼는지" 엑셀로 뽑을 수 있게 한다.

---

## 7. 숫자 카드 템플릿 (구현됨: `templates/stat_card.html`, `stat_card.py`)

레이아웃(1080×1350):
```
┌──────────────────────────────┐
│ AI로 재가공한 뉴스     (라벨)  │  좌상단, 기존과 동일
│                              │
│          55%                 │  value+unit: Pretendard ExtraBold, 300~360px, 노랑 #FFE500
│   AI 토큰 비용 절감률         │  label: 48px, 흰색, 1줄 (최대 14자)
│                              │
│  ── 원문 인용 한 줄 ──        │  source_quote 요약: 32px, 회색 #B8BBB8, 최대 2줄
│                      3/6     │  페이지 표시 기존과 동일
└──────────────────────────────┘
배경: 스모크그레이 그라데이션(#2A2C2A → #848884 대각선) + 아주 약한 노이즈 텍스처. 사진 없음.
```
구현:
- `card.css`에 `.card--stat` 변형 추가. `render.py`는 `slide_type`로 템플릿 분기.
- 자동 크기: value 글자 수 1~3자 360px, 4~5자 300px, 6자 이상(예: "1,000조")은 240px. 그래도 폭 초과면 기존 QA가 잡아 writer에 "짧게"를 요구(재작성 루프).
- 금지: 소수점 둘째 자리 이상, 단위 없는 숫자, 원문에 없는 환산치(예: 달러→원 환산은 writer가 하지 않는다).
- `validate.py`: stat 카드는 `value+unit`이 `source_quote` 안에 있고 `source_quote`가 원문에 있는지 **둘 다** 확인(기존 "숫자가 어딘가 있으면 통과" 약점 보완).

---

## 8. 파이프라인 흐름 (make_card.py 한 장 처리)

```
writer → validate(수치·글자수) ──┐
                                  ├─ photo: stock 검색(2질의) → vision_pick → used_images 검사 → 원본 저장+기록
                                  ├─ stat : (이미지 없음) → used_images 기록 없음
                                  └─ plain: 단색
→ render(템플릿 분기) → render QA(기존) → meta.json(usage·vision·image 기록)
→ articles.status='제작완료', card_folder 기록(2단계 배치가 수행)
```
실패 정책: 한 장이 실패하면 그 장만 재시도(최대 2회), 게시물 전체 실패 시 `status`는 `승인` 유지 + `memo`에 사유.

---

## 9. 비용 추정 (게시물 1건)

| 항목 | 호출 | 비고 |
|---|---|---|
| 스톡 검색 | ≤ 20회 | 0원 |
| 비전 검수 Haiku 5.5 | 사진 장당 ≤ 8회(재검색 시 +8) | 수원 단위 |

2026-10-21 실측(조선비즈 카카오 비전 인코더 기사, 6장): writer Sonnet 5.5 입력 2,619 / 출력 1,374 토큰(약 $0.019),
비전 호출 40회(재검색 1회 포함, 재검색 중복 심사는 이후 제거), 전체 144초. 게시물당 비용은 50원 미만.
| 원고 Sonnet 5.5 | 기존과 동일 | |

가드: `meta.json` usage 합산 → 월 상한(5만 원) 도달 시 생성 중단·Pexels 폴백·Discord 알림. 첫 2주는 하루 1~2건이라 실측 후 상한을 조정한다.

---

## 10. 표시·정책

- 좌상단 라벨 "AI로 재가공한 뉴스"는 유지. 생성 이미지를 쓴 장에는 하단 페이지 표시 옆에 **"이미지: AI 생성"** 24px 캡션을 추가(플랫폼 AI 표시 대응). stat·plain 장은 캡션 없음.
- 프롬프트 금지어에 실존 기업·제품·인물을 포함하고, 비전 검수의 `brand_like`로 2중 확인한다.
- 기사 본문 사용 정책(HANDOFF 8장 미결)은 3단계와 무관하게 결정 필요. 이미지 생성은 본문을 쓰지 않고 writer 원고만 쓴다.

---

## 11. 구현 순서와 완료 기준

1. `writer.py` 스키마 확장 + `validate.py` stat 검증 → 기존 샘플(`output/015_0005344713`)로 회귀 확인
2. `templates/card.css` `.card--stat` + `render.py` 분기 → `rerender.py`로 숫자 카드 1장 렌더, QA 통과
3. `imagegen.py`(Gemini) + `used_images` 테이블 + pHash → 표지 1장 생성·기록
4. `vision_pick.py` → 후보 2장 중 선택, 탈락 사유 meta 기록
5. `make_card.py`에 통합, Pexels 폴백 경로 테스트(키를 일부러 비워서)
6. 기사 3건으로 end-to-end, 장당 비용 실측 → 예산 가드 값 확정

완료 기준: 승인 기사 1건 → 6장 PNG + meta.json이 사람 개입 없이 나오고, 얼굴·글자·로고 0건, stat 카드 수치가 원문 문장과 일치, used_images에 기록, 장당 비용이 meta에 남는다.

## 12. 남은 결정

- Unsplash 키 발급 여부(없으면 Pexels만으로 시작)
- Gemini 생성은 2주 테스트 후 재검토
- stat 카드 배경: 순수 그라데이션 vs 아주 약한 생성 텍스처(비용 추가) → 그라데이션으로 시작 권장
- 표지만 Sonnet 비전 재확인을 켤지(품질 vs 비용)
- 생성 이미지 보관 기간과 백업(이전에 `output/`이 비워진 적 있음 → R2 검증 후 업로드)
