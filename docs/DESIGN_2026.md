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
- **글꼴**: Pretendard. 표지 84/800, 본문 제목 64/800, 본문 36/400(행간 1.55), 라벨 24/700, 숫자 카드 240~380/800.
- **장 유형과 배경 리듬**: 표지(종이) → 본문(종이, 번호 01·02·03) → 숫자(잉크 반전) → 마무리(형광 전면).
- **사진**: 액자 28px 라운드, 2px 잉크 테두리, 채도 .85, 웜 틴트 10%, 하단 종이색 페이드 28%.
- **고정 요소**: 좌상단 "AI로 재가공한 뉴스" 알약 라벨, 좌하단 출처, 우하단 n/6.
- **QA(render.py)**: 글자(잉크)와 배경 어두운 쪽 5퍼센타일 대비 ≥ 4.5, 텍스트가 사진 액자와 겹치지 않음, 그리드 3:4 크롭 안전, 제목 줄바꿈, 폰트 로딩, 8MB.

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
