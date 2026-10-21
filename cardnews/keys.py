"""키 로더. 우선순위: 환경 변수 → .env → ~/Desktop/클로드/keys.txt 의 [라벨] 섹션.

keys.txt 형식 (HANDOFF 3장):
    [Pexels-cardnews]
    PEXELS_API_KEY=...
"""

from __future__ import annotations

import os
import re
from pathlib import Path

KEYS_TXT = Path(os.environ.get("CARDNEWS_KEYS_TXT", Path.home() / "Desktop" / "클로드" / "keys.txt"))
_ENV_LOADED = False


def _load_env_file() -> None:
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    _ENV_LOADED = True
    for candidate in (Path.cwd() / ".env", Path(__file__).resolve().parent / ".env"):
        if candidate.exists():
            for raw in candidate.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _from_keys_txt(label: str, name: str) -> str:
    if not KEYS_TXT.exists():
        return ""
    section = None
    for raw in KEYS_TXT.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        m = re.fullmatch(r"\[(.+?)\].*", line)
        if m:
            section = m.group(1).strip()
            continue
        if section == label and "=" in line:
            k, _, v = line.partition("=")
            if k.strip() == name:
                return v.strip().strip('"').strip("'")
    return ""


def load(label: str, name: str, required: bool = True) -> str:
    _load_env_file()
    value = os.environ.get(name) or _from_keys_txt(label, name)
    if not value and required:
        raise RuntimeError(f"{name} 를 찾을 수 없습니다 (환경 변수, .env, {KEYS_TXT} [{label}] 확인)")
    return value
