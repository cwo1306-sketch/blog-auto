# cardkit — 어느 계정에나 쓰는 인스타그램 카드뉴스 키트

`blog-auto`의 AI 뉴스 카드뉴스에서 만든 **디자인 · 구성 엔진 · 포맷/원고 작성**을 계정과 무관하게 떼어 낸 패키지입니다.
계정마다 다른 것(**색 · 폰트 · 레이아웃 목록 · 포맷 목록**)은 `profiles/*.yaml` 하나로 바꿉니다.
원문은 뉴스 기사든 논문이든 `{id, title, body, credit, date}` JSON 하나면 됩니다.

```
원문(JSON) ─▶ 색 ─▶ 레이아웃 ─▶ 포맷 ─▶ 원고 작성(Claude) ─▶ 검수(원문 대조) ─▶ 사진(검색·비전 심사·톤) ─▶ 렌더(1080×1350) ─▶ 점검
              └────── 규칙 있는 무작위(compose.py) ──────┘
```

## 1. 설치

```bash
pip install anthropic playwright pillow pyyaml requests
playwright install chromium          # 또는 CHROMIUM_PATH=/path/to/chrome
export ANTHROPIC_API_KEY=...         # 원고 작성·사진 심사
export PEXELS_API_KEY=...            # 사진 (없으면 사진 없이 렌더)
export UNSPLASH_ACCESS_KEY=...       # 선택
```
폰트: 본문 **Pretendard**, 표지·마무리 제목 **배달의민족 주아체**(없으면 구글 폰트 Jua → Pretendard)를 시스템에 설치해 두세요.

## 2. 빠른 시작

```bash
# API 없이 계정 색·레이아웃·장 유형 미리보기 (예시 원고)
python -m cardkit preview --profile cardkit/profiles/psychology.yaml --out preview/

# 계정 팔레트 검사 (대비·눈 편안함·피할 브랜드색)
python -m cardkit audit --profile cardkit/profiles/psychology.yaml

# 실제 제작: 원문 JSON → 카드 세트
python -m cardkit make --profile cardkit/profiles/psychology.yaml --source paper.json --out out/kim2024

# 원고(script.json)를 손으로 고친 뒤: 검수만 / 같은 색·레이아웃으로 다시 그리기 / 고친 원고로 처음부터
python -m cardkit check    --profile P.yaml --source paper.json --script out/kim2024/script.json
python -m cardkit rerender --profile P.yaml --out out/kim2024
python -m cardkit make     --profile P.yaml --source paper.json --script out/kim2024/script.json --out out/kim2024b
```

원문 JSON 예 (논문):
```json
{"id": "kim2024", "kind": "논문", "title": "…", "credit": "Kim et al. (2024), Psychological Science",
 "date": "2024-05-01", "body": "초록·방법·결과·논의에서 카드에 쓸 부분을 붙여 넣는다 (수치는 원문 그대로)"}
```
수치·인용·차트 값은 **body 안의 문장과 글자 그대로 대조**합니다. 논문이라면 초록과 결과 문단(표 수치 포함)을 body 에 넣어 두세요.

파이썬에서:
```python
from cardkit import profile, pipeline
prof = profile.load("cardkit/profiles/psychology.yaml")
out = pipeline.make(source, prof, "out/kim2024", seed=None, photos=True)
```
출력 폴더: `card_01.jpg … card_NN.jpg`(+ html), `script.json`(원고), `caption.txt`(캡션+해시태그), `meta.json`(구성·점검·사진 출처).

## 3. 계정 설정 (profile YAML)

| 키 | 뜻 | 예 |
|---|---|---|
| `palettes` | 돌려 쓸 팔레트 목록 | `[sage, lavender, oat, ocean, clay]` |
| `palettes_custom` | 계정 전용 팔레트(12개 역할) | `lavender: {bg: …, brand: …}` |
| `layouts` | 돌려 쓸 레이아웃 | `[frame, card, split, type]` |
| `fonts.mode` / `fonts.body` / `fonts.display` | 폰트 혼합 방식(mixed·all·none)과 CSS font-family | `mode: mixed` |
| `formats` | 이 계정이 쓰는 포맷 | `[study, traits, checklist, myth, …]` |
| `name`·`label_top`·`handle`·`cta` | 계정 이름, 좌상단 라벨, 핸들, 마무리 버튼 | |
| `source_kind`·`persona`·`audience`·`tone` | 원고 작성 프롬프트에 들어갈 원문 종류·작성자·독자·말투 | |
| `hashtags_fixed` | 앞에 고정할 해시태그(검수함) | `["#심리학", "#심리", "#논문읽기"]` |
| `disclaimer` | 마무리 장 하단 + 캡션 면책 문구 | 건강·심리·금융 계정 |
| `photo_style` | 사진 심사의 분위기 기준 | `부드러운 자연광·여백…` |
| `avoid_colors` | 퍼스널 컬러와 겹치면 안 되는 브랜드색 | 기본: 카카오·네이버·배민·토스 |
| `store_path` | 사진 재사용 금지·구성 기록 DB | `cardkit_data/psychology.db` |

예시: `profiles/psychology.yaml`(심리학 논문), `profiles/ai_news.yaml`(AI 뉴스).

## 4. 디자인

### 팔레트 (palette.py)
12개 역할 토큰: `bg bg2 ink ink2 muted brand on_brand line deep on_deep pop mark`. 60·30·10(배경 60 · 잉크 30 · 퍼스널 컬러 10).
모든 팔레트는 `audit` 을 통과해야 합니다.
- 대비(WCAG): 제목/배경 ≥7, 본문 ≥4.5, 출처 ≥4.5, 형광펜 위 제목 ≥4.5, 마무리 글씨 ≥4.5, 어두운 카드 글씨 ≥7
- 눈 편안함: 제목 대비 ≤16(순흑·순백 금지), 배경 채도 ≤8, 배경 밝기 91~97.5(다크 10~22), 마무리 배경 채도 ≤50,
  형광펜 채도 ≤30·배경과 ΔE ≥8·노랑 계열(80~105°) 금지
- 피할 브랜드색과 색상각 ≥20°

내장: ocean · clay · sage · plum · mono · slate(다크) (+ 참고용 violet · coral). 심리학 예시에 lavender · oat 추가.

### 레이아웃 (templates/layout_*.css)
| 이름 | 생김새 | 사진 비중 |
|---|---|---|
| frame | 둥근 액자 사진 + 큰 번호 워터마크 | 보통 |
| fullbleed | 사진 전면 + 하단 딥 컬러 그라데이션 위 밝은 글씨 | 큼 |
| split | 위 절반 사진(모서리 없음) + 강조선 + 번호 배지 | 큼 |
| card | 옅은 퍼스널 컬러 바탕 위 종이 카드 | 보통 |
| band | 왼쪽 컬러 띠 + 오른쪽 세로 사진 + 큰 번호 | 큼 |
| type | 원형 작은 사진, 글씨가 주도 | 작음 |

색은 역할 토큰만 쓰므로 어떤 팔레트와도 조합됩니다. 공통 뼈대는 `templates/card.css`.

### 장 유형 (slide_type)
`photo` 사진+제목+본문 · `stat` 큰 숫자 · `chart` 그래프(막대·선·도넛·비교, Apache ECharts) · `list` 번호 항목 · `term` 용어 ·
`qa` 문답 · `compare` 2열 비교 · `quote` 인용 · `checklist` 체크 항목 3~5개 · `myth` 오해→사실. 표지(cover)·마무리(outro)는 공통.

### 폰트
`mixed`(기본): 표지 헤드라인·마무리 요약만 display(주아체), 나머지 Pretendard. `all`: 제목·숫자까지 display. `none`: 전부 본문 글꼴.

## 5. 구성 엔진 (compose.py)
색 → 레이아웃 → 포맷 순서로 **규칙 있는 무작위**:
- 직전 세트와 같은 색·레이아웃·포맷 금지, 최근 6세트 안의 (색, 레이아웃) 조합 금지
- 포맷은 원문 조건을 통과한 것만(포맷의 `cues` 단어, `min_numbers` 수치 개수, `terms` 용어 수, `always`)
- 사진 비중이 큰 레이아웃(fullbleed·split·band)은 사진 장 2장 이상 포맷에만
- 사람이 고친 원고(`script=`)는 포맷 고정
- 사진: 비전 점수(내용) + 팔레트 톤 가산점(무채색·유사색·보색 우대, 어중간한 색상각 감점, 풀블리드는 어두운 사진 우대). 합격선은 비전 점수만
- 사진 재사용 금지: 같은 (소스, id)와 최근 30일 dHash 유사 사진 제외 (`store_path`)

## 6. 포맷 (formats.py)

| 키 | 이름 | 본문 장 구성 | 쓰는 경우 |
|---|---|---|---|
| study | 연구 요약형 | 왜 중요 → 누구를 어떻게 → 결과(chart/stat) → 해석 → **한계** → 적용(list) | 논문·실험·조사 (논문 계정 기본) |
| traits | 특징 N가지 공감형 | 공감 → 특징 ×4(list) → 몇 개 해당? | 특징·유형·신호 |
| checklist | 체크리스트·자가점검형 | 왜 점검 → checklist ×2 → 해석 → 대처(list) | 점검 항목·증상·기준 |
| myth | 오해와 진실형 | 왜 오해 → myth ×3 → 정리 | 통념 바로잡기 |
| debate | 질문-토론-권고형 | 공감 → 수치 → 비유 → 찬반 → 반론 → 권고 | 찬반·권고 |
| glossary | 용어 묶음형 | 왜 쏟아지나 → term ×4 → 인용 | 낯선 용어 3개+ |
| scene | 현장 사례형 | 한 장 한 문장, 장면 → 작동 → 수치 → … | 장소·장면 |
| reveal | 반전 추리형 | 통념 → 단서 → 단서 → 알려진 것 vs 실제 → 왜 | 통념과 다른 결론 |
| qa | 문답형 | Q ×4 → 이렇게 하세요 | 독자 영향·방법 |
| numbers | 수치 브리핑형 | stat → chart/stat → stat → stat → 결론 | 수치 3개+ |
| explainer | 설명형 | 무슨 일 → 왜 중요 → 맥락 → 전망 | 그 외 |

포맷 자료집(노션 '카드뉴스 포맷 자료집', 43종)에서 더 옮기려면 `FORMATS` 에 `slides`·`rules`·`cues` 를 추가하면 됩니다.

## 7. 검수 (validate.py) — 원문 대조, 결정적 규칙
- 모든 수치는 원문에 같은 단위로 있어야 함(환산·반올림 금지), 장마다 근거 문장(evidence)이 원문에 그대로 있어야 하고 장의 수치는 그 근거 안에
- stat: 값+단위 ⊂ source_quote ⊂ 원문 / chart: 각 값+단위가 숫자 경계까지 source_quote 안에, 도넛은 % 합 95~105 / quote: 인용문이 원문에 그대로
- 차트에 나온 값을 stat 장이 반복하지 않기, stat 최대 2장·연속 금지(numbers 제외), chart 최대 1장
- 글자 수(표지 줄 12자, 장 유형별 제목·본문), 사진 검색어(영어, 인물·브랜드·글자 금지), 캡션 마지막 줄 '출처:', 해시태그 8~10개·고정 태그
- 검수를 못 넘은 stat·chart 장은 제작 때 photo 로 강등(사유는 meta.json notes)

## 8. 확장
- **팔레트 추가**: profile `palettes_custom` 에 12개 역할을 적고 `python -m cardkit audit` 로 통과 확인
- **레이아웃 추가**: `templates/layout_<이름>.css` 작성(역할 토큰만 사용) → `profile.LAYOUTS`·`compose.LAYOUTS` 에 등록.
  글씨를 사진 위에 얹는 레이아웃은 `body.cover { --overlay: 1; }` 로 겹침 검사를 끈다(대비 검사는 유지)
- **포맷 추가**: `formats.FORMATS` 에 `slides`(장 유형 순서, `a|b` 는 둘 중 하나), `rules`(작성 지시), `cues`(원문 단서) 추가
- **장 유형 추가**: `formats.SLIDE_TYPES`, `render._*_inner`, `card.css`, `validate.TYPE_LIMITS`, `writer.SYSTEM` 스키마

## 9. 라이선스
`templates/vendor/echarts.min.js` — Apache ECharts 6.1.0, Apache-2.0 (`ECHARTS_LICENSE`, `ECHARTS_NOTICE`).
