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
        rejected_by_gate: dict[str, int] = {}
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

                rejection = self._entry_gate_failure(latest, final_score, news_score)
                if rejection:
                    rejected_by_gate[rejection] = rejected_by_gate.get(rejection, 0) + 1
                    continue

                ai_note = self.ai.summarize(symbol, latest, news_items, final_score)
                reason = self._reason(latest, final_score, news_score)
                recommendation = self.risk.build_recommendation(symbol, latest, final_score, reason, news_score, ai_note)
                recommendations.append(recommendation)
            except Exception as exc:
                logger.exception("Scan failed for %s: %s", raw_symbol, exc)

        recommendations.sort(key=lambda item: item.score, reverse=True)
        selected = recommendations[: self.settings.max_recommendations]
        logger.info(
            "Scan diagnostics: %s qualified; rejected by entry gate: %s",
            len(recommendations),
            rejected_by_gate or "none",
        )
        if len(selected) < self.settings.min_recommendations:
            logger.info("Not enough qualifying stocks for a buy signal today.")
            return []
        return selected

    def _passes_entry_gate(self, latest, score: float, news_score: float) -> bool:
        return self._entry_gate_failure(latest, score, news_score) is None

    def _entry_gate_failure(self, latest, score: float, news_score: float) -> str | None:
        settings = getattr(self, "settings", None)
        minimum_buy_score = getattr(settings, "minimum_buy_score", 75.0)
        if score < minimum_buy_score:
            return "score"

        rsi = float(latest.get("RSI", 0))
        if not 45 <= rsi <= 75:
            return "RSI"

        macd = float(latest.get("MACD", 0))
        signal = float(latest.get("MACD_SIGNAL", 0))
        # A bullish crossover below zero can be an earlier, valid recovery
        # entry. The positive trend filters below remain mandatory.
        if macd <= signal:
            return "MACD crossover"

        close = float(latest.get("Close", 0))
        if close <= float(latest.get("SMA20", 0)):
            return "price/SMA20"

        if float(latest.get("EMA20", 0)) <= float(latest.get("EMA50", 0)):
            return "EMA trend"

        minimum_volume_ratio = getattr(settings, "minimum_volume_ratio", 1.1)
        if float(latest.get("VOLUME_RATIO", 0)) < minimum_volume_ratio:
            return "volume"

        if float(latest.get("MOMENTUM20", 0)) <= 0:
            return "momentum"

        return None

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
