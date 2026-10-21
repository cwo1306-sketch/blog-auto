"""호환 래퍼: 본체는 naver_cardnews.article (1단계 DB 본문 저장과 같은 파서를 쓴다)."""
from naver_cardnews.article import ArticleError, article_id, fetch, parse  # noqa: F401
from naver_cardnews.article import clean_html as _clean  # noqa: F401
