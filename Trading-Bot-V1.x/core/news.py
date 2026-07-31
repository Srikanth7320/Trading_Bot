import logging
from dataclasses import asdict
from datetime import datetime, timedelta

import requests

from core.models import NewsItem


logger = logging.getLogger(__name__)


POSITIVE_WORDS = {"beats", "growth", "profit", "record", "upgrade", "wins", "expands", "strong"}
NEGATIVE_WORDS = {"loss", "fraud", "downgrade", "falls", "weak", "debt", "probe", "decline"}


class NewsClient:
    def __init__(self, api_key: str, enabled: bool = True):
        self.api_key = api_key
        self.enabled = enabled and bool(api_key)
        if enabled and not api_key:
            raise RuntimeError("NEWS_API_KEY is required for mandatory news scoring.")

    def fetch(self, symbol: str, limit: int = 5) -> list[NewsItem]:
        if not self.enabled:
            return []
        from_date = (datetime.utcnow() - timedelta(days=3)).date().isoformat()
        params = {
            "q": f"{symbol} NSE OR stock",
            "from": from_date,
            "sortBy": "publishedAt",
            "pageSize": limit,
            "apiKey": self.api_key,
            "language": "en",
        }
        try:
            response = requests.get("https://newsapi.org/v2/everything", params=params, timeout=15)
            response.raise_for_status()
            articles = response.json().get("articles", [])
        except requests.RequestException as exc:
            logger.warning("NewsAPI request failed for %s: %s", symbol, exc)
            return []

        return [
            NewsItem(
                title=article.get("title") or "",
                source=(article.get("source") or {}).get("name") or "",
                url=article.get("url") or "",
                published_at=article.get("publishedAt") or "",
            )
            for article in articles
            if article.get("title")
        ]

    def score(self, news_items: list[NewsItem]) -> float:
        if not news_items:
            return 0.0
        score = 0
        for item in news_items:
            words = set(item.title.lower().split())
            score += len(words & POSITIVE_WORDS)
            score -= len(words & NEGATIVE_WORDS)
        return max(-10.0, min(10.0, score * 2.0))

    def as_dicts(self, news_items: list[NewsItem]) -> list[dict]:
        return [asdict(item) for item in news_items]
