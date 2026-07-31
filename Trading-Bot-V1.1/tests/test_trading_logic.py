from datetime import datetime, timedelta

import pandas as pd

import core.sell_engine as sell_engine_module
from core.models import Position
from core.scanner import Scanner
from core.sell_engine import SellEngine


class DummySettings:
    trailing_stop_pct = 4.0
    max_holding_days = 14


class DummyMarket:
    def __init__(self, history: pd.DataFrame):
        self.history = history

    def get_history(self, symbol, period="3mo", interval="1d"):
        return self.history


def test_entry_gate_requires_bullish_structure():
    scanner = Scanner.__new__(Scanner)
    latest = {
        "Close": 110.0,
        "RSI": 58.0,
        "MACD": 1.2,
        "MACD_SIGNAL": 0.2,
        "VOLUME_RATIO": 1.4,
        "EMA20": 108.0,
        "EMA50": 103.0,
        "SMA20": 105.0,
        "SMA50": 101.0,
        "MOMENTUM20": 6.0,
        "MOMENTUM50": 8.0,
    }

    assert scanner._passes_entry_gate(latest, 76.0, 2.0) is True


def test_entry_gate_rejects_weak_setup():
    scanner = Scanner.__new__(Scanner)
    latest = {
        "Close": 110.0,
        "RSI": 80.0,
        "MACD": 0.2,
        "MACD_SIGNAL": 0.4,
        "VOLUME_RATIO": 0.8,
        "EMA20": 109.0,
        "EMA50": 110.0,
        "SMA20": 109.0,
        "SMA50": 110.0,
        "MOMENTUM20": 1.0,
        "MOMENTUM50": 2.0,
    }

    assert scanner._passes_entry_gate(latest, 60.0, 0.0) is False


def test_sell_engine_exits_on_bearish_crossover_after_profit(monkeypatch):
    history = pd.DataFrame(
        {
            "Open": [100.0] * 2,
            "High": [100.5] * 2,
            "Low": [99.5] * 2,
            "Close": [100.0, 103.0],
            "Volume": [1000000, 1000000],
        }
    )

    def fake_add_indicators(_frame):
        return pd.DataFrame(
            {
                "Close": [103.0],
                "EMA20": [102.0],
                "EMA50": [103.5],
                "MACD": [-0.8],
                "MACD_SIGNAL": [0.2],
                "RSI": [72.0],
            }
        )

    monkeypatch.setattr(sell_engine_module, "add_indicators", fake_add_indicators)

    market = DummyMarket(history)
    engine = SellEngine(DummySettings(), market)
    position = Position(
        symbol="TEST",
        entry_price=100.0,
        quantity=1,
        stop_loss=95.0,
        target=106.0,
        highest_price=104.0,
        opened_at=(datetime.now() - timedelta(days=3)).isoformat(timespec="seconds"),
        reason="test",
    )

    decision = engine.evaluate(position)

    assert decision.action == "SELL"
    assert "bearish" in decision.reason.lower() or "ema" in decision.reason.lower()
