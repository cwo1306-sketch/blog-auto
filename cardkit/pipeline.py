"""카드 한 세트 만들기: 색 → 레이아웃 → 포맷 → (원고 작성·검수) → 사진 → 렌더.

    from cardkit import profile, pipeline
    prof = profile.load("cardkit/profiles/psychology.yaml")
    out = pipeline.make(source, prof, "out/kim2024")      # source = {id, title, body, credit, date}

키: ANTHROPIC_API_KEY(원고·사진 심사), PEXELS_API_KEY(+UNSPLASH_ACCESS_KEY, 선택) 환경 변수. 사진 키가 없으면 사진 없이(plain) 렌더한다.
원고를 사람이 이미 고쳤다면 script= 로 넘긴다(포맷 고정, 작성기 호출 없음).
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

from . import compose as composer
from . import render, validate, writer
from .chart import Chart, ChartError, validate_chart
from .imagehash import dhash, to_hex
from .profile import Profile
from .stat import Stat, StatError, validate_stat
from .store import Store

log = logging.getLogger(__name__)
MAX_REWRITES = 2
MAX_STAT_SLIDES, MAX_CHART_SLIDES = 2, 1
FALLBACK_QUERIES = ["abstract soft light texture", "minimal paper shadow"]


def normalize_slide_types(script: dict, body: str, notes: list[str]) -> None:
    """검수를 못 넘은 stat·chart 장은 photo 로 강등(사유를 notes 에). stat 은 최대 2장·연속 금지(numbers 포맷 제외),
    chart 는 최대 1장(종이 바탕이라 stat 과 이어져도 된다)."""
    prev_stat, stats, charts = False, 0, 0
    numbers = script.get("format") == "numbers"
    for s in script["slides"]:
        kind, reason = s.get("slide_type"), None
        if kind == "chart":
            try:
                validate_chart(Chart.from_dict(s.get("chart") or {}), article_text=body)
            except ChartError as exc:
                reason = str(exc)
            if reason is None and charts >= MAX_CHART_SLIDES:
                reason = f"chart {MAX_CHART_SLIDES}장 초과"
            charts += reason is None
        elif kind == "stat":
            st = s.get("stat") or {}
            try:
                validate_stat(Stat(str(st.get("value", "")), str(st.get("unit", "")), st.get("label", ""),
                                   st.get("source_quote", "")), article_text=body)
            except StatError as exc:
                reason = str(exc)
            if reason is None and not numbers and prev_stat:
                reason = "stat 연속"
            if reason is None and not numbers and stats >= MAX_STAT_SLIDES:
                reason = f"stat {MAX_STAT_SLIDES}장 초과"
            stats += reason is None
        if reason:
            notes.append(f"'{s.get('title', '')}': {kind} → photo 강등 ({reason})")
            s["slide_type"] = "photo"
            s.setdefault("image_queries", [])
        prev_stat = s.get("slide_type") == "stat"


def _stock_clients():
    from .stock import PexelsClient, UnsplashClient
    clients = []
    if os.environ.get("PEXELS_API_KEY"):
        clients.append(PexelsClient(os.environ["PEXELS_API_KEY"]))
    if os.environ.get("UNSPLASH_ACCESS_KEY"):
        clients.append(UnsplashClient(os.environ["UNSPLASH_ACCESS_KEY"]))
    return clients


def _pick_photo(store: Store, scorer, clients, item_id: str, slide_no: int, queries: list[str], headline: str,
                concept: str, out: Path, bonus) -> tuple[str | None, dict]:
    from .stock import download, search_candidates
    from .vision_pick import pick
    log_: dict = {"queries": queries, "attempts": []}
    seen: set = set()
    for attempt in range(2):
        cands = [c for c in search_candidates(queries or FALLBACK_QUERIES, clients, per_query=6 if attempt == 0 else 10)
                 if c.key not in seen]
        for c in cands:
            try:
                c.image_bytes = download(c.thumb_url)
            except Exception as exc:  # noqa: BLE001
                log_.setdefault("thumb_errors", []).append(f"{c.key}: {exc}")
        result = pick(cands, headline, concept, scorer, store, exclude=seen, bonus=bonus)
        seen.update(c.key for c in cands)
        log_["attempts"].append(result.to_dict())
        if result.chosen is not None:
            c = result.chosen
            name = f"bg_{slide_no:02d}.jpg"
            (out / name).write_bytes(download(c.full_url))
            store.record_image(item_id, slide_no, c.source, c.external_id, c.query, to_hex(dhash(c.image_bytes)),
                               str(out / name), c.photographer, c.page_url)
            log_["chosen"] = {"file": name, "source": c.source, "id": c.external_id, "photographer": c.photographer, "url": c.page_url}
            return name, log_
        queries = FALLBACK_QUERIES + queries[:1]
    log_["fallback"] = "plain"
    return None, log_


def make(source: dict, profile: Profile, out_dir: str | Path, script: dict | None = None, store: Store | None = None,
         palette: str | None = None, layout: str | None = None, fmt: str | None = None, seed: int | None = None,
         photos: bool = True, force: bool = False, api_key: str | None = None) -> Path:
    """한 세트를 만들고 출력 폴더를 돌려준다. 출력: card_NN.jpg/html, script.json, caption.txt, meta.json."""
    t0 = time.time()
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    own_store = store is None
    store = store or Store(profile.store_path)
    notes: list[str] = []
    item_id = str(source.get("id") or out.name)
    try:
        comp = composer.compose(source["body"], store.recent_compositions(), seed=seed,
                                locked_format=fmt or (script.get("format") if script else None),
                                locked_why="지정" if fmt else "사람이 고친 원고",
                                palettes=[palette] if palette else profile.palettes,
                                layouts=[layout] if layout else profile.layouts, formats=profile.formats)
        notes.append("구성: " + " / ".join(comp.reasons))

        usage = None
        if script is None:
            script = writer.write(source, profile, fmt=comp.format, api_key=api_key)
            usage = script.pop("_usage", None)
            errors = validate.check(script, source["body"], profile.formats, profile.hashtags_fixed)
            for _ in range(MAX_REWRITES):
                if not errors:
                    break
                script = writer.write(source, profile, fmt=comp.format, previous=script, errors=errors, api_key=api_key)
                script.pop("_usage", None)
                errors = validate.check(script, source["body"], profile.formats, profile.hashtags_fixed)
        else:
            errors = validate.check(script, source["body"], profile.formats, profile.hashtags_fixed)
        if errors and not force:
            (out / "script.json").write_text(json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")
            raise SystemExit(f"원고 검수 오류 {len(errors)}건 — {out / 'script.json'} 를 고친 뒤 script= 로 다시 실행 (무시: force=True)\n- "
                             + "\n- ".join(errors))
        normalize_slide_types(script, source["body"], notes)

        images: list[str | None] = [None] * (len(script["slides"]) + 1)
        photo_log: list[dict] = []
        clients = _stock_clients() if photos else []
        if clients:
            from .vision_pick import HaikuScorer
            scorer = HaikuScorer(api_key, account=profile.name, style=profile.photo_style)
            tone = lambda b: composer.tone_harmony(b, comp.palette, comp.layout)   # noqa: E731
            cover = script["cover"]
            images[0], lg = _pick_photo(store, scorer, clients, item_id, 1, cover.get("image_queries") or [],
                                        " ".join(l["text"] for l in cover["lines"]), cover.get("image_concept", ""), out, tone)
            photo_log.append({"slide": 1, **lg})
            for n, s in enumerate(script["slides"], start=2):
                if s.get("slide_type", "photo") != "photo":
                    continue
                images[n - 1], lg = _pick_photo(store, scorer, clients, item_id, n, s.get("image_queries") or [],
                                                s.get("title", ""), s.get("image_concept") or s.get("body", "")[:80], out, tone)
                photo_log.append({"slide": n, **lg})
        elif photos:
            notes.append("사진: PEXELS_API_KEY 없음 → 사진 없이 렌더")

        credit = f"출처: {source.get('credit', '')}".strip()
        files, qa = render.render(render.build_pages(script, images, credit, profile, comp.palette, comp.layout), str(out))
        (out / "script.json").write_text(json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")
        (out / "caption.txt").write_text(script.get("caption", "") + "\n\n" + " ".join(script.get("hashtags") or []), encoding="utf-8")
        meta = {"profile": profile.id, "source": {k: source.get(k) for k in ("id", "title", "credit", "date")},
                "composition": comp.to_dict(), "palette": comp.palette, "layout": comp.layout, "cards": files,
                "qa": {"script_errors": errors, "notes": notes, "render": qa, "seconds": round(time.time() - t0, 1)},
                "photos": photo_log, "usage": usage}
        (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        store.record_composition(item_id, comp.palette, comp.layout, comp.format, " / ".join(comp.reasons))
        return out
    finally:
        if own_store:
            store.close()


def rerender(out_dir: str | Path, profile: Profile) -> list[dict]:
    """script.json·meta.json 으로 같은 색·레이아웃으로 다시 그린다 (원고를 손으로 고친 뒤)."""
    out = Path(out_dir)
    script = json.loads((out / "script.json").read_text(encoding="utf-8"))
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    images = [None] * (len(script["slides"]) + 1)
    for p in meta.get("photos", []):
        if p.get("chosen"):
            images[p["slide"] - 1] = p["chosen"]["file"]
    credit = f"출처: {meta['source'].get('credit', '')}"
    _, qa = render.render(render.build_pages(script, images, credit, profile, meta["palette"], meta["layout"]), str(out))
    return qa
