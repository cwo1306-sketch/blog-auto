"""Playwright 렌더 + QA.

원본 대비 개선:
- document.fonts.ready 를 실제로 await (원본은 Promise를 기다리지 않아 폰트 로딩 전 캡처·QA 가능성)
- 장 유형 분기: cover / slide / stat / outro. v2 템플릿(templates/card.css): 사진은 액자(.photo), 본문 장 번호(.num-big), 숫자 카드는 잉크 반전, 마무리는 형광 전면
- 사진이 없는 장(단색 강등)은 .plain 으로 렌더
- 대비 측정에 Pillow getdata() 대신 tobytes() (Pillow 14 제거 예정 API 회피), 95퍼센타일 유지
- Chromium 경로를 CHROMIUM_PATH 로 지정 가능, 캡처 전 150ms 안정화
- QA 결과에 kind·font 로딩 여부 포함
"""

from __future__ import annotations

import os
from html import escape

from PIL import Image
from playwright.sync_api import sync_playwright

from naver_cardnews.stat_card import len_class

HANDLE = os.environ.get("CARDNEWS_HANDLE", "@your_handle")
# CARDNEWS_THEME=jua → templates/theme_jua.css 를 card.css 뒤에 덧씌운다 (폰트 테마)
LABEL = "AI로 재가공한 뉴스"
W, H = 1080, 1350
GRID_CROP = (W - H * 3 / 4) / 2  # 프로필 그리드 3:4 노출 시 좌우로 잘리는 폭
MIN_CONTRAST = 4.5               # WCAG 2.x AA 일반 텍스트 기준
STAT_MAX_QUOTE = 70


def _page(inner: str, bg: str | None, kind: str, source: str, page_no: str, num: str = "") -> str:
    """2026 템플릿: 사진은 풀블리드가 아니라 .photo 액자 안에, 본문 장은 큰 번호(.num-big)를 단다."""
    photo = f"""<div class="photo"><div class="bg" style="background-image:url('{bg}')"></div></div>""" if bg else ""
    num_big = f'<div class="num-big">{num}</div>' if num else ""
    plain = "" if (bg or kind in ("stat", "outro", "list", "term", "qa", "compare", "quote")) else " plain"
    theme = os.environ.get("CARDNEWS_THEME", "").strip()
    theme_css = f'<link rel="stylesheet" href="../../templates/theme_{theme}.css">' if theme else ""
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<link rel="stylesheet" href="../../templates/card.css">{theme_css}</head>
<body class="{kind}{plain}">
{photo}{num_big}
<div class="pill">{LABEL}</div>
{inner}
<div class="source">{escape(source)}</div><div class="page">{page_no}</div>
</body></html>"""


def _stat_inner(stat: dict) -> str:
    value, unit = str(stat["value"]), str(stat.get("unit", ""))
    unit_cls = "unit below" if len(unit) >= 3 else "unit"    # '파라미터'처럼 긴 단위는 숫자 아래 줄에
    quote = stat.get("source_quote", "")
    if len(quote) > STAT_MAX_QUOTE:
        quote = quote[:STAT_MAX_QUOTE - 1] + "…"
    return (f'<div class="text"><div class="value" data-len="{len_class(value, unit)}">'
            f'<span class="num">{escape(value)}<span class="{unit_cls}">{escape(unit)}</span></span></div>'
            f'<div class="stat-label">{escape(stat.get("label", ""))}</div></div>'
            f'<div class="quote">{escape(quote)}</div>')


def _list_inner(num: str, s: dict) -> str:
    return (f'<div class="text"><div class="list-num">{num}</div><h2>{escape(s.get("title", ""))}</h2>'
            f'<p>{escape(s.get("body", ""))}</p></div>')


def _term_inner(s: dict) -> str:
    return (f'<div class="text"><div class="kicker">이 단어, 뭐길래</div>'
            f'<div class="term"><mark>{escape(s.get("title", ""))}</mark></div>'
            f'<div class="definition">{escape(s.get("label", ""))}</div>'
            f'<p>{escape(s.get("body", ""))}</p></div>')


def _qa_inner(num: str, s: dict) -> str:
    return (f'<div class="text"><div class="q"><span class="badge">Q{num}</span>'
            f'<h2>{escape(s.get("title", ""))}</h2></div>'
            f'<div class="a"><span class="badge badge-a">A</span><p>{escape(s.get("body", ""))}</p></div></div>')


def _quote_inner(s: dict) -> str:
    return (f'<div class="text"><div class="qmark">“</div>'
            f'<blockquote>{escape(s.get("body", ""))}</blockquote>'
            f'<div class="who">{escape(s.get("label", ""))}</div>'
            f'<div class="gist">{escape(s.get("title", ""))}</div></div>')


def _compare_inner(s: dict) -> str:
    cmp = s.get("compare") or {"left": {}, "right": {}}
    def col(side: dict, cls: str) -> str:
        pts = "".join(f"<li>{escape(p)}</li>" for p in side.get("points", []))
        return f'<div class="col {cls}"><div class="col-label">{escape(side.get("label", ""))}</div><ul>{pts}</ul></div>'
    return (f'<div class="text"><h2>{escape(s.get("title", ""))}</h2>'
            f'<div class="cols">{col(cmp.get("left", {}), "left")}<div class="vs">vs</div>{col(cmp.get("right", {}), "right")}</div></div>')


def build_pages(script: dict, images: list[str | None], source: str) -> list[str]:
    """images[i]는 i번째 장(0=표지)의 배경 파일명. 사진 없는 장(stat/list/term/qa/compare)과 단색 강등 장은 None."""
    slides = script["slides"]
    total = 2 + len(slides)
    # 강조 줄은 형광펜(mark)으로. 글자색 노랑(구 템플릿)은 종이 배경에서 대비가 안 나와 쓰지 않는다
    lines = "".join(
        f'<div class="line">{"<mark>" + escape(l["text"]) + "</mark>" if l.get("highlight") else escape(l["text"])}</div>'
        for l in script["cover"]["lines"])
    pages = [_page(f'<div class="text">{lines}<div class="handle">{HANDLE}</div></div>',
                   images[0], "cover", source, f"1/{total}")]
    for i, s in enumerate(slides, start=2):
        kind = s.get("slide_type", "photo")
        num = f"{i - 1:02d}"
        if kind == "stat" and s.get("stat"):
            pages.append(_page(_stat_inner(s["stat"]), None, "stat", source, f"{i}/{total}"))
        elif kind == "list":
            pages.append(_page(_list_inner(num, s), None, "list", source, f"{i}/{total}"))
        elif kind == "term":
            pages.append(_page(_term_inner(s), None, "term", source, f"{i}/{total}"))
        elif kind == "qa":
            pages.append(_page(_qa_inner(str(i - 1), s), None, "qa", source, f"{i}/{total}"))
        elif kind == "compare" and s.get("compare"):
            pages.append(_page(_compare_inner(s), None, "compare", source, f"{i}/{total}"))
        elif kind == "quote":
            pages.append(_page(_quote_inner(s), None, "quote", source, f"{i}/{total}"))
        else:
            inner = f'<div class="text"><h2>{escape(s["title"])}</h2><p>{escape(s["body"])}</p></div>'
            pages.append(_page(inner, images[i - 1], "slide", source, f"{i}/{total}", num=num))
    o = script["outro"]
    inner = (f'<div class="text"><div class="kicker">오늘의 핵심</div>'
             f'<div class="summary">{escape(o["summary"])}</div>'
             f'<div class="question">Q. {escape(o["question"])}</div>'
             f'<div class="cta"><span>저장</span><span>공유</span><span>팔로우</span></div>'
             f'<div class="handle">{HANDLE}</div></div>')
    pages.append(_page(inner, None, "outro", source, f"{total}/{total}"))   # 마무리는 형광 블록, 사진 없음
    return pages


LAYOUT_JS = """() => {
  const box = document.querySelector('.text').getBoundingClientRect();
  const wrapped = [...document.querySelectorAll('.line, h2')].filter(e => {
    const lh = parseFloat(getComputedStyle(e).lineHeight);
    return e.getBoundingClientRect().height > lh * 1.5;
  }).map(e => e.textContent);
  const num = document.querySelector('.value .num');
  const photo = document.querySelector('.photo');
  return {top: box.top, bottom: box.bottom, left: box.left, right: box.right,
          x: box.x, y: box.y, w: box.width, h: box.height, wrapped,
          value_overflow: num ? num.getBoundingClientRect().right > %d - 64 : false,
          photo_bottom: photo ? photo.getBoundingClientRect().bottom : null,
          fonts: document.fonts.status};
}""" % W

SHRINK_JS = """() => {
  const v = document.querySelector('.value'); if (!v) return null;
  const n = v.querySelector('.num'); let size = parseFloat(getComputedStyle(v).fontSize);
  while (n.getBoundingClientRect().right > %d - 64 && size > 120) { size -= 20; v.style.fontSize = size + 'px'; }
  return size;
}""" % W


def _luminance(rgb):
    def ch(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = rgb
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def _contrast(bg_png: str, text_lum: float) -> float:
    """배경의 밝은 쪽 95퍼센타일을 기준으로 가장 불리한 대비를 잰다."""
    im = Image.open(bg_png).convert("RGB")
    data = im.tobytes()
    lums = sorted(_luminance(data[i:i + 3]) for i in range(0, len(data), 3))
    bg = lums[int(len(lums) * 0.95)]
    return (text_lum + 0.05) / (bg + 0.05)


def _contrast_dark_text(bg_png: str, text_lum: float) -> float:
    """어두운 글자용: 배경의 어두운 쪽 5퍼센타일을 기준으로 가장 불리한 대비를 잰다."""
    im = Image.open(bg_png).convert("RGB")
    data = im.tobytes()
    lums = sorted(_luminance(data[i:i + 3]) for i in range(0, len(data), 3))
    bg = lums[int(len(lums) * 0.05)]
    return (bg + 0.05) / (text_lum + 0.05)


def _kind(doc: str) -> str:
    for k in ("cover", "stat", "outro", "list", "term", "qa", "compare", "quote", "slide"):
        if f'<body class="{k}' in doc:
            return k
    return "slide"


def render(pages: list[str], out_dir: str) -> tuple[list[str], list[dict]]:
    files, qa = [], []
    launch = {}
    if os.environ.get("CHROMIUM_PATH"):
        launch["executable_path"] = os.environ["CHROMIUM_PATH"]
    with sync_playwright() as pw:
        browser = pw.chromium.launch(**launch)
        page = browser.new_page(viewport={"width": W, "height": H})
        for n, doc in enumerate(pages, start=1):
            kind = _kind(doc)
            html_path = os.path.join(out_dir, f"card_{n:02d}.html")
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(doc)
            page.goto("file://" + os.path.abspath(html_path))
            page.evaluate("() => document.fonts.ready")   # Promise를 실제로 기다린다
            page.wait_for_timeout(150)
            if kind == "stat":
                page.evaluate(SHRINK_JS)
            jpg = os.path.join(out_dir, f"card_{n:02d}.jpg")
            page.screenshot(path=jpg, type="jpeg", quality=92)
            files.append(jpg)

            box = page.evaluate(LAYOUT_JS)
            issues = []
            contrast = None
            if kind not in ("stat", "list", "term", "qa", "compare", "quote"):   # 단색 배경 장은 대비 측정 생략
                page.evaluate("document.body.classList.add('notext')")
                bg_png = os.path.join(out_dir, f".bg_text_{n:02d}.png")
                page.screenshot(path=bg_png, clip={"x": box["x"], "y": box["y"],
                                                   "width": box["w"], "height": box["h"]})
                # 글자색은 잉크(#141414). 배경(종이·형광·사진)의 '어두운 쪽' 5퍼센타일 대비 글자가 충분히 어두운지 잰다
                contrast = round(_contrast_dark_text(bg_png, _luminance((0x14, 0x14, 0x14))), 2)
                os.remove(bg_png)
                if box["photo_bottom"] is not None and box["top"] < box["photo_bottom"] + 20:
                    issues.append(f"텍스트가 사진 액자와 겹침(top={box['top']:.0f}, photo_bottom={box['photo_bottom']:.0f})")
                if contrast < MIN_CONTRAST:
                    issues.append(f"대비 부족 {contrast}:1")
            else:
                if box["value_overflow"]:
                    issues.append("숫자가 카드 폭을 넘음 (160px까지 줄여도 부족)")
            if box["bottom"] > H - 80:
                issues.append("텍스트가 출처 줄과 겹침")
            if box["left"] < GRID_CROP or box["right"] > W - GRID_CROP:
                issues.append("프로필 그리드(3:4)에서 잘림")
            if box["wrapped"]:
                issues.append(f"제목 줄바꿈 발생: {box['wrapped']}")
            if box["fonts"] != "loaded":
                issues.append(f"폰트 로딩 상태 {box['fonts']}")
            size_mb = os.path.getsize(jpg) / 1e6
            if size_mb > 8:
                issues.append(f"파일 {size_mb:.1f}MB > 8MB")
            qa.append({"card": n, "kind": kind, "contrast": contrast, "text_top": round(box["top"]),
                       "size_mb": round(size_mb, 2), "issues": issues})
        browser.close()
    return files, qa
