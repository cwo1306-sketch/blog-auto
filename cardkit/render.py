"""카드 렌더(Playwright·Chromium) + 자동 점검. 계정 설정(profile)으로 라벨·핸들·폰트·CTA·면책 문구를 넣는다.

- 색: 팔레트 역할 토큰을 :root 에 인라인으로 넣는다(계정 전용 팔레트도 파일 없이 적용)
- 레이아웃: templates/layout_<name>.css, 공통 뼈대: templates/card.css (절대 경로라 출력 폴더 위치와 무관)
- 점검: 글씨 대비(WCAG 4.5:1), 사진-글씨 겹침(풀블리드는 제외), 출처 줄 겹침, 3:4 그리드 잘림, 제목 줄바꿈, 폰트 로딩, 파일 크기
- Chromium 경로는 CHROMIUM_PATH 로 지정 가능
"""

from __future__ import annotations

import functools
import os
import re
from html import escape
from pathlib import Path

from PIL import Image

from . import palette as pal
from .chart import Chart, draw_script
from .profile import Profile
from .stat import len_class

TEMPLATES = Path(__file__).resolve().parent / "templates"
W, H = 1080, 1350
GRID_CROP = (W - H * 3 / 4) / 2  # 프로필 그리드 3:4 노출 시 좌우로 잘리는 폭
MIN_CONTRAST = 4.5               # WCAG 2.x AA 일반 텍스트 기준
STAT_MAX_QUOTE = 70


FONT_ALL = """body.cover .line, body.slide h2, body.list h2, body.list .list-num, body.term .term, body.qa .q h2, body.compare h2,
body.quote blockquote, body.outro .summary, body.stat .value, body.stat .stat-label, body.slide .num-big, body.chart h2,
body.checklist h2, body.myth h2 { font-family: var(--display); font-weight: 400; font-synthesis: none; letter-spacing: -0.01em; }"""
FONT_NONE = "body.cover .line, body.outro .summary { font-family: var(--font); font-weight: 800; }"


def _head(profile: Profile, palette: str, layout: str) -> str:
    links = f'<link rel="stylesheet" href="{(TEMPLATES / "card.css").as_uri()}">'
    if layout and layout != "frame":
        links += f'<link rel="stylesheet" href="{(TEMPLATES / f"layout_{layout}.css").as_uri()}">'
    style = pal.css_vars(palette) + f":root {{ --font: {profile.font_body}; --display: {profile.font_display}; }}\n"
    style += FONT_ALL if profile.font_mode == "all" else FONT_NONE if profile.font_mode == "none" else ""
    return links + f"<style>{style}</style>"


def _page(inner: str, bg: str | None, kind: str, source: str, page_no: str, num: str = "", *,
          profile: Profile, palette: str, layout: str) -> str:
    photo = f"""<div class="photo"><div class="bg" style="background-image:url('{bg}')"></div></div>""" if bg else ""
    num_big = f'<div class="num-big">{num}</div>' if num else ""
    plain = "" if (bg or kind != "slide") else " plain"
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">{_head(profile, palette, layout)}</head>
<body class="{kind}{plain}">
{photo}{num_big}
<div class="pill">{escape(profile.label_top)}</div>
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


def _chart_inner(s: dict) -> str:
    """그래프 장: 제목(결론) + 단위 + ECharts 영역 + 해석 한 줄. 그리기는 카드 안 스크립트가 CSS 토큰 색으로 한다."""
    ch = Chart.from_dict(s["chart"])
    body = f'<p class="chart-note">{escape(s["body"])}</p>' if s.get("body") else ""
    return (f'<div class="text"><h2>{escape(s.get("title", ""))}</h2><div class="chart-unit">단위: {escape(ch.unit)}</div></div>'
            f'<div id="chart"></div>{body}'
            f'<script src="{(TEMPLATES / "vendor" / "echarts.min.js").as_uri()}"></script><script>{draw_script(ch)}</script>')


def _checklist_inner(s: dict) -> str:
    items = "".join(f'<li><span class="box"></span>{escape(it)}</li>' for it in s.get("items") or [])
    note = f'<p class="note">{escape(s["body"])}</p>' if s.get("body") else ""
    return f'<div class="text"><div class="kicker">스스로 체크해 보세요</div><h2>{escape(s.get("title", ""))}</h2><ul class="checks">{items}</ul>{note}</div>'


def _myth_inner(s: dict) -> str:
    return (f'<div class="text"><div class="tag tag-myth">오해</div><h2>{escape(s.get("title", ""))}</h2>'
            f'<div class="fact"><div class="tag tag-fact">사실</div><p>{escape(s.get("body", ""))}</p></div></div>')


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


def build_pages(script: dict, images: list[str | None], source: str, profile: Profile, palette: str, layout: str = "frame") -> list[str]:
    """images[i]는 i번째 장(0=표지)의 사진 파일명(출력 폴더 기준), 사진 없는 장은 None. source 는 카드 하단 출처 문구."""
    page = functools.partial(_page, profile=profile, palette=palette, layout=layout)
    slides = script["slides"]
    total = 2 + len(slides)
    # 강조 줄은 형광펜(mark)으로. 글자색 노랑(구 템플릿)은 종이 배경에서 대비가 안 나와 쓰지 않는다
    lines = "".join(
        f'<div class="line">{"<mark>" + escape(l["text"]) + "</mark>" if l.get("highlight") else escape(l["text"])}</div>'
        for l in script["cover"]["lines"])
    pages = [page(f'<div class="text">{lines}<div class="handle">{escape(profile.handle)}</div></div>',
                   images[0], "cover", source, f"1/{total}")]
    for i, s in enumerate(slides, start=2):
        kind = s.get("slide_type", "photo")
        num = f"{i - 1:02d}"
        if kind == "stat" and s.get("stat"):
            pages.append(page(_stat_inner(s["stat"]), None, "stat", source, f"{i}/{total}"))
        elif kind == "chart" and s.get("chart"):
            pages.append(page(_chart_inner(s), None, "chart", source, f"{i}/{total}"))
        elif kind == "list":
            pages.append(page(_list_inner(num, s), None, "list", source, f"{i}/{total}"))
        elif kind == "term":
            pages.append(page(_term_inner(s), None, "term", source, f"{i}/{total}"))
        elif kind == "qa":
            pages.append(page(_qa_inner(str(i - 1), s), None, "qa", source, f"{i}/{total}"))
        elif kind == "compare" and s.get("compare"):
            pages.append(page(_compare_inner(s), None, "compare", source, f"{i}/{total}"))
        elif kind == "checklist":
            pages.append(page(_checklist_inner(s), None, "checklist", source, f"{i}/{total}"))
        elif kind == "myth":
            pages.append(page(_myth_inner(s), None, "myth", source, f"{i}/{total}"))
        elif kind == "quote":
            pages.append(page(_quote_inner(s), None, "quote", source, f"{i}/{total}"))
        else:
            inner = f'<div class="text"><h2>{escape(s["title"])}</h2><p>{escape(s["body"])}</p></div>'
            pages.append(page(inner, images[i - 1], "slide", source, f"{i}/{total}", num=num))
    o = script["outro"]
    inner = (f'<div class="text"><div class="kicker">오늘의 핵심</div>'
             f'<div class="summary">{escape(o["summary"])}</div>'
             f'<div class="question">Q. {escape(o["question"])}</div>'
             f'<div class="cta">{"".join(f"<span>{escape(c)}</span>" for c in profile.cta)}</div>'
             f'<div class="handle">{escape(profile.handle)}</div></div>')
    if profile.disclaimer:
        inner += f'<div class="disclaimer">{escape(profile.disclaimer)}</div>'
    pages.append(page(inner, None, "outro", source, f"{total}/{total}"))   # 마무리는 형광 블록, 사진 없음
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
          overlay: getComputedStyle(document.body).getPropertyValue('--overlay').trim() === '1',
          text_color: getComputedStyle(document.querySelector('.summary') || document.querySelector('.text h2')
                                       || document.querySelector('.line') || document.querySelector('.text')).color,
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
    for k in ("cover", "stat", "chart", "outro", "list", "term", "qa", "compare", "quote", "checklist", "myth", "slide"):
        if f'<body class="{k}' in doc:
            return k
    return "slide"


def render(pages: list[str], out_dir: str) -> tuple[list[str], list[dict]]:
    from playwright.sync_api import sync_playwright
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
            if kind == "chart":
                page.wait_for_function("window.__chartDone === true", timeout=10000)
            jpg = os.path.join(out_dir, f"card_{n:02d}.jpg")
            page.screenshot(path=jpg, type="jpeg", quality=92)
            files.append(jpg)

            box = page.evaluate(LAYOUT_JS)
            issues = []
            contrast = None
            if kind in ("cover", "slide", "outro"):   # 단색 배경 장은 대비 측정 생략
                page.evaluate("document.body.classList.add('notext')")
                bg_png = os.path.join(out_dir, f".bg_text_{n:02d}.png")
                page.screenshot(path=bg_png, clip={"x": box["x"], "y": box["y"],
                                                   "width": box["w"], "height": box["h"]})
                # 실제 글씨 색으로 잰다: 어두운 글씨면 배경의 밝은 쪽이 아니라 어두운 쪽(5퍼센타일)이,
                # 밝은 글씨(마무리 장 흰 글씨 등)면 배경의 밝은 쪽(95퍼센타일)이 가장 불리한 경우다.
                rgb = tuple(int(x) for x in re.findall(r"\d+", box["text_color"])[:3]) or (0x14, 0x14, 0x14)
                tl = _luminance(rgb)
                contrast = round(_contrast(bg_png, tl) if tl > 0.4 else _contrast_dark_text(bg_png, tl), 2)
                os.remove(bg_png)
                # 풀블리드처럼 글씨를 사진 위에 얹는 레이아웃(--overlay:1)은 겹침이 의도이므로 대비 검사만 한다
                if box["photo_bottom"] is not None and not box["overlay"] and box["top"] < box["photo_bottom"] + 20:
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
