import logging

from config import Settings
from core.ai_score import AIScorer
from core.indicators import add_indicators
from core.market_data import MarketDataClient
from core.models import Recommendation
from core.news import NewsClient
from core.risk import RiskEngine
from core.storage import Storage
from core.utils import display_symbol


logger = logging.getLogger(__name__)


class Scanner:
    def __init__(
        self,
        settings: Settings,
        market: MarketDataClient,
        storage: Storage,
        news: NewsClient,
        ai: AIScorer,
        risk: RiskEngine,
    ):
        self.settings = settings
        self.market = market
        self.storage = storage
        self.news = news
        self.ai = ai
        self.risk = risk

    def scan(self) -> list[Recommendation]:
        recommendations: list[Recommendation] = []
        active_symbols = {
                            position.symbol
                            for position in self.storage.load_positions()
                        }

        cooldown = self.storage.load_cooldown()

        for raw_symbol in self.settings.symbols:
            symbol = display_symbol(raw_symbol)
            if symbol in active_symbols:
                continue
            # Skip stocks under cooldown
            if symbol in cooldown:
                continue
            if (
                self.settings.prevent_same_day_buy
                and self.storage.bought_today(symbol)
            ):
                continue
            try:
                history = self.market.get_history(symbol)
                if history.empty or len(history) < 60:
                    continue
                enriched = add_indicators(history).dropna()
                if enriched.empty:
                    continue
                latest = enriched.iloc[-1]
                price = float(latest["Close"])
                if not self.risk.price_allowed(price):
                    continue

                news_items = self.news.fetch(symbol)
                news_score = self.news.score(news_items)
                technical_score = self.ai.technical_score(latest)
                final_score = max(0.0, min(100.0, technical_score + news_score))

                if not self._passes_entry_gate(latest, final_score, news_score):
                    continue

                ai_note = self.ai.summarize(symbol, latest, news_items, final_score)
                reason = self._reason(latest, final_score, news_score)
                recommendation = self.risk.build_recommendation(symbol, latest, final_score, reason, news_score, ai_note)
                recommendations.append(recommendation)
            except Exception as exc:
                logger.exception("Scan failed for %s: %s", raw_symbol, exc)

        recommendations.sort(key=lambda item: item.score, reverse=True)
        selected = recommendations[: self.settings.max_recommendations]
        if len(selected) < self.settings.min_recommendations:
            logger.info("Not enough qualifying stocks for a buy signal today.")
            return []
        return selected

    def _passes_entry_gate(self, latest, score: float, news_score: float) -> bool:
        settings = getattr(self, "settings", None)
        minimum_buy_score = getattr(settings, "minimum_buy_score", 75.0)
        if score < minimum_buy_score:
            return False

        rsi = float(latest.get("RSI", 0))
        if not 45 <= rsi <= 75:
            return False

        macd = float(latest.get("MACD", 0))
        signal = float(latest.get("MACD_SIGNAL", 0))
        if not (macd > signal and macd > 0):
            return False

        close = float(latest.get("Close", 0))
        if close <= float(latest.get("SMA20", 0)):
            return False

        if float(latest.get("EMA20", 0)) <= float(latest.get("EMA50", 0)):
            return False

        if float(latest.get("VOLUME_RATIO", 0)) < 1.2:
            return False

        if float(latest.get("MOMENTUM20", 0)) <= 0:
            return False

        return True

    def _reason(self, latest, score: float, news_score: float) -> str:
        parts = [f"score {score:.1f}"]
        if float(latest.get("MACD", 0)) > float(latest.get("MACD_SIGNAL", 0)):
            parts.append("MACD bullish")
        if float(latest.get("Close", 0)) > float(latest.get("SMA20", 0)):
            parts.append("price above SMA20")
        if float(latest.get("VOLUME_RATIO", 0)) >= 1.2:
            parts.append("volume expansion")
        if news_score > 0:
            parts.append("positive news bias")
        return ", ".join(parts)
