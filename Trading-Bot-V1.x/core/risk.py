from datetime import datetime

from core.models import Position, Recommendation


class RiskEngine:
    def __init__(self, settings):
        self.settings = settings

    def price_allowed(self, price: float) -> bool:
        return self.settings.min_price <= price <= self.settings.max_price

    def build_recommendation(self, symbol: str, latest, score: float, reason: str, news_score: float, ai_note: str) -> Recommendation:
        price = float(latest["Close"])
        atr = float(latest.get("ATR14") or 0)
        configured_stop_pct = max(1.0, float(self.settings.stop_loss_pct))
        stop_distance = max(
            price * (configured_stop_pct / 100),
            atr * 1.2 if atr > 0 else 0.0,
        )
        target_distance = max(price * (self.settings.target_pct / 100), stop_distance * 1.5)
        risk_amount = self.settings.portfolio_size * (self.settings.risk_per_trade_pct / 100)
        max_notional = self.settings.portfolio_size * (self.settings.max_position_value_pct / 100)
        quantity = int(risk_amount // stop_distance) if stop_distance > 0 else self.settings.default_quantity
        if quantity < 1:
            quantity = max(1, min(self.settings.default_quantity, int(max_notional // price) if price > 0 else 1))
        position_size = round(min(max_notional, quantity * price), 2)
        return Recommendation(
            symbol=symbol,
            price=round(price, 2),
            score=round(score, 2),
            action="BUY",
            reason=reason,
            stop_loss=round(price - stop_distance, 2),
            target=round(price + target_distance, 2),
            rsi=round(float(latest.get("RSI", 0)), 2),
            macd=round(float(latest.get("MACD", 0)), 4),
            signal=round(float(latest.get("MACD_SIGNAL", 0)), 4),
            volume_ratio=round(float(latest.get("VOLUME_RATIO", 0)), 2),
            quantity=quantity,
            position_size=position_size,
            risk_amount=round(min(risk_amount, stop_distance * quantity), 2),
            news_score=round(news_score, 2),
            ai_note=ai_note,
        )

    def open_position(self, recommendation: Recommendation) -> Position:
        return Position(
            symbol=recommendation.symbol,
            entry_price=recommendation.price,
            quantity=recommendation.quantity,
            stop_loss=recommendation.stop_loss,
            target=recommendation.target,
            highest_price=recommendation.price,
            opened_at=datetime.now().isoformat(timespec="seconds"),
            reason=recommendation.reason,
        )
