from datetime import datetime, timedelta

import pandas as pd

import core.sell_engine as sell_engine_module
from config import Settings
from core.backtest import SimpleBacktester
from core.models import Position
from core.risk import RiskEngine
from core.scanner import Scanner
from core.sell_engine import SellEngine


class DummySettings:
    trailing_stop_pct = 4.0
    trailing_atr_multiplier = 1.0
    max_holding_days = 14


class DummyMarket:
    def __init__(self, history: pd.DataFrame):
        self.history = history

    def get_history(self, symbol, period="3mo", interval="1d"):
        return self.history


def test_default_settings_are_not_overly_conservative():
    settings = Settings()
    assert settings.minimum_buy_score == 60.0
    assert settings.minimum_volume_ratio == 1.2
    assert settings.rsi_entry_max == 70.0
    assert settings.max_new_entries_per_scan == 1


def test_risk_engine_honors_configured_stop_loss():
    settings = Settings()
    settings = settings.__class__(
        stop_loss_pct=1.5,
        trailing_stop_pct=1.0,
        risk_per_trade_pct=1.0,
        portfolio_size=100000.0,
        max_position_value_pct=5.0,
    )
    risk = RiskEngine(settings)
    latest = {"Close": 100.0, "ATR14": 1.4, "RSI": 60.0}

    recommendation = risk.build_recommendation("TEST", latest, 80.0, "test", 0.0, "test")

    assert recommendation.stop_loss == 98.32


def test_entry_gate_requires_bullish_structure():
    scanner = Scanner.__new__(Scanner)
    latest = {
        "Close": 110.0,
        "RSI": 58.0,
        "MACD": 1.2,
        "MACD_SIGNAL": 0.2,
        "VOLUME_RATIO": 1.6,
        "EMA20": 108.0,
        "EMA50": 103.0,
        "SMA20": 105.0,
        "SMA50": 101.0,
        "MOMENTUM20": 9.0,
        "MOMENTUM50": 8.0,
        "GOLDEN_CROSS": True,
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


def test_entry_gate_rejects_weak_momentum_breakout():
    scanner = Scanner.__new__(Scanner)
    latest = {
        "Close": 110.0,
        "RSI": 60.0,
        "MACD": 1.2,
        "MACD_SIGNAL": 0.2,
        "VOLUME_RATIO": 1.2,
        "EMA20": 109.5,
        "EMA50": 108.8,
        "SMA20": 109.5,
        "SMA50": 108.5,
        "MOMENTUM20": 1.2,
        "MOMENTUM50": 2.0,
    }

    assert scanner._passes_entry_gate(latest, 75.0, 0.0) is False


def test_entry_gate_requires_stronger_breakout_confirmation():
    scanner = Scanner.__new__(Scanner)
    latest = {
        "Close": 110.0,
        "RSI": 60.0,
        "MACD": 1.5,
        "MACD_SIGNAL": 0.2,
        "VOLUME_RATIO": 1.4,
        "EMA20": 107.0,
        "EMA50": 105.0,
        "EMA200": 103.0,
        "SMA20": 108.0,
        "SMA50": 106.0,
        "MOMENTUM20": 4.0,
        "MOMENTUM50": 3.0,
    }

    assert scanner._passes_entry_gate(latest, 80.0, 0.0) is False


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


def test_market_validation_gate_accepts_profitable_strategy(monkeypatch):
    backtester = SimpleBacktester.__new__(SimpleBacktester)

    monkeypatch.setattr(
        backtester,
        "run",
        lambda symbols=None: {
            "trades": 8,
            "win_rate": 62.5,
            "avg_pnl": 2.4,
            "total_pnl": 19.2,
        },
    )

    result = backtester.validate_market_readiness(["RELIANCE"])

    assert result["pass"] is True
    assert result["reason"] == "strategy passes market-readiness gate"


def test_market_validation_gate_rejects_unprofitable_strategy(monkeypatch):
    backtester = SimpleBacktester.__new__(SimpleBacktester)

    monkeypatch.setattr(
        backtester,
        "run",
        lambda symbols=None: {
            "trades": 7,
            "win_rate": 28.6,
            "avg_pnl": -2.1,
            "total_pnl": -14.7,
        },
    )

    result = backtester.validate_market_readiness(["RELIANCE"])

    assert result["pass"] is False
    assert "not ready" in result["reason"].lower()


def test_paper_validation_gate_uses_same_readiness_criteria(monkeypatch):
    backtester = SimpleBacktester.__new__(SimpleBacktester)

    monkeypatch.setattr(
        backtester,
        "run",
        lambda symbols=None: {
            "trades": 10,
            "win_rate": 60.0,
            "avg_pnl": 1.5,
            "total_pnl": 15.0,
        },
    )

    result = backtester.validate_paper_run(["RELIANCE"])

    assert result["pass"] is True
    assert result["reason"] == "strategy passes market-readiness gate"
