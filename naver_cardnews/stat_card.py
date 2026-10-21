"""숫자 카드(stat) 렌더. HTML 템플릿을 채우고 Playwright(Chromium)로 1080×1350 PNG를 만든다."""

from __future__ import annotations

import html
import os
import re
from dataclasses import dataclass
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "stat_card.html"
LABEL_TOP = "AI로 재가공한 뉴스"
MAX_LABEL_CHARS = 14
MAX_QUOTE_CHARS = 70


@dataclass
class Stat:
    value: str          # "55", "1,000", "34.7"
    unit: str           # "%", "조원", "억달러"
    label: str          # 한 줄 설명 (≤14자)
    source_quote: str   # 원문에서 수치가 든 문장 그대로


class StatError(ValueError):
    pass


def validate_stat(stat: Stat, article_text: str | None = None) -> None:
    """작성 규칙 검사. article_text를 주면 원문 대조까지 한다 (validate.py의 수치 대조 보완)."""
    if not re.fullmatch(r"[0-9][0-9,]*(\.[0-9]{1,2})?", stat.value):
        raise StatError(f"value는 숫자만, 소수점 둘째 자리까지: {stat.value!r}")
    if not stat.unit.strip():
        raise StatError("단위가 없는 숫자는 쓰지 않는다")
    if len(stat.label) > MAX_LABEL_CHARS:
        raise StatError(f"label은 {MAX_LABEL_CHARS}자 이하: {stat.label!r}")
    quote_norm = stat.source_quote.replace(" ", "")
    if (stat.value + stat.unit).replace(" ", "") not in quote_norm:
        raise StatError("value+unit 이 source_quote 안에 그대로 없다")
    if article_text is not None and quote_norm not in article_text.replace(" ", ""):
        raise StatError("source_quote 가 원문에 없다")


def len_class(value: str, unit: str) -> str:
    """숫자 글자 수 + 단위 폭(한글 단위는 숫자 1자 폭, 기호는 반 자)으로 크기 단계를 정한다.
    렌더 때 그래도 넘치면 render_png가 글자 크기를 더 줄인다."""
    n = sum(ch.isdigit() for ch in value) + (0.5 if "." in value else 0)
    n += sum(1.0 if ord(ch) > 0x2E80 else 0.5 for ch in unit.strip())
    if n <= 3.5:
        return "short"
    if n <= 5.5:
        return "medium"
    return "long"


def render_html(stat: Stat, page_no: int, total: int = 6, label_top: str = LABEL_TOP) -> str:
    tpl = TEMPLATE.read_text(encoding="utf-8")
    quote = stat.source_quote
    if len(quote) > MAX_QUOTE_CHARS:
        quote = quote[:MAX_QUOTE_CHARS - 1] + "…"
    fields = {
        "label_top": label_top, "value": stat.value, "unit": stat.unit, "stat_label": stat.label,
        "quote": quote, "page_no": str(page_no), "total": str(total),
        "len_class": len_class(stat.value, stat.unit),
    }
    for k, v in fields.items():
        tpl = tpl.replace("{{" + k + "}}", html.escape(v))
    return tpl


def render_png(stat: Stat, out_path: Path, page_no: int, total: int = 6) -> dict:
    """PNG 저장 + 간단 QA(값 폭 넘침, 파일 크기). Playwright와 Chromium이 필요하다."""
    from playwright.sync_api import sync_playwright

    out_path.parent.mkdir(parents=True, exist_ok=True)
    html_path = out_path.with_suffix(".html")
    html_path.write_text(render_html(stat, page_no, total), encoding="utf-8")
    launch: dict = {}
    exe = os.environ.get("CHROMIUM_PATH")
    if exe:
        launch["executable_path"] = exe
    with sync_playwright() as p:
        browser = p.chromium.launch(**launch)
        page = browser.new_page(viewport={"width": 1080, "height": 1350}, device_scale_factor=1)
        page.goto(html_path.resolve().as_uri())
        page.wait_for_timeout(150)
        # 폭이 넘치면 160px까지 20px씩 줄인다 (폰트 폭 차이 대비)
        page.evaluate("""() => {
            const v = document.querySelector('.value'); const n = v.querySelector('.num');
            let size = parseFloat(getComputedStyle(v).fontSize);
            while (n.getBoundingClientRect().right > 1080 - 64 && size > 160) { size -= 20; v.style.fontSize = size + 'px'; }
        }""")
        qa = page.evaluate("""() => {
            const v = document.querySelector('.value .num'); const r = v.getBoundingClientRect();
            const q = document.querySelector('.quote');
            return {value_overflow: r.right > 1080 - 64, value_width: Math.round(r.width),
                    font_px: Math.round(parseFloat(getComputedStyle(document.querySelector('.value')).fontSize)),
                    quote_clipped: q.scrollHeight > q.clientHeight + 2};
        }""")
        page.screenshot(path=str(out_path), full_page=False)
        browser.close()
    qa["bytes"] = out_path.stat().st_size
    qa["ok"] = not qa["value_overflow"] and qa["bytes"] < 8 * 1024 * 1024
    return qa
