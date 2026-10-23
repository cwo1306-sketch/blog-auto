"""HANDOFF.md 로드맵 1단계 진입점: `python collect.py` == `python -m naver_cardnews collect`."""
import sys
from naver_cardnews.cli import main

sys.exit(main(["collect", *sys.argv[1:]]))
