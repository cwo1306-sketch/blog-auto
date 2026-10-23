"""cardkit 명령줄.

  python -m cardkit make     --profile P.yaml --source source.json --out DIR [--script script.json] [--palette X --layout Y --format Z --seed N --no-photos --force]
  python -m cardkit rerender --profile P.yaml --out DIR            # script.json 을 손으로 고친 뒤 같은 색·레이아웃으로 다시 그리기
  python -m cardkit preview  --profile P.yaml --out DIR            # API 없이 예시 원고로 계정 색·레이아웃 미리보기
  python -m cardkit audit    --profile P.yaml                      # 계정 팔레트 대비·눈 편안함 검사
  python -m cardkit prompt   --profile P.yaml [--format study]     # 원고 작성 프롬프트 확인
  python -m cardkit check    --profile P.yaml --source source.json --script script.json   # 원고 검수만
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import pipeline, profile as profile_mod, validate, writer


def _json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="cardkit")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("make", "rerender", "preview", "audit", "prompt", "check"):
        p = sub.add_parser(name)
        p.add_argument("--profile", required=True)
        if name in ("make", "check"):
            p.add_argument("--source", required=True, help="원문 JSON {id,title,body,credit,date,kind}")
        if name in ("make", "rerender", "preview"):
            p.add_argument("--out", required=True)
        if name in ("make", "check"):
            p.add_argument("--script", help="사람이 고친 원고 JSON (있으면 작성기를 부르지 않는다)")
        if name in ("make", "prompt"):
            p.add_argument("--format")
        if name == "make":
            p.add_argument("--palette"); p.add_argument("--layout"); p.add_argument("--seed", type=int)
            p.add_argument("--no-photos", action="store_true"); p.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    prof = profile_mod.load(a.profile)

    if a.cmd == "audit":
        bad = prof.audit_palettes()
        for p in prof.palettes:
            print(f"{p}: {'통과' if p not in bad else '실패 — ' + ', '.join(bad[p])}")
        return 1 if bad else 0
    if a.cmd == "prompt":
        from .samples import SOURCE
        print(writer.system_prompt(prof, SOURCE, a.format))
        return 0
    if a.cmd == "check":
        errs = validate.check(_json(a.script), _json(a.source)["body"], prof.formats, prof.hashtags_fixed)
        print("\n".join(errs) or "검수 통과")
        return 1 if errs else 0
    if a.cmd == "rerender":
        qa = pipeline.rerender(a.out, prof)
        print(json.dumps([q for q in qa if q["issues"]], ensure_ascii=False, indent=1) or "QA 이슈 없음")
        return 0
    if a.cmd == "preview":
        from . import render
        from .samples import SCRIPTS, SOURCE
        out_root = Path(a.out)
        fmts = [f for f in prof.formats if f in SCRIPTS] or list(SCRIPTS)
        for k, fmt in enumerate(fmts):
            pal_name = prof.palettes[k % len(prof.palettes)]
            lay = prof.layouts[k % len(prof.layouts)]
            out = out_root / f"{fmt}_{pal_name}_{lay}"
            out.mkdir(parents=True, exist_ok=True)
            script = SCRIPTS[fmt]
            pages = render.build_pages(script, [None] * (len(script["slides"]) + 1), f"출처: {SOURCE['credit']}", prof, pal_name, lay)
            files, qa = render.render(pages, str(out))
            issues = [(q["card"], q["kind"], q["issues"]) for q in qa if q["issues"]]
            print(f"{fmt} · {pal_name} · {lay}: {len(files)}장, {issues or 'QA 이슈 없음'}")
        return 0
    if a.cmd == "make":
        out = pipeline.make(_json(a.source), prof, a.out, script=_json(a.script) if a.script else None,
                            palette=a.palette, layout=a.layout, fmt=a.format, seed=a.seed,
                            photos=not a.no_photos, force=a.force)
        print(out)
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
