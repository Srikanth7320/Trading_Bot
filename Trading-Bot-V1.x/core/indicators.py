import numpy as np
import pandas as pd


def add_indicators(frame: pd.DataFrame) -> pd.DataFrame:
    data = frame.copy()
    close = data["Close"]
    high = data["High"]
    low = data["Low"]
    volume = data["Volume"]

    
    data["EMA12"] = close.ewm(span=12, adjust=False).mean()
    data["EMA26"] = close.ewm(span=26, adjust=False).mean()
    data["EMA20"] = close.ewm(span=20, adjust=False).mean()
    data["EMA50"] = close.ewm(span=50, adjust=False).mean()
    data["EMA200"] = close.ewm(span=200, adjust=False).mean()
    data["SMA20"] = close.rolling(20).mean()
    data["SMA50"] = close.rolling(50).mean()

    data["MACD"] = data["EMA12"] - data["EMA26"]
    data["MACD_SIGNAL"] = data["MACD"].ewm(span=9, adjust=False).mean()
    data["RSI"] = rsi(close)
    rolling_std = close.rolling(20).std()
    data["BB_UPPER"] = data["SMA20"] + (rolling_std * 2)
    data["BB_LOWER"] = data["SMA20"] - (rolling_std * 2)

    previous_close = close.shift(1)
    true_range = pd.concat(
        [
            (high - low).abs(),
            (high - previous_close).abs(),
            (low - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    data["ATR14"] = true_range.rolling(14).mean()
    data["VOLUME_RATIO"] = volume / volume.rolling(20).mean()
    data["VOLUME_BREAKOUT"] = data["VOLUME_RATIO"] >= 2
    data["HIGH_52W"] = high.rolling(252, min_periods=1).max()
    data["LOW_52W"] = low.rolling(252, min_periods=1).min()
    data["MOMENTUM20"] = close.pct_change(20) * 100
    data["MOMENTUM50"] = close.pct_change(50) * 100
    data["ABOVE_EMA20"] = close > data["EMA20"]
    data["ABOVE_EMA50"] = close > data["EMA50"]
    data["ABOVE_EMA200"] = close > data["EMA200"]
    data["GOLDEN_CROSS"] = (
                                data["EMA20"] > data["EMA50"]
                            ) & (
                                data["EMA20"].shift(1) <= data["EMA50"].shift(1)
                            )
    data["GREEN_CANDLE"] = data["Close"] > data["Open"]
    data["BB_POSITION"] = (
                                (close - data["BB_LOWER"])
                                /
                                (data["BB_UPPER"] - data["BB_LOWER"])
                            )
    data["ATR_PERCENT"] = (
                                data["ATR14"] / close
                            ) * 100
    return data
    

def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    relative_strength = avg_gain / avg_loss.replace(0, np.nan)
    values = 100 - (100 / (1 + relative_strength))
    values = values.mask((avg_loss == 0) & (avg_gain > 0), 100)
    values = values.mask((avg_loss == 0) & (avg_gain == 0), 50)
    return values
