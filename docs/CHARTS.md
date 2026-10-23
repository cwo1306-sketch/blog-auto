# 그래프·수치 표현용 오픈소스 검토 (2026-10-23)

지금 숫자 장(stat)은 큰 숫자 하나만 보여 준다. 추세·비교(연도별 시장 규모, 점유율, 전후 비교)를 그래프로 보여 주는 장을
넣는다면 쓸 만한 오픈소스를 비교했다. 기준: 우리 렌더러(Playwright + HTML/CSS)에 붙이기 쉬운가, 팔레트 토큰을 그대로 쓰나,
한글 폰트(Pretendard), 라이선스, 정적 이미지 품질.

## 실제로 그려 본 두 가지

같은 데이터(국제신문 카드뉴스의 라이브 커머스 시장 2.8 → 6.2 → 10조 원)를 ocean·slate 팔레트로 그렸다.
결과: `cardnews/output/chart_demo/chart_compare.jpg` (왼쪽부터 ECharts·Vega-Lite × ocean, ECharts·Vega-Lite × slate).
둘 다 한글·팔레트·강조 막대(마지막 값만 퍼스널 컬러) 모두 문제없었다.

| | Apache ECharts 6.1 | Vega-Lite 5 + vl-convert 1.9 |
|---|---|---|
| 라이선스 | Apache-2.0 | BSD-3 (vl-convert BSD-3) |
| 붙이는 방법 | 카드 HTML 에 `echarts.min.js`(1.1MB) 를 넣고 SVG 렌더러로 그림 → 지금 렌더러 그대로 | 파이썬에서 JSON 스펙 → SVG 변환(브라우저 불필요) → `<img>` 로 삽입 |
| 장점 | 차트 종류가 가장 많음(막대·선·도넛·게이지·트리맵·지도), 라벨·강조 세밀 제어, 애니메이션 끄면 정적 캡처 안정 | 스펙이 짧고 선언적이라 **LLM 이 원고와 함께 스펙을 쓰기 쉬움**, 결과가 결정적(같은 스펙 = 같은 그림), 테스트하기 쉬움 |
| 단점 | 옵션이 방대해 원고 작성기가 직접 쓰기엔 길다 → 우리 쪽에서 템플릿 함수로 감싸야 함 | 폰트는 `register_font_directory` 로 등록 필요, 차트 종류·장식은 ECharts 보다 적음 |

## 그 밖의 후보

- **Chart.js** (MIT): 가볍고 익숙하지만 캔버스 렌더라 확대 시 품질이 떨어지고 라벨 배치 제어가 약하다.
- **Observable Plot** (ISC): 문법이 깔끔한 D3 기반 고수준 라이브러리. Vega-Lite 와 비슷한 장점, 파이썬 변환기는 없다.
- **D3** (ISC): 무엇이든 되지만 차트마다 코드를 직접 짜야 한다.
- **matplotlib / Plotly(+Kaleido)**: 파이썬에서 바로 이미지를 만들지만 카드 디자인 톤(둥근 막대, 팔레트 토큰)을 맞추는 데 손이 많이 간다. Kaleido 는 크롬을 따로 띄운다.
- **Rough.js / chart.xkcd** (MIT): 손그림 느낌 차트. 라이프스타일 계정 톤에 맞을 수 있으나 뉴스 신뢰감과는 거리가 있다.

## 추천

**ECharts 를 기본으로, 차트 데이터는 원고 작성기가 Vega-Lite 와 비슷한 짧은 형식으로 내게 한다.**
- 원고에 `slide_type: "chart"` 를 추가하고 `chart: {type: bar|line|donut|compare, labels, values, unit, highlight, source_quote}` 만 쓰게 한다.
- 우리 코드가 이것을 ECharts 옵션으로 바꿔 팔레트 토큰(brand=강조, bg-2/ink 섞은 색=보조, ink-2=축 라벨)으로 그린다.
- 숫자는 stat 장처럼 **원문 대조 검수**(`source_quote` 안에 값이 그대로 있어야 함)를 거친다.
- 브라우저 없이 그려야 하는 곳(엑셀 미리보기 등)은 Vega-Lite + vl-convert 로 같은 데이터를 그린다.

규칙(데이터 시각화 기본): 막대는 0 에서 시작, 강조색은 한 곳만(가장 중요한 값), 축 눈금 대신 값 라벨, 장당 차트 1개, 출처 필수.
