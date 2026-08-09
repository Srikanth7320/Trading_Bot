import logging

import pandas as pd

from core.utils import nse_symbol

try:
    import yfinance as yf
except ImportError:  # pragma: no cover - dependency is installed by requirements
    yf = None


logger = logging.getLogger(__name__)


class MarketDataClient:
    def get_history(self, symbol: str, period: str = "60d", interval: str = "1h") -> pd.DataFrame:
        if yf is None:
            logger.warning("yfinance is not installed; skipping market data fetch for %s", symbol)
            return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])

        ticker = nse_symbol(symbol)
        try:
            frame = yf.download(ticker, period=period, interval=interval, progress=False, auto_adjust=False)
        except Exception as exc:
            logger.warning("Market data fetch failed for %s: %s", ticker, exc)
            return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])

        if frame.empty:
            if interval in {"1m", "2m", "5m", "15m", "30m"}:
                logger.info("Retrying market data for %s with interval 1h after empty %s response", ticker, interval)
                return self.get_history(symbol, period=period, interval="1h")
            if interval == "1h":
                logger.info("Retrying market data for %s with interval 1d after empty 1h response", ticker)
                return self.get_history(symbol, period=period, interval="1d")
            logger.warning("No market data returned for %s", ticker)
            return frame

        if isinstance(frame.columns, pd.MultiIndex):
            frame.columns = frame.columns.get_level_values(0)

        required = ["Open", "High", "Low", "Close", "Volume"]
        return frame[[column for column in required if column in frame.columns]].dropna()

    def get_current_price(self, symbol: str) -> float | None:
        frame = self.get_history(symbol, period="5d", interval="1h")
        if frame.empty:
            return None
        return float(frame["Close"].dropna().iloc[-1])
