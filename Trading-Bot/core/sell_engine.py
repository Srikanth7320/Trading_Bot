from core.indicators import add_indicators
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
        position.highest_price = max(position.highest_price, current_price)
        pnl_pct = ((current_price - position.entry_price) / position.entry_price) * 100
        trailing_stop = position.highest_price * (1 - self.settings.trailing_stop_pct / 100)

        if current_price <= position.stop_loss:
            return SellDecision(position.symbol, "SELL", round(current_price, 2), round(pnl_pct, 2), "Stop loss hit")
        if current_price >= position.target:
            return SellDecision(position.symbol, "SELL", round(current_price, 2), round(pnl_pct, 2), "Target reached")
        if current_price <= trailing_stop and pnl_pct > 0:
            return SellDecision(position.symbol, "SELL", round(current_price, 2), round(pnl_pct, 2), "Trailing stop hit")
        if float(latest.get("RSI", 50)) > 78:
            return SellDecision(position.symbol, "SELL", round(current_price, 2), round(pnl_pct, 2), "RSI overheated")
        if float(latest.get("MACD", 0)) < float(latest.get("MACD_SIGNAL", 0)) and pnl_pct > 1:
            return SellDecision(position.symbol, "SELL", round(current_price, 2), round(pnl_pct, 2), "MACD turned weak")

        return SellDecision(position.symbol, "HOLD", round(current_price, 2), round(pnl_pct, 2), "No exit condition")
