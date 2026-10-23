"""차트 장(chart): 연도별 추세·비교·비중을 Apache ECharts 로 그린다 (docs/CHARTS.md).

원고 스키마: chart = {type: bar|line|donut|compare, unit: 원문 단위, labels: [..], values: ["2.8", ...],
highlight: 강조할 값의 위치(0부터, 없으면 막대·선은 마지막, 도넛은 최댓값), source_quote: 수치가 든 원문 문장(여러 문장은 " / " 로 잇는다)}.

숫자 규칙은 stat 장과 같다: 값은 원문 표기 그대로(환산·반올림 금지), 값+단위가 source_quote 안에 있어야 하고
source_quote 는 원문에 그대로 있어야 한다. 시각화 규칙: 막대는 0부터, 강조색은 한 곳만, 축 눈금 대신 값 라벨, 장당 차트 1개.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

TYPES = ("bar", "line", "donut", "compare")
POINTS = {"bar": (2, 6), "line": (3, 8), "donut": (2, 5), "compare": (2, 2)}
MAX_LABEL = 8
VALUE_RE = re.compile(r"-?[0-9][0-9,]*(\.[0-9]{1,2})?")
_WS = re.compile(r"[\s'\"‘’“”`]")


class ChartError(ValueError):
    pass


@dataclass
class Chart:
    type: str
    unit: str
    labels: list[str]
    values: list[str]
    source_quote: str
    highlight: int | None = None
    notes: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "Chart":
        hl = d.get("highlight")
        return cls(type=str(d.get("type", "bar")).strip().lower(), unit=str(d.get("unit", "")).strip(),
                   labels=[str(x).strip() for x in d.get("labels") or []],
                   values=[str(x).strip() for x in d.get("values") or []],
                   source_quote=str(d.get("source_quote", "")).strip(),
                   highlight=int(hl) if isinstance(hl, (int, float, str)) and str(hl).lstrip("-").isdigit() else None)

    def numbers(self) -> list[float]:
        return [float(v.replace(",", "")) for v in self.values]

    def highlight_index(self) -> int:
        if self.highlight is not None and 0 <= self.highlight < len(self.values):
            return self.highlight
        if self.type == "donut":
            nums = self.numbers()
            return nums.index(max(nums))
        return len(self.values) - 1

    def to_dict(self) -> dict:
        return {"type": self.type, "unit": self.unit, "labels": self.labels, "values": self.values,
                "highlight": self.highlight_index(), "source_quote": self.source_quote}


def _n(s: str) -> str:
    return _WS.sub("", s or "").replace(",", "")


def _has_value(value: str, unit: str, quote_n: str) -> bool:
    """값+단위(공백·쉼표 무시)가 인용문에 있는지. '10' 이 '100' 안에서 잡히지 않게 앞뒤 숫자 경계를 본다."""
    v = value.replace(",", "")
    u = _n(unit)
    for k in range(len(u), 0, -1):   # '조원' → '조' 순으로 (원문이 '10조 원' 이든 '10조원' 이든)
        if re.search(rf"(?<![\d.]){re.escape(v)}{re.escape(u[:k])}", quote_n):
            return True
    return False


def validate_chart(chart: Chart, article_text: str | None = None) -> None:
    if chart.type not in TYPES:
        raise ChartError(f"type 은 {'/'.join(TYPES)} 중 하나: {chart.type!r}")
    lo, hi = POINTS[chart.type]
    n = len(chart.values)
    if not lo <= n <= hi:
        raise ChartError(f"{chart.type} 는 값 {lo}~{hi}개 (받은 값 {n}개)")
    if len(chart.labels) != n:
        raise ChartError(f"labels {len(chart.labels)}개와 values {n}개가 다름")
    for lab in chart.labels:
        if not lab or len(lab) > MAX_LABEL:
            raise ChartError(f"라벨은 1~{MAX_LABEL}자: {lab!r}")
    if not chart.unit:
        raise ChartError("단위가 없는 차트는 쓰지 않는다")
    for v in chart.values:
        if not VALUE_RE.fullmatch(v):
            raise ChartError(f"값은 숫자만(쉼표·소수점 둘째 자리): {v!r}")
    nums = chart.numbers()
    if chart.type in ("bar", "donut", "compare") and min(nums) < 0:
        raise ChartError("막대·도넛·비교는 음수를 쓰지 않는다(0 기준선)")
    if chart.type == "donut":
        if chart.unit.replace(" ", "") not in ("%", "퍼센트"):
            raise ChartError("도넛은 비중(%)일 때만")
        if not 95 <= sum(nums) <= 105:
            raise ChartError(f"도넛 비중 합 {sum(nums):g}% (95~105% 여야 함)")
    if not chart.source_quote:
        raise ChartError("source_quote 필요")
    quote_n = _n(chart.source_quote)
    for v in chart.values:
        if not _has_value(v, chart.unit, quote_n):
            raise ChartError(f"값 '{v}{chart.unit}' 이 source_quote 안에 그대로 없다")
    if article_text is not None:
        body_n = _n(article_text)
        for part in chart.source_quote.split(" / "):
            if _n(part) not in body_n:
                raise ChartError("source_quote 가 원문에 없다")


# ---------- 렌더 (카드 HTML 안에서 ECharts 가 그린다) ----------

ECHARTS_SRC = "../../templates/vendor/echarts.min.js"

# 색은 카드의 CSS 토큰에서 읽는다(팔레트·다크 모드 자동 대응). 강조 = --brand, 보조 = 잉크를 옅게 섞은 색, 라벨 = --ink / --ink-2.
# 그린 뒤 window.__chartDone = true (렌더러가 이 신호를 기다린 뒤 캡처한다).
DRAW_JS = r"""
(function () {
  const data = __DATA__;
  const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  function mix(a, b, t) {   // a 를 t 비율로, 나머지는 b
    const h = s => s.replace('#', '').match(/../g).map(x => parseInt(x, 16));
    const [x, y] = [h(a), h(b)];
    return '#' + x.map((v, i) => Math.round(v * t + y[i] * (1 - t)).toString(16).padStart(2, '0')).join('');
  }
  function draw() {
    const brand = css('--brand'), ink = css('--ink'), ink2 = css('--ink-2'), bg = css('--bg'), line = css('--line');
    const soft = mix(ink, bg, 0.16), font = 'Pretendard';
    const vals = data.values.map(v => parseFloat(String(v).replace(/,/g, '')));
    const hl = data.highlight;
    const label = {show: true, fontFamily: font, fontWeight: 800, color: ink, fontSize: 44,
                   formatter: p => data.values[p.dataIndex]};
    let opt;
    if (data.type === 'donut') {
      opt = {series: [{type: 'pie', radius: ['46%', '74%'], center: ['50%', '52%'], startAngle: 90, avoidLabelOverlap: true,
        itemStyle: {borderColor: bg, borderWidth: 6},
        label: {show: true, fontFamily: font, color: ink, fontSize: 32, fontWeight: 700, lineHeight: 44,
                formatter: p => p.name + '\n' + data.values[p.dataIndex] + data.unit},
        labelLine: {length: 18, length2: 18, lineStyle: {color: ink2}},
        data: vals.map((v, i) => ({value: v, name: data.labels[i],
          itemStyle: {color: i === hl ? brand : mix(ink, bg, 0.12 + 0.12 * (i % 3))}}))}]};
    } else {
      const isLine = data.type === 'line';
      // 선 그래프는 양 끝 점이 가장자리에 붙으므로(boundaryGap=false) 좌우 여백을 둬 값 라벨이 잘리지 않게 한다
      const pad = isLine ? 64 : 8;
      opt = {grid: {left: pad, right: pad, top: 80, bottom: 8, containLabel: true},
        xAxis: {type: 'category', data: data.labels, axisTick: {show: false}, boundaryGap: !isLine,
                axisLine: {lineStyle: {color: line, width: 2}},
                axisLabel: {fontFamily: font, fontSize: 32, fontWeight: 700, color: ink2, margin: 20}},
        yAxis: {type: 'value', show: false, scale: isLine,
                min: isLine ? (v => v.min - (v.max - v.min) * 0.3) : 0},   // 막대는 0부터, 선은 최솟값 아래로 여유
        series: [isLine ? {type: 'line', smooth: false, symbol: 'circle', symbolSize: 18, lineStyle: {width: 6, color: brand},
                            itemStyle: {color: brand}, areaStyle: {color: mix(brand, bg, 0.12)},
                            label: Object.assign({}, label, {position: 'top', fontSize: 38}),
                            data: vals.map((v, i) => ({value: v, symbolSize: i === hl ? 28 : 16,
                                                       label: {color: i === hl ? brand : ink}}))}
                         : {type: 'bar', barWidth: data.type === 'compare' ? '38%' : '52%',
                            label: Object.assign({}, label, {position: 'top'}),
                            data: vals.map((v, i) => ({value: v, itemStyle: {color: i === hl ? brand : soft, borderRadius: [18, 18, 0, 0]}}))}]};
    }
    opt.animation = false;
    const el = document.getElementById('chart');
    echarts.init(el, null, {renderer: 'svg'}).setOption(opt);
    window.__chartDone = true;
  }
  (document.fonts && document.fonts.ready ? document.fonts.ready : Promise.resolve()).then(draw);
})();
"""


def draw_script(chart: Chart) -> str:
    return DRAW_JS.replace("__DATA__", json.dumps(chart.to_dict(), ensure_ascii=False))
