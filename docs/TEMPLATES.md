# 카드뉴스 구성 템플릿 6종 (2026-10-21)

디자인(색·글꼴)은 `docs/DESIGN_2026.md`의 v2 시스템을 공유하고, 이 문서는 **구성(장의 순서와 역할)**을 정한다.
모두 표지 1 + 본문 4 + 마무리 1 = 6장. 본문 장의 `slide_type`(photo/stat/list/term/qa/compare)이 렌더를 결정하고,
`format`은 writer가 어떤 조합으로 쓸지 정하는 규칙이다. 코드: `naver_cardnews/formats.py`.

## 리서치 요약

- 국내 자료는 카드뉴스를 **나열형(리스티클)**과 **스토리텔링형**으로 나누고, 정보성은 "도입 → 정보1…N → 정리", 스토리성은
  "서론 → 본론 → 결론"(결론을 앞에 두는 변형 포함)으로 설명한다. 정부기관 카드뉴스 연구는 제공 방식을 **리스티클·문답형·반전스토리**로
  분류했고, 문답형의 원형은 2014년 VOX의 '카드 스택'(질문-답 카드를 넘기며 읽기)이다. 공통 원칙은 "한 장에 한 주장".
- 해외 캐러셀 가이드의 포맷 유형: **리스티클(장당 한 항목, 번호가 끝까지 넘기게 함)**, **오해 vs 사실(교대 배치)**,
  **이전/이후**, **단계형(장당 한 단계, 저장률에 유리)**, 뉴스·트렌드 설명형(사건 1~2일 내 "독자에게 무슨 의미인가").
- 장 구조 원칙: 1장이 훅, **2장은 제목 반복이 아니라 판돈(왜 중요한가)**, 장당 한 가지, 마지막 장은 CTA 하나. 분량은 5~8장.
- 국내 지역뉴스 요약 계정 사례는 "첫 장 제목을 크게"가 가장 큰 피드백이었다.
- 못 찾은 것: 뉴스 계정 전용 슬라이드별 템플릿, 비교형·타임라인형의 국내 사례. 뉴닉·어피티·스브스뉴스의 실제 구성은 계정을 직접 봐야 한다.

## 템플릿

| format | 이름 | 언제 | 본문 4장 구성 | 사진 |
|---|---|---|---|---|
| `explainer` | 설명형 | 사건을 처음 접하는 독자에게 맥락까지 (기본) | 무슨 일 → 왜 중요 → 맥락·숫자(stat 가능) → 전망 | 3~4장 |
| `listicle` | 나열형 | 항목이 여럿인 발표, "알아야 할 N가지" | 01 → 02 → 03 → 04 (장당 한 항목) | 표지만 |
| `numbers` | 수치형 | 원문 수치 3개 이상이 곧 메시지 | 큰 숫자 + 해석 × 3~4 | 표지만 |
| `term` | 용어해설 | 낯선 기술 용어 하나를 알면 뉴스가 풀릴 때 | 단어·정의·비유 → 왜 등장했나 → 어디에 쓰이나 → 무엇이 달라지나 | 2~3장 |
| `qa` | 문답형 | 정책·논란·서비스 변경, "나한테 뭐가 달라져?" | Q1 무슨 일 → Q2 내 영향 → Q3 왜 → Q4 언제부터 | 표지만 |
| `compare` | 비교형 | A vs B, 이전 vs 이후, 오해 vs 사실 | 축1 → 축2 → 축3 (2열) → 결론(photo/stat) | 표지 + 결론 |

### 선택 규칙 (writer `format: auto`)
수치 3개 이상이 핵심 → numbers · 낯선 용어가 핵심 → term · 두 대상의 차이가 핵심 → compare · 독자가 영향을 물을 만한 정책·논란 → qa ·
항목이 여럿인 발표 → listicle · 그 외 → explainer. CLI `draft --format qa`로 강제할 수 있다.

### 장 유형별 글자 수 (validate)
photo 제목 14 / 본문 80~125 · list 제목 14 / 본문 50~115 · term 용어 10 / 정의 32 / 본문 50~115 · qa 질문 32(물음표) / 답 50~125 ·
compare 축 14 / 라벨 8 / 포인트 2~3개 × 24자 · stat 은 기존 규칙(numbers 포맷에서는 연속·개수 제한 없음).

### 엑셀 '원고' 시트 매핑
공통 열(유형·제목·본문)을 쓰고, term 의 정의는 **라벨** 열, compare 는 라벨 열에 `좌 | 우`, 본문 열에 좌측 포인트(`;` 구분),
인용 열에 우측 포인트. `포맷` 열로 format 을 바꿀 수 있다(바꾸면 장 유형도 맞춰 고쳐야 검수를 통과한다).

### 사진이 없는 장이 많은 이유
리서치의 "타이포 주도" 흐름과 일치하고, 스톡 사진 품질 문제·비전 검수 비용을 줄인다. 설명형과 용어해설형만 사진 카드를 유지한다.

## 비용 영향
listicle/qa/numbers 는 사진이 표지 1장뿐이라 비전 검수 호출이 게시물당 ≤ 8회(설명형 24~40회).

## 출처
- http://www.hkrecruit.co.kr/news/articleView.html?idxno=23029
- https://blog.theprconsulting.com/602
- https://illustkorea.or.kr/data/file/IL_PDS/1949101453_fFjcMk3u_b573acfe16027870ded7747b041829cc65d7c3bb.pdf
- https://namu.wiki/w/%EC%B9%B4%EB%93%9C%EB%89%B4%EC%8A%A4
- https://www.idomin.com/news/articleView.html?idxno=831845
- https://www.dochipo.com/instagram-carousel-ideas/
- https://trycarouselz.com/blog/instagram-carousel-ideas
- https://www.virallized.com/instagram-carousel-ideas
- https://socialrails.com/blog/instagram-carousel-examples-high-converting-ideas
- https://www.viralbrain.ai/tools/carousel-planner
- https://instantdm.com/blog/steal-this-carousel-system-6-rules-for-2m-views
- https://postnitro.ai/blog/post/the-swipe-effect-unveiling-the-psychology-of-carousel-engagement
- https://madegooddesigns.com/?p=3585
