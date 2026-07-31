import numpy as np
import pandas as pd


def add_indicators(frame: pd.DataFrame) -> pd.DataFrame:
    data = frame.copy()
    close = data["Close"]
    high = data["High"]
    low = data["Low"]
    volume = data["Volume"]

    data["SMA20"] = close.rolling(20).mean()
    data["SMA50"] = close.rolling(50).mean()
    data["EMA12"] = close.ewm(span=12, adjust=False).mean()
    data["EMA26"] = close.ewm(span=26, adjust=False).mean()
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
