"""의존성 없는 dHash(difference hash). 같은 사진의 리사이즈·재압축본을 잡는 용도."""

from __future__ import annotations

import io

from PIL import Image


def dhash(data: bytes | Image.Image, size: int = 8) -> int:
    im = data if isinstance(data, Image.Image) else Image.open(io.BytesIO(data))
    im = im.convert("L").resize((size + 1, size), Image.LANCZOS)
    px = list(im.tobytes())
    bits = 0
    for row in range(size):
        for col in range(size):
            left, right = px[row * (size + 1) + col], px[row * (size + 1) + col + 1]
            bits = (bits << 1) | (1 if left > right else 0)
    return bits


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def to_hex(h: int) -> str:
    return f"{h:016x}"


def from_hex(s: str) -> int:
    return int(s, 16)
