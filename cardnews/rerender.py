"""원고·사진은 그대로 두고 디자인만 다시 렌더링한다. Usage: .venv/bin/python rerender.py <output 폴더>

원본 대비 개선: 장별 배경 파일을 meta["images"]에서 읽어 stat 장(사진 없음)·단색 강등 장을 그대로 재현한다.
구 meta(photo_credits)도 읽는다.
"""

from __future__ import annotations

import json
import os
import sys

import render


def _images(meta: dict) -> list[str | None]:
    if "images" in meta:
        return [(e.get("chosen") or {}).get("file") for e in meta["images"]]
    return [f"bg_{n:02d}.jpg" for n in range(1, len(meta["photo_credits"]) + 1)]   # 구 포맷


def main(out: str) -> None:
    meta_path = os.path.join(out, "meta.json")
    with open(meta_path, encoding="utf-8") as f:
        meta = json.load(f)
    a = meta["article"]
    source = f"출처: {a['press']} · {a['date'].replace('-', '.')}"
    files, qa = render.render(render.build_pages(meta["script"], _images(meta), source, palette=meta.get("palette", "")), out)
    meta["cards"] = files
    meta.setdefault("qa", {})["render"] = qa
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print([(q["card"], q["kind"], q["contrast"], q["issues"]) for q in qa])


if __name__ == "__main__":
    main(sys.argv[1])
