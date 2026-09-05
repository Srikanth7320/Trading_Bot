import logging
from datetime import datetime

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
                history = self.market.get_history(
                    symbol,
                    period=self.settings.history_period,
                    interval=self.settings.history_interval,
                )
                if history.empty or len(history) < 200:
                    if self.settings.history_interval != "1d":
                        history = self.market.get_history(symbol, period="6mo", interval="1d")
                if history.empty or len(history) < 80:
                    continue
                enriched = add_indicators(history).dropna()
                if enriched.empty:
                    continue
                latest = enriched.iloc[-1]
                price = float(latest["Close"])
                if not self.risk.price_allowed(price):
                    continue

                daily_latest = None
                if self.settings.history_interval != "1d":
                    daily_history = self.market.get_history(symbol, period="6mo", interval="1d")
                    if not daily_history.empty and len(daily_history) >= 80:
                        daily_enriched = add_indicators(daily_history).dropna()
                        if not daily_enriched.empty:
                            daily_latest = daily_enriched.iloc[-1]

                news_items = self.news.fetch(symbol)
                news_score = self.news.score(news_items)
                technical_score = self.ai.technical_score(latest, daily_latest)
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
        selected = self._select_recommendations(recommendations)
        # Enforce per-scan cap on new entries
        max_new = getattr(self.settings, "max_new_entries_per_scan", 2)
        if max_new and len(selected) > max_new:
            selected = selected[:max_new]
        scan_metric = {
            "created_at": self._now_iso(),
            "symbols_scanned": len(self.settings.symbols),
            "qualified": len(recommendations),
            "recommended": len(selected),
            "rejected_by_gate": rejected_by_gate,
        }
        self.storage.append_scan_metric(scan_metric)
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

    def _price_bucket(self, price: float) -> str:
        if price < 150:
            return "low"
        if price < 400:
            return "mid"
        return "high"

    def _select_recommendations(self, recommendations: list[Recommendation]) -> list[Recommendation]:
        if not recommendations:
            return []

        buckets: dict[str, int] = {}
        selected: list[Recommendation] = []

        for recommendation in recommendations:
            bucket = self._price_bucket(recommendation.price)
            if buckets.get(bucket, 0) < 2:
                selected.append(recommendation)
                buckets[bucket] = buckets.get(bucket, 0) + 1
            if len(selected) >= self.settings.max_recommendations:
                break

        if len(selected) < self.settings.max_recommendations:
            for recommendation in recommendations:
                if recommendation not in selected:
                    selected.append(recommendation)
                if len(selected) >= self.settings.max_recommendations:
                    break

        return selected

    def _entry_gate_failure(self, latest, score: float, news_score: float) -> str | None:
        settings = getattr(self, "settings", None)
        minimum_buy_score = getattr(settings, "minimum_buy_score", 65.0)
        if score < minimum_buy_score:
            return "score"

        rsi = float(latest.get("RSI", 0))
        rsi_max = getattr(settings, "rsi_entry_max", 70.0)
        if rsi > rsi_max or rsi < 45:
            return "RSI"

        macd = float(latest.get("MACD", 0))
        signal = float(latest.get("MACD_SIGNAL", 0))
        if macd <= signal:
            return "MACD crossover"

        close = float(latest.get("Close", 0))
        sma20 = float(latest.get("SMA20", 0))
        sma50 = float(latest.get("SMA50", 0))
        ema20 = float(latest.get("EMA20", 0))
        ema50 = float(latest.get("EMA50", 0))
        ema200 = float(latest.get("EMA200", 0))
        if close <= ema20:
            return "price/EMA20"
        if close <= sma20 * 1.02:
            return "weak breakout"
        if not (sma20 > sma50 and ema20 > ema50 > ema200):
            return "trend structure"
        if not (close > sma20 and sma20 > sma50):
            return "trend structure"

        minimum_volume_ratio = max(getattr(settings, "minimum_volume_ratio", 1.1), 1.5)
        volume_ratio = float(latest.get("VOLUME_RATIO", 0))
        if volume_ratio < minimum_volume_ratio:
            return "volume"

        momentum20 = float(latest.get("MOMENTUM20", 0))
        if momentum20 <= 8.0:
            return "momentum"

        if not bool(latest.get("GOLDEN_CROSS", False)):
            return "trend structure"

        return None

    @staticmethod
    def _now_iso() -> str:
        return datetime.utcnow().isoformat(timespec="seconds") + "Z"

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
