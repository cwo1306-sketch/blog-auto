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
from statistics import mean, median

log = logging.getLogger(__name__)

AXES = ["fact", "attribution", "plain", "structure", "hook"]
AXIS_KO = {"fact": "사실 일치", "attribution": "출처 주체", "plain": "쉬운 말", "structure": "구조 준수", "hook": "훅·마무리"}
WEIGHTS = {"fact": 0.35, "attribution": 0.15, "plain": 0.25, "structure": 0.1, "hook": 0.15}
JUDGE_MODEL = "claude-sonnet-5-5"      # 기본 판정기 (게이트에 쓰인다)
ALT_JUDGE_MODEL = "claude-opus-5-5"    # 비교 판정기: 작성기(Sonnet)와 다른 모델. 사람 기준선과 더 잘 맞는 쪽을 기본으로 삼는다
CLAIM_TYPES = ("사실 주장", "해석", "수사", "용어 풀이")
FALLBACK_BETA = "server-side-fallback-2026-07-01"

JUDGE_SYSTEM = """너는 뉴스 데스크의 데스킹 담당이자 인스타그램 카드뉴스 'AI 뉴스 3분 브리핑'의 편집장이다.
기사 원문과 카드뉴스 원고(JSON)를 받아 아래 5축을 1~5점으로 채점한다. 점수는 보수적으로 준다(근거 없는 칭찬 금지).

채점표
- fact(사실 일치): 원고의 주장·수치가 모두 원문에 근거하는가. 근거 없는 문장이 1개라도 있으면 3점 이하, 수치·단위가 틀리면 2점 이하, 원문과 반대면 1점.
- attribution(출처 주체): 수치·평가·전망을 누가 말했는지(회사 자료, 정부 통계, 전문가) 원고가 밝히는가. 자체 평가를 사실처럼 쓰면 2점 이하.
- plain(쉬운 말): 문장당 어절 12개 이하, 전문용어는 첫 등장에서 한 번 풀이, 번역투·피동·명사 나열이 적고, 어려운 원리에 일상 비유가 있는가.
- structure(구조 준수): format 규칙대로 장의 역할·순서·길이를 지켰는가. 2장이 표지 반복이면 감점. stat 수치·인용문이 원문 문장 그대로인가.
- hook(훅·마무리): 표지가 스크롤을 멈추게 하는가(질문·수치·반전), 마무리 질문이 댓글을 부르는가, 캡션 첫 줄이 표지와 다른 표현인가.

unsupported_claims 에는 원문에 근거가 없는 원고 문장을 그대로 옮기고, 각 항목의 type 을 하나 고른다.
- "사실 주장": 사건·수치·발언·주체에 관한 단정 (예: "조경태 의원 측 주장에 따르면…", "누구나 내려받을 수 있습니다")
- "해석": 원고가 덧붙인 의미 부여·전망 ("새 변수가 됐습니다")
- "수사": 질문·감탄 등 사실을 주장하지 않는 문장 ("로봇 강국인데 AI는 왜 못 쓸까?")
- "용어 풀이": 일반적인 용어 설명 ("비전 인코더는 사진의 특징을 뽑아…"). 풀이가 틀렸으면 "사실 주장"으로 분류한다.
원고에 장별 evidence(작성자가 밝힌 근거 원문 문장)가 있으면, 그 장의 주장이 evidence 로 실제로 뒷받침되는지도 본다.

반드시 아래 JSON만 출력한다.
{"scores":{"fact":int,"attribution":int,"plain":int,"structure":int,"hook":int},
 "issues":[{"axis":str,"slide":int|null,"text":"문제 문장 또는 위치","why":"한 문장"}],
 "unsupported_claims":[{"text":"원문에 근거가 없는 원고 문장 그대로","type":"사실 주장"|"해석"|"수사"|"용어 풀이","slide":int|null}],
 "summary":"두 문장 이내 총평"}"""


@dataclass
class Evaluation:
    scores: dict[str, int]
    issues: list[dict] = field(default_factory=list)
    unsupported_claims: list[dict] = field(default_factory=list)   # {text, type, slide, [votes]}
    summary: str = ""
    usage: dict = field(default_factory=dict)
    runs: list[dict] = field(default_factory=list)                  # 반복 채점 시 각 회차 점수
    stable: bool = True                                             # 회차 간 사실 일치 점수가 같았나

    @property
    def factual_claims(self) -> list[dict]:
        return [c for c in self.unsupported_claims if c.get("type") == "사실 주장"]

    @property
    def total(self) -> float:
        return round(sum(self.scores.get(a, 0) * WEIGHTS[a] for a in AXES), 2)

    def to_dict(self) -> dict:
        return {"scores": self.scores, "total": self.total, "issues": self.issues,
                "unsupported_claims": self.unsupported_claims, "summary": self.summary, "usage": self.usage,
                "runs": self.runs, "stable": self.stable}


def _claim(c) -> dict:
    if isinstance(c, str):
        return {"text": c, "type": "사실 주장", "slide": None}   # 유형 없는 옛 형식은 보수적으로 사실 주장
    t = c.get("type") if c.get("type") in CLAIM_TYPES else "사실 주장"
    return {"text": str(c.get("text", "")), "type": t, "slide": c.get("slide")}


def parse_evaluation(text: str) -> Evaluation:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError(f"판정 JSON 없음: {text[:120]!r}")
    d = json.loads(m.group(0))
    scores = {a: max(1, min(5, int(d.get("scores", {}).get(a, 0) or 0))) for a in AXES}
    return Evaluation(scores=scores, issues=list(d.get("issues") or []),
                      unsupported_claims=[_claim(c) for c in (d.get("unsupported_claims") or [])], summary=str(d.get("summary", "")))


def _ckey(text: str) -> str:
    return re.sub(r"[\s'\"‘’“”.,…!?·]", "", text)[:30]


def combine(runs: list[Evaluation]) -> Evaluation:
    """반복 채점 결과 합치기. 3회면 축별 중앙값, 2회면 낮은 점수(보수적). 근거 없는 주장은 과반 회차에 나온 것만 남긴다."""
    n = len(runs)
    if n == 1:
        return runs[0]
    scores = {a: (int(median([r.scores[a] for r in runs])) if n >= 3 else min(r.scores[a] for r in runs)) for a in AXES}
    need = n // 2 + 1 if n >= 3 else n
    votes: dict[str, list[dict]] = {}
    for r in runs:
        seen = set()
        for c in r.unsupported_claims:
            k = _ckey(c["text"])
            if k and k not in seen:
                seen.add(k)
                votes.setdefault(k, []).append(c)
    claims = []
    for k, cs in votes.items():
        if len(cs) >= need:
            types = [c["type"] for c in cs]
            t = "사실 주장" if "사실 주장" in types else max(set(types), key=types.count)   # 한 번이라도 사실 주장이면 사실 주장
            claims.append({"text": cs[0]["text"], "type": t, "slide": cs[0].get("slide"), "votes": len(cs)})
    worst = min(runs, key=lambda r: r.scores["fact"])
    usage = {"model": runs[0].usage.get("model"), "runs": n,
             "input_tokens": sum(r.usage.get("input_tokens", 0) for r in runs),
             "output_tokens": sum(r.usage.get("output_tokens", 0) for r in runs)}
    return Evaluation(scores=scores, issues=worst.issues, unsupported_claims=claims, summary=worst.summary, usage=usage,
                      runs=[r.scores for r in runs], stable=len({r.scores["fact"] for r in runs}) == 1)


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
        if s.get("evidence"):
            item["evidence"] = s["evidence"]
        out["slides"].append(item)
    return out


class Judge:
    def __init__(self, api_key: str | None = None, model: str = JUDGE_MODEL):
        import anthropic
        self.client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
        self.model = model

    def evaluate_stable(self, script: dict, article_body: str, format_rules: str = "", meta: dict | None = None,
                        max_runs: int = 3) -> Evaluation:
        """같은 원고를 2회 채점하고, 사실 일치 점수가 다르면 3회째로 결정한다 (실측: 같은 원고에서 3→2 로 흔들림)."""
        runs = [self.evaluate(script, article_body, format_rules, meta) for _ in range(2)]
        if runs[0].scores["fact"] != runs[1].scores["fact"] and max_runs >= 3:
            runs.append(self.evaluate(script, article_body, format_rules, meta))
        return combine(runs)

    def evaluate(self, script: dict, article_body: str, format_rules: str = "", meta: dict | None = None) -> Evaluation:
        """meta: {press, title, date}. 캡션 '출처: 언론사' 줄은 본문이 아니라 이 메타데이터가 근거다."""
        m = meta or {}
        meta_txt = (f"언론사: {m.get('press', '')}\n기사 제목: {m.get('title', '')}\n발행일: {m.get('date', '')}\n"
                    "(캡션의 '출처:' 줄은 위 언론사명과 맞는지만 본다.)")
        user = (f"[format 규칙]\n{format_rules}\n\n[기사 메타데이터]\n{meta_txt}\n\n[기사 원문]\n{article_body}\n\n"
                f"[카드뉴스 원고]\n{json.dumps(script_for_judge(script), ensure_ascii=False, indent=1)}")
        # 거부(refusal) 시 서버가 다른 모델로 자동 재시도하도록 server-side fallback 을 켠다
        msg = self.client.beta.messages.create(
            model=self.model, max_tokens=4000, system=JUDGE_SYSTEM,
            output_config={"effort": "medium"}, betas=[FALLBACK_BETA], fallbacks="default",
            messages=[{"role": "user", "content": user}],
        )
        if msg.stop_reason == "refusal":
            raise RuntimeError("판정 모델이 채점을 거부했습니다")
        text = "".join(b.text for b in msg.content if b.type == "text")
        ev = parse_evaluation(text)
        ev.usage = {"model": self.model, "input_tokens": msg.usage.input_tokens, "output_tokens": msg.usage.output_tokens}
        return ev


# --- 제작 게이트 -------------------------------------------------------------
FACT_GATE = 2   # 판정기 사실 일치가 이 값 이하면 제작 중단


def ensure_judged(db, article_id: str, version: int, script: dict, body: str, meta: dict, judge: "Judge | None"):
    """해당 버전의 판정을 돌려준다. 없으면 judge 로 (반복) 채점해 저장한다(judge 가 None 이면 None)."""
    ev = db.evaluation(article_id, version, "judge")
    if ev is not None or judge is None:
        return ev
    from .formats import format_rules
    res = judge.evaluate_stable(script, body, format_rules(script.get("format")), meta=meta)
    db.save_evaluation(article_id, version, "judge", res.scores, res.total, res.to_dict())
    return db.evaluation(article_id, version, "judge")


def gate(ev) -> tuple[bool, str]:
    """(통과 여부, 사유).
    - 판정이 없으면 막는다 (엑셀에서 고친 새 버전이 판정 없이 제작되는 것을 막기 위해)
    - 사실 일치 ≤ FACT_GATE 이고, 반복 채점에서 과반이 지적한 '사실 주장' 유형의 근거 없는 문장이 1개 이상이면 막는다.
      수사·해석·용어 풀이만 지적된 경우는 막지 않는다 (판정 기준은 그대로, 게이트 대상만 사실 주장으로 한정)."""
    if ev is None:
        return False, "이 원고 버전의 LLM 판정이 없음 (python -m naver_cardnews judge 실행 필요)"
    scores = json.loads(ev["scores_json"])
    claims = [_claim(c) for c in json.loads(ev["detail_json"]).get("unsupported_claims", [])]
    factual = [c["text"] for c in claims if c["type"] == "사실 주장"]
    if scores.get("fact", 5) <= FACT_GATE and factual:
        return False, f"판정 사실 일치 {scores['fact']}점 ≤ {FACT_GATE}, 근거 없는 사실 주장 {len(factual)}건: {factual}"
    return True, ""


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


def spearman(a: list[float], b: list[float]) -> float | None:
    """스피어만 순위 상관 (동점은 평균 순위). 표본 3개 미만이면 None."""
    n = len(a)
    if n < 3:
        return None

    def ranks(v):
        order = sorted(range(n), key=lambda i: v[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and v[order[j + 1]] == v[order[i]]:
                j += 1
            for k in range(i, j + 1):
                r[order[k]] = (i + j) / 2 + 1
            i = j + 1
        return r
    ra, rb = ranks(a), ranks(b)
    ma, mb = mean(ra), mean(rb)
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    den = (sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb)) ** 0.5
    return round(num / den, 3) if den else None


def total_report(totals: list[tuple[str, float, float]]) -> dict:
    if not totals:
        return {"n": 0}
    j = [t[1] for t in totals]; h = [t[2] for t in totals]
    gaps = sorted(totals, key=lambda t: -abs(t[1] - t[2]))
    return {"n": len(totals), "spearman": spearman(j, h), "bias": round(mean(j) - mean(h), 2),
            "mae": round(mean(abs(x - y) for x, y in zip(j, h)), 2),
            "largest_gaps": [{"id": t[0], "judge": t[1], "human": t[2], "gap": round(t[1] - t[2], 2)} for t in gaps[:5]]}


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
