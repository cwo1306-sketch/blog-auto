# 카드뉴스 디자인 시스템 v2 (2026 트렌드 반영)

2026-10-21. 기존 "사진 풀블리드 + 하단 스모크그레이 그라데이션 + 흰/노랑 헤드라인"을 대체한다.

## 리서치 요약

검색 가능한 2026년 자료는 대부분 마케팅·디자인 툴 업체 블로그라 수치는 참고치로만 본다. 그래도 여러 출처가 같은 방향을 가리킨다.

| 흐름 | 근거 | 적용 |
|---|---|---|
| **타이포가 주인공** — 3~4단어가 화면을 채우는 대형 그로테스크, 좁은 행간, 왼쪽 정렬. 첫 장의 굵은 글씨와 높은 대비가 스와이프를 결정 | 캐러셀 타이포 트렌드(Supaslides), 캐러셀 가이드(Social Habit, Slidy) | 표지 헤드라인 84px ExtraBold, 왼쪽 정렬, 본문 제목 64px |
| **잡지(에디토리얼) 페이지처럼** — 단색·질감 배경 위 큰 헤드라인 | 템플릿 모음(UI Creative), 폰트 트렌드(Simplified) | 종이 톤 단색 배경 + 그레인 질감 |
| **쿨그레이 → 웜뉴트럴** — 베이지·체스트넛 등 따뜻한 중성색, 거기에 채도 높은 포인트 한 색 | 2026 디자인 예측(We and the Color, Adobe Express, G2, DesignRush) | 종이색 #F3EEE4 + 잉크 #141414 + 형광 #FFE500 한 색 |
| **질감·개성** — 그레인, 하프톤, 약간의 불완전함 | Picsart, G2 | 전 장 그레인 오버레이(불투명도 11%) |
| **번호 매긴 단계(01, 02)·컬러 블로킹** | 2026 캐러셀 트렌드 모음(My Social Boutique, Scrolo) | 본문 장 큰 번호, 장 유형별 배경색 교대(종이 → 잉크 → 형광) |
| **첫 3장은 각각 단독으로 읽혀야** — 알고리즘이 중간 장을 따로 노출 | 원포인트 블로그 | 모든 본문 장에 제목+완결 문장, 출처 줄 |
| **저장·공유 CTA가 마지막 장** | 폴라애드, Carouselli | 마무리 장을 형광 전면으로, CTA 알약 버튼 |
| **4:5, 안전 영역, 모바일 본문 24pt 이상** | 하이아웃풋클럽, Veeso, Social Habit | 1080×1350, 여백 64px, 본문 36px |
| 캐러셀 저장률 3~5%(교육형), 상위 5~15% — 업체 표본 | Carouselpost, Carouselli | 7단계 지표 판정 기준의 참고치 |

국내 뉴스 계정(뉴닉·어피티·스브스뉴스)의 2025~26 시각 분석 자료는 검색으로 확인되지 않았다. 카카오 템플릿·캐럿 프롬프트 갤러리에서도
"단색 배경 + 타이포 중심 + 형광펜 강조"가 반복적으로 보인다.

## 왜 스톡 사진 문제도 같이 풀리는가

사진이 풀블리드일 때는 사진의 질이 카드의 질이었다. v2에서는 사진이 **상단 액자 요소**(세로의 40% 안팎)로 줄고, 웜 틴트와 채도 -15%로
한 톤으로 묶이며, 헤드라인이 시선을 가져간다. 뻔한 스톡 사진의 영향이 줄고, 비전 검수의 '하단 여백' 기준도 덜 중요해진다
(대신 액자 안에서 '무관·로고·얼굴'만 거르면 된다).

## 시스템

- **색**: 종이 `#F3EEE4`, 종이2 `#E9E2D4`, 잉크 `#141414`, 잉크2 `#4A4842`, 뮤트 `#8A867C`, 형광 `#FFE500`.
  형광은 글자색으로 쓰지 않는다(종이 위 대비 1.1:1). **형광펜 블록**(`<mark>`)과 **전면 배경**으로만.
- **글꼴**: Pretendard. 표지 96/800(하단 기준 정렬, 사진은 세로 36%), 본문 제목 64/800, 본문 36/400(행간 1.55), 라벨 24/700, 숫자 카드 240~380/800.
- **장 유형과 배경 리듬**: 표지(종이) → 본문(종이, 번호 01·02·03) → 숫자(잉크 반전) → 마무리(형광 전면).
- **사진**: 액자 28px 라운드, 2px 잉크 테두리, 채도 .85, 웜 틴트 10%, 하단 종이색 페이드 28%.
- **고정 요소**: 좌상단 "AI로 재가공한 뉴스" 알약 라벨, 좌하단 출처, 우하단 n/6.
- **QA(render.py)**: 글자(잉크)와 배경 어두운 쪽 5퍼센타일 대비 ≥ 4.5, 텍스트가 사진 액자와 겹치지 않음, 그리드 3:4 크롭 안전, 제목 줄바꿈, 폰트 로딩, 8MB.

## 포인트 색 비교 (2026-10-21)

형광 노랑 `#FFE500`과 주황빨강 `#FF4D1F`를 같은 6장으로 렌더해 비교했다. 주황은 더 강하지만 마무리 장(전면 배경) 잉크 대비가
5.3:1로 노랑(13.7:1)보다 크게 낮고, 뉴스 계정의 '친절한 브리핑' 톤에는 노랑이 맞다고 판단해 **노랑 유지**. 바꾸려면 `--hl` 변수 하나.

## 비전 검수 가중치

v2에서 사진이 액자로 들어가 하단 여백의 중요도가 낮아졌고, 관련성 약한 사진이 더 눈에 띈다. 가중치를 관련성 0.5 / 하단 0.2 / 톤 0.3으로
조정(이전 0.4/0.35/0.25). 실측: 5장 "작지만 강한 티니"가 라이터 든 손(관련성 약함) → 작은 전구(3.5점)로 바뀜.

## 실측 (재렌더, 카카오 비전 인코더 6장)

대비 13.7~15.1:1(이전 5.6~8.0), QA 이슈 0. 파일 크기 0.07~0.3MB.

## 출처

- https://1point.kr/blog/insights/why-insta-carousel-2026/
- https://blog.highoutputclub.com/2026-instagram-algorithm-update/
- https://veeso.ai/blog/instagram-carousel-safe-zone-guide
- https://polarad.co.kr/marketing-news/instagram-algorithm-2026-latest-trends-complete-an
- https://supaslides.app/blog/carousel-typography-trends-2026
- https://mysocialboutique.co/5-instagram-carousel-design-trends-fall-2026/
- https://scrolo.app/blog/top-trending-instagram-carousel-design-ideas-in-2026
- https://www.socialhabitmarketing.com/article-posts/the-ultimate-guide-to-designing-a-perfect-instagram-carousel
- https://slidycreator.com/blog/instagram-carousel-trends/
- https://uicreative.net/blog/best-instagram-carousel-design-template.html
- https://simplified.com/blog/design/creative-font-trends
- https://www.adpicto.com/en/blog/instagram-carousel-best-practices-2026
- https://carouselli.com/blog/instagram-carousel-best-practices
- https://carouselpost.io/digest/instagram-carousel-saves-metric-strategy-2026
- https://learn.g2.com/graphic-design-trends
- https://weandthecolor.com/design-forecast-2026-color-palettes-typography-youll-see-first/205925
- https://www.adobe.com/express/learn/blog/graphic-design-trends-2026
- https://picsart.com/blog/design-trends-2026/
- https://www.designrush.com/trends/state-of-design


## v2.2 혼합 폰트 (2026-10-21, 채택)

Pretendard 단독 · 혼합 · 전체 주아체 세 버전을 같은 원고로 비교한 뒤 **혼합**을 채택했다.

| 장 | 글꼴 | 이유 |
|---|---|---|
| 표지 헤드라인 | 배달의민족 주아체 90px | 피드에서 멈추게 하는 장. 친근함·계정 개성이 득 |
| 마무리 요약 | 배달의민족 주아체 64px | 저장·공유를 부르는 장 |
| 본문 제목·본문·숫자·인용·비교·라벨 | Pretendard | 수치와 발언을 전하는 장은 신뢰감이 우선. 주아체 숫자는 둥글어 가볍게 보이고, 긴 본문은 읽는 속도가 떨어진다 |

- 주아체는 굵기가 하나(Regular)라 `font-weight: 400; font-synthesis: none` 으로 가짜 굵게를 막고, 자폭이 넓어 크기를 한 단계 낮췄다.
- 글꼴 지정 순서: 로컬 설치명(`BM JUA_OTF` 맥 / `BM JUA_TTF` 윈도우 / `배달의민족 주아`) → 구글 폰트 `Jua`(OFL, 같은 글꼴) → Pretendard.
  로컬 렌더링 PC에 배민 주아체나 Jua 중 하나가 설치돼 있어야 한다.
- 라이선스: 구글 폰트판 Jua 는 SIL OFL 1.1, 배민 폰트도 상업 이용 무료. 폰트 파일 자체의 판매·재배포만 금지.
- 위험 관리: 주아체는 광고·밈에 흔해 가벼워 보일 수 있다. 표지에만 쓰는 이유이고, 2주 니치 테스트에서 표지 폰트별 저장률을 비교해 최종 확정한다.
- 전체 주아체 테마는 `CARDNEWS_THEME=jua`(`templates/theme_jua.css`)로 남겨 둔다.
