"""원고 채점표(rubric) + LLM 판정기(LLM-as-a-judge) + 사람 기준선 보정(일치도 통계).

채점표 5축, 각 1~5점:
  fact        사실 일치     원고의 모든 주장·수치에 원문 근거가 있는가 (근거 없는 문장 1개면 ≤3, 수치 오류면 ≤2)
  attribution 출처 주체     "회사 자료에 따르면/자체 평가 기준" 등 누가 말한 수치·주장인지 밝혔는가
  plain       쉬운 말       문장 짧고(어절 ≤12), 전문용어 첫 등장 시 풀이, 번역투·피동 적음, 비유가 있는가
  structure   구조 준수     format 규칙(장 역할·순서·장 수·길이)을 지켰는가, 2장이 표지 반복이 아닌가
  hook        훅과 마무리   표지가 멈추게 하는가, 마무리 질문이 댓글을 부르는가, 캡션이 표지와 다른 표현인가

사람 채점(엑셀 '채점' 시트)과 판정기 점수를 같은 축으로 모아 축별 가중 카파(quadratic weighted kappa)·평균 편차를 계산한다.
카파 0.6 미만인 축은 판정기를 믿지 말고 사람 채점을 늘리거나 판정 기준 문구를 고친다.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from statistics import mean

log = logging.getLogger(__name__)

AXES = ["fact", "attribution", "plain", "structure", "hook"]
AXIS_KO = {"fact": "사실 일치", "attribution": "출처 주체", "plain": "쉬운 말", "structure": "구조 준수", "hook": "훅·마무리"}
WEIGHTS = {"fact": 0.35, "attribution": 0.15, "plain": 0.25, "structure": 0.1, "hook": 0.15}
JUDGE_MODEL = "claude-sonnet-5-5"

JUDGE_SYSTEM = """너는 뉴스 데스크의 데스킹 담당이자 인스타그램 카드뉴스 'AI 뉴스 3분 브리핑'의 편집장이다.
기사 원문과 카드뉴스 원고(JSON)를 받아 아래 5축을 1~5점으로 채점한다. 점수는 보수적으로 준다(근거 없는 칭찬 금지).

채점표
- fact(사실 일치): 원고의 주장·수치가 모두 원문에 근거하는가. 근거 없는 문장이 1개라도 있으면 3점 이하, 수치·단위가 틀리면 2점 이하, 원문과 반대면 1점.
- attribution(출처 주체): 수치·평가·전망을 누가 말했는지(회사 자료, 정부 통계, 전문가) 원고가 밝히는가. 자체 평가를 사실처럼 쓰면 2점 이하.
- plain(쉬운 말): 문장당 어절 12개 이하, 전문용어는 첫 등장에서 한 번 풀이, 번역투·피동·명사 나열이 적고, 어려운 원리에 일상 비유가 있는가.
- structure(구조 준수): format 규칙대로 장의 역할·순서·길이를 지켰는가. 2장이 표지 반복이면 감점. stat 수치·인용문이 원문 문장 그대로인가.
- hook(훅·마무리): 표지가 스크롤을 멈추게 하는가(질문·수치·반전), 마무리 질문이 댓글을 부르는가, 캡션 첫 줄이 표지와 다른 표현인가.

반드시 아래 JSON만 출력한다.
{"scores":{"fact":int,"attribution":int,"plain":int,"structure":int,"hook":int},
 "issues":[{"axis":str,"slide":int|null,"text":"문제 문장 또는 위치","why":"한 문장"}],
 "unsupported_claims":["원문에 근거가 없는 원고 문장 그대로"],
 "summary":"두 문장 이내 총평"}"""


@dataclass
class Evaluation:
    scores: dict[str, int]
    issues: list[dict] = field(default_factory=list)
    unsupported_claims: list[str] = field(default_factory=list)
    summary: str = ""
    usage: dict = field(default_factory=dict)

    @property
    def total(self) -> float:
        return round(sum(self.scores.get(a, 0) * WEIGHTS[a] for a in AXES), 2)

    def to_dict(self) -> dict:
        return {"scores": self.scores, "total": self.total, "issues": self.issues,
                "unsupported_claims": self.unsupported_claims, "summary": self.summary, "usage": self.usage}


def parse_evaluation(text: str) -> Evaluation:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError(f"판정 JSON 없음: {text[:120]!r}")
    d = json.loads(m.group(0))
    scores = {a: max(1, min(5, int(d.get("scores", {}).get(a, 0) or 0))) for a in AXES}
    return Evaluation(scores=scores, issues=list(d.get("issues") or []),
                      unsupported_claims=list(d.get("unsupported_claims") or []), summary=str(d.get("summary", "")))


def script_for_judge(script: dict) -> dict:
    """판정에 불필요한 필드(검색어 등)를 뺀 원고."""
    out = {"format": script.get("format"), "cover": [l["text"] for l in script["cover"]["lines"]], "slides": [], "outro": script["outro"],
           "caption": script.get("caption", "")}
    for i, s in enumerate(script["slides"], start=2):
        item = {"slide": i, "type": s.get("slide_type"), "title": s.get("title"), "body": s.get("body")}
        if s.get("label"):
            item["label"] = s["label"]
        if s.get("stat"):
            item["stat"] = s["stat"]
        if s.get("compare"):
            item["compare"] = s["compare"]
        out["slides"].append(item)
    return out


class Judge:
    def __init__(self, api_key: str | None = None, model: str = JUDGE_MODEL):
        import anthropic
        self.client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
        self.model = model

    def evaluate(self, script: dict, article_body: str, format_rules: str = "", meta: dict | None = None) -> Evaluation:
        """meta: {press, title, date}. 캡션 '출처: 언론사' 줄은 본문이 아니라 이 메타데이터가 근거다."""
        m = meta or {}
        meta_txt = (f"언론사: {m.get('press', '')}\n기사 제목: {m.get('title', '')}\n발행일: {m.get('date', '')}\n"
                    "(캡션의 '출처:' 줄은 위 언론사명과 맞는지만 본다.)")
        user = (f"[format 규칙]\n{format_rules}\n\n[기사 메타데이터]\n{meta_txt}\n\n[기사 원문]\n{article_body}\n\n"
                f"[카드뉴스 원고]\n{json.dumps(script_for_judge(script), ensure_ascii=False, indent=1)}")
        msg = self.client.messages.create(
            model=self.model, max_tokens=4000, system=JUDGE_SYSTEM,
            output_config={"effort": "medium"},
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(b.text for b in msg.content if b.type == "text")
        ev = parse_evaluation(text)
        ev.usage = {"model": self.model, "input_tokens": msg.usage.input_tokens, "output_tokens": msg.usage.output_tokens}
        return ev


# --- 결정적 가독성 지표 (판정기와 별개로 엑셀에 같이 싣는다) -----------------------
_SENT_SPLIT = re.compile(r"(?<=[.!?다요죠])\s+")


def plain_metrics(script: dict) -> dict:
    texts = [s.get("body", "") for s in script["slides"] if s.get("body")] + [script["outro"]["summary"]]
    sents = [x.strip() for t in texts for x in _SENT_SPLIT.split(t) if x.strip()]
    if not sents:
        return {"sentences": 0, "avg_words": 0, "max_words": 0, "long_sentences": 0}
    words = [len(s.split()) for s in sents]
    return {"sentences": len(sents), "avg_words": round(mean(words), 1), "max_words": max(words),
            "long_sentences": sum(1 for w in words if w > 12)}


# --- 사람 기준선과의 일치도 ------------------------------------------------------
def weighted_kappa(a: list[int], b: list[int], k: int = 5) -> float | None:
    """Quadratic weighted Cohen's kappa (1~k 점). 표본 2개 미만이면 None."""
    n = len(a)
    if n < 2 or len(b) != n:
        return None
    O = [[0] * k for _ in range(k)]
    for x, y in zip(a, b):
        O[x - 1][y - 1] += 1
    ra = [sum(O[i]) for i in range(k)]
    rb = [sum(O[i][j] for i in range(k)) for j in range(k)]
    num = den = 0.0
    for i in range(k):
        for j in range(k):
            w = ((i - j) ** 2) / ((k - 1) ** 2)
            num += w * O[i][j]
            den += w * ra[i] * rb[j] / n
    if den == 0:
        return 1.0 if num == 0 else 0.0
    return round(1 - num / den, 3)


def agreement_report(pairs: list[tuple[dict, dict]]) -> dict:
    """pairs: [(judge_scores, human_scores), ...] 같은 원고에 대한 쌍. 축별 카파·평균 편차·±1 일치율."""
    out = {"n": len(pairs), "axes": {}}
    for a in AXES:
        j = [int(p[0].get(a, 0)) for p in pairs if p[0].get(a) and p[1].get(a)]
        h = [int(p[1].get(a, 0)) for p in pairs if p[0].get(a) and p[1].get(a)]
        if not j:
            out["axes"][a] = {"n": 0}
            continue
        within1 = sum(1 for x, y in zip(j, h) if abs(x - y) <= 1) / len(j)
        out["axes"][a] = {"n": len(j), "kappa": weighted_kappa(j, h), "bias": round(mean(j) - mean(h), 2),
                          "within1": round(within1, 2), "judge_mean": round(mean(j), 2), "human_mean": round(mean(h), 2)}
    return out


def verdict(report: dict) -> list[str]:
    lines = []
    for a, r in report["axes"].items():
        if r.get("n", 0) < 5:
            lines.append(f"{AXIS_KO[a]}: 표본 {r.get('n', 0)}건 — 사람 채점 5건 이상 필요")
            continue
        k = r["kappa"]
        level = "신뢰" if k is not None and k >= 0.6 else ("참고" if k is not None and k >= 0.4 else "불신")
        bias = f", 판정기가 {'후하게' if r['bias'] > 0.3 else '박하게' if r['bias'] < -0.3 else '비슷하게'} 줌({r['bias']:+.2f})"
        lines.append(f"{AXIS_KO[a]}: κ={k} → {level}{bias}, ±1 일치 {int(r['within1'] * 100)}%")
    return lines
