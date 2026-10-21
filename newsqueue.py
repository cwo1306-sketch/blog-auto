"""엑셀 큐 진입점 (`queue.py`는 표준 라이브러리 queue 모듈을 가리므로 이 이름을 쓴다).
`python newsqueue.py` == `python -m naver_cardnews run` (import → collect → export)."""
import sys
from naver_cardnews.cli import main

sys.exit(main(["run", *sys.argv[1:]]))
