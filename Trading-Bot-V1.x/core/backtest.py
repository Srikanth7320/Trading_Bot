import logging
from dataclasses import dataclass
from datetime import datetime
from typing import List

import pandas as pd

from core.ai_score import AIScorer
from core.indicators import add_indicators
from core.market_data import MarketDataClient
from core.news import NewsClient
from core.risk import RiskEngine
from core.storage import Storage


logger = logging.getLogger(__name__)


@dataclass
class BacktestTrade:
    symbol: str
    entry_date: str
    entry_price: float
    exit_date: str
    exit_price: float
    pnl_pct: float
    reason: str


class SimpleBacktester:
    def __init__(self, settings, market: MarketDataClient, news: NewsClient, ai: AIScorer, risk: RiskEngine):
        self.settings = settings
        self.market = market
        self.news = news
        self.ai = ai
        self.risk = risk
        self.storage = Storage(settings.data_dir)

    def run(self, symbols: List[str] | None = None) -> dict:
        if symbols is None:
            symbols = self.settings.symbols

        trades: List[BacktestTrade] = []
        for symbol in symbols:
            try:
                history = self.market.get_history(symbol, period="1y", interval="1d")
                if history.empty or len(history) < 90:
                    continue

                enriched = add_indicators(history).dropna()
                if enriched.empty:
                    continue

                for idx in range(60, len(enriched)):
                    latest = enriched.iloc[idx]
                    if not self._should_buy(latest):
                        continue

                    recommendation = self.risk.build_recommendation(
                        symbol=symbol,
                        latest=latest,
                        score=self.ai.technical_score(latest, latest),
                        reason="Backtest entry",
                        news_score=0.0,
                        ai_note="Backtest simulated trade.",
                    )
                    entry_price = recommendation.price
                    stop_loss = recommendation.stop_loss
                    target = recommendation.target
                    entry_date = str(enriched.index[idx])
                    exit_price = None
                    exit_date = None
                    reason = ""

                    for future_idx in range(idx + 1, min(len(enriched), idx + self.settings.max_holding_days + 1)):
                        future = enriched.iloc[future_idx]
                        current_price = float(future["Close"])
                        pnl_pct = ((current_price - entry_price) / entry_price) * 100
                        macd = float(future.get("MACD", 0))
                        signal = float(future.get("MACD_SIGNAL", 0))
                        ema20 = float(future.get("EMA20", current_price))
                        ema50 = float(future.get("EMA50", current_price))

                        if current_price <= stop_loss:
                            exit_price = current_price
                            exit_date = str(enriched.index[future_idx])
                            reason = "stop loss"
                            break
                        if current_price >= target:
                            exit_price = current_price
                            exit_date = str(enriched.index[future_idx])
                            reason = "target"
                            break
                        if future_idx - idx >= 2 and macd < signal and pnl_pct > 1.5:
                            exit_price = current_price
                            exit_date = str(enriched.index[future_idx])
                            reason = "bearish MACD crossover"
                            break
                        if future_idx - idx >= 2 and ema20 < ema50 and pnl_pct > 2:
                            exit_price = current_price
                            exit_date = str(enriched.index[future_idx])
                            reason = "EMA bearish cross"
                            break

                    if exit_price is None:
                        last_idx = min(len(enriched) - 1, idx + self.settings.max_holding_days)
                        exit_price = float(enriched.iloc[last_idx]["Close"])
                        exit_date = str(enriched.index[last_idx])
                        reason = "max hold"

                    trades.append(
                        BacktestTrade(
                            symbol=symbol,
                            entry_date=entry_date,
                            entry_price=entry_price,
                            exit_date=exit_date,
                            exit_price=float(exit_price),
                            pnl_pct=((float(exit_price) - entry_price) / entry_price) * 100,
                            reason=reason,
                        )
                    )
                    break
            except Exception as exc:
                logger.exception("Backtest failed for %s: %s", symbol, exc)

        if not trades:
            return {"trades": 0, "win_rate": 0.0, "avg_pnl": 0.0, "total_pnl": 0.0}

        pnl_values = [trade.pnl_pct for trade in trades]
        wins = sum(1 for value in pnl_values if value > 0)
        return {
            "trades": len(trades),
            "win_rate": round(wins / len(trades) * 100, 2),
            "avg_pnl": round(sum(pnl_values) / len(pnl_values), 2),
            "total_pnl": round(sum(pnl_values), 2),
            "trades_detail": [trade.__dict__ for trade in trades],
        }

    def _should_buy(self, latest) -> bool:
        price = float(latest.get("Close", 0))
        if not self.risk.price_allowed(price):
            return False

        score = self.ai.technical_score(latest, latest)
        if score < self.settings.minimum_buy_score:
            return False

        rsi = float(latest.get("RSI", 0))
        if not 40 <= rsi <= 80:
            return False

        macd = float(latest.get("MACD", 0))
        signal = float(latest.get("MACD_SIGNAL", 0))
        if macd <= signal:
            return False

        if price <= float(latest.get("EMA20", 0)):
            return False

        ema20 = float(latest.get("EMA20", 0))
        ema50 = float(latest.get("EMA50", 0))
        ema200 = float(latest.get("EMA200", 0))
        if not (ema20 > ema50 or ema50 > ema200):
            return False

        if float(latest.get("VOLUME_RATIO", 0)) < self.settings.minimum_volume_ratio:
            return False

        if float(latest.get("MOMENTUM20", 0)) <= 0:
            return False

        return True
