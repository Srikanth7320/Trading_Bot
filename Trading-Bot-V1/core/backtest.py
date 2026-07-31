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
from core.scanner import Scanner
from core.sell_engine import SellEngine
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
                if history.empty or len(history) < 60:
                    continue

                enriched = add_indicators(history).dropna()
                if enriched.empty:
                    continue

                for idx in range(60, len(enriched)):
                    snapshot = enriched.iloc[idx]
                    latest = enriched.iloc[idx]
                    if not self._should_buy(latest):
                        continue

                    entry_price = float(snapshot["Close"])
                    entry_date = str(enriched.index[idx])
                    exit_price = None
                    exit_date = None
                    reason = ""
                    for future_idx in range(idx + 1, len(enriched)):
                        future = enriched.iloc[future_idx]
                        current_price = float(future["Close"])
                        pnl_pct = ((current_price - entry_price) / entry_price) * 100
                        if current_price <= entry_price * 0.97:
                            exit_price = current_price
                            exit_date = str(enriched.index[future_idx])
                            reason = "stop loss"
                            break
                        if pnl_pct >= 6:
                            exit_price = current_price
                            exit_date = str(enriched.index[future_idx])
                            reason = "target"
                            break
                        if future_idx - idx >= 20:
                            exit_price = current_price
                            exit_date = str(enriched.index[future_idx])
                            reason = "hold period"
                            break

                    if exit_price is None:
                        continue

                    trades.append(
                        BacktestTrade(
                            symbol=symbol,
                            entry_date=entry_date,
                            entry_price=entry_price,
                            exit_date=exit_date or entry_date,
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
        if float(latest.get("RSI", 0)) < 45 or float(latest.get("RSI", 0)) > 75:
            return False
        if float(latest.get("MACD", 0)) <= float(latest.get("MACD_SIGNAL", 0)):
            return False
        if float(latest.get("Close", 0)) <= float(latest.get("SMA20", 0)):
            return False
        if float(latest.get("EMA20", 0)) <= float(latest.get("EMA50", 0)):
            return False
        if float(latest.get("VOLUME_RATIO", 0)) < 1.2:
            return False
        return True
