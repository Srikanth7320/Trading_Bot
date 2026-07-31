from datetime import datetime
from core.indicators import add_indicators, rsi
from core.market_data import MarketDataClient
from core.models import Position, SellDecision


class SellEngine:
    def __init__(self, settings, market: MarketDataClient):
        self.settings = settings
        self.market = market

    def evaluate(self, position: Position) -> SellDecision:
        history = self.market.get_history(position.symbol, period="3mo", interval="1d")
        if history.empty:
            return SellDecision(position.symbol, "HOLD", position.entry_price, 0.0, "No fresh market data")

        latest = add_indicators(history).dropna().iloc[-1]
        current_price = float(latest["Close"])
        # Holding period
        buy_date = datetime.fromisoformat(position.created_at)
        holding_days = (datetime.now() - buy_date).days
        if current_price > position.highest_price:
            position.highest_price = current_price
        pnl_pct = ((current_price - position.entry_price) / position.entry_price) * 100
        trailing_stop = position.highest_price * (1 - self.settings.trailing_stop_pct / 100)
        # Force exit after maximum holding period
        if holding_days >= self.settings.max_holding_days:
            return SellDecision(
                position.symbol,
                "SELL",
                round(current_price, 2),
                round(pnl_pct, 2),
                f"Maximum holding period ({holding_days} days)"
            )

        if current_price <= position.stop_loss:
            return SellDecision(position.symbol, "SELL", round(current_price, 2), round(pnl_pct, 2), "Stop loss hit")

        if current_price >= position.target and pnl_pct >= 3:
            return SellDecision(position.symbol, "SELL", round(current_price, 2), round(pnl_pct, 2), "Target reached")

        if current_price <= trailing_stop and pnl_pct > 2:
            return SellDecision(position.symbol, "SELL", round(current_price, 2), round(pnl_pct, 2), "Trailing stop hit")

        rsi = float(latest.get("RSI", 50))
        if rsi >= 75 and pnl_pct > 3:
            return SellDecision(position.symbol, "SELL", round(current_price, 2), round(pnl_pct, 2), "RSI overheated")

        macd = float(latest.get("MACD", 0))
        signal = float(latest.get("MACD_SIGNAL", 0))

        if macd < signal and pnl_pct > 1.5:
            return SellDecision(
                position.symbol,
                "SELL",
                round(current_price, 2),
                round(pnl_pct, 2),
                "MACD bearish crossover"
            )

        ema20 = float(latest.get("EMA20", current_price))
        ema50 = float(latest.get("EMA50", current_price))

        if ema20 < ema50 and pnl_pct > 2:
            return SellDecision(
                position.symbol,
                "SELL",
                round(current_price, 2),
                round(pnl_pct, 2),
                "EMA20 crossed below EMA50"
            )

        return SellDecision(
                                position.symbol,
                                "HOLD",
                                round(current_price, 2),
                                round(pnl_pct, 2),
                                f"Holding ({holding_days} days)"
                            )
