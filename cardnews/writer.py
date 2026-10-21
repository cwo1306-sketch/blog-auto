"""호환 래퍼: 본체는 naver_cardnews.writer. keys.txt/.env 의 Anthropic 키를 붙인다."""
import keys
from naver_cardnews import writer as _w
from naver_cardnews.writer import (MODEL, PICK_MODEL, SYSTEM, WriterError, normalize_script,  # noqa: F401
                                   parse_script, pick_photo, write)

_w.configure(keys.load("Anthropic-jachi", "ANTHROPIC_API_KEY", required=False))
